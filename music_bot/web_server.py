"""
Music Bot Web Control Server
Provides HTTP API for the website to control and monitor the Discord music bot.
Runs alongside the Discord bot on a separate port.

Endpoints:
  GET  /health                   - Health check
  GET  /guilds                   - List servers the bot is in
  GET  /status?guildId=XXX       - Get current playback status
  POST /control                  - Send control command to bot
  GET  /playlists?userId=XXX     - List all playlists for a user (across all guilds)
  POST /playlists/save           - Save a playlist from the website

Authentication: Bearer token via MUSIC_API_SECRET env var (optional in dev)
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional, TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from music_bot.bot import MusicBot

logger = logging.getLogger("music_bot.web_server")

MUSIC_API_SECRET = os.getenv("MUSIC_API_SECRET", "")
WEB_SERVER_PORT = int(os.getenv("MUSIC_WEB_SERVER_PORT", os.getenv("PORT", "8090")))
WEB_SERVER_HOST = os.getenv("MUSIC_WEB_SERVER_HOST", "0.0.0.0")

VALID_ACTIONS = {"pause", "resume", "skip", "stop", "volume", "loop", "shuffle", "play_playlist", "channels", "play", "play_now", "now_playing", "remove_queue"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _guild_icon_url(guild) -> Optional[str]:
    try:
        return str(guild.icon.url) if guild.icon else None
    except Exception:
        return None


def _guild_payload(guild) -> dict:
    active_player = guild.voice_client
    active_channel = getattr(active_player, "channel", None)
    return {
        "id": str(guild.id),
        "name": guild.name,
        "iconUrl": _guild_icon_url(guild),
        "memberCount": guild.member_count or 0,
        "voiceChannelCount": len(guild.voice_channels),
        "textChannelCount": len(guild.text_channels),
        "activeVoiceChannel": (
            {"id": str(active_channel.id), "name": active_channel.name}
            if active_channel else None
        ),
    }


def _verify_token(request: web.Request) -> bool:
    if not MUSIC_API_SECRET:
        return True  # dev mode: no secret required
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == MUSIC_API_SECRET
    return False


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }


def _json_response(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data),
        content_type="application/json",
        status=status,
        headers=_cors_headers(),
    )


def _get_player_status(bot: "MusicBot", guild_id: int) -> Optional[dict]:
    import wavelink
    guild = bot.get_guild(guild_id)
    if not guild:
        return None

    player = guild.voice_client
    if not player or not isinstance(player, wavelink.Player):
        return None

    current = getattr(player, "current", None)
    queue = getattr(player, "queue", None)

    current_track = None
    if current:
        current_track = {
            "title": getattr(current, "title", "Unknown"),
            "author": getattr(current, "author", "Unknown"),
            "uri": getattr(current, "uri", ""),
            "length": getattr(current, "length", 0),
            "position": getattr(player, "position", 0),
            "artwork": getattr(current, "artwork", None),
        }

    queue_tracks = []
    if queue and not queue.is_empty:
        for track in list(queue)[:20]:
            queue_tracks.append({
                "title": getattr(track, "title", "Unknown"),
                "author": getattr(track, "author", "Unknown"),
                "uri": getattr(track, "uri", ""),
                "length": getattr(track, "length", 0),
                "artwork": getattr(track, "artwork", None),
            })

    voice_channel = None
    if player.channel:
        voice_channel = {"id": str(player.channel.id), "name": player.channel.name}

    return {
        "guildId": str(guild_id),
        "guildName": guild.name,
        "playing": player.playing if hasattr(player, "playing") else False,
        "paused": player.paused if hasattr(player, "paused") else False,
        "volume": getattr(player, "volume", 100),
        "loopMode": getattr(player, "loop_mode", "off"),
        "currentTrack": current_track,
        "queue": queue_tracks,
        "queueSize": len(queue_tracks),
        "voiceChannel": voice_channel,
        "playlistName": getattr(player, "current_playlist_name", None),
        "updatedAt": time.time(),
        "source": "live",
    }


# ── Route handlers ────────────────────────────────────────────────────────────

async def _handle_health(request: web.Request) -> web.Response:
    return _json_response({"status": "ok", "service": "music-bot-api"})


async def _handle_guilds(request: web.Request) -> web.Response:
    if not _verify_token(request):
        return _json_response({"error": "Unauthorized"}, 401)
    bot: "MusicBot" = request.app["bot"]
    guilds = sorted((_guild_payload(g) for g in bot.guilds), key=lambda x: x["name"].lower())
    return _json_response({"ok": True, "guilds": guilds})


async def _handle_status(request: web.Request) -> web.Response:
    if not _verify_token(request):
        return _json_response({"error": "Unauthorized"}, 401)
    bot: "MusicBot" = request.app["bot"]
    guild_id_str = request.rel_url.query.get("guildId", "")

    if not guild_id_str:
        statuses = []
        for guild in bot.guilds:
            status = _get_player_status(bot, guild.id)
            if status and status.get("playing"):
                statuses.append(status)
        return _json_response({"guilds": statuses})

    try:
        guild_id = int(guild_id_str)
    except ValueError:
        return _json_response({"error": "Invalid guildId"}, 400)

    status = _get_player_status(bot, guild_id)
    if status is None:
        return _json_response({"guildId": guild_id_str, "playing": False, "currentTrack": None, "queue": [], "source": "live"})
    return _json_response(status)


async def _handle_playlists_list(request: web.Request) -> web.Response:
    """List all playlists for a Discord user (across all guilds)."""
    if not _verify_token(request):
        return _json_response({"error": "Unauthorized"}, 401)

    user_id_str = request.rel_url.query.get("userId", "")
    if not user_id_str:
        return _json_response({"error": "userId is required"}, 400)

    try:
        user_id = int(user_id_str)
    except ValueError:
        return _json_response({"error": "Invalid userId"}, 400)

    from music_bot.storage.playlist_storage import playlist_storage
    playlists = await playlist_storage.list_playlists_for_user(user_id)

    # Collect guild IDs that have playlists
    guild_ids = list({p["guildId"] for p in playlists if p.get("guildId")})

    return _json_response({"ok": True, "playlists": playlists, "guilds": guild_ids})


async def _handle_playlists_save(request: web.Request) -> web.Response:
    """Save a playlist from the website dashboard."""
    if not _verify_token(request):
        return _json_response({"error": "Unauthorized"}, 401)

    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON"}, 400)

    guild_id_str = str(body.get("guildId", ""))
    user_id_str = str(body.get("userId", ""))
    name = str(body.get("name", "")).strip()
    tracks = body.get("tracks", [])

    if not guild_id_str or not user_id_str or not name:
        return _json_response({"error": "guildId, userId, and name are required"}, 400)
    if not isinstance(tracks, list):
        return _json_response({"error": "tracks must be a list"}, 400)

    try:
        guild_id = int(guild_id_str)
        user_id = int(user_id_str)
    except ValueError:
        return _json_response({"error": "Invalid guildId or userId"}, 400)

    from music_bot.storage.playlist_storage import playlist_storage
    ok = await playlist_storage.save_playlist(guild_id, user_id, name, tracks)
    if ok:
        return _json_response({"ok": True, "saved": name, "tracks": len(tracks)})
    return _json_response({"error": "Failed to save playlist — database may be unavailable"}, 503)


async def _handle_control(request: web.Request) -> web.Response:
    if not _verify_token(request):
        return _json_response({"error": "Unauthorized"}, 401)

    try:
        body = await request.json()
    except Exception:
        return _json_response({"error": "Invalid JSON body"}, 400)

    action = body.get("action", "")
    guild_id_str = str(body.get("guildId", ""))
    value = body.get("value")
    voice_channel_id = body.get("voiceChannelId")
    text_channel_id = body.get("textChannelId")
    user_id = body.get("userId")

    if action not in VALID_ACTIONS:
        return _json_response({"error": f"Invalid action. Allowed: {', '.join(sorted(VALID_ACTIONS))}"}, 400)
    if not guild_id_str:
        return _json_response({"error": "guildId is required"}, 400)

    try:
        guild_id = int(guild_id_str)
    except ValueError:
        return _json_response({"error": "Invalid guildId"}, 400)

    import wavelink

    bot: "MusicBot" = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild:
        return _json_response({"error": "Guild not found — bot is not in this server"}, 404)

    player = guild.voice_client

    # Actions that don't need an active player
    if action not in ("channels", "play", "play_now", "play_playlist") and (not player or not isinstance(player, wavelink.Player)):
        return _json_response({"error": "Bot is not in a voice channel. Play something first."}, 404)

    try:
        if action == "channels":
            return _json_response({
                "ok": True,
                "voiceChannels": [{"id": str(c.id), "name": c.name} for c in guild.voice_channels],
                "textChannels": [{"id": str(c.id), "name": c.name} for c in guild.text_channels + guild.voice_channels],
            })

        elif action in ("play", "play_now"):
            query = str(value) if value else ""
            if not query:
                return _json_response({"error": "Query is required for play action"}, 400)

            if not player or not isinstance(player, wavelink.Player):
                if not voice_channel_id:
                    return _json_response({"error": "Bot is not in a voice channel — select a voice channel first"}, 400)
                vc = bot.get_channel(int(voice_channel_id))
                if not vc:
                    return _json_response({"error": "Voice channel not found"}, 404)
                from music_bot.cogs.music import CustomPlayer
                music_cog = bot.get_cog("Music")
                if music_cog and hasattr(music_cog, "force_clean_voice_state"):
                    await music_cog.force_clean_voice_state(guild)
                player = await vc.connect(cls=CustomPlayer, timeout=60.0, self_deaf=True)

            if text_channel_id and hasattr(player, "text_channel"):
                tc = guild.get_channel(int(text_channel_id))
                if tc:
                    player.text_channel = tc

            tracks = await wavelink.Playable.search(query)
            if not tracks:
                return _json_response({"error": "No tracks found for that search"}, 404)

            track = tracks[0] if isinstance(tracks, list) else tracks
            music_cog = bot.get_cog("Music")
            
            if isinstance(track, wavelink.Playlist):
                for t in track.tracks:
                    t.extras.requester_id = user_id or bot.user.id
                    t.extras.requester_name = "Web Dashboard"
                    await player.queue.put_wait(t)
                
                if action == "play_now" or (not player.playing and not player.queue.is_empty):
                    next_track = player.queue.get()
                    if music_cog:
                        await music_cog.safe_play(player, next_track)
                    else:
                        await player.play(next_track)
                return _json_response({"ok": True, "action": action, "track": track.name, "isPlaylist": True})
            else:
                track.extras.requester_id = user_id or bot.user.id
                track.extras.requester_name = "Web Dashboard"
                
                if action == "play_now":
                    if music_cog:
                        await music_cog.safe_play(player, track)
                    else:
                        await player.play(track)
                else:
                    await player.queue.put_wait(track)
                    if not player.playing:
                        next_track = player.queue.get()
                        if music_cog:
                            await music_cog.safe_play(player, next_track)
                        else:
                            await player.play(next_track)
                return _json_response({"ok": True, "action": action, "track": track.title})

        elif action == "pause":
            await player.pause(True)
            return _json_response({"ok": True, "action": "pause"})

        elif action == "resume":
            await player.pause(False)
            return _json_response({"ok": True, "action": "resume"})

        elif action == "skip":
            await player.skip(force=True)
            return _json_response({"ok": True, "action": "skip"})

        elif action == "remove_queue":
            try:
                index = int(value)
                player.queue.delete(index)
                return _json_response({"ok": True, "action": "remove_queue"})
            except (ValueError, TypeError, IndexError):
                return _json_response({"error": "Invalid queue index"}, 400)

        elif action == "stop":
            player.queue.clear()
            await player.stop()
            await player.disconnect()
            return _json_response({"ok": True, "action": "stop"})

        elif action == "volume":
            vol = max(0, min(200, int(value) if value is not None else 50))
            await player.set_volume(vol)
            return _json_response({"ok": True, "action": "volume", "value": vol})

        elif action == "loop":
            mode = str(value).lower() if value else "off"
            if mode not in ("off", "track", "queue"):
                return _json_response({"error": "loop value must be: off, track, or queue"}, 400)
            player.loop_mode = mode
            return _json_response({"ok": True, "action": "loop", "mode": mode})

        elif action == "shuffle":
            player.queue.shuffle()
            return _json_response({"ok": True, "action": "shuffle"})

        elif action == "now_playing":
            if not getattr(player, "current", None):
                return _json_response({"error": "Nothing is playing right now"}, 400)
            
            music_cog = bot.get_cog("Music")
            if not music_cog:
                return _json_response({"error": "Music cog not found"}, 500)
            
            from music_bot.cogs.music import PlayerControlView
            embed = music_cog.create_now_playing_embed(player)
            view = PlayerControlView(player)
            
            if text_channel_id and hasattr(player, "text_channel"):
                tc = guild.get_channel(int(text_channel_id))
                if tc:
                    player.text_channel = tc

            if not getattr(player, "text_channel", None):
                tc = guild.system_channel
                if not tc or not tc.permissions_for(guild.me).send_messages:
                    tc = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
                if not tc:
                    return _json_response({"error": "No text channel available to send the message"}, 400)
                player.text_channel = tc

            if hasattr(player, "now_playing_message") and player.now_playing_message:
                try:
                    await player.now_playing_message.delete()
                except:
                    pass

            
            player.now_playing_message = await player.text_channel.send(embed=embed, view=view)
            player.now_playing_message_created_at = __import__("time").time()
            return _json_response({"ok": True, "action": "now_playing"})


        elif action == "play_playlist":
            playlist_name = str(value) if value else ""
            if not playlist_name:
                return _json_response({"error": "Playlist name required as value"}, 400)
            if not user_id:
                return _json_response({"error": "userId is required to load a saved playlist"}, 400)

            if not player or not isinstance(player, wavelink.Player):
                if not voice_channel_id:
                    return _json_response({"error": "Select a voice channel before playing a playlist"}, 400)
                vc = bot.get_channel(int(voice_channel_id))
                if not vc:
                    return _json_response({"error": "Voice channel not found"}, 404)
                from music_bot.cogs.music import CustomPlayer
                player = await vc.connect(cls=CustomPlayer)

            if text_channel_id and hasattr(player, "text_channel"):
                tc = guild.get_channel(int(text_channel_id))
                if tc:
                    player.text_channel = tc

            from music_bot.storage.playlist_storage import playlist_storage
            playlist = await playlist_storage.load_playlist(guild_id, int(user_id), playlist_name)
            if not playlist:
                return _json_response({"error": "Playlist not found — save it first with /playlist save in Discord"}, 404)

            loaded = 0
            music_cog = bot.get_cog("Music")
            for saved_track in playlist.get("tracks", []):
                uri = saved_track.get("uri") or saved_track.get("title")
                if not uri:
                    continue
                found = await wavelink.Playable.search(str(uri))
                if not found:
                    continue
                t = found[0] if isinstance(found, list) else found
                if isinstance(t, wavelink.Playlist):
                    for pt in t.tracks:
                        pt.extras.requester_id = user_id or bot.user.id
                        pt.extras.requester_name = "Web Dashboard"
                        if playlist.get("iconUrl"):
                            pt.extras.playlist_icon_url = playlist.get("iconUrl")
                        await player.queue.put_wait(pt)
                        loaded += 1
                else:
                    t.extras.requester_id = user_id or bot.user.id
                    t.extras.requester_name = "Web Dashboard"
                    if playlist.get("iconUrl"):
                        t.extras.playlist_icon_url = playlist.get("iconUrl")
                    await player.queue.put_wait(t)
                    loaded += 1

            if loaded == 0:
                return _json_response({"error": "No playable tracks found in that playlist"}, 404)

            player.current_playlist_name = playlist_name
            if not player.playing and not player.queue.is_empty:
                next_track = player.queue.get()
                if music_cog:
                    await music_cog.safe_play(player, next_track)
                else:
                    await player.play(next_track)
            return _json_response({"ok": True, "action": "play_playlist", "playlist": playlist_name, "tracks": loaded})

    except Exception as e:
        logger.exception("Control action %s failed: %s", action, e)
        return _json_response({"error": str(e)}, 500)

    return _json_response({"error": "Unknown error"}, 500)


async def _handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers())


def create_web_app(bot: "MusicBot") -> web.Application:
    app = web.Application()
    app["bot"] = bot

    app.router.add_get("/health", _handle_health)
    app.router.add_get("/guilds", _handle_guilds)
    app.router.add_get("/status", _handle_status)
    app.router.add_post("/control", _handle_control)
    app.router.add_get("/playlists", _handle_playlists_list)
    app.router.add_post("/playlists/save", _handle_playlists_save)
    app.router.add_options("/{path_info:.*}", _handle_options)

    return app


async def start_web_server(bot: "MusicBot") -> web.AppRunner:
    app = create_web_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    logger.info("Music bot web server started on %s:%s", WEB_SERVER_HOST, WEB_SERVER_PORT)
    return runner

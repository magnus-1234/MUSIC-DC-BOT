"""
Playlist Management UI Components
Interactive views, modals, and buttons for playlist management
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
from datetime import datetime
import wavelink

from music_bot.storage.playlist_storage import playlist_storage


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class SavePlaylistModal(discord.ui.Modal, title="Save Playlist"):
    """Modal for saving the current queue as a playlist"""

    playlist_name = discord.ui.TextInput(
        label="Playlist Name",
        placeholder="Enter a name for this playlist...",
        max_length=50,
        required=True
    )

    def __init__(self, player, user_id: int, guild_id: int):
        super().__init__()
        self.player = player
        self.user_id = user_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()

            if self.player.queue.is_empty and not self.player.current:
                await interaction.followup.send("❌ Queue is empty! Add some tracks first.", ephemeral=True)
                return

            tracks = []

            if self.player.current:
                track = self.player.current
                tracks.append({
                    'title': track.title,
                    'author': track.author,
                    'uri': track.uri,
                    'length': track.length
                })

            for track in list(self.player.queue):
                tracks.append({
                    'title': track.title,
                    'author': track.author,
                    'uri': track.uri,
                    'length': track.length
                })

            name = self.playlist_name.value.strip()
            success = await playlist_storage.save_playlist(
                self.guild_id,
                self.user_id,
                name,
                tracks
            )

            if success:
                await interaction.followup.send(
                    f"✅ Saved playlist **{name}** with **{len(tracks)}** tracks!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to save playlist. Please try again.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class AddTrackToPlaylistModal(discord.ui.Modal, title="Add to Playlist"):
    """Modal for adding the current track to an existing or new playlist"""

    playlist_name = discord.ui.TextInput(
        label="Playlist Name",
        placeholder="Enter existing or new playlist name...",
        max_length=50,
        required=True
    )

    def __init__(self, player, user_id: int, guild_id: int, track_data: dict):
        super().__init__()
        self.player = player
        self.user_id = user_id
        self.guild_id = guild_id
        self.track_data = track_data

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()

            playlist_name = self.playlist_name.value.strip()

            existing_playlist = await playlist_storage.load_playlist(
                self.guild_id,
                self.user_id,
                playlist_name
            )

            if existing_playlist:
                tracks = existing_playlist['tracks']
                tracks.append(self.track_data)

                success = await playlist_storage.save_playlist(
                    self.guild_id,
                    self.user_id,
                    playlist_name,
                    tracks
                )

                if success:
                    await interaction.followup.send(
                        f"✅ Added **{self.track_data['title']}** to playlist **{playlist_name}**!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Failed to add track to playlist. Please try again.",
                        ephemeral=True
                    )
            else:
                success = await playlist_storage.save_playlist(
                    self.guild_id,
                    self.user_id,
                    playlist_name,
                    [self.track_data]
                )

                if success:
                    await interaction.followup.send(
                        f"✅ Created new playlist **{playlist_name}** with **{self.track_data['title']}**!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Failed to create playlist. Please try again.",
                        ephemeral=True
                    )
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


# ---------------------------------------------------------------------------
# Helper: get track count from playlist dict (handles both key names)
# ---------------------------------------------------------------------------

def _get_track_count(playlist: dict) -> int:
    return playlist.get('trackCount', len(playlist.get('tracks', [])))


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class PlaylistManagementView(discord.ui.View):

    def __init__(self, user_id: int, guild_id: int, player):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.player = player
        self.playlist_count = 0
        self.total_tracks = 0

    async def load_data(self):
        playlists = await playlist_storage.list_playlists(self.guild_id, self.user_id)
        self.playlist_count = len(playlists)
        self.total_tracks = sum(_get_track_count(p) for p in playlists)

    def get_embed(self) -> discord.Embed:
        queue_count = self.player.queue.count
        current_playing = self.player.current.title if self.player.current else "Nothing"

        embed = discord.Embed(
            title="🎵 Playlist Manager",
            color=0x5865F2,
            description=""
        )

        status_text = f"**Queue:** {queue_count} tracks\n"
        status_text += f"**Now Playing:** {current_playing}\n\n"
        status_text += f"**Saved Playlists:** {self.playlist_count} playlist(s)\n"
        status_text += f"**Total Tracks:** {self.total_tracks} track(s)\n"

        if getattr(self.player, 'current_playlist_name', None):
            status_text += f"\n**Loaded Playlist:** 📁 {self.player.current_playlist_name}"

        embed.add_field(name="📊 Current Status", value=status_text, inline=False)
        embed.add_field(
            name="💡 Quick Actions",
            value="• **Save Current Queue** - Save your current queue as a playlist\n"
                  "• **My Playlists** - View and manage your saved playlists",
            inline=False
        )

        return embed

    @discord.ui.button(emoji="💾", label="Save Current Queue", style=discord.ButtonStyle.primary, custom_id="save_queue", row=0)
    async def save_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to save current queue"""
        if self.player.queue.is_empty and not self.player.current:
            await interaction.response.send_message("❌ Queue is empty! Add some tracks first.", ephemeral=True)
            return

        modal = SavePlaylistModal(self.player, self.user_id, self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="📋", label="My Playlists", style=discord.ButtonStyle.secondary, custom_id="my_playlists", row=0)
    async def my_playlists(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show saved playlists"""
        view = PlaylistListView(self.user_id, self.guild_id, self.player)
        await view.load_playlists()
        await view.update_view(interaction)

    @discord.ui.button(emoji="❌", label="Close", style=discord.ButtonStyle.danger, custom_id="close", row=0)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the playlist manager"""
        embed = discord.Embed(description="✅ Playlist manager closed", color=0x57F287)
        await interaction.response.edit_message(embed=embed, view=None)


class PlaylistListView(discord.ui.View):
    """View for displaying and managing saved playlists"""

    def __init__(self, user_id: int, guild_id: int, player, page: int = 0):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.player = player
        self.page = page
        self.per_page = 10
        self.playlists = []
        self.total_count = 0

    async def load_playlists(self):
        """Load playlists from database"""
        self.total_count = await playlist_storage.count_playlists(self.guild_id, self.user_id)
        self.playlists = await playlist_storage.list_playlists(
            self.guild_id,
            self.user_id,
            limit=self.per_page,
            offset=self.page * self.per_page
        )

    def get_embed(self) -> discord.Embed:
        total_pages = max(1, (self.total_count + self.per_page - 1) // self.per_page)

        embed = discord.Embed(
            title="📋 My Playlists",
            color=0x00CED1,
            description=f"You have **{self.total_count}** saved playlist(s)"
        )

        if not self.playlists:
            embed.add_field(
                name="No Playlists",
                value="You haven't saved any playlists yet!\nUse the **Save Current Queue** button to create one.",
                inline=False
            )
        else:
            playlist_text = ""
            for i, playlist in enumerate(self.playlists, start=1):
                created = datetime.fromisoformat(playlist['created_at']).strftime("%Y-%m-%d")
                track_count = _get_track_count(playlist)
                playlist_text += f"`{i}.` **{playlist['name']}**\n"
                playlist_text += f"   └ {track_count} tracks • Created: {created}\n\n"

            embed.add_field(name="Your Playlists", value=playlist_text, inline=False)

        embed.set_footer(text=f"Page {self.page + 1}/{total_pages}")
        return embed

    async def update_view(self, interaction: discord.Interaction):
        """Refresh the view with current data"""
        await self.load_playlists()
        self.clear_items()

        if self.playlists:
            # Load select
            load_options = [
                discord.SelectOption(
                    label=p['name'],
                    description=f"{_get_track_count(p)} tracks",
                    value=p['name']
                ) for p in self.playlists[:25]
            ]
            load_select = discord.ui.Select(
                placeholder="Select playlist to load...",
                options=load_options,
                custom_id="playlist_select_load"
            )
            load_select.callback = self.load_playlist_callback
            self.add_item(load_select)

            # Delete select
            delete_options = [
                discord.SelectOption(
                    label=p['name'],
                    description=f"{_get_track_count(p)} tracks",
                    value=p['name']
                ) for p in self.playlists[:25]
            ]
            delete_select = discord.ui.Select(
                placeholder="Select playlist to delete...",
                options=delete_options,
                custom_id="playlist_select_delete"
            )
            delete_select.callback = self.delete_playlist_callback
            self.add_item(delete_select)

        total_pages = max(1, (self.total_count + self.per_page - 1) // self.per_page)

        prev_button = discord.ui.Button(
            emoji="◀️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
            custom_id="prev_page"
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)

        next_button = discord.ui.Button(
            emoji="▶️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total_pages - 1),
            custom_id="next_page"
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

        back_button = discord.ui.Button(
            emoji="🔙",
            label="Back",
            style=discord.ButtonStyle.secondary,
            custom_id="back"
        )
        back_button.callback = self.back_to_main
        self.add_item(back_button)

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.get_embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def load_playlist_callback(self, interaction: discord.Interaction):
        """Handle playlist loading"""
        loading_message = None
        try:
            await interaction.response.defer()
            playlist_name = interaction.data['values'][0]

            loading_embed = discord.Embed(
                title="⏳ Loading Playlist",
                description=f"Loading **{playlist_name}**...\n\n🔄 Please wait while we load your tracks",
                color=0x5865F2
            )
            loading_embed.set_footer(text="This may take a moment depending on playlist size")
            loading_message = await interaction.followup.send(embed=loading_embed, ephemeral=True)

            playlist = await playlist_storage.load_playlist(
                self.guild_id,
                self.user_id,
                playlist_name
            )

            if not playlist:
                if loading_message:
                    try:
                        await loading_message.delete()
                    except:
                        pass
                await interaction.followup.send("❌ Playlist not found!", ephemeral=True)
                return

            self.player.queue.clear()
            self.player.current_playlist_name = playlist_name

            loaded_count = 0
            total_tracks = len(playlist['tracks'])

            for idx, track_data in enumerate(playlist['tracks'], 1):
                try:
                    if idx % 5 == 0 or idx == total_tracks:
                        try:
                            loading_embed.description = f"Loading **{playlist_name}**...\n\n🔄 Loading tracks: {idx}/{total_tracks}"
                            await loading_message.edit(embed=loading_embed)
                        except:
                            pass

                    tracks = await wavelink.Playable.search(track_data['uri'])
                    if tracks:
                        track = tracks[0] if isinstance(tracks, list) else tracks
                        track.extras.requester_id = self.user_id
                        track.extras.requester_name = str(interaction.user)
                        self.player.queue.put(track)
                        loaded_count += 1
                except Exception as e:
                    print(f"Failed to load track {track_data['title']}: {e}")
                    continue

            if not self.player.playing and not self.player.queue.is_empty:
                next_track = self.player.queue.get()
                await self.player.play(next_track)

            if loading_message:
                try:
                    await loading_message.delete()
                except:
                    pass

            embed = discord.Embed(
                title="✅ Playlist Loaded",
                description=f"Successfully loaded **{playlist_name}**",
                color=0x57F287
            )
            embed.add_field(
                name="📊 Stats",
                value=f"**Tracks Loaded:** {loaded_count}/{len(playlist['tracks'])}\n**Queue Size:** {self.player.queue.count}",
                inline=False
            )
            embed.add_field(
                name="🎵 Now Playing",
                value=self.player.current.title if self.player.current else "Starting playback...",
                inline=False
            )
            embed.set_footer(text="Use the buttons below to manage your playlist")

            view = PlaylistLoadedView(self.player, playlist_name)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            if loading_message:
                try:
                    await loading_message.delete()
                except:
                    pass
            await interaction.followup.send(f"❌ Error loading playlist: {e}", ephemeral=True)

    async def delete_playlist_callback(self, interaction: discord.Interaction):
        """Handle playlist deletion"""
        try:
            playlist_name = interaction.data['values'][0]

            success = await playlist_storage.delete_playlist(
                self.guild_id,
                self.user_id,
                playlist_name
            )

            if success:
                await interaction.response.send_message(
                    f"🗑️ Deleted playlist **{playlist_name}**",
                    ephemeral=True
                )
                await self.update_view(interaction)
            else:
                await interaction.response.send_message("❌ Failed to delete playlist", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    async def previous_page(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            await self.update_view(interaction)
        else:
            await interaction.response.send_message("Already on first page", ephemeral=True)

    async def next_page(self, interaction: discord.Interaction):
        total_pages = max(1, (self.total_count + self.per_page - 1) // self.per_page)
        if self.page < total_pages - 1:
            self.page += 1
            await self.update_view(interaction)
        else:
            await interaction.response.send_message("Already on last page", ephemeral=True)

    async def back_to_main(self, interaction: discord.Interaction):
        view = PlaylistManagementView(self.user_id, self.guild_id, self.player)
        await view.load_data()
        embed = view.get_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class PlaylistLoadedView(discord.ui.View):
    """View shown after successfully loading a playlist"""

    def __init__(self, player, playlist_name: str):
        super().__init__(timeout=180)
        self.player = player
        self.playlist_name = playlist_name

    @discord.ui.button(emoji="📋", label="View Queue", style=discord.ButtonStyle.primary, row=0)
    async def view_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        from music_bot.cogs.music import QueuePaginationView
        view = QueuePaginationView(self.player, page=0)
        await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

    @discord.ui.button(emoji="🔁", label="Loop Off", style=discord.ButtonStyle.secondary, row=0)
    async def loop_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop_mode = "off"
        await interaction.response.send_message("🔁 Loop mode: **Off**", ephemeral=True)

    @discord.ui.button(emoji="🔂", label="Loop Track", style=discord.ButtonStyle.secondary, row=0)
    async def loop_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop_mode = "track"
        await interaction.response.send_message("🔂 Loop mode: **Track** (current song will repeat)", ephemeral=True)

    @discord.ui.button(emoji="🔁", label="Loop Queue", style=discord.ButtonStyle.success, row=1)
    async def loop_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop_mode = "queue"
        await interaction.response.send_message("🔁 Loop mode: **Queue** (playlist will repeat)", ephemeral=True)

    @discord.ui.button(emoji="🎵", label="Now Playing", style=discord.ButtonStyle.primary, row=1)
    async def now_playing(self, interaction: discord.Interaction, button: discord.ui.Button):
        from music_bot.cogs.music import Music, PlayerControlView

        if not self.player.current:
            await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
            return

        music_cog = interaction.client.get_cog('Music')
        if music_cog:
            embed = music_cog.create_now_playing_embed(self.player)
            view = PlayerControlView(self.player)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Music cog not found!", ephemeral=True)


class AddToPlaylistView(discord.ui.View):
    """View for adding the current track to a playlist"""

    def __init__(self, player, user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.player = player
        self.user_id = user_id
        self.guild_id = guild_id
        self.playlists = []
        self.per_page = 25

    async def load_playlists(self):
        """Load user's playlists and build the select menu if any exist"""
        self.playlists = await playlist_storage.list_playlists(
            self.guild_id,
            self.user_id,
            limit=self.per_page,
            offset=0
        )

        if self.playlists:
            self.clear_items()

            options = [
                discord.SelectOption(
                    label=p['name'],
                    description=f"{_get_track_count(p)} tracks",
                    value=p['name']
                ) for p in self.playlists[:25]
            ]

            select = discord.ui.Select(
                placeholder="Select a playlist to add to...",
                options=options,
                custom_id="add_to_existing"
            )
            select.callback = self.add_to_existing_callback
            self.add_item(select)

            # Re-add buttons after clearing
            create_btn = discord.ui.Button(
                emoji="➕",
                label="Create New Playlist",
                style=discord.ButtonStyle.primary,
                row=1,
                custom_id="create_new"
            )
            create_btn.callback = self.create_new_playlist
            self.add_item(create_btn)

            cancel_btn = discord.ui.Button(
                emoji="❌",
                label="Cancel",
                style=discord.ButtonStyle.secondary,
                row=1,
                custom_id="cancel"
            )
            cancel_btn.callback = self.cancel_button
            self.add_item(cancel_btn)

    def get_embed(self) -> discord.Embed:
        if not self.player.current:
            return discord.Embed(
                title="❌ Nothing Playing",
                description="No track is currently playing!",
                color=0xFF0000
            )

        track = self.player.current

        embed = discord.Embed(
            title="➕ Add to Playlist",
            description=f"Add **{track.title}** by **{track.author}** to a playlist",
            color=0x57F287
        )

        if self.playlists:
            embed.add_field(
                name="📋 Your Playlists",
                value=f"You have **{len(self.playlists)}** playlist(s). Select one from the dropdown below, or create a new one.",
                inline=False
            )
        else:
            embed.add_field(
                name="📝 No Playlists Yet",
                value="You don't have any playlists. Use the button below to create one!",
                inline=False
            )

        embed.set_footer(text="Select from existing or create new playlist")

        if hasattr(track, 'artwork') and track.artwork:
            embed.set_thumbnail(url=track.artwork)
        elif hasattr(track, 'thumbnail') and track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        return embed

    async def add_to_existing_callback(self, interaction: discord.Interaction):
        """Handle adding to existing playlist"""
        try:
            playlist_name = interaction.data['values'][0]
            track = self.player.current
            track_data = {
                'title': track.title,
                'author': track.author,
                'uri': track.uri,
                'length': track.length
            }

            existing_playlist = await playlist_storage.load_playlist(
                self.guild_id,
                self.user_id,
                playlist_name
            )

            if existing_playlist:
                tracks = existing_playlist['tracks']
                tracks.append(track_data)

                success = await playlist_storage.save_playlist(
                    self.guild_id,
                    self.user_id,
                    playlist_name,
                    tracks
                )

                if success:
                    await interaction.response.send_message(
                        f"✅ Added **{track_data['title']}** to playlist **{playlist_name}**!",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Failed to add track to playlist. Please try again.",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message("❌ Playlist not found!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    async def create_new_playlist(self, interaction: discord.Interaction):
        """Create new playlist with current track"""
        try:
            if not self.player.current:
                await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
                return

            track = self.player.current
            track_data = {
                'title': track.title,
                'author': track.author,
                'uri': track.uri,
                'length': track.length
            }

            modal = AddTrackToPlaylistModal(self.player, self.user_id, self.guild_id, track_data)
            await interaction.response.send_modal(modal)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    async def cancel_button(self, interaction: discord.Interaction):
        """Cancel adding to playlist"""
        embed = discord.Embed(description="✅ Cancelled", color=0x5865F2)
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(emoji="➕", label="Create New Playlist", style=discord.ButtonStyle.primary, row=1, custom_id="create_new_default")
    async def create_new_default(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fallback button shown when no playlists exist"""
        await self.create_new_playlist(interaction)

    @discord.ui.button(emoji="❌", label="Cancel", style=discord.ButtonStyle.secondary, row=1, custom_id="cancel_default")
    async def cancel_default(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Fallback cancel when no playlists exist"""
        await self.cancel_button(interaction)

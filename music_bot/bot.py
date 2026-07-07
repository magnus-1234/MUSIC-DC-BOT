import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(
    level=os.getenv("MUSIC_BOT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("music_bot")


def _guild_ids() -> list[int]:
    configured = os.getenv("MUSIC_GUILD_IDS")
    if configured:
        values = configured.replace(";", ",").split(",")
    else:
        values = [os.getenv("GUILD_ID_1"), os.getenv("GUILD_ID_2")]

    guilds: list[int] = []
    for value in values:
        value = (value or "").strip()
        if not value:
            continue
        try:
            guilds.append(int(value))
        except ValueError:
            logger.warning("Ignoring invalid guild id: %s", value)
    return guilds


class MusicBot(commands.Bot):
    async def setup_hook(self) -> None:
        from music_bot.storage.music_state_storage import music_state_storage
        from music_bot.storage.playlist_storage import playlist_storage

        await playlist_storage.initialize()
        await music_state_storage.initialize()
        await self.load_extension("music_bot.cogs.music")
        logger.info("Loaded music bot cog")

        guild_ids = _guild_ids()
        if guild_ids:
            for guild_id in guild_ids:
                try:
                    guild = discord.Object(id=guild_id)
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    logger.info("Synced %s music commands to guild %s", len(synced), guild_id)
                except discord.Forbidden as e:
                    logger.warning("Could not sync commands to guild %s due to missing permissions (Forbidden): %s", guild_id, e)
                except discord.HTTPException as e:
                    logger.warning("HTTPException when syncing commands to guild %s: %s", guild_id, e)
        else:
            try:
                synced = await self.tree.sync()
                logger.info("Synced %s music commands globally", len(synced))
            except discord.HTTPException as e:
                logger.warning("Failed to sync commands globally: %s", e)


intents = discord.Intents.default()
intents.message_content = True
intents.members = False
intents.voice_states = True

bot = MusicBot(command_prefix=os.getenv("MUSIC_COMMAND_PREFIX", "!"), intents=intents)


@bot.event
async def on_ready() -> None:
    logger.info("Music bot logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")

@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
    channel_id = 1523997324513116241
    channel = bot.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as e:
            logger.error(f"Could not fetch notification channel: {e}")
            
    if channel:
        embed = discord.Embed(title="Bot Joined a New Server! 🎉", color=discord.Color.green())
        embed.add_field(name="Server Name", value=guild.name, inline=False)
        embed.add_field(name="Server ID", value=str(guild.id), inline=False)
        embed.add_field(name="Member Count", value=str(guild.member_count), inline=False)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send join notification: {e}")

@bot.event
async def on_guild_remove(guild: discord.Guild):
    logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
    channel_id = 1523997324513116241
    channel = bot.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as e:
            logger.error(f"Could not fetch notification channel: {e}")
            
    if channel:
        embed = discord.Embed(title="Bot Left a Server 😢", color=discord.Color.red())
        embed.add_field(name="Server Name", value=guild.name, inline=False)
        embed.add_field(name="Server ID", value=str(guild.id), inline=False)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send leave notification: {e}")


async def main() -> None:
    token = os.getenv("MUSIC_DISCORD_TOKEN")
    if not token:
        raise RuntimeError("MUSIC_DISCORD_TOKEN is not set")

    web_runner = None
    try:
        from music_bot.web_server import start_web_server
        async with bot:
            # Start the web control server once the bot is ready
            async def _start_web_after_ready():
                await bot.wait_until_ready()
                nonlocal web_runner
                web_runner = await start_web_server(bot)

            asyncio.create_task(_start_web_after_ready())
            await bot.start(token)
    finally:
        if web_runner:
            try:
                await web_runner.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())

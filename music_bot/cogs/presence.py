import discord
from discord.ext import commands, tasks
import random
import logging

logger = logging.getLogger("music_bot.presence")

class RichPresence(commands.Cog):
    """Handles rotating bot statuses (Rich Presence) for the Music Bot"""
    
    def __init__(self, bot):
        self.bot = bot
        self.presence_task.start()
        logger.info("✨ Music Bot Rich Presence cog loaded")

    def cog_unload(self):
        self.presence_task.cancel()

    @tasks.loop(seconds=15)
    async def presence_task(self):
        await self.bot.wait_until_ready()
        
        # Calculate dynamic stats
        guild_count = len(self.bot.guilds)
        
        # Presence List
        presences = [
            discord.Activity(type=discord.ActivityType.listening, name="🎵 /play [song]"),
            discord.Activity(type=discord.ActivityType.listening, name="⏸️ /pause | ▶️ /resume"),
            discord.Activity(type=discord.ActivityType.listening, name="⏭️ /skip to next song"),
            discord.Activity(type=discord.ActivityType.listening, name="🎼 /queue to view songs"),
            discord.Activity(type=discord.ActivityType.listening, name="🎚️ /volume [0-100]"),
            discord.Activity(type=discord.ActivityType.listening, name="📜 /nowplaying"),
            discord.Activity(type=discord.ActivityType.listening, name="🛑 /stop to end music"),
            discord.Activity(type=discord.ActivityType.watching, name=f"{guild_count} servers playing music!"),
            discord.Activity(type=discord.ActivityType.playing, name="🎶 High Quality Audio"),
        ]
        
        try:
            activity = random.choice(presences)
            await self.bot.change_presence(activity=activity)
        except Exception as e:
            logger.error(f"⚠️ Failed to update presence: {e}")

    @presence_task.before_loop
    async def before_presence(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RichPresence(bot))

import discord
from discord.ext import commands
from discord import app_commands


class HelpPaginationView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=120)
        self.pages = pages
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.first_page_button.disabled = self.current_page == 0
        self.prev_page_button.disabled = self.current_page == 0
        self.next_page_button.disabled = self.current_page == len(self.pages) - 1
        self.last_page_button.disabled = self.current_page == len(self.pages) - 1
        self.page_indicator.label = f"Page {self.current_page + 1}/{len(self.pages)}"

    @discord.ui.button(label="⏪", style=discord.ButtonStyle.secondary, custom_id="help_first")
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary, custom_id="help_prev")
    async def prev_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="help_indicator")
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary, custom_id="help_next")
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="⏩", style=discord.ButtonStyle.secondary, custom_id="help_last")
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all available music commands")
    async def help_command(self, interaction: discord.Interaction):
        embeds = []

        # Page 1: Playback Controls
        embed1 = discord.Embed(title="🎵 Music Bot Help - Playback Controls", color=discord.Color.blurple())
        embed1.description = "Control the playback of your music."
        embed1.add_field(name="`/play`", value="Play a song or add it to the queue.", inline=False)
        embed1.add_field(name="`/pause`", value="Pause the current track.", inline=False)
        embed1.add_field(name="`/resume`", value="Resume playback.", inline=False)
        embed1.add_field(name="`/skip`", value="Skip the current track.", inline=False)
        embed1.add_field(name="`/previous`", value="Play the previous track from history.", inline=False)
        embed1.add_field(name="`/stop`", value="Stop playback and disconnect.", inline=False)
        embeds.append(embed1)

        # Page 2: Queue Management
        embed2 = discord.Embed(title="🎵 Music Bot Help - Queue Management", color=discord.Color.blurple())
        embed2.description = "Manage your music queue."
        embed2.add_field(name="`/queue`", value="Show the music queue.", inline=False)
        embed2.add_field(name="`/nowplaying`", value="Show currently playing track.", inline=False)
        embed2.add_field(name="`/clear`", value="Clear the queue.", inline=False)
        embed2.add_field(name="`/remove`", value="Remove a track from the queue.", inline=False)
        embed2.add_field(name="`/shuffle`", value="Shuffle the queue.", inline=False)
        embed2.add_field(name="`/loop`", value="Set loop mode.", inline=False)
        embeds.append(embed2)

        # Page 3: Other
        embed3 = discord.Embed(title="🎵 Music Bot Help - Other", color=discord.Color.blurple())
        embed3.description = "Other utility commands."
        embed3.add_field(name="`/volume`", value="Set playback volume.", inline=False)
        embed3.add_field(name="`/seek`", value="Seek to a position in the current track.", inline=False)
        embed3.add_field(name="`/playlist`", value="Manage your saved playlists.", inline=False)
        embeds.append(embed3)
        
        for embed in embeds:
            embed.set_footer(text="Use the buttons below to navigate pages.")

        view = HelpPaginationView(embeds)
        await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))

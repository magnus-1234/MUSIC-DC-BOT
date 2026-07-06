import discord
from discord.ext import commands

class ContextInteractionAdapter:
    """
    Acts as a fake discord.Interaction object wrapping a commands.Context.
    This allows us to reuse slash command callbacks for prefix commands!
    """
    def __init__(self, ctx: commands.Context):
        self._ctx = ctx
        self.user = ctx.author
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.client = ctx.bot
        
        self.response = self.ResponseAdapter(ctx)
        self.followup = self.FollowupAdapter(ctx)
        
    @property
    def id(self):
        return self._ctx.message.id
        
    @property
    def token(self):
        return "mock_token_for_adapter"

    async def original_response(self):
        return self.response._last_message

    class ResponseAdapter:
        def __init__(self, ctx: commands.Context):
            self._ctx = ctx
            self._is_done = False
            self._last_message = None
            
        def is_done(self):
            return self._is_done
            
        async def defer(self, ephemeral: bool = False, thinking: bool = False):
            if not self._is_done:
                await self._ctx.typing()
                self._is_done = True
                
        async def send_message(self, *args, **kwargs):
            kwargs.pop('ephemeral', None)
            msg = await self._ctx.send(*args, **kwargs)
            self._is_done = True
            self._last_message = msg
            return msg

    class FollowupAdapter:
        def __init__(self, ctx: commands.Context):
            self._ctx = ctx
            
        async def send(self, *args, **kwargs):
            kwargs.pop('ephemeral', None)
            return await self._ctx.send(*args, **kwargs)

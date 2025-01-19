# cogs/moderation.py

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from datetime import timedelta
from loguru import logger
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from main import MoguMoguBot


class ModerationCog(commands.Cog):
    """
    A production-ready moderation cog that handles:
      - Ban, Kick
      - Mute, Unmute
      - Deafen, Disconnect
      - Timeout
      - Warn
    All commands log to the database's `moderation_logs` table for auditing.
    """

    moderation_group = SlashCommandGroup("moderation", "Commands for moderating members.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def log_action(
        self,
        moderator_id: int,
        user_id: int,
        action: str,
        reason: str
    ):
        """
        Insert an entry into the moderation_logs table with the performed action.
        This should match your `moderation_logs` schema:
            id SERIAL PRIMARY KEY,
            moderator_id BIGINT,
            user_id BIGINT,
            action TEXT,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        """
        try:
            query = """
                INSERT INTO moderation_logs (moderator_id, user_id, action, reason)
                VALUES ($1, $2, $3, $4);
            """
            await self.bot.db.execute(query, moderator_id, user_id, action, reason)
            logger.info(f"Logged moderation action: {action} by {moderator_id} on {user_id}.")
        except Exception as e:
            logger.exception(f"Failed to log moderation action: {e}")

    @moderation_group.command(name="ban", description="Ban a user from the server.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def ban_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to ban"),
        reason: Option(str, "Reason for ban", default="No reason provided")
    ):
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        # Check if user is bannable
        if member == ctx.author:
            await ctx.followup.send("You cannot ban yourself.", ephemeral=True)
            return
        if member.top_role >= ctx.author.top_role:
            await ctx.followup.send("You cannot ban someone with an equal or higher role.", ephemeral=True)
            return

        try:
            await member.ban(reason=reason)
            await self.log_action(ctx.author.id, member.id, "ban", reason)
            await ctx.followup.send(f"{member.mention} has been banned. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to ban this user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Ban failed: {e}", ephemeral=True)

    @moderation_group.command(name="kick", description="Kick a user from the server.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def kick_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to kick"),
        reason: Option(str, "Reason for kick", default="No reason provided")
    ):
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        if member == ctx.author:
            await ctx.followup.send("You cannot kick yourself.", ephemeral=True)
            return
        if member.top_role >= ctx.author.top_role:
            await ctx.followup.send("You cannot kick someone with an equal or higher role.", ephemeral=True)
            return

        try:
            await member.kick(reason=reason)
            await self.log_action(ctx.author.id, member.id, "kick", reason)
            await ctx.followup.send(f"{member.mention} has been kicked. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to kick this user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Kick failed: {e}", ephemeral=True)

    @moderation_group.command(name="mute", description="Give the user the muted role to prevent them from sending messages.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def mute_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to mute"),
        reason: Option(str, "Reason for mute", default="No reason provided")
    ):
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        # Suppose you have a "Muted" role in your config
        muted_role_id = self.bot.config.get("muted_role_id")
        if not muted_role_id:
            await ctx.followup.send("No muted_role_id found in config. Can't proceed.", ephemeral=True)
            return

        muted_role = ctx.guild.get_role(muted_role_id)
        if not muted_role:
            await ctx.followup.send("Muted role not found in this server.", ephemeral=True)
            return

        if muted_role in member.roles:
            await ctx.followup.send(f"{member.mention} is already muted.", ephemeral=True)
            return

        try:
            await member.add_roles(muted_role, reason=reason)
            await self.log_action(ctx.author.id, member.id, "mute", reason)
            await ctx.followup.send(f"{member.mention} has been muted. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to manage roles for that user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Mute failed: {e}", ephemeral=True)

    @moderation_group.command(name="unmute", description="Remove the muted role from a user.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def unmute_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to unmute")
    ):
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        muted_role_id = self.bot.config.get("muted_role_id")
        if not muted_role_id:
            await ctx.followup.send("No muted_role_id found in config. Can't proceed.", ephemeral=True)
            return

        muted_role = ctx.guild.get_role(muted_role_id)
        if not muted_role or muted_role not in member.roles:
            await ctx.followup.send(f"{member.mention} is not muted.", ephemeral=True)
            return

        try:
            await member.remove_roles(muted_role, reason="Unmute")
            await self.log_action(ctx.author.id, member.id, "unmute", "Unmute")
            await ctx.followup.send(f"{member.mention} has been unmuted.", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to manage roles for that user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Unmute failed: {e}", ephemeral=True)

    @moderation_group.command(name="deafen", description="Server-deafen a user in voice.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def deafen_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to deafen"),
        reason: Option(str, "Reason for deafening", default="No reason provided")
    ):
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        if not member.voice or not member.voice.channel:
            await ctx.followup.send(f"{member.mention} is not in a voice channel.", ephemeral=True)
            return

        try:
            await member.edit(deafen=True, reason=reason)
            await self.log_action(ctx.author.id, member.id, "deafen", reason)
            await ctx.followup.send(f"{member.mention} has been deafened. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to deafen this user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Deafen failed: {e}", ephemeral=True)

    @moderation_group.command(name="disconnect", description="Disconnect a user from voice.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def disconnect_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to disconnect"),
        reason: Option(str, "Reason for disconnect", default="No reason provided")
    ):
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        if not member.voice or not member.voice.channel:
            await ctx.followup.send(f"{member.mention} is not in a voice channel.", ephemeral=True)
            return

        try:
            await member.edit(voice_channel=None, reason=reason)
            await self.log_action(ctx.author.id, member.id, "disconnect", reason)
            await ctx.followup.send(f"{member.mention} has been disconnected from voice. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to disconnect this user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Disconnect failed: {e}", ephemeral=True)

    @moderation_group.command(name="timeout", description="Timeout a user for a given number of minutes.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def timeout_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to timeout"),
        minutes: Option(int, "Number of minutes to timeout", default=10),
        reason: Option(str, "Reason for timeout", default="No reason provided")
    ):
        """
        Note: This uses Discord's built-in "timeout" feature (requires the bot to have permission).
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        if minutes <= 0:
            await ctx.followup.send("Timeout duration must be greater than 0.", ephemeral=True)
            return

        duration = timedelta(minutes=minutes)

        try:
            await member.timeout(duration=duration, reason=reason)
            await self.log_action(ctx.author.id, member.id, "timeout", f"{reason} ({minutes}m)")
            await ctx.followup.send(f"{member.mention} has been timed out for {minutes} minutes. Reason: {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.followup.send("I do not have permission to timeout this user.", ephemeral=True)
        except discord.HTTPException as e:
            await ctx.followup.send(f"Timeout failed: {e}", ephemeral=True)

    @moderation_group.command(name="warn", description="Issue a warning to a user and record it.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def warn_user(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "The member to warn"),
        reason: Option(str, "Reason for warning", default="No reason provided")
    ):
        """
        Inserts into a 'warnings' table if one is present,
        and also logs the action into 'moderation_logs'.
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used within a server.", ephemeral=True)
            return

        # Insert into 'warnings' table if it exists:
        try:
            query = """
                INSERT INTO warnings (user_id, moderator_id, reason)
                VALUES ($1, $2, $3);
            """
            await self.bot.db.execute(query, member.id, ctx.author.id, reason)
            logger.info(f"{member.id} has been warned by {ctx.author.id}. Reason: {reason}")
        except Exception as e:
            logger.exception(f"Failed to insert warning: {e}")

        # Also log in moderation_logs
        await self.log_action(ctx.author.id, member.id, "warn", reason)

        await ctx.followup.send(f"{member.mention} has been warned. Reason: {reason}", ephemeral=True)


def setup(bot: "MoguMoguBot"):
    bot.add_cog(ModerationCog(bot))

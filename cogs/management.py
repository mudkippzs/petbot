# ./cogs/management.py
import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from discord import Option
from loguru import logger
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from main import MoguMoguBot

class ManagementCog(commands.Cog):
    """
    Cog for server management tasks, including:
    - Feature toggles (on/off)
    - Staff role management (add/remove)
    - Backup configuration (recipients, channel, interval)
    
    All commands in this cog require staff permissions.
    """

    management = SlashCommandGroup("manage", "Commands for managing server configuration.")
    
    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def set_server_config(self, key: str, value: Any):
        """
        Set a configuration key in the server_config table.
        """
        await self.bot.db.execute(
            "INSERT INTO server_config (key, value) VALUES ($1, $2) "
            "ON CONFLICT (key) DO UPDATE SET value=$2;",
            key, value
        )

    async def get_server_config(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a configuration value from the server_config table.
        """
        row = await self.bot.db.fetchrow("SELECT value FROM server_config WHERE key=$1;", key)
        return row["value"] if row else None

    @management.command(name="feature", description="Enable or disable a feature.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_feature(self,
                             ctx: discord.ApplicationContext,
                             feature_name: str,
                             state: Option(str, "on|off", choices=["on", "off"])):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        value = {"enabled": (state == "on")}
        await self.set_server_config(f"feature_{feature_name}", value)
        await ctx.followup.send(f"Feature '{feature_name}' set to {state}.")
        logger.info(f"Feature '{feature_name}' set to {state} by user {ctx.author.id}.")

    @management.command(name="add_staff_role", description="Add a role as staff.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_add_staff_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("INSERT INTO staff_roles (role_id) VALUES ($1) ON CONFLICT DO NOTHING;", role.id)
        await ctx.followup.send(f"Role {role.mention} added as a staff role.")
        logger.info(f"Staff role {role.id} added by user {ctx.author.id}.")

    @management.command(name="remove_staff_role", description="Remove a staff role.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_remove_staff_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("DELETE FROM staff_roles WHERE role_id=$1;", role.id)
        await ctx.followup.send(f"Role {role.mention} removed from staff roles.")
        logger.info(f"Staff role {role.id} removed by user {ctx.author.id}.")

    @management.command(name="add_user", description="Add a user as a backup recipient.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_group_add_user(self, ctx: discord.ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("INSERT INTO backup_recipients (user_id) VALUES ($1) ON CONFLICT DO NOTHING;", user.id)
        await ctx.followup.send(f"User <@{user.id}> added as a backup recipient.")
        logger.info(f"Backup recipient {user.id} added by user {ctx.author.id}.")

    @management.command(name="remove_user", description="Remove a user from backup recipients.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_group_remove_user(self, ctx: discord.ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("DELETE FROM backup_recipients WHERE user_id=$1;", user.id)
        await ctx.followup.send(f"User <@{user.id}> removed from backup recipients.")
        logger.info(f"Backup recipient {user.id} removed by user {ctx.author.id}.")

    @management.command(name="channel", description="Set the channel where backups are posted.")
    @commands.has_any_role("Gentleman", "Harlot", "Boss", "Underboss", "Consigliere")
    async def config_group_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        value = {"channel_id": channel.id}
        await self.set_server_config("backup_channel_id", value)
        await ctx.followup.send(f"Backup channel set to {channel.mention}.")
        logger.info(f"Backup channel set to {channel.id} by user {ctx.author.id}.")

    @management.command(name="interval", description="Set the backup interval in minutes.")
    async def config_group_interval(self, ctx: discord.ApplicationContext, minutes: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if minutes <= 0:
            await ctx.followup.send("Interval must be greater than 0.")
            return

        value = {"interval_minutes": minutes}
        await self.set_server_config("backup_interval", value)
        await ctx.followup.send(f"Backup interval set to {minutes} minutes.")
        logger.info(f"Backup interval set to {minutes} minutes by user {ctx.author.id}.")

def setup(bot: "MoguMoguBot"):
    bot.add_cog(ManagementCog(bot))

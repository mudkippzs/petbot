# ./cogs/management.py
import discord
from discord.ext import commands
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

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def is_staff(self, member: discord.Member) -> bool:
        """
        Check if the given member has any of the configured staff roles.
        """
        staff_roles = await self.bot.db.fetch("SELECT role_id FROM staff_roles;")
        staff_role_ids = [r["role_id"] for r in staff_roles]
        if not staff_role_ids:
            return False
        return any(role.id in staff_role_ids for role in member.roles)

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

    @commands.slash_command(name="config", description="Server configuration commands.")
    async def config_group(self, ctx: discord.ApplicationContext):
        """
        Base command group for configuration.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return
        
        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can access configuration commands.")
            return

        # If no subcommand is called, just provide a hint.
        await ctx.followup.send("Use a subcommand to configure the server settings.")

    @config_group.sub_command(name="feature", description="Enable or disable a feature.")
    async def config_feature(self,
                             ctx: discord.ApplicationContext,
                             feature_name: str,
                             state: Option(str, "on|off", choices=["on", "off"])):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can toggle features.")
            return

        value = {"enabled": (state == "on")}
        await self.set_server_config(f"feature_{feature_name}", value)
        await ctx.followup.send(f"Feature '{feature_name}' set to {state}.")
        logger.info(f"Feature '{feature_name}' set to {state} by user {ctx.author.id}.")

    @config_group.sub_command(name="add_staff_role", description="Add a role as staff.")
    async def config_add_staff_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can add staff roles.")
            return

        await self.bot.db.execute("INSERT INTO staff_roles (role_id) VALUES ($1) ON CONFLICT DO NOTHING;", role.id)
        await ctx.followup.send(f"Role {role.mention} added as a staff role.")
        logger.info(f"Staff role {role.id} added by user {ctx.author.id}.")

    @config_group.sub_command(name="remove_staff_role", description="Remove a staff role.")
    async def config_remove_staff_role(self, ctx: discord.ApplicationContext, role: discord.Role):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can remove staff roles.")
            return

        await self.bot.db.execute("DELETE FROM staff_roles WHERE role_id=$1;", role.id)
        await ctx.followup.send(f"Role {role.mention} removed from staff roles.")
        logger.info(f"Staff role {role.id} removed by user {ctx.author.id}.")

    @config_group.sub_command(name="backup", description="Manage backup settings.")
    async def config_backup_group(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can manage backups.")
            return

        # If no subcommand is called here, just provide a hint.
        await ctx.followup.send("Use a backup subcommand to configure backup settings.")

    @config_backup_group.sub_command(name="add_user", description="Add a user as a backup recipient.")
    async def config_backup_add_user(self, ctx: discord.ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can add backup recipients.")
            return

        await self.bot.db.execute("INSERT INTO backup_recipients (user_id) VALUES ($1) ON CONFLICT DO NOTHING;", user.id)
        await ctx.followup.send(f"User <@{user.id}> added as a backup recipient.")
        logger.info(f"Backup recipient {user.id} added by user {ctx.author.id}.")

    @config_backup_group.sub_command(name="remove_user", description="Remove a user from backup recipients.")
    async def config_backup_remove_user(self, ctx: discord.ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can remove backup recipients.")
            return

        await self.bot.db.execute("DELETE FROM backup_recipients WHERE user_id=$1;", user.id)
        await ctx.followup.send(f"User <@{user.id}> removed from backup recipients.")
        logger.info(f"Backup recipient {user.id} removed by user {ctx.author.id}.")

    @config_backup_group.sub_command(name="channel", description="Set the channel where backups are posted.")
    async def config_backup_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can set the backup channel.")
            return

        value = {"channel_id": channel.id}
        await self.set_server_config("backup_channel_id", value)
        await ctx.followup.send(f"Backup channel set to {channel.mention}.")
        logger.info(f"Backup channel set to {channel.id} by user {ctx.author.id}.")

    @config_backup_group.sub_command(name="interval", description="Set the backup interval in minutes.")
    async def config_backup_interval(self, ctx: discord.ApplicationContext, minutes: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can set the backup interval.")
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

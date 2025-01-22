import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from discord import ApplicationContext, Attachment
from loguru import logger
from typing import TYPE_CHECKING, Any, Dict, Optional
import json
import io
import asyncio

if TYPE_CHECKING:
    from main import MoguMoguBot

def chunk_list(lst, size):
    """Yield successive chunks of `size` from the list `lst`."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

class ManagementCog(commands.Cog):
    """
    Cog for server management tasks, including:
    - Feature toggles (on/off)
    - Staff role management (add/remove)
    - Backup configuration (recipients, channel, interval)
    - Export/Import of role and channel permissions (with chunked and rate-limited updates).
    
    All commands in this cog require staff permissions.
    """

    management = SlashCommandGroup("manage", "Commands for managing server configuration.")
    
    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    # -----------------------
    # Database Helpers
    # -----------------------
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

    # -----------------------
    # Feature Management
    # -----------------------
    @management.command(name="feature", description="Enable or disable a feature.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_feature(self,
                             ctx: ApplicationContext,
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
    async def config_add_staff_role(self, ctx: ApplicationContext, role: discord.Role):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("INSERT INTO staff_roles (role_id) VALUES ($1) ON CONFLICT DO NOTHING;", role.id)
        await ctx.followup.send(f"Role {role.mention} added as a staff role.")
        logger.info(f"Staff role {role.id} added by user {ctx.author.id}.")

    @management.command(name="remove_staff_role", description="Remove a staff role.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_remove_staff_role(self, ctx: ApplicationContext, role: discord.Role):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("DELETE FROM staff_roles WHERE role_id=$1;", role.id)
        await ctx.followup.send(f"Role {role.mention} removed from staff roles.")
        logger.info(f"Staff role {role.id} removed by user {ctx.author.id}.")

    # -----------------------
    # Backup Recipients
    # -----------------------
    @management.command(name="add_user", description="Add a user as a backup recipient.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_group_add_user(self, ctx: ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("INSERT INTO backup_recipients (user_id) VALUES ($1) ON CONFLICT DO NOTHING;", user.id)
        await ctx.followup.send(f"User <@{user.id}> added as a backup recipient.")
        logger.info(f"Backup recipient {user.id} added by user {ctx.author.id}.")

    @management.command(name="remove_user", description="Remove a user from backup recipients.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def config_group_remove_user(self, ctx: ApplicationContext, user: discord.User):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        await self.bot.db.execute("DELETE FROM backup_recipients WHERE user_id=$1;", user.id)
        await ctx.followup.send(f"User <@{user.id}> removed from backup recipients.")
        logger.info(f"Backup recipient {user.id} removed by user {ctx.author.id}.")

    # -----------------------
    # Backup Channel & Interval
    # -----------------------
    @management.command(name="channel", description="Set the channel where backups are posted.")
    @commands.has_any_role("Gentleman", "Harlot", "Boss", "Underboss", "Consigliere")
    async def config_group_channel(self, ctx: ApplicationContext, channel: discord.TextChannel):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        value = {"channel_id": channel.id}
        await self.set_server_config("backup_channel_id", value)
        await ctx.followup.send(f"Backup channel set to {channel.mention}.")
        logger.info(f"Backup channel set to {channel.id} by user {ctx.author.id}.")

    @management.command(name="interval", description="Set the backup interval in minutes.")
    async def config_group_interval(self, ctx: ApplicationContext, minutes: int):
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

    # -----------------------
    # Export Permissions
    # -----------------------
    @management.command(name="export_perms", description="Export all roles and channel/category permissions to JSON.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def export_permissions(self, ctx: ApplicationContext):
        """Export the server's role perms and channel/category overwrites (including user-level) to JSON."""
        await ctx.defer(ephemeral=True)

        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        guild: discord.Guild = ctx.guild
        
        # 1. Gather role permissions
        roles_data = {}
        for role in guild.roles:
            roles_data[str(role.id)] = {
                "name": role.name,
                "permissions_value": role.permissions.value,
                "color": role.color.value,
                "position": role.position,
                "mentionable": role.mentionable,
                "hoist": role.hoist
            }

        # 2. Gather channel/category overwrites (for both roles & users)
        channels_data = {}
        for channel in guild.channels:
            overwrites_dict = {}
            for target, overwrite in channel.overwrites.items():
                allow, deny = overwrite.pair()
                # Distinguish role vs. user
                if isinstance(target, discord.Role):
                    target_type = "role"
                elif isinstance(target, discord.Member):
                    target_type = "member"
                else:
                    continue  # If there's some unexpected case, skip it

                overwrites_dict[str(target.id)] = {
                    "type": target_type,
                    "allow": allow.value,
                    "deny": deny.value
                }

            channels_data[str(channel.id)] = {
                "name": channel.name,
                "type": str(channel.type),   # e.g. "text", "voice", "category"
                "parent_id": str(channel.category_id) if channel.category_id else None,
                "overwrites": overwrites_dict
            }

        # Convert dicts to JSON text
        roles_json = json.dumps(roles_data, indent=2)
        channels_json = json.dumps(channels_data, indent=2)

        # Convert the JSON text into file-like objects
        roles_file = discord.File(
            io.BytesIO(roles_json.encode("utf-8")),
            filename="roles.json"
        )
        channels_file = discord.File(
            io.BytesIO(channels_json.encode("utf-8")),
            filename="channels.json"
        )

        # Send ephemeral response with attachments
        await ctx.followup.send(
            content="Here are the exported permissions files:",
            files=[roles_file, channels_file],
            ephemeral=True
        )
        logger.info(f"Permissions exported by user {ctx.author.id}.")

    # -----------------------
    # Import Permissions
    # -----------------------
    @management.command(name="import_perms", description="Import roles and channel/category permissions from JSON.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def import_permissions(
        self,
        ctx: ApplicationContext,
        roles_file: Option(Attachment, description="Attach the roles.json file", required=True),
        channels_file: Option(Attachment, description="Attach the channels.json file", required=True)
    ):
        """
        Import (restore) the server's role perms and channel/category overwrites from JSON.
        This will overwrite existing permissions with the data from your JSON backup.
        """
        await ctx.defer(ephemeral=True)

        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        guild: discord.Guild = ctx.guild
        
        # 1. Parse the roles.json
        try:
            roles_data = json.loads(await roles_file.read())
        except Exception as e:
            await ctx.followup.send(f"Failed to parse `roles.json`: {e}")
            return

        # 2. Parse the channels.json
        try:
            channels_data = json.loads(await channels_file.read())
        except Exception as e:
            await ctx.followup.send(f"Failed to parse `channels.json`: {e}")
            return

        # -----------------------
        # Update Role Permissions
        # -----------------------
        all_role_ids = list(roles_data.keys())
        updated_roles = 0
        # Chunk the role updates (5 roles per batch, 2s pause by default)
        for chunk in chunk_list(all_role_ids, 5):
            for role_id_str in chunk:
                role_info = roles_data[role_id_str]
                role_id = int(role_id_str)
                role = guild.get_role(role_id)
                if not role:
                    continue

                try:
                    await role.edit(
                        permissions=discord.Permissions(role_info["permissions_value"]),
                        color=discord.Color(role_info["color"]),
                        mentionable=role_info["mentionable"],
                        hoist=role_info["hoist"]
                    )
                    updated_roles += 1
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to edit role {role.name} ({role.id}).")
                except Exception as e:
                    logger.error(f"Error updating role {role.name} ({role.id}): {e}")

            # Sleep between role updates to avoid rate-limits
            await asyncio.sleep(2)

        # -----------------------
        # Update Channel Overwrites
        # -----------------------
        all_channel_ids = list(channels_data.keys())
        updated_channels = 0

        for chunk in chunk_list(all_channel_ids, 5):
            # Build a batch of channels to edit
            for channel_id_str in chunk:
                chan_info = channels_data[channel_id_str]
                channel_id = int(channel_id_str)
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue

                # Prepare new overwrites dict that will overwrite everything
                overwrites_map = {}
                for target_id_str, perms_dict in chan_info["overwrites"].items():
                    target_id = int(target_id_str)
                    allow_perms = discord.Permissions(perms_dict["allow"])
                    deny_perms = discord.Permissions(perms_dict["deny"])
                    overwrite = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)

                    if perms_dict["type"] == "role":
                        target = guild.get_role(target_id)
                    else:
                        # "member"
                        target = guild.get_member(target_id)

                    if target:
                        overwrites_map[target] = overwrite
                    else:
                        # If the role/user no longer exists, skip
                        continue

                # Attempt to overwrite the channel's entire permissions map
                try:
                    await channel.edit(overwrites=overwrites_map)
                    updated_channels += 1
                except discord.Forbidden:
                    logger.warning(f"Missing permissions to set perms for channel {channel.name} ({channel.id}).")
                except Exception as e:
                    logger.error(f"Error setting perms for channel {channel.name}: {e}")

            # Sleep between channel updates to avoid rate-limits
            await asyncio.sleep(2)

        # Summary response
        await ctx.followup.send(
            f"Import complete!\n"
            f"Updated **{updated_roles}** roles and **{updated_channels}** channels/categories."
        )
        logger.info(f"Permissions imported by user {ctx.author.id}.")

def setup(bot: "MoguMoguBot"):
    bot.add_cog(ManagementCog(bot))

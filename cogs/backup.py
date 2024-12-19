# ./cogs/backup.py
import discord
from discord.ext import commands, tasks
from loguru import logger
import io
import json
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from main import MoguMoguBot

class BackupCog(commands.Cog):
    """
    A cog that performs regular database backups and distributes them to staff and configured recipients.
    Also provides a fallback JSON backup for redundancy.
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self.interval = self.bot.config["backup"].get("interval_minutes", 15)
        self.staff_channel_id = self.bot.config["backup"].get("staff_channel_id")
        self.backup_recipients: List[int] = self.bot.config["backup"].get("backup_recipients", [])
        self.backup_task.add_exception_type(Exception)

        # Adjust the backup interval dynamically if needed and start
        self.backup_task.change_interval(minutes=self.interval)
        self.backup_task.start()

    def cog_unload(self):
        """Called when the cog is unloaded. Cancels the backup task."""
        self.backup_task.cancel()

    @tasks.loop(minutes=15)
    async def backup_task(self):
        """
        Task loop that runs periodically to create and send a database backup.
        Interval is overridden after initialization.
        """
        await self.do_backup()

    @backup_task.before_loop
    async def before_backup(self):
        """Wait until the bot is ready before starting the backup task."""
        await self.bot.wait_until_ready()
        logger.info("Backup task is about to start...")

    async def do_backup(self) -> None:
        """
        Perform the database backup operation and send the backup file 
        to the designated staff channel and backup recipients.
        Also creates a fallback JSON backup of some critical tables.
        """
        logger.info("Starting database backup...")

        # Primary SQL Backup
        backup_data = await self.bot.db.backup_database()
        if not backup_data:
            logger.error("No backup data returned; backup may have failed.")
            return

        # Create fallback JSON backup: for example, we back up a few key tables as JSON
        fallback_json_data = await self.create_fallback_json_backup()

        # Prepare files
        backup_sql_file = io.BytesIO(backup_data.encode('utf-8'))
        backup_sql_file.name = "database_backup.sql"

        fallback_json_file = io.BytesIO(json.dumps(fallback_json_data, indent=4).encode('utf-8'))
        fallback_json_file.name = "database_backup_fallback.json"

        # Send to staff channel if configured
        if self.staff_channel_id:
            channel = self.bot.get_channel(self.staff_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(
                        content="Here's the latest database backup (SQL and fallback JSON):", 
                        files=[
                            discord.File(backup_sql_file, filename="database_backup.sql"),
                            discord.File(fallback_json_file, filename="database_backup_fallback.json")
                        ]
                    )
                except discord.DiscordException as e:
                    logger.exception(f"Failed to send backup to staff channel {self.staff_channel_id}: {e}")
            else:
                logger.warning(f"Staff channel with ID {self.staff_channel_id} not found or not a text channel.")
        else:
            logger.warning("No staff_channel_id configured for backups.")

        # Reset the file pointers before sending to recipients
        backup_sql_file.seek(0)
        fallback_json_file.seek(0)

        # DM the backup recipients
        for user_id in self.backup_recipients:
            user = self.bot.get_user(user_id)
            if user:
                try:
                    await user.send(
                        content="Here's the latest database backup (SQL and fallback JSON):",
                        files=[
                            discord.File(backup_sql_file, filename="database_backup.sql"),
                            discord.File(fallback_json_file, filename="database_backup_fallback.json")
                        ]
                    )
                    # Reset after each send
                    backup_sql_file.seek(0)
                    fallback_json_file.seek(0)
                except discord.Forbidden:
                    logger.warning(f"Cannot DM user {user_id} for backup.")
                except discord.DiscordException as e:
                    logger.exception(f"Failed to DM backup to user {user_id}: {e}")
            else:
                logger.warning(f"User {user_id} not found. Cannot send backup DM.")

        logger.info("Database backup completed.")

    async def create_fallback_json_backup(self) -> dict:
        """
        Create a fallback JSON backup as a secondary format.
        We fetch a few critical tables and store their data as JSON.
        This is a simplified backup, not a full export, but ensures 
        critical info is retained if SQL backup fails.

        Returns:
            dict: A dictionary containing fallback data.
        """
        fallback_data = {}

        # Add any critical tables you deem necessary. For example:
        # Subs and ownership:
        subs = await self.bot.db.fetch("SELECT * FROM subs;")
        subs_ownership = await self.bot.db.fetch("SELECT * FROM sub_ownership;")

        # Convert asyncpg.Record to normal dict
        def records_to_list(records):
            return [dict(r) for r in records]

        fallback_data["subs"] = records_to_list(subs)
        fallback_data["sub_ownership"] = records_to_list(subs_ownership)

        # Add more tables if needed
        # e.g.:
        # services = await self.bot.db.fetch("SELECT * FROM sub_services;")
        # fallback_data["sub_services"] = records_to_list(services)

        return fallback_data


def setup(bot: "MoguMoguBot"):
    bot.add_cog(BackupCog(bot))

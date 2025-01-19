# ./cogs/backup.py
import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from loguru import logger
import aiohttp
import asyncio
import io
import json
import subprocess
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from main import MoguMoguBot


class BackupCog(commands.Cog):
    """
    A cog that performs regular database backups and distributes them to staff 
    and configured recipients. Also provides manual commands to back up and 
    restore (from an external SQL file URL). The restore operation first 
    backs up the current DB, ensuring we always have a fallback.
    """

    backup_group = SlashCommandGroup(
        "backup",
        "Commands for managing the bot's database backup and restore."
    )

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self.interval = self.bot.config["backup"].get("interval_minutes", 15)
        self.staff_channel_id = self.bot.config["backup"].get("staff_channel_id")
        self.backup_recipients: List[int] = self.bot.config["backup"].get("backup_recipients", [])

        # Start the backup task on load
        self.backup_task.add_exception_type(Exception)
        self.backup_task.change_interval(minutes=self.interval)
        #self.backup_task.start()

    def cog_unload(self):
        """Called when the cog is unloaded. Cancels the backup loop."""
        self.backup_task.cancel()

    # ------------------ REGULAR BACKUP LOOP ------------------
    @tasks.loop(minutes=30)
    async def backup_task(self):
        """
        Periodic task loop to create and send a database backup.
        The interval is updated to `self.interval` after initialization.
        """
        await self.do_backup()

    @backup_task.before_loop
    async def before_backup(self):
        """Wait until the bot is ready before starting the backup loop."""
        await self.bot.wait_until_ready()
        logger.info("Backup task is about to start...")

    # ------------------ HELPERS: BACKUP / RESTORE ------------------
    async def do_backup(self) -> None:
        """
        Perform the database backup operation and distribute it to 
        the designated staff channel and backup recipients.
        Also creates a fallback JSON backup of selected tables as a secondary format.
        """
        logger.info("Starting database backup...")

        # 1) Primary SQL Backup
        backup_data = await self.bot.db.backup_database()
        if not backup_data:
            logger.error("No backup data returned; backup may have failed.")
            return

        # 2) Create fallback JSON backup: can add more tables if desired
        fallback_json_data = await self.create_fallback_json_backup()

        # 3) Prepare in-memory files
        backup_sql_file = io.BytesIO(backup_data.encode('utf-8'))
        backup_sql_file.name = "database_backup.sql"

        fallback_json_file = io.BytesIO(json.dumps(fallback_json_data, indent=4).encode('utf-8'))
        fallback_json_file.name = "database_backup_fallback.json"

        # 4) Send to staff channel if configured
        if self.staff_channel_id:
            channel = self.bot.get_channel(self.staff_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(
                        content="Here's the latest database backup (SQL + fallback JSON).",
                        files=[
                            discord.File(backup_sql_file, filename=backup_sql_file.name),
                            discord.File(fallback_json_file, filename=fallback_json_file.name)
                        ]
                    )
                except discord.DiscordException as e:
                    logger.exception(f"Failed to send backup to staff channel {self.staff_channel_id}: {e}")
            else:
                logger.warning(
                    f"Staff channel with ID {self.staff_channel_id} not found or not a text channel."
                )
        else:
            logger.warning("No staff_channel_id configured for backups.")

        # 5) Reset file pointers before sending to recipients
        backup_sql_file.seek(0)
        fallback_json_file.seek(0)

        # 6) DM the backup recipients
        for user_id in self.backup_recipients:
            user = self.bot.get_user(user_id)
            if user:
                try:
                    await user.send(
                        content="Here's the latest database backup (SQL + fallback JSON).",
                        files=[
                            discord.File(backup_sql_file, filename=backup_sql_file.name),
                            discord.File(fallback_json_file, filename=fallback_json_file.name)
                        ]
                    )
                    # Reset after each DM send
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
        By default, we back up the `subs` and `sub_ownership` tables. 
        Extend as needed for your environment.

        Returns:
            dict: A dictionary containing fallback data from some critical tables.
        """
        fallback_data = {}
        try:
            # Example: subs and sub_ownership
            subs = await self.bot.db.fetch("SELECT * FROM subs;")
            subs_ownership = await self.bot.db.fetch("SELECT * FROM sub_ownership;")

            def records_to_list(records):
                return [dict(r) for r in records]

            fallback_data["subs"] = records_to_list(subs)
            fallback_data["sub_ownership"] = records_to_list(subs_ownership)

        except Exception as e:
            logger.exception(f"Failed to create fallback JSON backup: {e}")

        return fallback_data

    async def restore_database_from_sql(self, sql_data: str) -> bool:
        """
        Overwrite the entire database from an SQL dump string using `psql`.

        Steps:
        1. Close existing connection pool.
        2. Shell out to `psql` with the provided SQL data as input.
        3. Reconnect the bot's DB pool.

        Returns:
            bool: True if restore succeeded, False otherwise.
        """
        db_conf = self.bot.config["db_creds"]
        cmd = [
            "psql",
            "-U", db_conf["user"],
            "-h", db_conf["host"],
            "--quiet",
            "--single-transaction",
            db_conf["dbname"]
        ]
        env = {"PGPASSWORD": db_conf["pass"]}

        try:
            # 1) Close existing connection pool
            await self.bot.db.close()
            logger.info("Database connection pool closed before restore.")

            logger.info("Starting restore using psql...")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout_data, stderr_data = await process.communicate(input=sql_data.encode('utf-8'))

            if process.returncode != 0:
                error_msg = stderr_data.decode('utf-8', errors='replace')
                logger.error(f"Database restore failed: {error_msg}")
                # Attempt to reconnect anyway
                await self.bot.db.connect()
                return False

            logger.info("Database restore completed successfully.")
        except FileNotFoundError:
            logger.error("psql not found. Please ensure it is installed and in PATH.")
            # Attempt to reconnect
            await self.bot.db.connect()
            return False
        except Exception as e:
            logger.exception(f"Unexpected error during database restore: {e}")
            # Attempt to reconnect
            await self.bot.db.connect()
            return False

        # 2) Reconnect
        await self.bot.db.connect()
        logger.info("Database connection pool re-created after restore.")
        return True

    # ------------------ COMMANDS ------------------

    @backup_group.command(name="now", description="Manually trigger an immediate backup.")
    @commands.has_any_role("Boss")
    async def backup_now(self, ctx: discord.ApplicationContext):
        """
        Staff command to manually trigger a database backup right now.
        """
        # Check guild & staff
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return        

        await ctx.defer(ephemeral=True)
        await self.do_backup()
        await ctx.followup.send("Manual backup completed and sent to configured recipients.", ephemeral=True)

    @backup_group.command(name="restore", description="Restore the database from a given SQL dump URL (staff-only).")
    @commands.has_any_role("Boss")
    async def backup_restore(self, ctx: discord.ApplicationContext, url: str):
        """
        Staff command to restore the entire database from a SQL dump file hosted at <url>.

        Steps:
        1. Create a secondary backup of the current DB (so we have a fallback).
        2. Fetch the new SQL from <url>.
        3. Use `psql` to overwrite the DB with the new data.
        4. Reconnect the bot's DB pool.

        :param url: Direct link to the .sql file (must be accessible without login).
        """
        # Check guild & staff
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return
        
        await ctx.defer(ephemeral=True)
        # 1) Create a fallback backup
        await ctx.followup.send("Creating a backup of the **current** database before restoring...", ephemeral=True)
        await self.do_backup()

        # 2) Fetch the new SQL data
        await ctx.followup.send(f"Fetching SQL dump from: {url}", ephemeral=True)
        sql_data = await self.fetch_file_from_url(url)
        if sql_data is None:
            await ctx.followup.send("Failed to fetch the SQL file. Aborting restore.", ephemeral=True)
            return

        # 3) Restore
        await ctx.followup.send("Restoring database from the provided SQL dump...", ephemeral=True)
        success = await self.restore_database_from_sql(sql_data)
        if not success:
            await ctx.followup.send(
                "Database restore **failed**. Attempted to reconnect to the old DB. Check logs for details.",
                ephemeral=True
            )
            return

        # 4) Done
        await ctx.followup.send(
            "Database restore **completed** successfully! The bot has reconnected to the new database.",
            ephemeral=True
        )

    # ------------------ UTILS ------------------
    async def fetch_file_from_url(self, url: str) -> Optional[str]:
        """
        Fetch raw text data (SQL) from the given URL using aiohttp.

        :param url: The direct URL to the file resource.
        :return: The file contents as a string, or None if it fails.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to GET {url}. Status code: {resp.status}")
                        return None
                    return await resp.text()
        except Exception as e:
            logger.exception(f"Error fetching file from {url}: {e}")
            return None


def setup(bot: "MoguMoguBot"):
    bot.add_cog(BackupCog(bot))

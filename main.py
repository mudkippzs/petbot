# ./main.py
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict
from loguru import logger
import discord
from discord.ext import commands
from utils import load_json_config
from db import Database

"""
This is the main entry point of the bot. It:
- Configures logging.
- Loads configuration files (config, strings, theme).
- Initializes the bot with the provided configurations.
- Connects to the database and loads all cogs.
- Starts the bot using the provided token.
"""

# Configure logging: console and rotating file logs.
logger.remove()
logger.add(sys.stdout, format="{time} {level} {message}", level="INFO")
logger.add("logs/soupbot_{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days", compression="zip")


class MoguMoguBot(commands.Bot):
    """
    The primary bot class for the MoguMoguBot application.
    Manages configuration, database connections, and dynamically loads cogs.
    """

    def __init__(self, config: Dict[str, Any], strings: Dict[str, Any], theme: Dict[str, Any]):
        intents = discord.Intents.all()
        super().__init__(intents=intents, description=strings.get("welcome_message", "Welcome!"))
        self.config = config
        self.strings = strings
        self.theme = theme
        self.db = Database(config)

    async def setup_hook(self) -> None:
        """
        Runs after the bot is setup but before connecting to Discord.
        Ensures the database is ready and loads all cogs dynamically.
        """
        await self.db.connect()

        # Load all cogs in the cogs directory.
        for ext in Path("cogs").glob("*.py"):
            try:
                await self.load_extension(f"cogs.{ext.stem}")
                logger.info(f"Loaded cog: {ext.stem}")
            except Exception as e:
                logger.exception(f"Failed to load cog {ext.stem}: {e}")

        # Sync slash commands with Discord.
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application commands.")
        except Exception as e:
            logger.exception(f"Failed to sync application commands: {e}")

    async def on_ready(self):
        """
        Event called when the bot successfully connects to Discord.
        """
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is ready and connected.")

    async def on_error(self, event_method: str, *args, **kwargs):
        """
        Global error event handler. Logs exceptions for debugging.
        """
        logger.exception(f"Error in event {event_method}")

    async def close(self) -> None:
        """
        Close the database connection pool and then close the bot.
        """
        await self.db.close()
        await super().close()


async def main():
    """
    The main entrypoint of the bot.
    Loads configurations, initializes the bot instance, and starts it.
    """
    # Load configuration files asynchronously.
    config = await load_json_config("config.json")
    strings = await load_json_config("strings.json")
    theme = await load_json_config("theme.json")

    if "token" not in config or not config["token"]:
        logger.error("No 'token' found in config.json. Cannot start the bot.")
        return

    bot = MoguMoguBot(config, strings, theme)
    # Using async with ensures proper cleanup if an exception occurs during bot startup/shutdown.
    async with bot:
        await bot.start(config["token"])


if __name__ == '__main__':
    asyncio.run(main())

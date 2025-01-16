import asyncio
import sys
from pathlib import Path
from typing import Any, Dict
from loguru import logger
import discord
from discord.ext import commands
from utils import load_json_config
from db import Database


class MoguMoguBot(commands.Bot):
    def __init__(
        self,
        config: Dict[str, Any],
        strings: Dict[str, Any],
        theme: Dict[str, Any]
    ):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=config.get("prefix", "!"),
            description=strings.get("welcome_message", "Welcome!"),
            intents=intents
        )
        self.config = config
        self.strings = strings
        self.theme = theme
        self.db = Database(config)

    async def on_ready(self):
        """Event called when the bot connects to Discord."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

    async def on_error(self, event_method: str, *args, **kwargs):
        """Global error event handler."""
        logger.exception(f"Error in event {event_method}")

    async def close(self) -> None:
        """Close the DB connection then close the bot."""
        await self.db.close()
        await super().close()

async def main():
    # Asynchronously load config files
    config = await load_json_config("config.json")
    strings = await load_json_config("strings.json")
    theme = await load_json_config("theme.json")

    if "token" not in config or not config["token"]:
        logger.error("No 'token' found in config.json. Cannot start the bot.")
        return

    bot = MoguMoguBot(config, strings, theme)

    # Bot connects...
    await bot.db.connect()

    # Then load all cogs in the cogs directory
    for ext in Path("cogs").glob("*.py"):
        try:
            bot.load_extension(f"cogs.{ext.stem}")
            logger.info(f"Loaded cog: {ext.stem}")
        except Exception as e:
            logger.exception(f"Failed to load cog {ext.stem}: {e}")

    # Run the bot
    try:
        await bot.start(config["token"])
    except KeyboardInterrupt:
        logger.info("Detected Ctrl+C, shutting down...")
    finally:
        await bot.close()


if __name__ == '__main__':
    asyncio.run(main())

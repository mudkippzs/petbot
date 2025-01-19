# ./utils.py
import json
import csv
import aiohttp
import asyncio
import aiofiles

from discord.ext import commands
from discord import Guild
from loguru import logger
from typing import Any, Dict, List, Optional


async def load_json_config(file: str) -> Dict[str, Any]:
    """
    Asynchronously load a JSON configuration file and return its contents as a dictionary.

    Parameters:
        file (str): The path to the JSON file.

    Returns:
        dict: The JSON data as a Python dictionary, or empty dict if file not found or invalid.
    """
    try:
        async with aiofiles.open(file, mode='r', encoding='utf-8') as f:
            data = await f.read()
        return json.loads(data)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {file}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in {file}: {e}")
        return {}


async def write_json_config(file: str, config: Dict[str, Any]) -> None:
    """
    Asynchronously write a dictionary to a JSON file.

    Parameters:
        file (str): The path to the JSON file.
        config (dict): The configuration data to write.
    """
    try:
        async with aiofiles.open(file, 'w', encoding='utf-8') as f:
            # Use json.dumps with indent for readability
            await f.write(json.dumps(config, indent=4))
        logger.info(f"Configuration successfully written to {file}.")
    except Exception as e:
        logger.exception(f"Failed to write JSON config to {file}: {e}")


async def write_csv_file(file: str, data: List[List[Any]]) -> None:
    """
    Asynchronously write a CSV file from a list of rows using proper escaping.

    Parameters:
        file (str): The path to the CSV file.
        data (List[List[Any]]): A list of rows, each row being a list of values.
    """
    try:
        # We'll handle CSV writing in a synchronous function, executed in a thread,
        # to take advantage of Python's built-in csv.writer.
        def write_csv_sync(filepath: str, rows: List[List[Any]]):
            with open(filepath, 'w', encoding='utf-8', newline='') as fp:
                writer = csv.writer(fp)
                writer.writerows(rows)

        await asyncio.to_thread(write_csv_sync, file, data)
        logger.info(f"CSV file successfully written to {file}.")
    except Exception as e:
        logger.exception(f"Failed to write CSV file {file}: {e}")


async def get_highest_dict_key(dictionary: Dict[Any, Any]) -> Optional[Any]:
    """
    Asynchronously retrieve the key in a dictionary whose value is highest.

    Parameters:
        dictionary (dict): The dictionary to evaluate.

    Returns:
        Optional[Any]: The key with the highest value, or None if the dictionary is empty.
    """
    if not dictionary:
        return None
    # Minimal async simulation:
    await asyncio.sleep(0)
    return max(dictionary, key=lambda k: dictionary[k])

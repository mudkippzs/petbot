# ./cogs/events.py
import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from discord import Option
from loguru import logger
from typing import TYPE_CHECKING, Optional
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from main import MoguMoguBot

class EventsCog(commands.Cog):
    """
    Cog for managing temporary events (voice or text) for subs.
    Owners can create event channels that auto-delete after the event ends.
    """

    event_group = SlashCommandGroup("events", "Commands to create and manage events.")    

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self.event_check_loop.start()

    def cog_unload(self):
        self.event_check_loop.cancel()

    async def sub_exists(self, sub_id: int) -> bool:
        """Check if a sub with the given ID exists."""
        row = await self.bot.db.fetchrow("SELECT id FROM subs WHERE id=$1;", sub_id)
        return row is not None

    async def is_owner(self, user_id: int, sub_id: int) -> bool:
        """Check if a user is an owner of a sub."""
        row = await self.bot.db.fetchrow("SELECT 1 FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;", sub_id, user_id)
        return row is not None

    async def get_sub_owners(self, sub_id: int):
        """Get all owners of a sub (user_ids)."""
        rows = await self.bot.db.fetch("SELECT user_id FROM sub_ownership WHERE sub_id=$1;", sub_id)
        return [r["user_id"] for r in rows]

    async def get_event(self, event_id: int):
        """Retrieve an event by its ID."""
        return await self.bot.db.fetchrow("SELECT * FROM events WHERE id=$1;", event_id)

    @tasks.loop(minutes=1)
    async def event_check_loop(self):
        """
        Periodic task to automatically end events whose end_time has passed.
        It deletes the event channel and cleans up the DB record.
        """
        now = datetime.utcnow()
        ended_events = await self.bot.db.fetch("SELECT id, channel_id FROM events WHERE end_time < $1;", now)
        for e in ended_events:
            event_id = e["id"]
            channel_id = e["channel_id"]
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete(reason="Event ended (time expired).")
                except discord.DiscordException as ex:
                    logger.exception(f"Failed to delete event channel {channel_id} for event {event_id}: {ex}")
            await self.bot.db.execute("DELETE FROM events WHERE id=$1;", event_id)
            logger.info(f"Event {event_id} ended automatically (time expired).")

    @event_check_loop.before_loop
    async def before_event_check_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Event auto-end loop started.")

    @event_group.command(name="create", description="Create a new temporary event channel for a sub.")
    async def event_create(self,
                           ctx: discord.ApplicationContext,
                           sub_id: int,
                           type: Option(str, "Type of event: voice or text", choices=["voice", "text"]),
                           duration_minutes: Option(int, "Duration of the event in minutes", default=60)):
        """
        Create a temporary event channel for the specified sub.
        Only an owner can create an event.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if not await self.sub_exists(sub_id):
            await ctx.followup.send("Sub not found.")
            return

        if not await self.is_owner(ctx.author.id, sub_id):
            await ctx.followup.send("Only an owner of this sub can create an event.")
            return

        end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
        owners = await self.get_sub_owners(sub_id)

        # Determine permissions
        # Default: no access for @everyone
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }

        # Give owners elevated perms depending on channel type
        for owner_id in owners:
            member = ctx.guild.get_member(owner_id)
            if member is None:
                logger.warning(f"Owner {owner_id} is not in the guild. Skipping permission assignment.")
                continue

            if type == "voice":
                # Owners: can manage voice channel
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    mute_members=True,
                    deafen_members=True,
                    move_members=True,
                    manage_channels=True
                )
            else:
                # Text channel: owners can manage messages and channel
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True,
                    manage_channels=True
                )

        category_id = self.bot.config.get("event_category_id")  # Optional configuration
        category = ctx.guild.get_channel(category_id) if category_id else None

        # Create the channel
        try:
            if type == "voice":
                channel = await ctx.guild.create_voice_channel(
                    name=f"Sub-{sub_id}-Event",
                    overwrites=overwrites,
                    category=category,
                    reason=f"Created temporary {type} event by {ctx.author.id}"
                )
            else:
                channel = await ctx.guild.create_text_channel(
                    name=f"sub-{sub_id}-event",
                    overwrites=overwrites,
                    category=category,
                    reason=f"Created temporary {type} event by {ctx.author.id}"
                )
        except discord.DiscordException as ex:
            logger.exception(f"Failed to create event channel for sub {sub_id}: {ex}")
            await ctx.followup.send("Failed to create event channel. Please check permissions and try again.")
            return

        # Insert event into DB
        row = await self.bot.db.fetchrow(
            "INSERT INTO events (sub_id, channel_id, end_time) VALUES ($1, $2, $3) RETURNING id;",
            sub_id, channel.id, end_time
        )
        event_id = row["id"]

        await ctx.followup.send(
            f"Event #{event_id} created! Channel: {channel.mention}, will end in {duration_minutes} minutes."
        )
        logger.info(f"Event {event_id} created for sub {sub_id} by {ctx.author.id}, channel {channel.id}, type={type}.")

    @event_group.command(name="end", description="End an ongoing event.")
    async def event_end(self,
                        ctx: discord.ApplicationContext,
                        event_id: int):
        """
        End an ongoing event early. Only an owner of the sub can end the event.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        event = await self.get_event(event_id)
        if not event:
            await ctx.followup.send("Event not found.")
            return

        sub_id = event["sub_id"]
        channel_id = event["channel_id"]
        channel = self.bot.get_channel(channel_id)

        if not await self.is_owner(ctx.author.id, sub_id):
            await ctx.followup.send("Only an owner of the sub can end the event.")
            return

        # Delete channel
        if channel:
            try:
                await channel.delete(reason=f"Event ended by {ctx.author.id}")
            except discord.DiscordException as ex:
                logger.exception(f"Failed to delete event channel {channel_id} for event {event_id}: {ex}")
                await ctx.followup.send("Failed to delete event channel. Please try again later.")
                return

        await self.bot.db.execute("DELETE FROM events WHERE id=$1;", event_id)
        await ctx.followup.send(f"Event #{event_id} ended and channel removed.")
        logger.info(f"Event {event_id} ended by user {ctx.author.id}.")

    @event_group.command(name="info", description="View information about a current event.")
    async def event_info(self,
                         ctx: discord.ApplicationContext,
                         event_id: int):
        """
        View details about an ongoing event.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        event = await self.get_event(event_id)
        if not event:
            await ctx.followup.send("Event not found.")
            return

        sub_id = event["sub_id"]
        channel_id = event["channel_id"]
        end_time = event["end_time"]

        embed = discord.Embed(title=f"Event #{event_id}", color=0x2F3136)
        embed.add_field(name="Sub ID", value=str(sub_id), inline=True)
        embed.add_field(name="Channel ID", value=str(channel_id), inline=True)
        embed.add_field(name="Ends At", value=end_time.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=False)

        await ctx.followup.send(embed=embed)


def setup(bot: "MoguMoguBot"):
    bot.add_cog(EventsCog(bot))

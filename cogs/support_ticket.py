# cogs/support_ticket.py

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from datetime import datetime
from loguru import logger
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from main import MoguMoguBot


class SupportTicketCog(commands.Cog):
    """
    A production-ready support ticket cog.
    Provides commands to:
      - open a ticket channel
      - add participants
      - remove participants
      - close a ticket
    Also listens to on_message to store messages in DB if channel is recognized as a ticket.
    """

    ticket_group = SlashCommandGroup("ticket", "Open and manage support tickets.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    # -----------
    # LISTENER: LOG MESSAGES
    # -----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        If a message is sent in a ticket channel, store it in ticket_messages.
        """
        # Ignore bot or system messages
        if message.author.bot or not message.guild:
            return

        # Check if channel is a recognized ticket channel
        ticket_row = await self.bot.db.fetchrow(
            "SELECT id FROM tickets WHERE channel_id = $1 AND status = 'open';",
            message.channel.id
        )
        if not ticket_row:
            return  # Not a ticket channel or the ticket is closed

        ticket_id = ticket_row["id"]

        # Store the message content & attachments
        attachments_urls = [att.url for att in message.attachments] if message.attachments else []
        try:
            await self.bot.db.execute(
                """
                INSERT INTO ticket_messages (ticket_id, author_id, content, attachments)
                VALUES ($1, $2, $3, $4);
                """,
                ticket_id, message.author.id, message.content, attachments_urls
            )
        except Exception as e:
            logger.exception(f"Failed to record ticket message: {e}")

    # -----------
    # COMMAND: CREATE TICKET
    # -----------
    @ticket_group.command(name="open", description="Open a new support ticket.")
    @commands.has_any_role("Verified Member")
    async def open_ticket(
        self,
        ctx: discord.ApplicationContext,
        reason: Option(str, "Short description of the issue", default="No reason provided")
    ):
        """
        Creates a new text channel for the ticket, restricted to:
          - The user who opened the ticket
          - Staff role (from config)
          - Bot
        Adds an entry to the tickets table, plus the user to ticket_participants.
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        user = ctx.author
        guild = ctx.guild

        # Ticket Category from config
        ticket_category_id = self.bot.config.get("ticket_category_id")
        category = guild.get_channel(ticket_category_id) if ticket_category_id else None

        staff_role_id = self.bot.config.get("staff_role_id")
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None

        # Prepare overwrites: only user, staff, and bot can view
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Create channel
        channel_name = f"ticket-{user.name}-{user.discriminator}"
        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category,
                reason=f"Support ticket opened by {user} ({user.id})."
            )
        except discord.Forbidden:
            await ctx.followup.send("I lack permission to create a ticket channel.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await ctx.followup.send(f"Failed to create ticket channel: {e}", ephemeral=True)
            return

        # Insert into tickets table
        ticket_id = None
        try:
            row = await self.bot.db.fetchrow(
                """
                INSERT INTO tickets (user_id, channel_id, status)
                VALUES ($1, $2, 'open') RETURNING id;
                """,
                user.id, ticket_channel.id
            )
            ticket_id = row["id"]
        except Exception as e:
            await ticket_channel.delete(reason="Failed to record ticket in DB.")
            await ctx.followup.send("Database error creating ticket. Aborting.", ephemeral=True)
            logger.exception(f"Failed to insert ticket row: {e}")
            return

        # Insert user as participant
        try:
            await self.bot.db.execute(
                """
                INSERT INTO ticket_participants (ticket_id, user_id, added_by)
                VALUES ($1, $2, NULL); -- The user created the ticket, so 'added_by' can be NULL or user.id
                """,
                ticket_id, user.id
            )
        except Exception as e:
            logger.exception(f"Failed to insert ticket participant: {e}")
            # Not a fatal error, we can continue. But ideally, revert or handle as needed.

        # Send a message in the new ticket channel
        await ticket_channel.send(
            f"{user.mention}, thank you for opening a ticket.\n"
            f"Reason: **{reason}**\n"
            "Staff will be with you shortly!"
        )

        await ctx.followup.send(f"Your support ticket is created: {ticket_channel.mention}", ephemeral=True)

    # -----------
    # COMMAND: CLOSE TICKET
    # -----------
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    @ticket_group.command(name="close", description="Close a support ticket.")
    async def close_ticket(
        self,
        ctx: discord.ApplicationContext,
        ticket_id: Option(int, "ID of the ticket to close")
    ):
        """
        Closes a ticket by:
          - Checking DB if user is the ticket owner or staff
          - Setting status='closed', closed_at=NOW()
          - Deleting the channel
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        user = ctx.author
        guild = ctx.guild

        # Fetch ticket info
        ticket = await self.bot.db.fetchrow("SELECT * FROM tickets WHERE id=$1;", ticket_id)
        if not ticket:
            await ctx.followup.send("Ticket not found.", ephemeral=True)
            return

        if ticket["status"] == "closed":
            await ctx.followup.send("That ticket is already closed.", ephemeral=True)
            return

        # Check if user is staff or the ticket owner
        staff_role_id = self.bot.config.get("staff_role_id")
        user_is_staff = False
        if isinstance(user, discord.Member) and staff_role_id:
            user_is_staff = any(role.id == staff_role_id for role in user.roles)

        # The user may be staff OR the original ticket opener
        is_ticket_owner = (ticket["user_id"] == user.id)
        if not (user_is_staff or is_ticket_owner):
            await ctx.followup.send("Only staff or the ticket opener can close this ticket.", ephemeral=True)
            return

        # Set status='closed', closed_at=NOW()
        try:
            await self.bot.db.execute(
                "UPDATE tickets SET status='closed', closed_at=NOW() WHERE id=$1;",
                ticket_id
            )
        except Exception as e:
            logger.exception(f"Failed to close ticket {ticket_id}: {e}")
            await ctx.followup.send("Database error closing ticket. Try again later.", ephemeral=True)
            return

        # Delete channel
        ticket_channel_id = ticket["channel_id"]
        channel = guild.get_channel(ticket_channel_id)
        if channel:
            try:
                await channel.delete(reason=f"Ticket #{ticket_id} closed by {user.id}")
            except discord.Forbidden:
                await ctx.followup.send("I do not have permission to delete the ticket channel.", ephemeral=True)
                return
            except discord.HTTPException as e:
                await ctx.followup.send(f"Failed to delete the ticket channel: {e}", ephemeral=True)
                return

        await ctx.followup.send(f"Ticket #{ticket_id} is now closed.", ephemeral=True)

    # -----------
    # COMMAND: ADD USER
    # -----------
    @ticket_group.command(name="add_user", description="Add a user to an existing ticket.")    
    @commands.has_any_role("Verified Member")
    async def add_user_to_ticket(
        self,
        ctx: discord.ApplicationContext,
        ticket_id: Option(int, "ID of the ticket"),
        user: Option(discord.Member, "User to add to the ticket")
    ):
        """
        Adds a user as a participant in the ticket. Grants them channel permissions.
        Only staff or the ticket owner can add participants.
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        actor = ctx.author
        guild = ctx.guild

        ticket = await self.bot.db.fetchrow("SELECT * FROM tickets WHERE id=$1;", ticket_id)
        if not ticket:
            await ctx.followup.send("Ticket not found.", ephemeral=True)
            return
        if ticket["status"] == "closed":
            await ctx.followup.send("Cannot add users to a closed ticket.", ephemeral=True)
            return

        # Check if actor is staff or ticket owner
        staff_role_id = self.bot.config.get("staff_role_id")
        actor_is_staff = False
        if isinstance(actor, discord.Member) and staff_role_id:
            actor_is_staff = any(role.id == staff_role_id for role in actor.roles)
        is_ticket_owner = (ticket["user_id"] == actor.id)

        if not (actor_is_staff or is_ticket_owner):
            await ctx.followup.send("Only staff or the ticket owner can add participants.", ephemeral=True)
            return

        # Insert user into ticket_participants
        try:
            await self.bot.db.execute(
                """
                INSERT INTO ticket_participants (ticket_id, user_id, added_by)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING;
                """,
                ticket_id, user.id, actor.id
            )
        except Exception as e:
            logger.exception(f"Failed to add participant: {e}")
            await ctx.followup.send("Database error adding user to ticket.", ephemeral=True)
            return

        # Update channel permission
        channel_id = ticket["channel_id"]
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.set_permissions(
                    user,
                    view_channel=True,
                    send_messages=True
                )
            except discord.Forbidden:
                await ctx.followup.send("I lack permission to set channel overwrites.", ephemeral=True)
                return
            except discord.HTTPException as e:
                await ctx.followup.send(f"Failed to update channel permissions: {e}", ephemeral=True)
                return

        await ctx.followup.send(
            f"{user.mention} has been added to ticket #{ticket_id}.",
            ephemeral=True
        )

    # -----------
    # COMMAND: REMOVE USER
    # -----------
    @ticket_group.command(name="remove_user", description="Remove a user from an existing ticket.")
    @commands.has_any_role("Verified Member")
    async def remove_user_from_ticket(
        self,
        ctx: discord.ApplicationContext,
        ticket_id: Option(int, "ID of the ticket"),
        user: Option(discord.Member, "User to remove from the ticket")
    ):
        """
        Removes a user from the ticket participants, revokes channel perms.
        Only staff or the ticket owner can remove participants.
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        actor = ctx.author
        guild = ctx.guild

        ticket = await self.bot.db.fetchrow("SELECT * FROM tickets WHERE id=$1;", ticket_id)
        if not ticket:
            await ctx.followup.send("Ticket not found.", ephemeral=True)
            return
        if ticket["status"] == "closed":
            await ctx.followup.send("Cannot remove users from a closed ticket.", ephemeral=True)
            return

        # Check if actor is staff or ticket owner
        staff_role_id = self.bot.config.get("staff_role_id")
        actor_is_staff = False
        if isinstance(actor, discord.Member) and staff_role_id:
            actor_is_staff = any(role.id == staff_role_id for role in actor.roles)
        is_ticket_owner = (ticket["user_id"] == actor.id)

        if not (actor_is_staff or is_ticket_owner):
            await ctx.followup.send("Only staff or the ticket owner can remove participants.", ephemeral=True)
            return

        # Remove from ticket_participants
        try:
            result = await self.bot.db.execute(
                """
                DELETE FROM ticket_participants
                WHERE ticket_id=$1 AND user_id=$2
                """,
                ticket_id, user.id
            )
            # result might be "DELETE 1" if it removed something
        except Exception as e:
            logger.exception(f"Failed to remove participant: {e}")
            await ctx.followup.send("Database error removing user from ticket.", ephemeral=True)
            return

        # Remove channel permission
        channel_id = ticket["channel_id"]
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.set_permissions(user, overwrite=None)  # remove specific overwrites
            except discord.Forbidden:
                await ctx.followup.send("I lack permission to unset channel overwrites.", ephemeral=True)
                return
            except discord.HTTPException as e:
                await ctx.followup.send(f"Failed to update channel permissions: {e}", ephemeral=True)
                return

        await ctx.followup.send(
            f"{user.mention} has been removed from ticket #{ticket_id}.",
            ephemeral=True
        )

    # -----------
    # COMMAND: INFO
    # -----------
    @ticket_group.command(name="info", description="View information about an existing ticket.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def ticket_info(
        self,
        ctx: discord.ApplicationContext,
        ticket_id: Option(int, "ID of the ticket")
    ):
        """
        Shows basic info about a ticket: status, channel, participants, etc.
        """
        await ctx.defer(ephemeral=True)
        if not ctx.guild:
            await ctx.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        ticket = await self.bot.db.fetchrow("SELECT * FROM tickets WHERE id=$1;", ticket_id)
        if not ticket:
            await ctx.followup.send("Ticket not found.", ephemeral=True)
            return

        # Gather participants
        participants = await self.bot.db.fetch(
            "SELECT user_id FROM ticket_participants WHERE ticket_id=$1;",
            ticket_id
        )
        p_list = [f"<@{p['user_id']}>" for p in participants]

        # Build embed
        embed = discord.Embed(
            title=f"Ticket #{ticket_id}",
            description=(
                f"**Status:** {ticket['status']}\n"
                f"**Channel:** <#{ticket['channel_id']}>\n"
                f"**Opened By:** <@{ticket['user_id']}>\n"
                f"**Created At:** {ticket['created_at']}\n"
            ),
            color=discord.Color.blue()
        )
        if ticket["closed_at"]:
            embed.add_field(name="Closed At", value=str(ticket["closed_at"]), inline=False)
        if p_list:
            embed.add_field(name="Participants", value=", ".join(p_list), inline=False)

        await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: "MoguMoguBot"):
    bot.add_cog(SupportTicketCog(bot))

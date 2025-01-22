import discord
from discord.ext import commands, tasks
from loguru import logger
import datetime
from typing import Optional, List

# --------------------------------------
# Constants & Helpers
# --------------------------------------

VERIFICATION_LOG_CHANNEL_ID = 1331573988584853524  # The channel for verification logs
STAFF_ROLE_NAMES = ["Owner", "Underboss", "The Company", "Consigliere"] 
# or use IDs from your config, e.g. staff_roles = [12345, 67890, ...]

YELLOW = 0xFFFF00
GREEN = 0x00FF00
RED = 0xFF0000

# In-memory store for active verification approvals:
# Maps verification_request_id -> set of staff_user_ids that have clicked Approve
verification_approvals = {}

# --------------------------------------
# The Cog
# --------------------------------------

class SupportTicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.support_channel_id = bot.config.get("support_channel_id")  # 'contact-the-boss' channel
        self.verification_channel_id = bot.config.get("verification_channel_id", VERIFICATION_LOG_CHANNEL_ID)
        self.staff_roles = bot.config.get("staff_roles", STAFF_ROLE_NAMES)
        self.transcripts_enabled = bot.config.get("transcripts_enabled", True)
        self.inactivity_limit = bot.config.get("inactivity_limit", 48)
        self.kick_on_rejection = bot.config.get("kick_on_rejection", False)  # from config.json
        self.ticket_cleanup_loop.start()

    @tasks.loop(hours=1)
    async def ticket_cleanup_loop(self):
        """Automatically closes inactive tickets in the support channel (if used for standard tickets)."""
        if not self.support_channel_id:
            return

        support_channel = self.bot.get_channel(self.support_channel_id)
        if not support_channel:
            return

        now = datetime.datetime.utcnow()
        async for thread in support_channel.threads:
            if thread.archived:
                continue
            last_message = await thread.fetch_message(thread.last_message_id)
            if not last_message:
                continue
            last_activity = last_message.created_at
            inactivity_duration = (now - last_activity).total_seconds() / 3600
            if inactivity_duration >= self.inactivity_limit:
                await self.close_ticket(thread, "closed due to inactivity")

    async def close_ticket(self, thread: discord.Thread, reason: str):
        """Closes a ticket thread and optionally sends a transcript (for support tickets)."""
        await thread.edit(archived=True, locked=True)
        if self.transcripts_enabled:
            transcript = await self.generate_transcript(thread)
            # If it's a normal "ticket-" thread, fetch from tickets table
            if thread.name.startswith("ticket-"):
                ticket_id = int(thread.name.split("-")[-1])
                opener = await self.bot.db.fetchval(
                    "SELECT user_id FROM tickets WHERE id = $1", ticket_id
                )
                if opener:
                    opener_user = self.bot.get_user(opener) or await self.bot.fetch_user(opener)
                    if opener_user:
                        try:
                            await opener_user.send(
                                f"Your ticket '{thread.name}' was {reason}. Here is the transcript:",
                                file=discord.File(transcript, filename=f"{thread.name}_transcript.txt")
                            )
                        except discord.Forbidden:
                            pass

                await self.bot.db.execute(
                    "UPDATE tickets SET status = $1, closed_at = NOW() WHERE id = $2",
                    "closed",
                    ticket_id
                )

    async def generate_transcript(self, thread: discord.Thread) -> str:
        """Generates a transcript for a thread."""
        messages = []
        async for msg in thread.history(limit=None, oldest_first=True):
            messages.append(msg)
        transcript = "\n".join(
            f"[{msg.created_at:%Y-%m-%d %H:%M:%S}] {msg.author}: {msg.clean_content or '[Attachment]'}"
            for msg in messages
        )
        return transcript

    @commands.Cog.listener()
    async def on_ready(self):
        """Set up the support splash in #contact-the-boss channel."""
        if not self.support_channel_id:
            return

        support_channel = self.bot.get_channel(self.support_channel_id)
        if not support_channel:
            return

        view = SplashContactView(bot=self.bot)
        self.bot.add_view(view)  # Make the view persistent across restarts

        embed = self.build_support_embed()
        async for msg in support_channel.history(limit=50):
            if (msg.author == self.bot.user) and ("Support Instructions" in msg.content or "Support System" in msg.content):
                await msg.edit(
                    content="Support Instructions",
                    embed=embed,
                    view=view
                )
                break
        else:
            await support_channel.send(
                content="Support Instructions",
                embed=embed,
                view=view
            )


        # Attempt to reattach views for any pending verification requests
        await self.reattach_pending_verification_views()

    async def reattach_pending_verification_views(self):
        """
        Called in on_ready to reattach the view for all pending verification logs.
        Also rehydrate partial approvals so the Approve button says (1/2) if needed.
        """
        records = await self.bot.db.fetch(
            """
            SELECT id, user_id, log_message_id
              FROM verification_requests
             WHERE status = 'pending'
               AND log_message_id IS NOT NULL
            """
        )

        for row in records:
            verification_id = row["id"]
            user_id = row["user_id"]
            message_id = row["log_message_id"]

            # Fetch the user object
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

            # Create the view
            view = VerificationLogView(
                cog=self,
                verification_id=verification_id,
                user=user
            )

            # Here we re-check how many staff have already approved
            approved_count = await self.bot.db.fetchval(
                """
                SELECT COUNT(*) FROM verification_approvals
                 WHERE verification_id = $1
                """,
                verification_id
            )

            # Adjust the Approve button label & emoji based on that count
            # The Approve button is the second item in the view's children by default, but
            # search by type or custom_id to be sure:
            approve_button = None
            for child in view.children:
                if isinstance(child, discord.ui.Button) and "Approve" in child.label:
                    approve_button = child
                    break

            if approve_button:
                if approved_count == 1:
                    approve_button.label = "Approve (1/2)"
                    approve_button.emoji = "1️⃣"
                elif approved_count >= 2:
                    # It's already fully approved, or beyond
                    # Typically we wouldn't even attach a live view if it's done,
                    # but if you'd like to display it, you can disable the buttons:
                    approve_button.label = "Approve (2/2)"
                    approve_button.emoji = "2️⃣"
                    for child in view.children:
                        child.disabled = True

            # Finally, attach the view to the original message
            self.bot.add_view(view, message_id=message_id)

            # Optional: fetch the message and forcibly re-edit it with the updated label
            # so the new label is visible. Some older clients need a forced re-edit:
            verif_log_channel = self.bot.get_channel(self.verification_channel_id)
            if verif_log_channel:
                try:
                    msg = await verif_log_channel.fetch_message(message_id)
                    await msg.edit(view=view)
                except:
                    pass


    def build_support_embed(self) -> discord.Embed:
        """Builds the support splash embed."""
        return discord.Embed(
            title="Support & Verification System",
            description="Click 'Contact Staff' to open an ephemeral menu for support or verification.",
            color=discord.Color.blurple(),
        )

    # ----------------------------------------------------------------------
    #  Creating a Verification Ticket & Logging in Verification Channel
    # ----------------------------------------------------------------------

    async def create_verification_thread(
        self,
        user: discord.Member,
        q1: str,
        q2: str,
        q3: str,
        image_link: str
    ):
        """
        Creates a private thread for verification, logs details to the DB (without the image_link),
        and sends an embed to the verification logs channel with staff mention + 'Assign/Approve/Reject' buttons.
        """

        # 1) Insert into DB (storing only Q1-Q3, not image URL)
        verification_id = await self.bot.db.fetchval(
            """
            INSERT INTO verification_requests (user_id, q1, q2, q3)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            user.id, q1, q2, q3
        )

        # 2) Create a private thread in #contact-the-boss channel
        channel = self.bot.get_channel(self.support_channel_id)
        if not channel:
            logger.error("Cannot find the support (contact-the-boss) channel.")
            return None

        thread_name = f"verification-{user.display_name}-#{verification_id}"
        thread = await channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread
        )
        await thread.add_user(user)

        # 3) Post the user’s answers in the private thread
        #    (including the image link so staff can see it, but we do NOT store it in DB).
        await thread.send(
            content=(
                f"**Verification Request from {user.mention}**\n\n"
                f"**Q1:** {q1}\n"
                f"**Q2:** {q2}\n"
                f"**Q3:** {q3}\n"
                f"**Image:** {image_link}"
            )
        )

        # 4) Send an embed + Staff mention in the Verification Logs channel
        verif_log_channel = self.bot.get_channel(self.verification_channel_id)
        if not verif_log_channel:
            logger.warning("Cannot find the verification logs channel.")
            return thread

        # Mention all staff roles. This can be done by constructing a string of pings.
        # If your staff roles are IDs, you'll do f"<@&{role_id}>" for each.
        role_mentions = []
        guild = user.guild
        for role_name_or_id in self.staff_roles:
            role = None
            if isinstance(role_name_or_id, int):
                role = guild.get_role(role_name_or_id)
            else:
                role = discord.utils.get(guild.roles, name=role_name_or_id)
            if role:
                role_mentions.append(role.mention)

        staff_mention_str = " ".join(role_mentions) if role_mentions else ""        

        embed = discord.Embed(
            title=f"New Verification #{verification_id} - {user}",
            description=(
                f"{staff_mention_str}\n\n"
                f"**User:** {user.mention}\n"
                f"**Thread:** [Jump to Thread]({thread.jump_url})\n"
                f"**Status:** Pending"
            ),
            color=YELLOW,
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"User ID: {user.id} | Verification ID: {verification_id}")

        view = VerificationLogView(
            cog=self,
            verification_id=verification_id,
            user=user
        )
        msg = await verif_log_channel.send(
            content=staff_mention_str,  # mention staff if desired
            embed=embed,
            view=view
        )

        # Store this message ID in the database so we can reattach after a restart
        await self.bot.db.execute(
            """
            UPDATE verification_requests
               SET log_message_id = $1
             WHERE id = $2
            """,
            msg.id,
            verification_id
        )

        return thread

    # Called when both staff approvals are reached:
    async def handle_verification_approved(self, verification_id: int, user: discord.Member):
        """
        Mark verification as approved in DB, add 'Verified' role, delete the private thread, 
        and update the embed color to GREEN in verification logs.
        """
        # 1) Update DB
        await self.bot.db.execute(
            """
            UPDATE verification_requests
               SET status = 'approved',
                   updated_at = NOW()
             WHERE id = $1
            """,
            verification_id
        )

        # 2) Add "Verified" role
        # Convert User -> Member
        # If the member is not cached, fetch_member will do an API call:
        guild_id = self.bot.config["guild_id"]  # Replace with your guild's ID
        guild = self.bot.get_guild(guild_id)
        if not guild:
            # Could not find the guild in cache, can't add a role
            return
        member = guild.get_member(user.id)
        if not member:
            try:
                member = await guild.fetch_member(user.id)
            except discord.NotFound:
                # The user might have left the guild
                return

        logger.debug(f"[DEBUG] {member.display_name} has been veriried - attempting to get verification role and add it to the user.")
        # Now add the role
        verified_role = discord.utils.get(guild.roles, name="Verified")
        unverified_role = discord.utils.get(guild.roles, name="Unverified")
        if verified_role:
            await member.add_roles(verified_role, reason="User verified")
            await member.remove_roles(unverified_role, reason="User verified")
            logger.debug(f"[DEBUG] Added {verified_role.name} to {member.display_name}, removed {unverified_role}")

        # 3) Attempt to find the private thread (by name) and delete it
        #    so the user’s image link is scrubbed.
        private_thread_name = f"verification-{user.display_name}-#{verification_id}"
        contact_channel = self.bot.get_channel(self.support_channel_id)
        if contact_channel and isinstance(contact_channel, discord.TextChannel):
            thread_to_delete = discord.utils.get(contact_channel.threads, name=private_thread_name)
            if thread_to_delete:
                await thread_to_delete.delete()

        # 4) Update the embed color in the verification logs to green
        #    This requires that we kept track of the original message ID, or we search for it.
        verif_log_channel = self.bot.get_channel(self.verification_channel_id)
        if not verif_log_channel:
            return

        # If you kept the last log message ID in the DB or a dictionary,
        # you can fetch and edit it directly. For example:
        #   msg = await verif_log_channel.fetch_message(log_message_id)
        #   ...
        # For brevity, let's do a simple search for demonstration:
        async for message in verif_log_channel.history(limit=200):
            if message.author == self.bot.user and message.embeds:
                emb = message.embeds[0]
                if emb.footer and f"Verification ID: {verification_id}" in str(emb.footer.text):
                    # Found the correct embed
                    embed = emb
                    embed.color = GREEN
                    embed.description = embed.description.replace("**Status:** Pending", "**Status:** Approved")
                    await message.edit(embed=embed, view=None)  # Remove buttons or set view=None
                    break

    async def handle_verification_rejected(self, verification_id: int, user: discord.Member, reason: str):
        """
        Mark verification as rejected in DB, DM the user, optionally kick them, 
        and update the embed color to RED in verification logs.
        """
        # 1) Update DB
        await self.bot.db.execute(
            """
            UPDATE verification_requests
               SET status = 'rejected',
                   updated_at = NOW()
             WHERE id = $1
            """,
            verification_id
        )

        # 2) DM the user with the reason
        try:
            await user.send(f"Your verification request was rejected.\nReason: {reason}")
        except discord.Forbidden:
            pass

        # 3) Optionally kick the user
        if self.kick_on_rejection:
            try:
                await user.kick(reason=reason)
            except discord.Forbidden:
                logger.warning(f"Failed to kick {user} due to insufficient permissions.")

            # Also log the kick in moderation_logs table:
            moderator_id = self.bot.user.id  # or whoever triggered the final rejection
            await self.bot.db.execute(
                """
                INSERT INTO moderation_logs (moderator_id, user_id, action, reason)
                VALUES ($1, $2, 'kick', $3)
                """,
                moderator_id, user.id, reason
            )

        # 4) Delete the private verification thread
        private_thread_name = f"verification-{user.display_name}-#{verification_id}"
        contact_channel = self.bot.get_channel(self.support_channel_id)
        if contact_channel and isinstance(contact_channel, discord.TextChannel):
            thread_to_delete = discord.utils.get(contact_channel.threads, name=private_thread_name)
            if thread_to_delete:
                await thread_to_delete.delete()
        # 5) Update the embed color in the verification logs to red & show justification
        verif_log_channel = self.bot.get_channel(self.verification_channel_id)
        if not verif_log_channel:
            return

        async for message in verif_log_channel.history(limit=200):
            if message.author == self.bot.user and message.embeds:
                emb = message.embeds[0]
                if emb.footer and f"Verification ID: {verification_id}" in str(emb.footer.text):
                    embed = emb
                    embed.color = RED
                    embed.description = embed.description.replace("**Status:** Pending", "**Status:** Rejected")
                    # Append the reason
                    embed.description += f"\n**Rejection Reason:** {reason}"
                    await message.edit(embed=embed, view=None)
                    break


# --------------------------------------
# Views & Modals
# --------------------------------------

class SplashContactView(discord.ui.View):
    """Splash view with a single 'Contact Staff' button."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Contact Staff", style=discord.ButtonStyle.primary, custom_id="contact_staff")
    async def contact_staff(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Shows an ephemeral view with support and verification options."""
        is_verified = discord.utils.get(interaction.user.roles, name="Verified")
        view = EphemeralSupportView(bot=self.bot, show_verification=not is_verified)
        await interaction.response.send_message("Select an option below:", view=view, ephemeral=True, delete_after=300.0)


class EphemeralSupportView(discord.ui.View):
    """Ephemeral view for support and verification options."""

    def __init__(self, bot: commands.Bot, show_verification: bool):
        super().__init__(timeout=None)
        self.bot = bot
        self.show_verification = show_verification
        # Support always visible
        self.add_item(SupportButton(bot))
        # Verification only if user is NOT verified
        if self.show_verification:
            self.add_item(VerificationButton(bot))


class SupportButton(discord.ui.Button):
    """Button to initiate support."""

    def __init__(self, bot: commands.Bot):
        super().__init__(
            label="Get Support", 
            style=discord.ButtonStyle.primary, 
            custom_id="get_support"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        """Opens the support ticket modal."""
        modal = SupportTicketModal(self.bot)
        await interaction.response.send_modal(modal)


class VerificationButton(discord.ui.Button):
    """Button to initiate verification."""

    def __init__(self, bot: commands.Bot):
        super().__init__(
            label="Get Verified", 
            style=discord.ButtonStyle.success, 
            custom_id="get_verified"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        """Opens the verification modal."""
        modal = VerificationModal(self.bot)
        await interaction.response.send_modal(modal)


# --------------------------
#   Support Ticket Modal
# --------------------------

class SupportTicketModal(discord.ui.Modal):
    """Modal for creating a support ticket."""

    def __init__(self, bot: commands.Bot):
        super().__init__(title="Create Support Ticket")
        self.bot = bot

        self.issue_description = discord.ui.InputText(
            label="Issue Description",
            style=discord.InputTextStyle.long,
            placeholder="Describe the issue you're facing.",
            required=True
        )
        self.attachments = discord.ui.InputText(
            label="Attachment Links",
            style=discord.InputTextStyle.long,
            placeholder="Provide links to attachments, if any.",
            required=False
        )

        self.add_item(self.issue_description)
        self.add_item(self.attachments)

    async def callback(self, interaction: discord.Interaction):
        """Creates a support thread after modal submission."""
        support_channel = self.bot.get_channel(self.bot.config["support_channel_id"])
        if not support_channel:
            return await interaction.response.send_message(
                "Support channel is not configured. Please contact an admin.", ephemeral=True, delete_after=30.0
            )

        # Insert the ticket into the database
        ticket_id = await self.bot.db.fetchval(
            "INSERT INTO tickets (user_id, channel_id) VALUES ($1, $2) RETURNING id",
            interaction.user.id,
            support_channel.id
        )

        thread_name = f"ticket-{interaction.user.display_name}-#{ticket_id}"
        thread = await support_channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread
        )
        await thread.add_user(interaction.user)

        # Add the opener as a participant
        await self.bot.db.execute(
            "INSERT INTO ticket_participants (ticket_id, user_id) VALUES ($1, $2)",
            ticket_id,
            interaction.user.id
        )

        await thread.send(
            content=(
                f"**Ticket #{ticket_id} Opened by {interaction.user.mention}**\n\n"
                f"**Issue Description:** {self.issue_description.value}\n"
                f"**Attachments:** {self.attachments.value if self.attachments.value else 'None'}"
            )
        )

        await interaction.response.send_message(
            f"Your ticket has been created: {thread.mention}. Staff will assist you soon.",
            ephemeral=True,
            delete_after=30.0
        )


# --------------------------
#   Verification Modal
# --------------------------

class VerificationModal(discord.ui.Modal):
    """Modal for submitting verification details."""

    def __init__(self, bot: commands.Bot):
        super().__init__(title="Verification Process")
        self.bot = bot

        self.q1 = discord.ui.InputText(
            label="Question 1",
            style=discord.InputTextStyle.short,
            placeholder="Answer the first question.",
            required=True
        )
        self.q2 = discord.ui.InputText(
            label="Question 2",
            style=discord.InputTextStyle.short,
            placeholder="Answer the second question.",
            required=True
        )
        self.q3 = discord.ui.InputText(
            label="Question 3",
            style=discord.InputTextStyle.short,
            placeholder="Answer the third question.",
            required=True
        )
        self.image_instructions = discord.ui.InputText(
            label="Image Attachment Link",
            style=discord.InputTextStyle.long,
            placeholder="Provide a link to your image as instructed.",
            required=True
        )

        self.add_item(self.q1)
        self.add_item(self.q2)
        self.add_item(self.q3)
        self.add_item(self.image_instructions)

    async def callback(self, interaction: discord.Interaction):
        """Creates a verification thread and logs it."""
        cog: SupportTicketCog = self.bot.get_cog("SupportTicketCog")
        if not cog:
            return await interaction.response.send_message(
                "Verification system is not available right now.", ephemeral=True, delete_after=30.0
            )

        thread = await cog.create_verification_thread(
            user=interaction.user,
            q1=self.q1.value,
            q2=self.q2.value,
            q3=self.q3.value,
            image_link=self.image_instructions.value
        )

        if thread:
            await interaction.response.send_message(
                f"Your verification ticket has been created: {thread.mention}. Staff will be with you shortly.",
                ephemeral=True,
                delete_after=30.0
            )
        else:
            await interaction.response.send_message(
                "Could not create your verification ticket. Please contact staff.",
                ephemeral=True,
                delete_after=30.0
            )


# -----------------------------
#   Verification Log View
# -----------------------------

class VerificationLogView(discord.ui.View):
    """
    A view displayed in the Verification Logs channel, containing:
    - An "Assign" button
    - An "Approve" button (two-staff needed)
    - A "Reject" button (modal for reason)
    """

    def __init__(self, cog: SupportTicketCog, verification_id: int, user: discord.Member):
        super().__init__(timeout=None)
        self.cog = cog
        self.bot = cog.bot
        self.verification_id = verification_id
        self.user = user
        self.assignee: Optional[discord.Member] = None
        self.assigned_at: Optional[datetime.datetime] = None

        # Initialize or reset the in-memory approvals set
        verification_approvals[verification_id] = set()

    @discord.ui.button(label="Assign", custom_id="verification-logs-approval-button-assign", style=discord.ButtonStyle.secondary)
    async def assign_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        The first staff member to click becomes the assignee; subsequent clicks reassign.
        Updates the embed fields to show current assignee and assigned timestamp.
        """
        # Check staff roles
        if not await self.user_is_staff(interaction.user):
            return await interaction.response.send_message(
                "You do not have permission to assign this ticket.", ephemeral=True, delete_after=30.0
            )

        self.assignee = interaction.user
        self.assigned_at = datetime.datetime.utcnow()

        # Update embed to reflect the new assignee
        await self.update_log_embed(interaction=interaction)

        await interaction.response.send_message(
            f"You have assigned this verification ticket to yourself.",
            ephemeral=True,
            delete_after=30.0
        )

    @discord.ui.button(label="Approve (0/2)", custom_id="verification-logs-approval-button-approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        The Approve button requires two distinct staff members to click it.
        First distinct staff -> label becomes (1/2).
        Second distinct staff -> finalize approval.
        """
        if not await self.user_is_staff(interaction.user):
            return await interaction.response.send_message(
                "You do not have permission to approve this verification.", ephemeral=True, delete_after=30.0
            )

        # Check if they have already approved in the DB
        row = await self.bot.db.fetchrow(
            """
            SELECT 1 FROM verification_approvals
             WHERE verification_id = $1
               AND staff_id = $2
            """,
            self.verification_id,
            interaction.user.id
        )
        if row:
            return await interaction.response.send_message(
                "You have already approved this request.", ephemeral=True, delete_after=30.0
            )

        # Insert the new approval
        await self.bot.db.execute(
            """
            INSERT INTO verification_approvals (verification_id, staff_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            self.verification_id,
            interaction.user.id
        )

        # Count how many distinct staff members have approved so far
        count = await self.bot.db.fetchval(
            """
            SELECT COUNT(*) FROM verification_approvals
             WHERE verification_id = $1
            """,
            self.verification_id
        )

        if count == 1:
            self.approve_button.label = "Approve (1/2)"
            self.approve_button.emoji = "1️⃣"
            await self.update_log_embed(interaction=interaction, show_status=False)
            await interaction.response.send_message(
                "First approval recorded. Awaiting one more approval.",
                ephemeral=True,
                delete_after=30.0
            )

        elif count == 2:
            # Final approval
            self.approve_button.label = "Approve (2/2)"
            self.approve_button.emoji = "2️⃣"
            await self.update_log_embed(interaction=interaction, show_status=False)

            # Call handle_verification_approved to finalize
            await self.cog.handle_verification_approved(
                verification_id=self.verification_id,
                user=self.user
            )

            # Remove or disable all buttons
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)

            await interaction.response.send_message(
                "Verification approved! The user has been verified and the thread is deleted.",
                ephemeral=True,
                delete_after=30.0
            )

        else:
            # If you allow more than 2 staff approvals, handle it. Otherwise, do something like:
            await interaction.response.send_message(
                f"Already {count} approvals reached. This is unexpected.",
                ephemeral=True,
                delete_after=30.0
            )

    @discord.ui.button(label="Reject", custom_id="verification-logs-approval-button-reject", style=discord.ButtonStyle.danger)
    async def reject_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Shows a modal that requests a rejection reason.
        After submission, handle_verification_rejected is called.
        """
        if not await self.user_is_staff(interaction.user):
            return await interaction.response.send_message(
                "You do not have permission to reject this verification.", ephemeral=True, delete_after=30.0
            )

        # Show a modal to gather the reason
        await interaction.response.send_modal(VerificationRejectionModal(self))

    async def user_is_staff(self, member: discord.Member) -> bool:
        """Check if the user has any of the staff roles from the cog config."""
        for role_name_or_id in self.cog.staff_roles:
            role = None
            if isinstance(role_name_or_id, int):
                role = member.guild.get_role(role_name_or_id)
            else:
                role = discord.utils.get(member.roles, name=role_name_or_id)

            if role in member.roles:
                return True
        return False

    async def update_log_embed(self, interaction: discord.Interaction, show_status: bool = True):
        """
        Finds the embed in the current message, updates the "Assignee" field
        and (optionally) the status line in the description, or label on Approve button.
        """
        message = interaction.message
        if not message or not message.embeds:
            return

        embed = message.embeds[0]
        fields = embed.fields
        # We'll remove existing "Assignee" field if it exists
        new_fields = []
        for f in fields:
            if f.name.lower() != "assignee":
                new_fields.append(f)

        assignee_field_value = "None"
        if self.assignee:
            dt_str = self.assigned_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            assignee_field_value = f"{self.assignee.mention} (Assigned at {dt_str})"

        new_fields.append(discord.EmbedField(name="Assignee", value=assignee_field_value, inline=False))

        embed._fields = new_fields  # monkey-patch fields in place

        # Optionally also update the description or color. Example: keep it yellow until final outcome
        # embed.color = YELLOW

        await message.edit(embed=embed, view=self)


# -----------------------------
#  Rejection Modal
# -----------------------------

class VerificationRejectionModal(discord.ui.Modal):
    """A modal that prompts for the reason for rejecting a verification request."""

    def __init__(self, parent_view: VerificationLogView):
        super().__init__(title="Reject Verification")
        self.parent_view = parent_view

        self.reason_input = discord.ui.InputText(
            label="Reason for Rejection",
            style=discord.InputTextStyle.long,
            placeholder="Explain why you are rejecting this verification.",
            required=True
        )
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        # final rejection
        reason = self.reason_input.value.strip()
        await self.parent_view.cog.handle_verification_rejected(
            verification_id=self.parent_view.verification_id,
            user=self.parent_view.user,
            reason=reason
        )

        # Disable the parent view buttons
        for child in self.parent_view.children:
            child.disabled = True
        await interaction.message.edit(view=self.parent_view)

        await interaction.response.send_message(
            "Verification rejected and the user has been notified.",
            ephemeral=True,
            delete_after=30.0
        )


# -----------------------------
#   Setup
# -----------------------------
def setup(bot: commands.Bot):
    bot.add_cog(SupportTicketCog(bot))

import discord
import datetime
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup, Option
from loguru import logger
from typing import Optional, TYPE_CHECKING, Union
import asyncio
import time
import hashlib
import datetime

# Import *only* the UI classes from your second file
from ownership_views import (
    OwnershipClaimStaffView,
    OwnershipClaimSubView,
    SingleUserOwnershipView,
    OwnershipBrowserView,
    PartialClaimModal,
    DirectClaimModal,
    TransactModal,
    AskForDMApprovalView
)

if TYPE_CHECKING:
    from main import MoguMoguBot


class OwnershipCog(commands.Cog):
    """
    Main logic and commands for the Ownership system.

    This cog handles creation and finalization of claims, ownership transfers,
    DM permission requests, and more. It uses interactive views that are recorded
    in the database with an expiration time so that, for example, DM–based messages
    remain reconnectable on bot restart (with the remaining timeout).
    """

    ownership_group = SlashCommandGroup("ownership", "Manage sub ownership.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

        # Roles
        self.owner_role_id = bot.config["owner_role_id"]
        self.sub_role_id = bot.config["sub_role_id"]

        # Channels
        self.staff_ledger_channel_id = bot.config["staff_channel_ownership_id"]
        self.ask_to_dm_channel_id = bot.config["ask_to_dm_channel_id"]
        self.blockchain_channel_id = bot.config["blockchain_transaction_channel_id"]

        # Times/cooldowns
        self.membership_minimum_secs = bot.config.get("membership_minimum_seconds", 86400)
        self.mag_react_cooldown = bot.config.get("mag_react_cooldown", 60)
        self.dm_request_cooldown = bot.config.get("dm_request_cooldown", 60)

        # Partial-claim settings
        self.claim_expiry_hours = 24
        self.require_staff_approval = bot.config.get("ownership_require_staff_approval", False)
        self.cooldown_days = bot.config.get("ownership_cooldown_days", 7)
        self.rejected_claim_cooldown_hours = 24

        self._reattached = False
        self.mag_react_cooldowns = {}  # In-memory reaction cooldowns (resets on bot restart)
        self.dm_request_cooldowns = {}  # In-memory DM request cooldowns

        # Start tasks
        self.expiry_loop.start()

    # ------------------------------------------------------------------
    # on_ready reattachment of legacy and DM-based views
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        """
        Reattach legacy and DM-based interactive views on bot startup.
        This ensures that views which have not yet timed out (for example,
        DM-based messages that should exist for 10 minutes) are reattached
        with the correct remaining timeout even after a bot crash or restart.
        """
        if self._reattached:
            return
        self._reattached = True

        # === Reattach legacy claim views (staff/sub) ===
        pending_claims = await self.bot.db.fetch(
            "SELECT id, staff_msg_id, sub_msg_id FROM claims WHERE status='pending';"
        )
        for row in pending_claims:
            claim_id = row["id"]
            staff_msg_id = row["staff_msg_id"]
            sub_msg_id = row["sub_msg_id"]
            if staff_msg_id:
                staff_view = OwnershipClaimStaffView(bot=self.bot, claim_id=claim_id, timeout=None)
                self.bot.add_view(staff_view, message_id=staff_msg_id)
                logger.debug(f"Reattached OwnershipClaimStaffView to message: {staff_msg_id}")
            if sub_msg_id:
                sub_view = OwnershipClaimSubView(bot=self.bot, claim_id=claim_id, timeout=None)
                self.bot.add_view(sub_view, message_id=sub_msg_id)
                logger.debug(f"Reattached OwnershipClaimSubView to message: {sub_msg_id}")

        # === Reattach DM-based views (e.g. SingleUserOwnershipView) ===
        # These messages are stored in the database along with an "expires_at" timestamp.
        # On restart, calculate the remaining lifetime and reattach the view if still valid.
        dm_rows = await self.bot.db.fetch(
            """
            SELECT message_id, user_id, target_user_id, expires_at 
            FROM dm_ownership_views 
            WHERE active=TRUE;
            """
        )
        now = datetime.datetime.utcnow()
        for r in dm_rows:
            msg_id = r["message_id"]
            target_user = self.bot.get_user(r["target_user_id"])
            if not target_user:
                continue
            expires_at = r["expires_at"]
            remaining = (expires_at - now).total_seconds()
            if remaining <= 0:
                continue  # Skip views that have already expired.
            # Create the view with the remaining timeout.
            view = SingleUserOwnershipView(bot=self.bot, target_user=target_user, timeout=remaining, message_id=msg_id)
            self.bot.add_view(view, message_id=msg_id)
            logger.debug(f"Reattached SingleUserOwnershipView for message {msg_id} with {remaining:.1f} seconds remaining.")

    # ------------------------------------------------------------------
    # Reaction-based "🔍" -> DM (User Browser Trigger)
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Trigger a DM-based user browser when a user reacts with the magnifying glass emoji.
        Also ensures that a cooldown is applied to prevent spam.
        """
        if str(payload.emoji) != "🔍":
            return
        if payload.user_id == self.bot.user.id:
            return

        now = time.time()
        last_used = self.mag_react_cooldowns.get(payload.user_id, 0)
        if now - last_used < self.mag_react_cooldown:
            return
        self.mag_react_cooldowns[payload.user_id] = now

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member:
            return

        # Only verified users with accepted rules may browse.
        role_names = [r.name for r in member.roles]
        if "Unverified" in role_names or "Rules Accepted" not in role_names:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # Remove the reaction immediately.
        await message.remove_reaction(emoji=payload.emoji, member=member)

        # Ignore messages from bots.
        if message.author.bot:
            return

        target_user = message.author

        # Query details for the user browser.
        query = """
        SELECT 
            w.balance AS wallet_balance,
            u.age_range,
            u.gender_role,
            u.relationship,
            u.location,
            u.orientation,
            u.dm_status,
            array_to_string(u.here_for, ', ') AS here_for,
            array_to_string(u.kinks, ', ') AS kinks,
            CASE 
                WHEN dm_perms.user2_id IS NOT NULL THEN 'Yes'
                ELSE 'No'
            END AS has_dm_permission,
            array_agg(o.user_id) AS owners
        FROM wallets w
        LEFT JOIN user_roles u ON w.user_id = u.user_id
        LEFT JOIN open_dm_perms dm_perms 
            ON (dm_perms.user1_id = $1 AND dm_perms.user2_id = $2)
            OR (dm_perms.user1_id = $2 AND dm_perms.user2_id = $1)
        LEFT JOIN sub_ownership o ON o.sub_id = w.user_id
        WHERE w.user_id = $2
        GROUP BY w.user_id, u.user_id, dm_perms.user2_id;
        """

        record = await self.bot.db.fetchrow(query, member.id, target_user.id)
        if not record:
            return

        # Convert owner IDs into display names.
        owners_list = record["owners"] or []
        owner_names = []
        for owner_id in owners_list:
            owner_member = guild.get_member(owner_id)
            if owner_member:
                owner_names.append(owner_member.display_name)
            else:
                owner_names.append(str(owner_id))
        owners_str = ", ".join(owner_names) if owner_names else "None"

        wallet_balance = record["wallet_balance"] or 0
        dm_status = record["dm_status"] or "Unknown"
        has_dm_permission = record["has_dm_permission"] or "No"

        details_value = (
            f"**Age:** *{record['age_range'] or 'Unknown'}*\n"
            f"**Gender:** *{record['gender_role'] or 'Unknown'}*\n"
            f"**Relationship:** *{record['relationship'] or 'Unknown'}*\n"
            f"**Location:** *{record['location'] or 'Unknown'}*\n"
            f"**Orientation:** *{record['orientation'] or 'Unknown'}*\n"
            f"**Here For:** *{record['here_for'] or 'Unknown'}*\n"
            f"**Kinks:** *{record['kinks'] or 'Unknown'}*\n"
        )

        try:
            dm = await member.create_dm()
        except discord.Forbidden:
            return

        embed = discord.Embed(
            title=f"User Browser: {target_user.display_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Details", value=details_value, inline=False)
        embed.add_field(name="DMs", value=f"```{dm_status}```", inline=True)
        embed.add_field(name="DMs with you?", value=f"```{has_dm_permission}```", inline=True)
        embed.add_field(name="Owner(s)", value=f"```{owners_str}```", inline=False)
        embed.add_field(name="Wallet Balance", value=f"```${wallet_balance}```", inline=True)
        embed.set_thumbnail(url=target_user.display_avatar)

        # Create a SingleUserOwnershipView with a 10-minute lifetime.
        view = SingleUserOwnershipView(bot=self.bot, target_user=target_user, timeout=600)
        dm_msg = await dm.send(embed=embed, view=view)

        # Record the DM view along with its expiration time (10 minutes from now)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        await self.bot.db.execute(
            """
            INSERT INTO dm_ownership_views (message_id, user_id, target_user_id, active, expires_at)
            VALUES ($1, $2, $3, TRUE, $4)
            ON CONFLICT (message_id) DO UPDATE SET active=TRUE, expires_at=$4;
            """,
            dm_msg.id, member.id, target_user.id, expires_at
        )

    # ------------------------------------------------------------------
    # 24-hour Expiry Loop for Claims
    # ------------------------------------------------------------------
    @tasks.loop(minutes=15)
    async def expiry_loop(self):
        """
        Periodically checks for claims that have expired and auto-expires them.
        """
        now = datetime.datetime.utcnow()
        rows = await self.bot.db.fetch(
            """
            SELECT id FROM claims
            WHERE status IN ('pending','countered')
              AND expires_at IS NOT NULL
              AND expires_at < $1
            """,
            now
        )
        for r in rows:
            cid = r["id"]
            await self.auto_expire_claim(cid)

    async def auto_expire_claim(self, claim_id: int):
        """
        Automatically expires a claim that has been inactive past its expiration time.
        """
        claim = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return
        await self.bot.db.execute(
            """
            UPDATE claims
            SET status='expired',
                rejection_reason='Claim expired after 24 hours inactivity'
            WHERE id=$1
            """,
            claim_id
        )
        await self.notify_claim_status(
            claim_id,
            new_status="Expired",
            reason="Claim expired after 24 hours of inactivity."
        )

    async def _propose_claim_cmd(
        self,
        owner: discord.Member,
        sub: discord.Member,
        respond: Union[discord.ApplicationContext, discord.Interaction],
    ):
        """
        Shared logic for proposing a claim, used by both slash commands and button callbacks.
        Validates roles, membership duration, and DM permissions.
        """
        owner_roles = [r.id for r in owner.roles]
        sub_roles = [r.id for r in sub.roles]

        if self.owner_role_id not in owner_roles:
            return await respond.send_message("You must be a male (owner) to propose a claim.", ephemeral=True)

        if self.sub_role_id not in sub_roles:
            return await respond.send_message(f"{sub.mention} is not a sub (female).", ephemeral=True)

        pending_claim = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE sub_id=$1 AND status IN ('pending', 'countered');",
            sub.id
        )
        if pending_claim:
            return await respond.send_message(f"{sub.mention} already has a pending claim.", ephemeral=True)

        if await self.user_on_cooldown(owner.id):
            cooldown_end = await self.get_user_cooldown(owner.id)
            remaining_time = (cooldown_end - datetime.datetime.utcnow()).total_seconds() / 3600
            return await respond.send_message(
                f"You are on cooldown for {remaining_time:.1f} more hours.",
                ephemeral=True
            )

        sub_membership_time = datetime.datetime.utcnow() - sub.joined_at
        if sub_membership_time.total_seconds() < self.membership_minimum_secs:
            return await respond.send_message(
                f"{sub.mention} hasn’t been in the server long enough to be claimed (24-hour minimum).",
                ephemeral=True
            )

        owner_membership_time = datetime.datetime.utcnow() - owner.joined_at
        if owner_membership_time.total_seconds() < self.membership_minimum_secs:
            return await respond.send_message(
                "You haven’t been in the server long enough to propose a claim (24-hour minimum).",
                ephemeral=True
            )

        open_dm = await self.bot.db.fetchrow(
            """
            SELECT 1 FROM open_dm_perms
            WHERE (user1_id=$1 AND user2_id=$2) OR (user1_id=$2 AND user2_id=$1)
              AND active=TRUE;
            """,
            owner.id, sub.id
        )
        if not open_dm:
            return await respond.send_message(
                f"You do not have permission to DM {sub.mention}. Complete the 'Ask to DM' process first.",
                ephemeral=True
            )

        majority_owner_id, majority_share = await self.find_majority_owner(sub.id)
        if majority_owner_id and majority_share >= 50:
            modal = PartialClaimModal(
                cog=self,
                prospective_owner=owner,
                sub=sub,
                majority_owner_id=majority_owner_id
            )
            await respond.send_message(
                f"Proposing a **partial ownership claim** for {sub.mention}.",
                ephemeral=True
            )
            await respond.send_modal(modal)
        else:
            modal = DirectClaimModal(
                cog=self,
                prospective_owner=owner,
                sub=sub
            )
            await respond.send_message(
                f"Proposing a **direct ownership claim** for {sub.mention}.",
                ephemeral=True
            )
            await respond.send_modal(modal)

    # ------------------------------------------------------------------
    # Slash Commands (/ownership ...)
    # ------------------------------------------------------------------
    @ownership_group.command(name="browse", description="Browse sub ownership details (ephemeral UI).")
    async def browse_cmd(self, ctx: discord.ApplicationContext):
        """
        Slash command to browse sub ownership details with an ephemeral interface.
        """
        await ctx.defer(ephemeral=True)
        member = ctx.user
        role_names = [r.name for r in member.roles]
        if "Unverified" in role_names or "Rules Accepted" not in role_names:
            return
        view = OwnershipBrowserView(bot=self.bot)
        await ctx.followup.send(
            content="Select a user below to see ownership info or propose a claim:",
            view=view,
            ephemeral=True
        )

    @ownership_group.command(name="transfer_full", description="Transfer 100% ownership of a sub.")
    async def transfer_full_command(
        self,
        ctx: discord.ApplicationContext,
        sub_id: Option(int, "Sub ID"),
        new_owner_id: Option(str, "New owner ID"),
        sale_amount: Option(int, "Sale amount in credits", default=0),
    ):
        """
        Transfers full (100%) ownership of a sub from the current owner to another.
        """
        await ctx.defer(ephemeral=True)
        if self.owner_role_id not in [r.id for r in ctx.user.roles]:
            return await ctx.followup.send("You must be a male (owner) to transfer a sub.", ephemeral=True)

        sub_member = ctx.guild.get_member(sub_id)
        if not sub_member or (self.sub_role_id not in [r.id for r in sub_member.roles]):
            return await ctx.followup.send("Invalid sub ID or user is not a sub (female).", ephemeral=True)

        try:
            new_owner_id_int = int(new_owner_id)
        except ValueError:
            return await ctx.followup.send("New owner ID must be numeric.", ephemeral=True)
        new_owner = ctx.guild.get_member(new_owner_id_int)
        if not new_owner or (self.owner_role_id not in [r.id for r in new_owner.roles]):
            return await ctx.followup.send("The target new owner is not a male (owner) or not in guild.", ephemeral=True)

        pending_claim = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE sub_id = $1 AND status IN ('pending', 'countered');",
            sub_id
        )
        if pending_claim:
            return await ctx.followup.send("This sub has a pending claim.", ephemeral=True)

        if not await self.is_primary_owner(ctx.author.id, sub_id):
            return await ctx.followup.send("You are not the sub's primary owner.", ephemeral=True)

        success, msg = await self.transfer_full_ownership(sub_id, ctx.author.id, new_owner_id_int, sale_amount)
        if success:
            await ctx.followup.send(
                f"Sub {sub_id} fully transferred to <@{new_owner_id_int}>.\n{msg}",
                ephemeral=True
            )
        else:
            await ctx.followup.send(f"Transfer failed: {msg}", ephemeral=True)

    @ownership_group.command(name="transfer_partial", description="Transfer partial shares of a sub.")
    async def transfer_partial_command(
        self,
        ctx: discord.ApplicationContext,
        sub_id: Option(int, "Sub ID"),
        buyer_id: Option(str, "Buyer user ID"),
        shares: Option(int, "Shares % (1-99)"),
        sale_amount: Option(int, "Sale amount in credits", default=0),
    ):
        """
        Transfers partial ownership shares from the seller to the buyer.
        """
        await ctx.defer(ephemeral=True)
        if self.owner_role_id not in [r.id for r in ctx.user.roles]:
            return await ctx.followup.send("You must be a male (owner) to transfer partial shares.", ephemeral=True)

        sub_member = ctx.guild.get_member(sub_id)
        if not sub_member or (self.sub_role_id not in [r.id for r in sub_member.roles]):
            return await ctx.followup.send("Invalid sub ID or user is not a sub (female).", ephemeral=True)

        try:
            buyer_id_int = int(buyer_id)
        except ValueError:
            return await ctx.followup.send("Buyer user ID must be numeric.", ephemeral=True)

        buyer_member = ctx.guild.get_member(buyer_id_int)
        if not buyer_member or (self.owner_role_id not in [r.id for r in buyer_member.roles]):
            return await ctx.followup.send("Buyer is not a male (owner).", ephemeral=True)

        pending_claim = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE sub_id = $1 AND status IN ('pending', 'countered');",
            sub_id
        )
        if pending_claim:
            return await ctx.followup.send("This sub has a pending claim.", ephemeral=True)

        if not await self.has_enough_shares(ctx.user.id, sub_id, shares):
            return await ctx.followup.send(
                f"You do not have {shares}% in sub {sub_id}.",
                ephemeral=True
            )

        success, msg = await self.transfer_partial_ownership(sub_id, ctx.user.id, buyer_id_int, shares, sale_amount)
        if success:
            await ctx.followup.send(
                f"Transferred {shares}% of sub {sub_id} to <@{buyer_id_int}>.\n{msg}",
                ephemeral=True
            )
        else:
            await ctx.followup.send(f"Partial transfer failed: {msg}", ephemeral=True)

    @ownership_group.command(name="info", description="View sub ownership info (ephemeral).")
    async def info_command(self, ctx: discord.ApplicationContext, sub_id: int):
        """
        Displays detailed information about a sub's ownership status.
        """
        await ctx.defer(ephemeral=True)
        embed = await self.build_sub_info_embed(sub_id)
        await ctx.followup.send(embed=embed, ephemeral=True)

    @ownership_group.command(
        name="propose",
        description="Propose a new partial or direct claim on a sub."
    )
    async def propose_claim_cmd(
        self,
        ctx: discord.ApplicationContext,
        target_user: Option(discord.Member, "Which user (sub) to claim")
    ):
        """
        Proposes a new claim (partial or direct) via a slash command.
        """
        await ctx.defer(ephemeral=True)
        await self._propose_claim_cmd(
            owner=ctx.user,
            sub=target_user,
            respond=ctx
        )

    @ownership_group.command(name="claim", description="(Legacy) Request ownership of a user (older approach).")
    async def claim_cmd(self, ctx: discord.ApplicationContext, sub_user: Option(discord.Member, "User to claim")):
        """
        Legacy command for initiating an ownership claim. This approach requires both
        staff and sub approvals.
        """
        await ctx.defer(ephemeral=True)

        if self.owner_role_id not in [r.id for r in ctx.user.roles]:
            return await ctx.followup.send("Only male (owner) can do that.", ephemeral=True)
        if self.sub_role_id not in [r.id for r in sub_user.roles]:
            return await ctx.followup.send(f"{sub_user.mention} is not a sub.", ephemeral=True)

        row_sub_claim = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE sub_id=$1 AND status IN ('pending','countered');",
            sub_user.id
        )
        if row_sub_claim:
            return await ctx.followup.send("User has a pending claim.", ephemeral=True)

        row_owner_sub = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE owner_id=$1 AND sub_id=$2 AND status IN('pending','countered');",
            ctx.user.id, sub_user.id
        )
        if row_owner_sub:
            return await ctx.followup.send("You already have a pending claim on them.", ephemeral=True)

        if await self.user_on_cooldown(ctx.user.id):
            cd_end = await self.get_user_cooldown(ctx.user.id)
            remain_hrs = (cd_end - datetime.datetime.utcnow()).total_seconds() / 3600
            return await ctx.followup.send(
                f"You are on cooldown for {remain_hrs:.1f} hours.",
                ephemeral=True
            )

        sub_joined_delta = datetime.datetime.utcnow() - sub_user.joined_at
        if sub_joined_delta.total_seconds() < self.membership_minimum_secs:
            return await ctx.followup.send("User hasn't been here 24h. Claim not allowed.", ephemeral=True)
        owner_joined_delta = datetime.datetime.utcnow() - ctx.user.joined_at
        if owner_joined_delta.total_seconds() < self.membership_minimum_secs:
            return await ctx.followup.send("You haven't been here 24h. Claim not allowed.", ephemeral=True)

        if await self.check_has_majority_owner(sub_user.id):
            return await ctx.followup.send("They have a majority owner. Legacy claim blocked.", ephemeral=True)

        claim_id = await self.create_claim_record(ctx.user.id, sub_user.id)
        if claim_id is None:
            return await ctx.followup.send("Cannot create claim. Possibly pending already.", ephemeral=True)

        staff_ch = self.bot.get_channel(self.staff_ledger_channel_id)
        if staff_ch:
            staff_embed = await self.build_staff_claim_embed(claim_id, ctx.user, sub_user)
            staff_view = OwnershipClaimStaffView(self.bot, claim_id, timeout=None)
            staff_msg = await staff_ch.send(
                content=f"New ownership claim #{claim_id}",
                embed=staff_embed,
                view=staff_view
            )
            await self.bot.db.execute(
                "UPDATE claims SET staff_msg_id=$1 WHERE id=$2;",
                staff_msg.id, claim_id
            )

        try:
            dm_ch = await sub_user.create_dm()
            sub_embed = await self.build_sub_claim_embed(claim_id, ctx.user, sub_user)
            sub_view = OwnershipClaimSubView(self.bot, claim_id, timeout=None)
            sub_msg = await dm_ch.send(
                content=f"You are being claimed by {ctx.user.mention} (legacy).",
                embed=sub_embed,
                view=sub_view
            )
            await self.bot.db.execute(
                "UPDATE claims SET sub_msg_id=$1 WHERE id=$2;",
                sub_msg.id, claim_id
            )
        except discord.Forbidden:
            pass

        await ctx.followup.send(
            f"Ownership claim initiated for {sub_user.mention}, ID#{claim_id}.",
            ephemeral=True
        )

    # ------------------------------------------------------------------
    # DM Request Handling
    # ------------------------------------------------------------------
    async def handle_dm_request(
        self,
        requestor: discord.Member,
        target_user: discord.Member,
        interaction: discord.Interaction,
        view_to_disable_button: Optional[discord.ui.View] = None,
    ):
        """
        Handles a DM request. If the target’s DM settings are "open", grants permission
        automatically; otherwise, initiates an approval flow.
        """
        now = time.time()
        last_req = self.dm_request_cooldowns.get(requestor.id, 0)
        if now - last_req < self.dm_request_cooldown:
            remaining = int(self.dm_request_cooldown - (now - last_req))
            await interaction.response.send_message(
                f"You are on cooldown. Wait {remaining} seconds before requesting DM again.",
                ephemeral=True
            )
            return
        self.dm_request_cooldowns[requestor.id] = now

        if view_to_disable_button:
            for child in view_to_disable_button.children:
                if getattr(child, "custom_id", "") in ["browseview_request_dm_btn", "singleuser_request_dm"]:
                    child.disabled = True

        # Re-check the target's DM status immediately.
        row = await self.bot.db.fetchrow(
            "SELECT dm_status FROM user_roles WHERE user_id=$1;",
            target_user.id
        )
        dm_status = (row["dm_status"] if row else "closed").lower()

        if "open" in dm_status:
            await self.add_open_dm_pair(requestor.id, target_user.id, reason="auto_open")
            return await interaction.response.send_message(
                "That user’s DMs are open by default. You now have permission to DM them.",
                ephemeral=True
            )
        elif "closed" in dm_status:
            return await interaction.response.send_message(
                "They have closed DMs. You cannot DM them at this time.",
                ephemeral=True
            )
        elif dm_status.startswith("ask"):
            if "ask to" in dm_status:
                await self.start_ask_flow(
                    requestor=requestor,
                    approver=target_user,
                    reason="ask",
                    interaction=interaction
                )
            elif "ask owner to" in dm_status:
                mo_id, _ = await self.find_majority_owner(target_user.id)
                if mo_id:
                    mo_member = interaction.guild.get_member(mo_id)
                    if mo_member:
                        await self.start_ask_flow(
                            requestor=requestor,
                            approver=mo_member,
                            reason="ask owner",
                            interaction=interaction
                        )
                    else:
                        await interaction.response.send_message(
                            "No valid majority owner found or user not in guild. Cannot proceed.",
                            ephemeral=True
                        )
                else:
                    await interaction.response.send_message(
                        "No majority owner found; cannot request approval.",
                        ephemeral=True
                    )
        else:
            return await interaction.response.send_message(
                "DM status unknown; cannot request DM.",
                ephemeral=True
            )

    async def start_ask_flow(
        self,
        requestor: discord.Member,
        approver: discord.Member,
        reason: str,
        interaction: discord.Interaction
    ):
        """
        Starts the DM approval flow by logging the request in a designated channel
        and DMing the approver with an interactive view.
        """
        channel = self.bot.get_channel(self.ask_to_dm_channel_id)
        if not channel:
            await interaction.response.send_message("ask_to_dm channel not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="DM Request Pending",
            description=(
                f"**From:** {requestor.mention}\n"
                f"**To Approver:** {approver.mention}\n\n"
                f"**Reason:** {reason}\n"
                "Status: **Pending**"
            ),
            color=discord.Color.yellow()
        )
        log_msg = await channel.send(embed=embed)

        try:
            dm = await approver.create_dm()
            view = AskForDMApprovalView(bot=self.bot, requestor=requestor, log_message=log_msg)
            dm_embed = discord.Embed(
                title="DM Request Received",
                description=(
                    f"{requestor.mention} is requesting permission to DM.\n"
                    "Click **Accept** or **Deny**, optionally provide a reason."
                ),
                color=discord.Color.gold()
            )
            await dm.send(embed=dm_embed, view=view)
            await interaction.response.send_message(
                f"DM approval request sent to {approver.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            fail_embed = discord.Embed(
                title="DM Request Failed to Send",
                description=(embed.description + "\n\n**Failed to DM (Forbidden).**"),
                color=discord.Color.red()
            )
            await log_msg.edit(embed=fail_embed)
            await interaction.response.send_message(
                "Could not DM the approver (Forbidden).",
                ephemeral=True
            )

    async def add_open_dm_pair(self, user1_id: int, user2_id: int, reason: str):
        """
        Adds or reactivates an open DM permission pair between two users.
        """
        umin, umax = min(user1_id, user2_id), max(user1_id, user2_id)
        await self.bot.db.execute(
            """
            INSERT INTO open_dm_perms (user1_id, user2_id, opened_at, active, reason)
            VALUES($1, $2, NOW(), TRUE, $3)
            ON CONFLICT (user1_id, user2_id)
            DO UPDATE SET active=TRUE, opened_at=NOW(), reason=$3, closed_at=NULL
            """,
            umin, umax, reason
        )

    async def close_dm_pair(self, user1_id: int, user2_id: int, reason: str):
        """
        Closes an open DM permission pair.
        """
        umin, umax = min(user1_id, user2_id), max(user1_id, user2_id)
        await self.bot.db.execute(
            """
            UPDATE open_dm_perms
            SET active=FALSE,
                closed_at=NOW(),
                reason=$3
            WHERE user1_id=$1 AND user2_id=$2 AND active=TRUE
            """,
            umin, umax, reason
        )

    # ------------------------------------------------------------------
    # Notification of Claim Status via DM
    # ------------------------------------------------------------------
    async def notify_claim_status(
        self,
        claim_id: int,
        new_status: str,
        reason: str = "",
        staff_user: Optional[discord.Member] = None
    ):
        """
        Notifies both parties involved in a claim of its updated status by DM.
        """
        claim = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not claim:
            return

        sub_id = claim["sub_id"]
        owner_id = claim["owner_id"]
        sub_user = self.bot.get_user(sub_id)
        owner_user = self.bot.get_user(owner_id)

        embed = discord.Embed(
            title=f"Ownership Claim #{claim_id} Update",
            description=f"**Status:** {new_status}",
            color=discord.Color.orange()
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        if staff_user:
            embed.set_footer(text=f"Action taken by staff: {staff_user.display_name}")

        if claim.get("justification"):
            embed.add_field(
                name="Original Justification",
                value=claim["justification"],
                inline=False
            )

        if sub_user:
            try:
                dm_ch = await sub_user.create_dm()
                await dm_ch.send(embed=embed)
            except discord.Forbidden:
                pass

        if owner_user:
            try:
                dm_ch = await owner_user.create_dm()
                await dm_ch.send(embed=embed)
            except discord.Forbidden:
                pass

    # ------------------------------------------------------------------
    # Finalize Claim / Staff Approval Logic
    # ------------------------------------------------------------------
    async def finalize_claim(self, claim_id: int, forced_by_staff: bool=False):
        """
        Finalizes a claim by updating ownership records and marking the claim as approved.
        Ensures that the operation is atomic and revalidates that the new owner still has the correct role.
        """
        claim = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not claim or claim["status"] in ("approved", "denied", "expired", "auto_rejected"):
            return

        sub_id = claim["sub_id"]
        new_owner_id = claim["owner_id"]
        majority_id = claim.get("majority_owner_id")
        final_pct = claim.get("requested_percentage", 100)

        # Revalidate that the new owner exists in the guild and has the owner role.
        guild = self.bot.get_guild(self.bot.config["guild_id"])
        owner_member = guild.get_member(new_owner_id) if guild else None
        if not owner_member or self.owner_role_id not in [r.id for r in owner_member.roles]:
            logger.error(f"Finalization aborted: Owner {new_owner_id} not valid or missing required role.")
            return

        if majority_id and 0 < final_pct < 100:
            await self.bot.db.execute(
                """
                UPDATE sub_ownership
                SET percentage=percentage-$1
                WHERE sub_id=$2 AND user_id=$3
                """,
                final_pct, sub_id, majority_id
            )
            row = await self.bot.db.fetchrow(
                "SELECT 1 FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;",
                sub_id, new_owner_id
            )
            if row:
                await self.bot.db.execute(
                    """
                    UPDATE sub_ownership
                    SET percentage=percentage+$1
                    WHERE sub_id=$2 AND user_id=$3
                    """,
                    final_pct, sub_id, new_owner_id
                )
            else:
                await self.bot.db.execute(
                    """
                    INSERT INTO sub_ownership(sub_id, user_id, percentage)
                    VALUES($1,$2,$3)
                    """,
                    sub_id, new_owner_id, final_pct
                )
        else:
            await self.bot.db.execute("DELETE FROM sub_ownership WHERE sub_id=$1;", sub_id)
            await self.bot.db.execute(
                "INSERT INTO sub_ownership(sub_id,user_id,percentage) VALUES($1,$2,100);",
                sub_id, new_owner_id
            )

        await self.bot.db.execute(
            "UPDATE claims SET status='approved' WHERE id=$1;",
            claim_id
        )
        await self.auto_reject_parallel(sub_id, claim_id)

        if not claim.get("cooldown_exempt"):
            await self.apply_success_cooldowns(sub_id, new_owner_id)

        logger.info(f"Claim {claim_id} -> Approved. sub={sub_id}, new_owner={new_owner_id}, share={final_pct}")

        status_reason = "Claim approved (staff & sub)." if forced_by_staff else "Claim fully approved."
        await self.notify_claim_status(
            claim_id,
            new_status="Approved",
            reason=status_reason
        )

    async def auto_reject_parallel(self, sub_id: int, accepted_claim_id: int):
        """
        Automatically rejects all other pending claims on a sub when one claim is accepted.
        """
        rows = await self.bot.db.fetch(
            """
            SELECT id FROM claims
            WHERE sub_id=$1
              AND id<>$2
              AND status IN('pending','countered')
            """,
            sub_id, accepted_claim_id
        )
        for r in rows:
            c2 = r["id"]
            await self.bot.db.execute(
                """
                UPDATE claims
                SET status='auto_rejected',
                    rejection_reason='Another claim was accepted first'
                WHERE id=$1
                """,
                c2
            )
            await self.notify_claim_status(
                c2,
                new_status="Auto-Rejected",
                reason="Another claim was accepted first."
            )

    async def staff_approve_claim(self, claim_id: int, staff_id: int):
        """
        Records a staff approval for a claim and finalizes it if the conditions are met.
        """
        row = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims_staff_approvals WHERE claim_id=$1 AND staff_id=$2;",
            claim_id, staff_id
        )
        if row:
            return

        await self.bot.db.execute(
            "INSERT INTO claims_staff_approvals (claim_id, staff_id) VALUES ($1,$2);",
            claim_id, staff_id
        )
        await self.bot.db.execute(
            "UPDATE claims SET staff_approvals=staff_approvals+1 WHERE id=$1;",
            claim_id
        )

        claim = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return

        staff_count = claim["staff_approvals"]
        sub_approved = claim["sub_approved"]
        if staff_count >= 2 and sub_approved:
            staff_user = self.bot.get_user(staff_id)
            await self.finalize_claim(claim_id, forced_by_staff=True)

    async def staff_deny_claim(self, claim_id: int, staff_id: int):
        """
        Denies a claim based on staff decision.
        """
        staff_user = self.bot.get_user(staff_id)
        denial_reason = (
            f"Denied by staff {staff_user.mention}" if staff_user
            else f"Denied by staff ID {staff_id}"
        )

        await self.bot.db.execute(
            """
            UPDATE claims
            SET status='denied',
                rejection_reason=$2
            WHERE id=$1
            """,
            claim_id, denial_reason
        )

        await self.notify_claim_status(
            claim_id,
            new_status="Denied by staff",
            reason=denial_reason,
            staff_user=staff_user
        )

        ledger_ch = self.bot.get_channel(self.staff_ledger_channel_id)
        if ledger_ch:
            await ledger_ch.send(f"Claim #{claim_id} denied by staff <@{staff_id}>.")

    async def sub_approve_claim(self, claim_id: int, user_id: int):
        """
        Processes sub approval for a claim.
        """
        claim = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not claim or claim["status"] != "pending":
            return
        if claim["sub_id"] != user_id:
            return

        await self.bot.db.execute(
            "UPDATE claims SET sub_approved=TRUE WHERE id=$1;",
            claim_id
        )

        if claim["staff_approvals"] >= 2:
            await self.finalize_claim(claim_id)

    async def sub_deny_claim(self, claim_id: int, user_id: int):
        """
        Processes sub denial for a claim and applies a cooldown.
        """
        claim = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not claim or claim["status"] != "pending":
            return
        if claim["sub_id"] != user_id:
            return

        await self.bot.db.execute(
            """
            UPDATE claims
            SET status='denied',
                rejection_reason='Sub denied (old approach)'
            WHERE id=$1
            """,
            claim_id
        )

        await self.apply_rejected_cooldown(claim["owner_id"])

        await self.notify_claim_status(
            claim_id,
            new_status="Denied by sub",
            reason="The sub has rejected the claim."
        )

        ledger_ch = self.bot.get_channel(self.staff_ledger_channel_id)
        if ledger_ch:
            await ledger_ch.send(f"Claim #{claim_id} denied by sub <@{user_id}>.")

    # ------------------------------------------------------------------
    # Ownership and Share Checks
    # ------------------------------------------------------------------
    async def find_majority_owner(self, sub_id: int):
        """
        Finds the majority owner for a given sub.
        In case of equal percentages (e.g. 50%/50%), the owner with the earlier acquisition
        (based on the acquired_at timestamp) is chosen.
        """
        row = await self.bot.db.fetchrow(
            """
            SELECT user_id, percentage
            FROM sub_ownership
            WHERE sub_id=$1::bigint
            ORDER BY percentage DESC, acquired_at ASC
            LIMIT 1
            """,
            sub_id
        )
        if not row or row["percentage"] < 50:
            return (None, 0)
        return (row["user_id"], row["percentage"])

    async def check_has_majority_owner(self, user_id: int) -> bool:
        """
        Checks if a sub already has a majority owner (>= 50%).
        """
        row2 = await self.bot.db.fetchrow(
            """
            SELECT 1
            FROM sub_ownership
            WHERE sub_id=$1::bigint
              AND percentage>=50
            """,
            user_id
        )
        return bool(row2)

    # ------------------------------------------------------------------
    # Cooldown Functions
    # ------------------------------------------------------------------
    async def user_on_cooldown(self, user_id: int) -> bool:
        """
        Checks if a user is currently on global cooldown.
        """
        row = await self.bot.db.fetchrow(
            """
            SELECT global_cooldown_until
            FROM user_cooldowns
            WHERE user_id=$1
            """,
            user_id
        )
        if not row or not row["global_cooldown_until"]:
            return False
        if row["global_cooldown_until"] <= datetime.datetime.utcnow():
            return False
        return True

    async def get_user_cooldown(self, user_id: int) -> Optional[datetime.datetime]:
        """
        Retrieves the cooldown expiration for a user.
        """
        row = await self.bot.db.fetchrow(
            """
            SELECT global_cooldown_until
            FROM user_cooldowns
            WHERE user_id=$1
            """,
            user_id
        )
        if not row:
            return None
        return row["global_cooldown_until"]

    async def set_user_cooldown(self, user_id: int, until: datetime.datetime):
        """
        Sets a global cooldown for a user until the specified datetime.
        """
        await self.bot.db.execute(
            """
            INSERT INTO user_cooldowns(user_id, global_cooldown_until)
            VALUES($1, $2)
            ON CONFLICT(user_id) DO UPDATE
            SET global_cooldown_until=EXCLUDED.global_cooldown_until
            """,
            user_id, until
        )

    async def apply_success_cooldowns(self, sub_id: int, new_owner_id: int):
        """
        Applies a cooldown to the sub, the new owner, and all associated owners after a successful claim.
        """
        until = datetime.datetime.utcnow() + datetime.timedelta(days=self.cooldown_days)
        await self.set_user_cooldown(sub_id, until)
        await self.set_user_cooldown(new_owner_id, until)
        owners = await self.bot.db.fetch(
            """
            SELECT user_id FROM sub_ownership
            WHERE sub_id=$1
            """,
            sub_id
        )
        for o in owners:
            await self.set_user_cooldown(o["user_id"], until)

    async def apply_rejected_cooldown(self, user_id: int):
        """
        Applies a cooldown to a user after their claim has been rejected.
        """
        until = datetime.datetime.utcnow() + datetime.timedelta(hours=self.rejected_claim_cooldown_hours)
        await self.set_user_cooldown(user_id, until)

    # ------------------------------------------------------------------
    # Claim Record Creation
    # ------------------------------------------------------------------
    async def create_claim_record(self, owner_id: int, sub_id: int) -> Optional[int]:
        """
        Creates a new claim record for the specified owner and sub.
        Wraps the insert in a transaction to avoid race conditions.
        """
        existing_claim = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE sub_id=$1 AND status IN ('pending','countered');",
            sub_id
        )
        if existing_claim:
            return None
        try:
            async with self.bot.db.transaction():
                row = await self.bot.db.fetchrow(
                    """
                    INSERT INTO claims(owner_id, sub_id, staff_approvals, sub_approved, status)
                    VALUES($1,$2,0,FALSE,'pending')
                    RETURNING id
                    """,
                    owner_id, sub_id
                )
            return row["id"] if row else None
        except Exception as e:
            logger.error(f"Error creating claim record: {e}")
            return None

    # ------------------------------------------------------------------
    # Embed Builders
    # ------------------------------------------------------------------
    async def build_staff_claim_embed(self, claim_id: int, owner: discord.Member, sub: discord.Member) -> discord.Embed:
        """
        Builds an embed for staff with details of the claim.
        """
        embed = discord.Embed(
            title=f"Ownership Claim #{claim_id}",
            description=(
                f"**Prospective Owner:** {owner.mention}\n"
                f"**Claimed Sub:** {sub.mention}\n"
                "**Needs 2 staff + sub acceptance.**"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Staff: Approve or Deny below.")
        return embed

    async def build_sub_claim_embed(self, claim_id: int, owner: discord.Member, sub: discord.Member) -> discord.Embed:
        """
        Builds an embed for the sub with details about the incoming claim.
        """
        embed = discord.Embed(
            title=f"Ownership Claim #{claim_id}",
            description=(
                f"{owner.mention} wants to claim you (old approach).\n"
                "Click Approve or Deny.\n"
                "If you do nothing, staff may require your input later."
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Think carefully before consenting!")
        return embed

    async def build_sub_info_embed(self, sub_id: int) -> discord.Embed:
        """
        Constructs an embed that displays ownership details and extra info for a sub.
        """
        embed = discord.Embed(title=f"Sub #{sub_id} Info", color=discord.Color.blue())
        owners = await self.bot.db.fetch(
            """
            SELECT user_id, percentage
            FROM sub_ownership
            WHERE sub_id=$1
            ORDER BY percentage DESC
            """,
            sub_id
        )
        if owners:
            lines = [f"<@{o['user_id']}> - {o['percentage']}%" for o in owners]
            embed.add_field(name="Owners", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Owners", value="None", inline=False)

        row = await self.bot.db.fetchrow(
            """
            SELECT monthly_earnings, service_menu_url
            FROM subs
            WHERE id=$1
            """,
            sub_id
        )
        if row:
            me = row["monthly_earnings"] or 0
            embed.add_field(name="Monthly Earnings", value=f"{me} credits", inline=True)
            if row["service_menu_url"]:
                embed.add_field(
                    name="Service Menu",
                    value=f"[View Menu]({row['service_menu_url']})",
                    inline=True
                )

        embed.set_footer(text="Ownership data from the system.")
        return embed

    # ------------------------------------------------------------------
    # Transaction Logging (Blockchain)
    # ------------------------------------------------------------------
    async def log_transaction(self, sender_id: int, recipient_id: int, amount: int, justification: str):
        """
        Logs a transaction to a blockchain-like ledger and posts a summary to a designated channel.
        """
        last_tx = await self.bot.db.fetchrow("SELECT id, hash FROM transactions ORDER BY id DESC LIMIT 1;")
        last_hash = last_tx["hash"] if last_tx else "0"

        row = await self.bot.db.fetchrow(
            """
            INSERT INTO transactions(sender_id, recipient_id, amount, justification, status)
            VALUES($1,$2,$3,$4,'completed')
            RETURNING id
            """,
            sender_id, recipient_id, amount, justification
        )
        tx_id = row["id"]

        to_hash = f"{tx_id}{sender_id}{recipient_id}{amount}{justification}{last_hash}"
        tx_hash = hashlib.sha256(to_hash.encode()).hexdigest()

        await self.bot.db.execute(
            """
            UPDATE transactions
            SET hash=$1
            WHERE id=$2
            """,
            tx_hash, tx_id
        )

        sender_user = self.bot.get_user(sender_id)
        recipient_user = self.bot.get_user(recipient_id)
        embed = discord.Embed(
            title="Transaction Logged",
            description="A new transaction was recorded on the ledger.",
            color=discord.Color.green()
        )
        embed.add_field(name="Amount", value=f"```{amount} credits```", inline=False)
        embed.add_field(
            name="Sender",
            value=sender_user.mention if sender_user else f"ID: {sender_id}",
            inline=True
        )
        embed.add_field(
            name="Recipient",
            value=recipient_user.mention if recipient_user else f"ID: {recipient_id}",
            inline=True
        )
        embed.add_field(name="Justification", value=f"```{justification}```", inline=False)
        embed.add_field(name="Transaction Hash", value=f"```{tx_hash}```", inline=False)

        tx_channel = self.bot.get_channel(self.blockchain_channel_id)
        if tx_channel:
            await tx_channel.send(embed=embed)

    # ------------------------------------------------------------------
    # Staff Verification Posting for Partial Claims
    # ------------------------------------------------------------------
    async def post_staff_verification(self, claim_id: int, owner: discord.Member, sub: discord.Member, percentage: int):
        """
        Posts a partial-claim verification message to the staff channel.
        """
        staff_channel = self.bot.get_channel(self.staff_ledger_channel_id)
        if not staff_channel:
            logger.warning(f"Staff claim channel ({self.staff_ledger_channel_id}) not found.")
            return

        logger.debug(f"Posting partial-claim to staff for verification: claim_id={claim_id}, %={percentage}")

        embed = discord.Embed(
            title=f"Ownership Claim #{claim_id}",
            description=(
                f"**Prospective Owner:** {owner.mention}\n"
                f"**Claimed Sub:** {sub.mention}\n"
                f"**Percentage Requested:** {percentage}%\n\n"
                "**Staff must review and approve.**"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Staff: Approve or Deny below.")
        view = OwnershipClaimStaffView(self.bot, claim_id, timeout=None)

        message = await staff_channel.send(
            content=f"New ownership claim #{claim_id} requires approval.",
            embed=embed,
            view=view
        )
        await self.bot.db.execute(
            "UPDATE claims SET staff_msg_id=$1 WHERE id=$2;",
            message.id, claim_id
        )

    # ------------------------------------------------------------------
    # Transfer Logic (Full and Partial)
    # ------------------------------------------------------------------
    async def is_primary_owner(self, user_id: int, sub_id: int) -> bool:
        """
        Placeholder check for primary ownership. Adjust as needed based on your data schema.
        """
        return True

    async def has_enough_shares(self, user_id: int, sub_id: int, shares: int) -> bool:
        """
        Checks whether the user has at least the specified percentage of ownership.
        """
        row = await self.bot.db.fetchrow(
            """
            SELECT percentage
            FROM sub_ownership
            WHERE sub_id=$1 AND user_id=$2
            """,
            sub_id, user_id
        )
        return bool(row and row["percentage"] >= shares)

    async def transfer_full_ownership(self, sub_id: int, old_owner_id: int, new_owner_id: int, sale_amount: int):
        """
        Performs a full (100%) ownership transfer from old_owner to new_owner.
        The operation is wrapped in a transaction to ensure atomicity.
        """
        try:
            async with self.bot.db.transaction():
                if sale_amount > 0:
                    buyer_balance = await self.user_balance(new_owner_id)
                    if buyer_balance < sale_amount:
                        return (False, "Buyer lacks funds.")
                    await self.bot.db.execute(
                        "UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;",
                        sale_amount, new_owner_id
                    )
                    await self.bot.db.execute(
                        "UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;",
                        sale_amount, old_owner_id
                    )
                await self.bot.db.execute("DELETE FROM sub_ownership WHERE sub_id=$1;", sub_id)
                await self.bot.db.execute(
                    "INSERT INTO sub_ownership(sub_id, user_id, percentage) VALUES($1,$2,100);",
                    sub_id, new_owner_id
                )
            return (True, "Full ownership transfer completed.")
        except Exception as e:
            logger.error(f"transfer_full_ownership DB error: {e}")
            return (False, f"DB error: {e}")

    async def transfer_partial_ownership(self, sub_id: int, seller_id: int, buyer_id: int, shares: int, sale_amount: int):
        """
        Performs a partial ownership transfer from seller to buyer.
        The operation is wrapped in a transaction to ensure atomicity.
        """
        try:
            async with self.bot.db.transaction():
                if sale_amount > 0:
                    buyer_balance = await self.user_balance(buyer_id)
                    if buyer_balance < sale_amount:
                        return (False, "Buyer lacks funds.")
                    await self.bot.db.execute(
                        "UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;",
                        sale_amount, buyer_id
                    )
                    await self.bot.db.execute(
                        "UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;",
                        sale_amount, seller_id
                    )
                await self.bot.db.execute(
                    """
                    UPDATE sub_ownership
                    SET percentage=percentage-$1
                    WHERE sub_id=$2
                      AND user_id=$3
                    """,
                    shares, sub_id, seller_id
                )
                row = await self.bot.db.fetchrow(
                    """
                    SELECT 1 FROM sub_ownership
                    WHERE sub_id=$1
                      AND user_id=$2
                    """,
                    sub_id, buyer_id
                )
                if row:
                    await self.bot.db.execute(
                        """
                        UPDATE sub_ownership
                        SET percentage=percentage+$1
                        WHERE sub_id=$2
                          AND user_id=$3
                        """,
                        shares, sub_id, buyer_id
                    )
                else:
                    await self.bot.db.execute(
                        """
                        INSERT INTO sub_ownership(sub_id,user_id,percentage)
                        VALUES($1,$2,$3)
                        """,
                        sub_id, buyer_id, shares
                    )
            return (True, "Partial ownership transfer completed.")
        except Exception as e:
            logger.error(f"transfer_partial_ownership DB error: {e}")
            return (False, f"DB error: {e}")

    async def user_balance(self, user_id: int) -> int:
        """
        Retrieves the balance of the user's wallet. If the user does not have a wallet,
        one is created with a balance of 0.
        """
        row = await self.bot.db.fetchrow(
            "SELECT balance FROM wallets WHERE user_id=$1",
            user_id
        )
        if not row:
            await self.bot.db.execute(
                """
                INSERT INTO wallets(user_id,balance)
                VALUES($1,0)
                ON CONFLICT DO NOTHING
                """,
                user_id
            )
            return 0
        return row["balance"]

    # ------------------------------------------------------------------
    # End of OwnershipCog class
    # ------------------------------------------------------------------

def setup(bot: commands.Bot):
    """
    Sets up the OwnershipCog.
    """
    bot.add_cog(OwnershipCog(bot))

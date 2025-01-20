import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
from loguru import logger
from typing import Optional, TYPE_CHECKING
import asyncio
import time  # for cooldown checks
import hashlib  # for computing transaction hashes

if TYPE_CHECKING:
    from main import MoguMoguBot


class OwnershipCog(commands.Cog):
    """
    A comprehensive OwnershipCog that handles:
      1) Slash-based ephemeral ownership browsing (/ownership browse).
      2) Reaction-based shortcuts: reacting with "🔍" -> DM with SingleUserOwnershipView
      3) Full & partial ownership transfers.
      4) Ownership info.
      5) Multi-approval 'claim' workflow requiring staff + sub approvals.
      6) Transactions logged on a blockchain-style ledger.
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

        # ─── CONFIG ───
        self.owner_role_id = bot.config["owner_role_id"]
        self.sub_role_id = bot.config["sub_role_id"]
        self.staff_ledger_channel_id = bot.config["staff_channel_ownership_id"]
        self.ask_to_dm_channel_id = bot.config["ask_to_dm_channel_id"]
        self.membership_minimum_secs = bot.config.get("membership_minimum_seconds", 86400)
        self.blockchain_channel_id = bot.config["blockchain_transaction_channel_id"]

        # ─── RATE LIMITS ───
        self.mag_react_cooldown = bot.config.get("mag_react_cooldown", 60)
        self.dm_request_cooldown = bot.config.get("dm_request_cooldown", 60)

        # ─── STATE ───
        self._reattached = False
        self.mag_react_cooldowns = {}  # { user_id: last_timestamp }
        self.dm_request_cooldowns = {} # { user_id: last_timestamp }

    # ─────────────────────────────────────────────────────────────────
    # Re-attach persistent Views in on_ready
    # ─────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        if self._reattached:
            return
        self._reattached = True

        # 1) Re-attach staff/sub claim views for pending claims
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
                logger.debug(f"Reattached OwnershipClaimStaffView for claim_id={claim_id} on message_id={staff_msg_id}")
            if sub_msg_id:
                sub_view = OwnershipClaimSubView(bot=self.bot, claim_id=claim_id, timeout=None)
                self.bot.add_view(sub_view, message_id=sub_msg_id)
                logger.debug(f"Reattached OwnershipClaimSubView for claim_id={claim_id} on message_id={sub_msg_id}")

        # 2) Re-attach SingleUserOwnershipView messages from "🔍" DMs
        dm_rows = await self.bot.db.fetch(
            "SELECT message_id, user_id, target_user_id FROM dm_ownership_views WHERE active=TRUE;"
        )
        for r in dm_rows:
            msg_id = r["message_id"]
            target_user = self.bot.get_user(r["target_user_id"])
            if not target_user:
                continue
            view = SingleUserOwnershipView(bot=self.bot, target_user=target_user, timeout=None)
            self.bot.add_view(view, message_id=msg_id)
            logger.debug(f"Reattached SingleUserOwnershipView for target_user={target_user} on message_id={msg_id}")

    # ─────────────────────────────────────────────────────────────────
    # Reaction-based "🔍"
    # ─────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != "🔍":
            return
        if payload.user_id == self.bot.user.id:
            return

        # ─── COOLDOWN CHECK FOR MAG REACT ───
        now = time.time()
        last_used = self.mag_react_cooldowns.get(payload.user_id, 0)
        if now - last_used < self.mag_react_cooldown:
            logger.debug(f"[mag react] user {payload.user_id} is on cooldown, ignoring.")
            return
        # Update the cooldown
        self.mag_react_cooldowns[payload.user_id] = now

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member:
            return

        role_ids = [r.id for r in member.roles]
        if (self.owner_role_id not in role_ids) and (self.sub_role_id not in role_ids):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # Clean up reaction.
        await message.remove_reaction(emoji=payload.emoji, member=member)

        if message.author.bot:
            return

        target_user = message.author

        try:
            dm = await member.create_dm()
        except discord.Forbidden:
            return

        embed = discord.Embed(
            title="Quick Ownership Browser",
            description=f"You used 🔍 on {target_user.mention}'s message.\nHere is a single-user ownership interface.",
            color=discord.Color.gold()
        )
        # Make it persistent with timeout=None
        view = SingleUserOwnershipView(bot=self.bot, target_user=target_user, timeout=None)
        dm_msg = await dm.send(embed=embed, view=view)

        # Store the DM message_id
        await self.bot.db.execute(
            """
            INSERT INTO dm_ownership_views (message_id, user_id, target_user_id, active)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (message_id) DO UPDATE SET active=TRUE;
            """,
            dm_msg.id, member.id, target_user.id
        )

    # ─────────────────────────────────────────────────────────────────
    # Slash Command Group
    # ─────────────────────────────────────────────────────────────────
    ownership_group = SlashCommandGroup("ownership", "Manage sub ownership.")

    @ownership_group.command(name="browse", description="Browse sub ownership details (ephemeral UI).")
    async def browse_cmd(self, ctx: discord.ApplicationContext):
        # ephemeral - does not persist
        await ctx.defer(ephemeral=True)
        view = OwnershipBrowserView(bot=self.bot)
        await ctx.followup.send(
            content="Select a user below to see ownership info:",
            view=view,
            ephemeral=True,
            delete_after=30.0
        )

    @ownership_group.command(name="transfer_full", description="Transfer 100% ownership of a sub.")
    async def transfer_full_command(
        self,
        ctx: discord.ApplicationContext,
        sub_id: Option(int, "Sub ID"),
        new_owner_id: Option(str, "New owner ID"),
        sale_amount: Option(int, "Sale amount in credits", default=0),
    ):
        await ctx.defer(ephemeral=True)
        try:
            new_owner_id_int = int(new_owner_id)
        except ValueError:
            return await ctx.followup.send("New owner ID must be numeric.", ephemeral=True, delete_after=30.0)

        if not await self.is_primary_owner(ctx.author.id, sub_id):
            return await ctx.followup.send("You are not the primary owner.", ephemeral=True, delete_after=30.0)

        success, msg = await self.transfer_full_ownership(
            sub_id, ctx.author.id, new_owner_id_int, sale_amount
        )
        if success:
            await ctx.followup.send(
                f"Sub {sub_id} fully transferred to <@{new_owner_id_int}>. {msg}",
                ephemeral=True
            )
        else:
            await ctx.followup.send(f"Transfer failed: {msg}", ephemeral=True, delete_after=30.0)

    @ownership_group.command(name="transfer_partial", description="Transfer partial shares of a sub.")
    async def transfer_partial_command(
        self,
        ctx: discord.ApplicationContext,
        sub_id: Option(int, "Sub ID"),
        buyer_id: Option(str, "Buyer user ID"),
        shares: Option(int, "Shares % (1-99)"),
        sale_amount: Option(int, "Sale amount in credits", default=0),
    ):
        await ctx.defer(ephemeral=True)
        try:
            buyer_id_int = int(buyer_id)
        except ValueError:
            return await ctx.followup.send("Buyer user ID must be numeric.", ephemeral=True, delete_after=30.0)

        if not await self.has_enough_shares(ctx.author.id, sub_id, shares):
            return await ctx.followup.send(
                f"You do not have {shares}% in sub {sub_id}.",
                ephemeral=True
            )

        success, msg = await self.transfer_partial_ownership(
            sub_id, ctx.author.id, buyer_id_int, shares, sale_amount
        )
        if success:
            await ctx.followup.send(
                f"You transferred {shares}% of sub {sub_id} to <@{buyer_id_int}>. {msg}",
                ephemeral=True
            )
        else:
            await ctx.followup.send(f"Partial transfer failed: {msg}", ephemeral=True, delete_after=30.0)

    @ownership_group.command(name="info", description="View sub ownership info (ephemeral).")
    async def info_command(self, ctx: discord.ApplicationContext, sub_id: int):
        await ctx.defer(ephemeral=True)
        embed = await self.build_sub_info_embed(sub_id)
        await ctx.followup.send(embed=embed, ephemeral=True, delete_after=30.0)

    @ownership_group.command(name="claim", description="Request ownership of a user.")
    async def claim_cmd(self, ctx: discord.ApplicationContext, sub_user: Option(discord.Member, "User to claim")):
        await ctx.defer(ephemeral=True)
        sub_joined_delta = discord.utils.utcnow() - sub_user.joined_at
        if sub_joined_delta.total_seconds() < self.membership_minimum_secs:
            return await ctx.followup.send(
                "That user hasn't been here 24 hours. Claim disallowed.", ephemeral=True
            )
        owner_joined_delta = discord.utils.utcnow() - ctx.user.joined_at
        if owner_joined_delta.total_seconds() < self.membership_minimum_secs:
            return await ctx.followup.send(
                "You haven't been here 24 hours. Claim disallowed.", ephemeral=True
            )
        if await self.check_has_majority_owner(sub_user.id):
            return await ctx.followup.send("User already has a majority owner.", ephemeral=True, delete_after=30.0)

        claim_id = await self.create_claim_record(ctx.author.id, sub_user.id)
        staff_ch = self.bot.get_channel(self.staff_ledger_channel_id)
        if staff_ch:
            staff_embed = await self.build_staff_claim_embed(claim_id, ctx.author, sub_user)
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
            sub_embed = await self.build_sub_claim_embed(claim_id, ctx.author, sub_user)
            sub_view = OwnershipClaimSubView(self.bot, claim_id, timeout=None)
            sub_msg = await dm_ch.send(
                content=f"You are being claimed by {ctx.author.mention}!",
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
            f"Ownership claim initiated for {sub_user.mention} (#{claim_id}). Staff + sub must approve.",
            ephemeral=True
        )

    # ─────────────────────────────────────────────────────────────────
    # Unified Helper for DM Requests
    # ─────────────────────────────────────────────────────────────────
    async def handle_dm_request(
        self,
        requestor: discord.Member,
        target_user: discord.Member,
        interaction: discord.Interaction,
        view_to_disable_button: Optional[discord.ui.View] = None,
    ):
        """
        Called by both ephemeral and persistent views' "Request DM" button.
        Checks cooldown, dm_status, and triggers the ask-flow if necessary.
        Also disables the request DM button to prevent spam.
        """
        # Check cooldown
        now = time.time()
        last_req = self.dm_request_cooldowns.get(requestor.id, 0)
        if now - last_req < self.dm_request_cooldown:
            remaining = int(self.dm_request_cooldown - (now - last_req))
            await interaction.response.send_message(
                f"You are on cooldown. Please wait {remaining} seconds before requesting DM again.",
                ephemeral=True
            )
            return

        # Record the new cooldown
        self.dm_request_cooldowns[requestor.id] = now

        # If the parent view is provided, disable its "Request DM" button now.
        if view_to_disable_button:
            for child in view_to_disable_button.children:
                if getattr(child, "custom_id", "") in ["browseview_request_dm_btn", "singleuser_request_dm"]:
                    child.disabled = True

        # We'll fetch dm_status from the DB
        row = await self.bot.db.fetchrow(
            "SELECT dm_status FROM user_roles WHERE user_id=$1;",
            target_user.id
        )
        dm_status = (row["dm_status"] if row else "closed").lower()

        if "open" in dm_status:
            await interaction.response.send_message(
                "That user is open to DMs! Feel free to message them directly.",
                ephemeral=True
            )
        elif "closed" in dm_status:
            await interaction.response.send_message(
                "They have closed DMs. You cannot DM them at this time.",
                ephemeral=True
            )
        elif dm_status.startswith("ask"):
            # 'ask' or 'ask owner'
            if "ask to" in dm_status:
                # The target_user must personally approve
                await self.start_ask_flow(
                    requestor=requestor,
                    approver=target_user,
                    reason="ask",
                    interaction=interaction
                )
            elif "ask owner to" in dm_status:
                # We must find the majority owner and ask them
                owner_id = await self.find_majority_owner(target_user.id)
                if owner_id:
                    guild = interaction.guild
                    owner_member = guild.get_member(owner_id) if guild else None
                    if owner_member:
                        await self.start_ask_flow(
                            requestor=requestor,
                            approver=owner_member,
                            reason="ask owner",
                            interaction=interaction
                        )
                    else:
                        await interaction.response.send_message(
                            "No valid owner found or owner not in guild. Cannot proceed.",
                            ephemeral=True
                        )
                else:
                    await interaction.response.send_message(
                        "No majority owner found; cannot request approval.",
                        ephemeral=True
                    )
        else:
            # unknown or not set
            await interaction.response.send_message(
                "DM status unknown or not set; cannot request DM.",
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
        1) Creates a log embed in ask_to_dm channel (color = yellow).
        2) Sends a DM to the 'approver' with an approval view (AskForDMApprovalView).
        """
        channel = self.bot.get_channel(self.ask_to_dm_channel_id)
        if not channel:
            await interaction.response.send_message(
                "ask_to_dm channel not found. Cannot proceed.",
                ephemeral=True
            )
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
        embed.set_footer(text="No actions can be taken here; see your DM to approve or deny.")
        log_msg = await channel.send(embed=embed)

        # Try DMing the approver
        try:
            dm = await approver.create_dm()
            view = AskForDMApprovalView(
                bot=self.bot,
                requestor=requestor,
                log_message=log_msg
            )
            dm_embed = discord.Embed(
                title="DM Request Received",
                description=(
                    f"{requestor.mention} is requesting permission to DM.\n"
                    "Click **Accept** or **Deny**, and optionally provide a reason."
                ),
                color=discord.Color.gold()
            )
            await dm.send(embed=dm_embed, view=view)
            await interaction.response.send_message(
                f"A DM approval request has been sent to {approver.mention}.",
                ephemeral=True
            )
        except discord.Forbidden:
            new_desc = embed.description + "\n\n**Failed to DM the approver (Forbidden).**"
            new_embed = discord.Embed(
                title="DM Request Failed to Send",
                description=new_desc,
                color=discord.Color.red()
            )
            await log_msg.edit(embed=new_embed)
            await interaction.response.send_message(
                "Failed to DM the approver (Forbidden).",
                ephemeral=True
            )

    async def find_majority_owner(self, user_id: int) -> Optional[int]:
        rec = await self.bot.db.fetchrow(
            "SELECT user_id FROM sub_ownership WHERE sub_id=$1 ORDER BY percentage DESC LIMIT 1;",
            user_id
        )
        return rec["user_id"] if rec else None

    # ─────────────────────────────────────────────────────────────────
    # Claims Helpers
    # ─────────────────────────────────────────────────────────────────
    async def check_has_majority_owner(self, user_id: int) -> bool:
        row = await self.bot.db.fetchrow(
            "SELECT primary_owner_id FROM subs WHERE user_id=$1;",
            user_id
        )
        if row and row["primary_owner_id"]:
            return True
        row2 = await self.bot.db.fetchrow(
            "SELECT 1 FROM sub_ownership WHERE sub_id=$1 AND percentage >= 50;",
            user_id
        )
        return bool(row2)

    async def create_claim_record(self, owner_id: int, sub_id: int) -> int:
        row = await self.bot.db.fetchrow(
            """
            INSERT INTO claims (owner_id, sub_id, staff_approvals, sub_approved, status)
            VALUES ($1, $2, 0, FALSE, 'pending')
            RETURNING id;
            """,
            owner_id, sub_id
        )
        return row["id"]

    async def build_staff_claim_embed(self, claim_id: int, owner: discord.Member, sub: discord.Member) -> discord.Embed:
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
        embed = discord.Embed(
            title=f"Ownership Claim #{claim_id}",
            description=(
                f"{owner.mention} wants to claim you.\n"
                "Click Approve or Deny.\n"
                "If you do nothing, staff may require your input later."
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Think carefully before consenting!")
        return embed

    async def staff_approve_claim(self, claim_id: int, staff_id: int):
        # Check if already approved by this staffer
        row = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims_staff_approvals WHERE claim_id=$1 AND staff_id=$2;",
            claim_id, staff_id
        )
        if row:
            return
        await self.bot.db.execute(
            "INSERT INTO claims_staff_approvals (claim_id, staff_id) VALUES ($1, $2);",
            claim_id, staff_id
        )
        await self.bot.db.execute(
            "UPDATE claims SET staff_approvals=staff_approvals+1 WHERE id=$1;",
            claim_id
        )
        await self.finalize_claim_if_ready(claim_id)

    async def staff_deny_claim(self, claim_id: int, staff_id: int):
        await self.bot.db.execute(
            "UPDATE claims SET status='denied' WHERE id=$1;",
            claim_id
        )
        ledger_ch = self.bot.get_channel(self.staff_ledger_channel_id)
        if ledger_ch:
            await ledger_ch.send(f"Claim #{claim_id} denied by staff <@{staff_id}>.")

    async def sub_approve_claim(self, claim_id: int, user_id: int):
        row = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not row or row["status"] != "pending":
            return
        if row["sub_id"] != user_id:
            return
        await self.bot.db.execute(
            "UPDATE claims SET sub_approved=TRUE WHERE id=$1;",
            claim_id
        )
        await self.finalize_claim_if_ready(claim_id)

    async def sub_deny_claim(self, claim_id: int, user_id: int):
        row = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not row or row["status"] != "pending":
            return
        if row["sub_id"] != user_id:
            return
        await self.bot.db.execute(
            "UPDATE claims SET status='denied' WHERE id=$1;",
            claim_id
        )
        ledger_ch = self.bot.get_channel(self.staff_ledger_channel_id)
        if ledger_ch:
            await ledger_ch.send(f"Claim #{claim_id} denied by sub <@{user_id}>.")

    async def finalize_claim_if_ready(self, claim_id: int):
        row = await self.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", claim_id)
        if not row or row["status"] != "pending":
            return
        staff_approvals = row["staff_approvals"]
        sub_approved = row["sub_approved"]
        if staff_approvals >= 2 and sub_approved:
            # finalize
            await self.bot.db.execute(
                "UPDATE claims SET status='approved' WHERE id=$1;",
                claim_id
            )
            await self.bot.db.execute(
                "DELETE FROM sub_ownership WHERE sub_id=$1;",
                row["sub_id"]
            )
            await self.bot.db.execute(
                "INSERT INTO sub_ownership (sub_id, user_id, percentage) VALUES ($1, $2, 100);",
                row["sub_id"], row["owner_id"]
            )
            await self.bot.db.execute(
                "UPDATE subs SET primary_owner_id=$1 WHERE user_id=$2;",
                row["owner_id"], row["sub_id"]
            )
            ledger_ch = self.bot.get_channel(self.staff_ledger_channel_id)
            if ledger_ch:
                await ledger_ch.send(
                    f"Claim #{claim_id} APPROVED. <@{row['owner_id']}> now owns <@{row['sub_id']}>."
                )

    # ─────────────────────────────────────────────────────────────────
    # Ownership logic
    # ─────────────────────────────────────────────────────────────────
    async def is_primary_owner(self, user_id: int, sub_id: int) -> bool:
        row = await self.bot.db.fetchrow(
            "SELECT 1 FROM subs WHERE id=$1 AND primary_owner_id=$2;",
            sub_id, user_id
        )
        return bool(row)

    async def has_enough_shares(self, user_id: int, sub_id: int, shares: int) -> bool:
        row = await self.bot.db.fetchrow(
            "SELECT percentage FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;",
            sub_id, user_id
        )
        return (row and row["percentage"] >= shares)

    async def transfer_full_ownership(self, sub_id: int, old_owner_id: int, new_owner_id: int, sale_amount: int):
        try:
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
                "INSERT INTO sub_ownership (sub_id, user_id, percentage) VALUES ($1, $2, 100);",
                sub_id, new_owner_id
            )
            await self.bot.db.execute(
                "UPDATE subs SET primary_owner_id=$1 WHERE id=$2;",
                new_owner_id, sub_id
            )
            return (True, "Full ownership transfer completed.")
        except Exception as e:
            return (False, f"DB error: {e}")

    async def transfer_partial_ownership(self, sub_id: int, seller_id: int, buyer_id: int, shares: int, sale_amount: int):
        try:
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
                "UPDATE sub_ownership SET percentage=percentage-$1 WHERE sub_id=$2 AND user_id=$3;",
                shares, sub_id, seller_id
            )
            row = await self.bot.db.fetchrow(
                "SELECT 1 FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;",
                sub_id, buyer_id
            )
            if row:
                await self.bot.db.execute(
                    "UPDATE sub_ownership SET percentage=percentage+$1 WHERE sub_id=$2 AND user_id=$3;",
                    shares, sub_id, buyer_id
                )
            else:
                await self.bot.db.execute(
                    "INSERT INTO sub_ownership (sub_id, user_id, percentage) VALUES ($1, $2, $3);",
                    sub_id, buyer_id, shares
                )
            return (True, "Partial ownership transfer completed.")
        except Exception as e:
            return (False, f"DB error: {e}")

    async def user_balance(self, user_id: int) -> int:
        row = await self.bot.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", user_id)
        if not row:
            await self.bot.db.execute("INSERT INTO wallets (user_id,balance) VALUES ($1,0);", user_id)
            return 0
        return row["balance"]

    async def build_sub_info_embed(self, sub_id: int) -> discord.Embed:
        embed = discord.Embed(title=f"Sub #{sub_id} Info", color=discord.Color.blue())
        owners = await self.bot.db.fetch(
            "SELECT user_id, percentage FROM sub_ownership WHERE sub_id=$1 ORDER BY percentage DESC;",
            sub_id
        )
        if owners:
            lines = [f"<@{o['user_id']}> - {o['percentage']}%" for o in owners]
            embed.add_field(name="Owners", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Owners", value="None", inline=False)

        row = await self.bot.db.fetchrow(
            "SELECT monthly_earnings, service_menu_url FROM subs WHERE id=$1;",
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

    # ─────────────────────────────────────────────────────────────────
    # Blockchain Transaction Logging
    # ─────────────────────────────────────────────────────────────────
    async def log_transaction(self, sender_id: int, recipient_id: int, amount: int, justification: str):
        """
        Inserts a new transaction into the 'transactions' table, computing
        a SHA-256 hash of this transaction + previous transaction hash,
        then logs it via an embed to the blockchain channel.
        """

        # 1) Fetch the last transaction's hash (if any)
        last_tx = await self.bot.db.fetchrow("SELECT id, hash FROM transactions ORDER BY id DESC LIMIT 1;")
        last_hash = last_tx["hash"] if last_tx else "0"

        # 2) Insert a new row (status can be 'completed' or whatever you'd like)
        row = await self.bot.db.fetchrow(
            """
            INSERT INTO transactions (sender_id, recipient_id, amount, justification, status)
            VALUES ($1, $2, $3, $4, 'completed')
            RETURNING id;
            """,
            sender_id, recipient_id, amount, justification
        )
        tx_id = row["id"]

        # 3) Compute the chain-based hash
        to_hash = f"{tx_id}{sender_id}{recipient_id}{amount}{justification}{last_hash}"
        tx_hash = hashlib.sha256(to_hash.encode()).hexdigest()

        # 4) Update the transaction with the computed hash
        await self.bot.db.execute(
            "UPDATE transactions SET hash=$1 WHERE id=$2;",
            tx_hash, tx_id
        )

        # 5) Build the transaction embed
        sender_user = self.bot.get_user(sender_id)
        recipient_user = self.bot.get_user(recipient_id)
        embed = discord.Embed(
            title="Transaction Logged",
            description="A new transaction has been recorded on the ledger.",
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
        embed.add_field(name="Justification", value=f"```{justification}```" or "No memo", inline=False)
        embed.add_field(name="Transaction Hash", value=f"```{tx_hash}```", inline=False)

        # 6) Send the embed to the designated blockchain transaction channel
        tx_channel = self.bot.get_channel(self.blockchain_channel_id)
        if tx_channel:
            await tx_channel.send(embed=embed)


# ─────────────────────────────────────────────────────────────────
# Ephemeral View (browse)
# ─────────────────────────────────────────────────────────────────
class OwnershipBrowserView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=600)
        self.bot = bot
        self.current_user_id = None

        # add the user-select
        self.user_select = OwnershipUserSelect(self)
        self.add_item(self.user_select)
    
    async def update_embed_for_user(self, interaction: discord.Interaction, user_id: int):
        self.current_user_id = user_id
        embed = discord.Embed(
            title=f"Ownership Browser: <@{user_id}>",
            color=discord.Color.gold()
        )
        row = await self.bot.db.fetchrow(
            "SELECT dm_status FROM user_roles WHERE user_id=$1;",
            user_id
        )
        dm_status = row["dm_status"] if row else "unknown"

        embed.add_field(
            name="User Info",
            value=f"DM status: **{dm_status}**\nUse the buttons below to request DM or transact.",
            inline=False
        )
        embed.set_footer(text="Use the buttons below.")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="Request DM",
        style=discord.ButtonStyle.primary,
        row=2,
        custom_id="browseview_request_dm_btn"
    )
    async def request_dm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.current_user_id:
            return await interaction.response.send_message("Select a user first!", ephemeral=True, delete_after=30.0)

        target_user = interaction.guild.get_member(self.current_user_id)
        if not target_user:
            return await interaction.response.send_message("User not in guild or not found.", ephemeral=True, delete_after=30.0)

        ownership_cog: OwnershipCog = self.bot.get_cog("OwnershipCog")
        if ownership_cog:
            await ownership_cog.handle_dm_request(
                requestor=interaction.user,
                target_user=target_user,
                interaction=interaction,
                view_to_disable_button=self
            )

    @discord.ui.button(
        label="Transact",
        style=discord.ButtonStyle.secondary,
        row=2,
        custom_id="browseview_transact_btn"
    )
    async def transact_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.current_user_id:
            return await interaction.response.send_message("Select a user first!", ephemeral=True, delete_after=30.0)
        modal = TransactModal(target_user_id=self.current_user_id)
        await interaction.response.send_modal(modal)


class OwnershipUserSelect(discord.ui.Select):
    """
    A user-select component (PyCord 2.6+).
    """
    def __init__(self, parent_view: OwnershipBrowserView):
        super().__init__(
            placeholder="Select a user...",
            min_values=1,
            max_values=1,
            custom_id="browseview_user_select",
            select_type=discord.ComponentType.user_select
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # self.values is a list of selected users, each .id is the user ID
        # We'll assume only one user selected
        selected_user = self.values[0]
        user_id = int(selected_user.id)
        await self.parent_view.update_embed_for_user(interaction, user_id)


# ─────────────────────────────────────────────────────────────────
# SingleUserOwnershipView (Persistent)
# ─────────────────────────────────────────────────────────────────
class SingleUserOwnershipView(discord.ui.View):
    """
    Extended version of SingleUserOwnershipView to handle
    a 'DM request requiring approval' flow.
    """
    def __init__(self, bot: commands.Bot, target_user: discord.Member, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.target_user = target_user

    @discord.ui.button(
        label="Request DM",
        style=discord.ButtonStyle.primary,
        custom_id="singleuser_request_dm"
    )
    async def request_dm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        cog: OwnershipCog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.handle_dm_request(
                requestor=interaction.user,
                target_user=self.target_user,
                interaction=interaction,
                view_to_disable_button=self
            )


# ─────────────────────────────────────────────────────────────────
# Approval Flow for "ask" or "ask owner"
# ─────────────────────────────────────────────────────────────────
class AskForDMApprovalView(discord.ui.View):
    """
    This view is DM'd to the 'approver' (target user or their owner).
    It has two buttons: Accept and Deny.
    Clicking either will open a modal for optional justification.
    """
    def __init__(
        self,
        bot: commands.Bot,
        requestor: discord.Member,
        log_message: discord.Message
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.requestor = requestor
        self.log_message = log_message
        self.approval_action = None  # "accepted" or "denied"

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="dm_approval_accept")
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.approval_action = "accepted"
        await interaction.response.send_modal(
            AskForDMJustificationModal(parent_view=self, action="accepted")
        )

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="dm_approval_deny")
    async def deny_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.approval_action = "denied"
        await interaction.response.send_modal(
            AskForDMJustificationModal(parent_view=self, action="denied")
        )

    async def finalize_request(self, interaction: discord.Interaction, action: str, justification: str):
        """
        Called from the modal once the user has submitted the optional justification.
        Edits the log embed in ask_to_dm channel to reflect acceptance or rejection.
        """
        self.disable_all_items()
        await interaction.message.edit(view=self)  # disable the buttons in DM

        original_embed = self.log_message.embeds[0]
        desc_lines = original_embed.description.split("\n")
        for i, line in enumerate(desc_lines):
            if "Status:" in line:
                desc_lines[i] = f"Status: **{action.title()}**"
                break

        new_embed = discord.Embed(
            title="DM Request",
            description="\n".join(desc_lines),
            color=discord.Color.green() if action == "accepted" else discord.Color.red()
        )
        if justification.strip():
            new_embed.add_field(name="Justification", value=justification, inline=False)
        new_embed.set_footer(text=original_embed.footer.text)
        await self.log_message.edit(embed=new_embed)


class AskForDMJustificationModal(discord.ui.Modal):
    def __init__(self, parent_view: AskForDMApprovalView, action: str):
        super().__init__(title=f"DM Request: {action.capitalize()}")
        self.parent_view = parent_view
        self.action = action

        self.text_input = discord.ui.InputText(
            label="Optional Justification",
            style=discord.InputTextStyle.long,
            required=False,
            placeholder="(You can leave this blank...)"
        )
        self.add_item(self.text_input)

    async def callback(self, interaction: discord.Interaction):
        user_text = self.text_input.value.strip()
        await self.parent_view.finalize_request(
            interaction=interaction,
            action=self.action,
            justification=user_text
        )
        await interaction.response.send_message(
            f"You have **{self.action}** the DM request.",
            ephemeral=True
        )


# ─────────────────────────────────────────────────────────────────
# Transaction Modal (calls the blockchain logger)
# ─────────────────────────────────────────────────────────────────
class TransactModal(discord.ui.Modal):

    def __init__(self, target_user_id: int):
        super().__init__(title="Transaction")
        
        self.amount = discord.ui.InputText(
            label="Amount (credits)",
            placeholder="Ex: 100",
            style=discord.InputTextStyle.short
        )
        
        self.justification = discord.ui.InputText(
            label="Justification",
            placeholder="Reason or memo (optional)",
            style=discord.InputTextStyle.long,
            required=False
        )
        
        self.target_user_id = target_user_id
        self.add_item(self.amount)
        self.add_item(self.justification)

    async def callback(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("Invalid amount, must be an integer.", ephemeral=True, delete_after=30.0)
        if amt <= 0:
            return await interaction.response.send_message("Amount must be > 0.", ephemeral=True, delete_after=30.0)

        memo = self.justification.value or "No memo"
        sender_id = interaction.user.id
        receiver_id = self.target_user_id

        if sender_id == receiver_id:
            return await interaction.response.send_message("You can't pay yourself.", ephemeral=True, delete_after=30.0)

        # Ensure we have a wallet row for the sender
        row = await interaction.client.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", sender_id)
        sender_balance = row["balance"] if row else 0
        if sender_balance < amt:
            return await interaction.response.send_message("Insufficient funds.", ephemeral=True, delete_after=30.0)

        # Deduct from sender
        await interaction.client.db.execute(
            "UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;",
            amt, sender_id
        )
        # Ensure wallet for recipient
        row2 = await interaction.client.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", receiver_id)
        if not row2:
            await interaction.client.db.execute("INSERT INTO wallets (user_id,balance) VALUES($1,0);", receiver_id)
        # Add to recipient
        await interaction.client.db.execute(
            "UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;",
            amt, receiver_id
        )

        # Call the cog to log this transaction to the blockchain ledger
        ownership_cog = interaction.client.get_cog("OwnershipCog")
        if ownership_cog:
            await ownership_cog.log_transaction(sender_id, receiver_id, amt, memo)

        await interaction.response.send_message(
            f"Transaction successful! You sent {amt} credits to <@{receiver_id}>.\n"
            f"**Justification:** {memo}",
            ephemeral=True
        )


# ─────────────────────────────────────────────────────────────────
# STAFF & SUB Claim Views (Persistent => custom_id required)
# ─────────────────────────────────────────────────────────────────
class OwnershipClaimStaffView(discord.ui.View):
    def __init__(self, bot: commands.Bot, claim_id: int, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.claim_id = claim_id

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="claim_staff_approve"
    )
    async def approve_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        ownership_cog = self.bot.get_cog("OwnershipCog")
        if ownership_cog:
            await ownership_cog.staff_approve_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="claim_staff_deny"
    )
    async def deny_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        ownership_cog = self.bot.get_cog("OwnershipCog")
        if ownership_cog:
            await ownership_cog.staff_deny_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)


class OwnershipClaimSubView(discord.ui.View):
    def __init__(self, bot: commands.Bot, claim_id: int, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.claim_id = claim_id

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        emoji="🤝",
        custom_id="claim_sub_approve"
    )
    async def approve_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        ownership_cog = self.bot.get_cog("OwnershipCog")
        if ownership_cog:
            await ownership_cog.sub_approve_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        emoji="🚫",
        custom_id="claim_sub_deny"
    )
    async def deny_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        ownership_cog = self.bot.get_cog("OwnershipCog")
        if ownership_cog:
            await ownership_cog.sub_deny_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)


def setup(bot: commands.Bot):
    bot.add_cog(OwnershipCog(bot))

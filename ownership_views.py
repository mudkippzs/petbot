import discord
import datetime
from discord.ext import commands
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ------------------------------------------------------
# Legacy Staff & Sub Views
# ------------------------------------------------------
class OwnershipClaimStaffView(discord.ui.View):
    """
    View for staff to Approve or Deny a legacy claim.
    Approval/denial is handed off to OwnershipCog methods:
      - staff_approve_claim(...)
      - staff_deny_claim(...)
    """
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
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.staff_approve_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="claim_staff_deny"
    )
    async def deny_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.staff_deny_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)


class OwnershipClaimSubView(discord.ui.View):
    """
    View for a sub to Approve or Deny a legacy claim (staff + sub needed).
    """
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
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.sub_approve_claim(self.claim_id, interaction.user.id)
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
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.sub_deny_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)


# ------------------------------------------------------
# SingleUserOwnershipView (DM-based, from "🔍" Reaction)
# ------------------------------------------------------
class SingleUserOwnershipView(discord.ui.View):
    """
    DM-based 'single user' browser for a particular target_user.
    Offers:
      - Request DM / Close DM
      - Transact
      - Propose Claim (if user is male and DMs are open)
    """
    def __init__(self, bot: commands.Bot, target_user: discord.Member, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.target_user = target_user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Optionally restrict usage to only the invoker or staff
        return True

    async def on_timeout(self):
        self.disable_all_items()
        # Optionally edit the message to reflect inactivity.

    @discord.ui.button(label="Request DM", style=discord.ButtonStyle.primary, custom_id="singleuser_request_dm")
    async def request_dm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            return

        row = await self.bot.db.fetchrow(
            """
            SELECT active FROM open_dm_perms
            WHERE (user1_id=$1 AND user2_id=$2) OR (user1_id=$2 AND user2_id=$1);
            """,
            interaction.user.id, self.target_user.id
        )
        if row and row["active"]:
            # DM open -> close it
            await cog.close_dm_pair(interaction.user.id, self.target_user.id, reason="user_closed_via_single_view")
            await interaction.response.send_message("You have **closed** DMs with this user.", ephemeral=True)
            button.label = "Request DM"
            button.disabled = False
            await interaction.message.edit(view=self)
        else:
            # Not open -> request
            await cog.handle_dm_request(
                requestor=interaction.user,
                target_user=self.target_user,
                interaction=interaction,
                view_to_disable_button=self
            )

    @discord.ui.button(label="Transact", style=discord.ButtonStyle.secondary, custom_id="singleuser_transact_btn")
    async def transact_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = TransactModal(target_user_id=self.target_user.id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Propose Claim", style=discord.ButtonStyle.blurple, custom_id="singleuser_propose_claim")
    async def propose_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        For owners to propose partial or direct claims (assuming DMs open).
        """
        # 1) Find the OwnershipCog
        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            # If for some reason the cog is missing, just exit
            return

        # 2) Verify open DMs between the two parties
        row = await self.bot.db.fetchrow(
            """
            SELECT 1
            FROM open_dm_perms
            WHERE ((user1_id = $1 AND user2_id = $2) OR (user1_id = $2 AND user2_id = $1))
              AND active = TRUE;
            """,
            interaction.user.id, self.target_user.id
        )
        if not row:
            return await interaction.response.send_message(
                "DMs are not open between you and this user. You must open DMs first.",
                ephemeral=True
            )

        # 3) Fetch members from your guild (adjust logic if multiple guilds)
        if not cog.bot.guilds:
            return await interaction.response.send_message(
                "Bot is not currently in any guilds!",
                ephemeral=True
            )
        guild = cog.bot.guilds[0]

        try:
            owner_member = await guild.fetch_member(interaction.user.id)
            sub_member = await guild.fetch_member(self.target_user.id)
        except discord.NotFound:
            return await interaction.response.send_message(
                "Could not fetch both users from the guild.",
                ephemeral=True
            )

        # 4) Check roles
        if cog.owner_role_id not in [r.id for r in owner_member.roles]:
            return await interaction.response.send_message(
                "You must be a male (owner) to claim a sub.",
                ephemeral=True
            )
        if cog.sub_role_id not in [r.id for r in sub_member.roles]:
            return await interaction.response.send_message(
                "The target user is not a sub (female).",
                ephemeral=True
            )

        # 5) Check if a claim already exists (either sub has a pending claim or you already claimed them)
        row_sub_claim = await self.bot.db.fetchrow(
            """
            SELECT 1 
            FROM claims 
            WHERE sub_id = $1 
              AND status IN ('pending','countered');
            """,
            self.target_user.id
        )
        if row_sub_claim:
            return await interaction.response.send_message(
                "That user already has a pending claim!",
                ephemeral=True
            )

        row_owner_sub = await self.bot.db.fetchrow(
            """
            SELECT 1 
            FROM claims 
            WHERE owner_id = $1 
              AND sub_id = $2 
              AND status IN ('pending','countered');
            """,
            interaction.user.id, self.target_user.id
        )
        if row_owner_sub:
            return await interaction.response.send_message(
                "You already have a pending claim on them.",
                ephemeral=True
            )

        # 6) Check your (the owner's) cooldown
        if await cog.user_on_cooldown(interaction.user.id):
            cd_end = await cog.get_user_cooldown(interaction.user.id)
            remain_hrs = (cd_end - datetime.datetime.utcnow()).total_seconds() / 3600
            return await interaction.response.send_message(
                f"You are on cooldown for {remain_hrs:.1f} more hours.",
                ephemeral=True
            )

        # 7) Decide partial or direct claim
        majority_owner_id, majority_share = await cog.find_majority_owner(self.target_user.id)
        if majority_owner_id and majority_share >= 50:
            # PARTIAL CLAIM
            modal = PartialClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user,
                majority_owner_id=majority_owner_id
            )
            await interaction.response.send_modal(modal)
        else:
            # DIRECT CLAIM
            modal = DirectClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user
            )
            await interaction.response.send_modal(modal)


# ------------------------------------------------------
# AskForDMApprovalView (for user or majority-owner approval)
# ------------------------------------------------------
class AskForDMApprovalView(discord.ui.View):
    """
    Presented to the sub or the majority owner so they can accept/deny DM requests from an owner.
    """
    def __init__(self, bot: commands.Bot, requestor: discord.Member, log_message: discord.Message):
        super().__init__(timeout=None)
        self.bot = bot
        self.requestor = requestor
        self.log_message = log_message
        self.approval_action = None

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
        self.disable_all_items()
        await interaction.message.edit(view=self)

        # Update the log embed
        original_embed = self.log_message.embeds[0]
        desc_lines = original_embed.description.split("\n")
        for i, line in enumerate(desc_lines):
            if "Status:" in line:
                desc_lines[i] = f"Status: **{action.title()}**"
                break
        new_desc = "\n".join(desc_lines)

        new_embed = discord.Embed(
            title="DM Request",
            description=new_desc,
            color=discord.Color.green() if action == "accepted" else discord.Color.red()
        )
        if justification.strip():
            new_embed.add_field(name="Justification", value=justification, inline=False)

        await self.log_message.edit(embed=new_embed)

        # If accepted, open DM perms
        if action == "accepted":
            cog = self.bot.get_cog("OwnershipCog")
            if cog:
                await cog.add_open_dm_pair(self.requestor.id, interaction.user.id, reason="approved_by_user_or_owner")

        await interaction.response.send_message(
            f"You have **{action}** the DM request.",
            ephemeral=True
        )


class AskForDMJustificationModal(discord.ui.Modal):
    """
    Modal for providing an optional reason when accepting or denying a DM request.
    """
    def __init__(self, parent_view: AskForDMApprovalView, action: str):
        super().__init__(title=f"DM Request: {action.capitalize()}")
        self.parent_view = parent_view
        self.action = action

        self.text_input = discord.ui.InputText(
            label="Optional Justification",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.text_input)

    async def callback(self, interaction: discord.Interaction):
        reason = self.text_input.value.strip()
        await self.parent_view.finalize_request(interaction, self.action, reason)


# ------------------------------------------------------
# Ephemeral "browse" view (/ownership browse)
# ------------------------------------------------------
class OwnershipBrowserView(discord.ui.View):
    """
    Slash-based ephemeral UI for selecting a user, then performing:
      - Request DM / Close DM
      - Transaction
      - Propose Claim
    """
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=600)
        self.bot = bot
        self.current_user_id: Optional[int] = None

        self.user_select = OwnershipUserSelect(self)
        self.add_item(self.user_select)

    @discord.ui.button(
        label="Request DM",
        style=discord.ButtonStyle.primary,
        row=2,
        custom_id="browseview_request_dm_btn"
    )
    async def request_dm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.current_user_id:
            return await interaction.response.send_message("Select a user first!", ephemeral=True)

        target_member = interaction.guild.get_member(self.current_user_id)
        if not target_member:
            return await interaction.response.send_message("User not found.", ephemeral=True)

        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            return

        # Check if DMs are open
        row = await self.bot.db.fetchrow(
            """
            SELECT active FROM open_dm_perms
            WHERE (user1_id=$1 AND user2_id=$2) OR (user1_id=$2 AND user2_id=$1);
            """,
            interaction.user.id, target_member.id
        )
        if row and row["active"]:
            # => close DM
            await cog.close_dm_pair(interaction.user.id, target_member.id, reason="user_closed_via_browseview")
            await interaction.response.send_message("You have **closed** DMs with this user.", ephemeral=True)
            button.label = "Request DM"
            button.disabled = False
            await interaction.edit_original_response(view=self)
        else:
            # => request DM
            await cog.handle_dm_request(
                requestor=interaction.user,
                target_user=target_member,
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
            return await interaction.response.send_message("Select a user first!", ephemeral=True)

        modal = TransactModal(target_user_id=self.current_user_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Propose Claim", style=discord.ButtonStyle.blurple, row=2, custom_id="singleuser_propose_claim")
    async def propose_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        For owners to propose partial or direct claims (assuming DMs open).
        """

        # 1) Find the OwnershipCog
        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            # If for some reason the cog is missing, just exit
            return

        # 2) Verify open DMs between the two parties
        row = await self.bot.db.fetchrow(
            """
            SELECT 1
            FROM open_dm_perms
            WHERE ((user1_id = $1 AND user2_id = $2) OR (user1_id = $2 AND user2_id = $1))
              AND active = TRUE;
            """,
            interaction.user.id, self.target_user.id
        )
        if not row:
            return await interaction.response.send_message(
                "DMs are not open between you and this user. You must open DMs first.",
                ephemeral=True
            )

        # 3) Fetch members from your guild (adjust logic if multiple guilds)
        if not cog.bot.guilds:
            return await interaction.response.send_message(
                "Bot is not currently in any guilds!",
                ephemeral=True
            )
        guild = cog.bot.guilds[0]

        try:
            owner_member = await guild.fetch_member(interaction.user.id)
            sub_member = await guild.fetch_member(self.target_user.id)
        except discord.NotFound:
            return await interaction.response.send_message(
                "Could not fetch both users from the guild.",
                ephemeral=True
            )

        # 4) Check roles
        if cog.owner_role_id not in [r.id for r in owner_member.roles]:
            return await interaction.response.send_message(
                "You must be a male (owner) to claim a sub.",
                ephemeral=True
            )
        if cog.sub_role_id not in [r.id for r in sub_member.roles]:
            return await interaction.response.send_message(
                "The target user is not a sub (female).",
                ephemeral=True
            )

        # 5) Check if a claim already exists (either sub has a pending claim or you already claimed them)
        row_sub_claim = await self.bot.db.fetchrow(
            """
            SELECT 1 
            FROM claims 
            WHERE sub_id = $1 
              AND status IN ('pending','countered');
            """,
            self.target_user.id
        )
        if row_sub_claim:
            return await interaction.response.send_message(
                "That user already has a pending claim!",
                ephemeral=True
            )

        row_owner_sub = await self.bot.db.fetchrow(
            """
            SELECT 1 
            FROM claims 
            WHERE owner_id = $1 
              AND sub_id = $2 
              AND status IN ('pending','countered');
            """,
            interaction.user.id, self.target_user.id
        )
        if row_owner_sub:
            return await interaction.response.send_message(
                "You already have a pending claim on them.",
                ephemeral=True
            )

        # 6) Check your (the owner's) cooldown
        if await cog.user_on_cooldown(interaction.user.id):
            cd_end = await cog.get_user_cooldown(interaction.user.id)
            remain_hrs = (cd_end - datetime.datetime.utcnow()).total_seconds() / 3600
            return await interaction.response.send_message(
                f"You are on cooldown for {remain_hrs:.1f} more hours.",
                ephemeral=True
            )

        # 7) Decide partial or direct claim
        majority_owner_id, majority_share = await cog.find_majority_owner(self.target_user.id)
        if majority_owner_id and majority_share >= 50:
            # PARTIAL CLAIM
            modal = PartialClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user,
                majority_owner_id=majority_owner_id
            )
            await interaction.response.send_modal(modal)
        else:
            # DIRECT CLAIM
            modal = DirectClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user
            )
            await interaction.response.send_modal(modal)

    async def update_embed_for_user(self, interaction: discord.Interaction, user_id: int):
        """
        Called whenever the user changes selection in the user-select.
        Updates the embed with DM status, toggles button labels, etc.
        """
        self.current_user_id = user_id
        target_member = interaction.guild.get_member(user_id)
        self.target_user = target_member
        embed = discord.Embed(
            title=f"User Browser: <{target_member.display_name}>",
            color=discord.Color.gold()
        )

        # DM status from user_roles
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

        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow(query, interaction.user.id, user_id)

        if not record:
            return

        # Extract data from the query result
        wallet_balance = record["wallet_balance"] or 0
        dm_status = record["dm_status"] or "Unknown"
        has_dm_permission = record["has_dm_permission"]
        owners = ", ".join(map(str, record["owners"])) if record["owners"] else "None"
        user_details = f"""
        Age: {record['age_range'] or 'Unknown'}
        Gender: {record['gender_role'] or 'Unknown'}
        Relationship: {record['relationship'] or 'Unknown'}
        Location: {record['location'] or 'Unknown'}
        Orientation: {record['orientation'] or 'Unknown'}
        Here For: {record['here_for'] or 'Unknown'}
        Kinks: {record['kinks'] or 'Unknown'}
        """

        dms_active = bool(has_dm_permission)

        embed.add_field(name="Details", value=f"{user_details}")
        embed.add_field(name="DMs", value=f"{dm_status}")
        embed.add_field(name="DMs with you?", value=f"{has_dm_permission}")
        embed.add_field(name="Owner(s)", value=f"{owners}")
        embed.add_field(name="Wallet Balance", value=f"${wallet}")

        # Toggle the "Request DM" button
        request_dm_button = self.get_item("browseview_request_dm_btn")
        if request_dm_button:
            if dms_active:
                request_dm_button.label = "Close DM"
            else:
                request_dm_button.label = "Request DM"
            request_dm_button.disabled = False

        # Toggle "Propose Claim"
        propose_btn = self.get_item("browseview_propose_dynamic_btn")
        if propose_btn:
            # Only enable if viewer is male, target is female, and DMs are open
            user_roles = [r.id for r in interaction.user.roles]
            
            if not target_member:
                propose_btn.disabled = True
            else:
                target_roles = [r.id for r in target_member.roles]
                row_sub_claim = await self.bot.db.fetchrow(
                    "SELECT 1 FROM claims WHERE sub_id=$1 AND status IN('pending','countered');",
                    user_id
                )
                row_owner_sub = await self.bot.db.fetchrow(
                    "SELECT 1 FROM claims WHERE owner_id=$1 AND sub_id=$2 AND status IN('pending','countered');",
                    interaction.user.id, user_id
                )
                cog = self.bot.get_cog("OwnershipCog")
                if not cog:
                    propose_btn.disabled = True
                else:
                    if (
                        cog.owner_role_id not in user_roles
                        or cog.sub_role_id not in target_roles
                        or row_sub_claim
                        or row_owner_sub
                        or not dms_active
                    ):
                        propose_btn.disabled = True
                    else:
                        propose_btn.disabled = False

        embed.set_footer(text="Use the buttons below to perform actions.")
        await interaction.response.edit_message(embed=embed, view=self)


class OwnershipUserSelect(discord.ui.Select):
    """
    A user-select component that allows ephemeral picking of a user from the server
    so that the viewer can see DM status, propose claims, etc.
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
        if not self.values:
            return
        selected_user_id = int(self.values[0].id)        
        await self.parent_view.update_embed_for_user(interaction, selected_user_id)


# ------------------------------------------------------
# Transaction Modal
# ------------------------------------------------------
class TransactModal(discord.ui.Modal):
    """
    Simple modal to handle credit transactions from the user to a target.
    """
    def __init__(self, target_user_id: int):
        super().__init__(title="Transaction")
        self.target_user_id = target_user_id

        self.amount_input = discord.ui.InputText(
            label="Amount (credits)",
            required=True
        )
        self.justification_input = discord.ui.InputText(
            label="Justification",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.amount_input)
        self.add_item(self.justification_input)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("OwnershipCog")
        if not cog:
            return await interaction.response.send_message("OwnershipCog not found.", ephemeral=True)

        try:
            amount = int(self.amount_input.value)
        except ValueError:
            return await interaction.response.send_message("Invalid amount, must be integer.", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("Amount must be > 0.", ephemeral=True)

        memo = self.justification_input.value or "(no memo)"
        sender_id = interaction.user.id
        if sender_id == self.target_user_id:
            return await interaction.response.send_message("Cannot transact with yourself!", ephemeral=True)

        # Check sender balance
        sender_balance = await cog.user_balance(sender_id)
        if sender_balance < amount:
            return await interaction.response.send_message("Insufficient funds.", ephemeral=True)

        # Subtract from sender
        await interaction.client.db.execute(
            "UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;",
            amount, sender_id
        )
        # Add to recipient
        row2 = await interaction.client.db.fetchrow(
            "SELECT balance FROM wallets WHERE user_id=$1;",
            self.target_user_id
        )
        if not row2:
            await interaction.client.db.execute(
                "INSERT INTO wallets(user_id,balance) VALUES($1,0);",
                self.target_user_id
            )
        await interaction.client.db.execute(
            "UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;",
            amount, self.target_user_id
        )

        # Log on-chain / ledger
        await cog.log_transaction(sender_id, self.target_user_id, amount, memo)

        await interaction.response.send_message(
            f"Transaction success! {amount} → <@{self.target_user_id}>. Memo: {memo}",
            ephemeral=True
        )


# ------------------------------------------------------
# Partial / Direct Claim Modals
# ------------------------------------------------------
class PartialClaimModal(discord.ui.Modal):
    """
    For owners to propose partial ownership of a sub that already has
    a majority owner. We record a new claim with `requested_percentage`
    from the input, then DM the majority owner with a view so they can
    accept, counter, or reject.
    """
    def __init__(self, cog, prospective_owner: discord.Member, sub: discord.Member, majority_owner_id: int):
        super().__init__(title="Propose Partial Ownership")
        self.cog = cog
        self.prospective_owner = prospective_owner
        self.sub = sub
        self.majority_owner_id = majority_owner_id

        self.percentage_input = discord.ui.InputText(
            label="Desired % to claim (1-99)",
            required=True
        )
        self.reason_input = discord.ui.InputText(
            label="Justification / Reason",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.percentage_input)
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            requested_pct = int(self.percentage_input.value)
        except ValueError:
            return await interaction.response.send_message("Invalid percentage, must be integer.", ephemeral=True)

        if not (1 <= requested_pct < 100):
            return await interaction.response.send_message("Percentage must be in 1-99.", ephemeral=True)

        justification = self.reason_input.value or ""
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=self.cog.claim_expiry_hours)

        # Create new claim record
        row = await self.cog.bot.db.fetchrow(
            """
            INSERT INTO claims (
                owner_id,
                sub_id,
                majority_owner_id,
                requested_percentage,
                justification,
                status,
                expires_at,
                require_staff_approval
            )
            VALUES ($1,$2,$3,$4,$5,'pending',$6,$7)
            RETURNING id
            """,
            self.prospective_owner.id,
            self.sub.id,
            self.majority_owner_id,
            requested_pct,
            justification,
            expires_at,
            self.cog.require_staff_approval
        )
        claim_id = row["id"]

        # If staff approval is required, post to staff channel
        if self.cog.require_staff_approval:
            await self.cog.post_staff_verification(
                claim_id, self.prospective_owner, self.sub, requested_pct
            )

        # DM the majority owner with a view so they can Accept / Counter / Reject
        majority_user = self.cog.bot.get_user(self.majority_owner_id)
        if majority_user:
            try:
                dm_channel = await majority_user.create_dm()
                embed = discord.Embed(
                    title=f"New Partial-Ownership Claim #{claim_id}",
                    description=(
                        f"**New prospective owner:** {self.prospective_owner.mention}\n"
                        f"**Sub (female):** {self.sub.mention}\n"
                        f"**Requested %:** {requested_pct}%\n\n"
                        f"**Justification:**\n```\n{justification}\n```"
                    ),
                    color=discord.Color.orange()
                )
                view = MajorityOwnerClaimView(cog=self.cog, claim_id=claim_id)
                await dm_channel.send(
                    content="You are the majority owner for this sub. Action required:",
                    embed=embed,
                    view=view
                )
            except discord.Forbidden:
                logger.warning("Could not DM the majority owner about partial claim.")

        await interaction.response.send_message(
            f"Partial-ownership claim (#{claim_id}) created. The majority owner will be DM'd to accept, counter, or reject.",
            ephemeral=True
        )


class DirectClaimModal(discord.ui.Modal):
    """
    For owners to propose direct (100%) ownership of a sub that
    currently has no majority owner or no owners at all.
    """
    def __init__(self, cog, prospective_owner: discord.Member, sub: discord.Member):
        super().__init__(title="Propose Direct Ownership")
        self.cog = cog
        self.prospective_owner = prospective_owner
        self.sub = sub

        self.reason_input = discord.ui.InputText(
            label="Justification / Reason",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        justification = self.reason_input.value or ""
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=self.cog.claim_expiry_hours)

        row = await self.cog.bot.db.fetchrow(
            """
            INSERT INTO claims (
                owner_id,
                sub_id,
                requested_percentage,
                justification,
                status,
                expires_at,
                require_staff_approval
            )
            VALUES ($1,$2,100,$3,'pending',$4,$5)
            RETURNING id
            """,
            self.prospective_owner.id,
            self.sub.id,
            justification,
            expires_at,
            self.cog.require_staff_approval
        )
        claim_id = row["id"]

        # DM the sub (the female) to accept or reject
        try:
            dm_channel = await self.sub.create_dm()
            embed = discord.Embed(
                title=f"Ownership Claim #{claim_id}",
                description=(
                    f"{self.prospective_owner.mention} wants to claim **100% ownership** of you.\n\n"
                    f"Justification:\n```\n{justification}\n```"
                ),
                color=discord.Color.blurple()
            )
            view = SubClaimView(cog=self.cog, claim_id=claim_id)
            await dm_channel.send(
                content="You have a new direct-ownership request:",
                embed=embed,
                view=view
            )
        except discord.Forbidden:
            logger.warning("Could not DM the sub about direct claim.")

        # If staff approval is needed, notify staff
        if self.cog.require_staff_approval:
            await self.cog.post_staff_verification(
                claim_id, self.prospective_owner, self.sub, 100
            )

        await interaction.response.send_message(
            f"Direct-ownership claim (#{claim_id}) created. The sub will be DM'd to accept or reject.",
            ephemeral=True
        )


# ------------------------------------------------------
# MajorityOwnerClaimView (partial claims)
# ------------------------------------------------------
class MajorityOwnerClaimView(discord.ui.View):
    """
    Presented to the majority owner in a partial-claim scenario.
    They can Accept, Counter, or Reject the new prospective owner's claim.
    """
    def __init__(self, cog, claim_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.claim_id = claim_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow(
            "SELECT * FROM claims WHERE id=$1;", self.claim_id
        )
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("This claim is not pending/countered.", ephemeral=True)

        # Mark sub_approved => can finalize if staff not required or staff_approvals >= 2
        await self.cog.bot.db.execute(
            "UPDATE claims SET sub_approved=TRUE WHERE id=$1;",
            self.claim_id
        )

        # Check staff approvals
        if (not claim["require_staff_approval"]) or (claim["staff_approvals"] >= 2):
            await self.cog.finalize_claim(self.claim_id)
            await interaction.response.send_message("You accepted this partial claim. **Finalized**!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "You have accepted. Additional staff approval may still be required.",
                ephemeral=True
            )

        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Counter", style=discord.ButtonStyle.primary)
    async def counter_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow(
            "SELECT * FROM claims WHERE id=$1;", self.claim_id
        )
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim is not currently pending/countered.", ephemeral=True)

        modal = CounterOfferModal(cog=self.cog, claim_id=self.claim_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow(
            "SELECT * FROM claims WHERE id=$1;", self.claim_id
        )
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim is not currently pending/countered.", ephemeral=True)

        modal = MajorityRejectModal(cog=self.cog, claim_id=self.claim_id)
        await interaction.response.send_modal(modal)


class SubClaimView(discord.ui.View):
    """
    Presented to the sub (female) when a direct-ownership claim is proposed.
    They can accept or reject.
    """
    def __init__(self, cog, claim_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.claim_id = claim_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow(
            "SELECT * FROM claims WHERE id=$1;", self.claim_id
        )
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("No valid pending claim found.", ephemeral=True)

        # Mark sub_approved
        await self.cog.bot.db.execute(
            "UPDATE claims SET sub_approved=TRUE WHERE id=$1;",
            self.claim_id
        )

        # Possibly finalize
        if (not claim["require_staff_approval"]) or (claim["staff_approvals"] >= 2):
            await self.cog.finalize_claim(self.claim_id)
            await interaction.response.send_message("You accepted. **Ownership** is finalized!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "You accepted. Staff approval might still be required.",
                ephemeral=True
            )

        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow(
            "SELECT * FROM claims WHERE id=$1;", self.claim_id
        )
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("No valid pending claim to reject.", ephemeral=True)

        modal = SubRejectModal(cog=self.cog, claim_id=self.claim_id)
        await interaction.response.send_modal(modal)


# ------------------------------------------------------
# Counter Offer + Rejection
# ------------------------------------------------------
class CounterOfferModal(discord.ui.Modal):
    """
    If the majority owner counters with a new percentage, we update the claim
    to 'countered' status. Then the prospective new owner can accept or reject
    that counter in the NewUserCounterView.
    """
    def __init__(self, cog, claim_id: int):
        super().__init__(title="Counter-Offer")
        self.cog = cog
        self.claim_id = claim_id

        self.counter_input = discord.ui.InputText(
            label="New % for the prospective owner",
            required=True
        )
        self.reason_input = discord.ui.InputText(
            label="Justification (optional)",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.counter_input)
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            new_pct = int(self.counter_input.value)
        except ValueError:
            return await interaction.response.send_message("Invalid percentage.", ephemeral=True)
        if not (1 <= new_pct <= 100):
            return await interaction.response.send_message("Must be between 1 and 100.", ephemeral=True)

        await self.cog.bot.db.execute(
            """
            UPDATE claims
            SET counter_percentage=$1,
                counter_justification=$2,
                status='countered'
            WHERE id=$3
            """,
            new_pct,
            self.reason_input.value or "",
            self.claim_id
        )

        # DM the prospective owner so they can respond
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if claim:
            new_owner_id = claim["owner_id"]
            new_owner = interaction.guild.get_member(new_owner_id)
            if new_owner:
                try:
                    dm = await new_owner.create_dm()
                    embed = discord.Embed(
                        title=f"Counter-Offer for Claim #{self.claim_id}",
                        description=(
                            f"The majority owner proposes **{new_pct}%**.\n\n"
                            f"**Reason:**\n```\n{self.reason_input.value or '(none)'}\n```"
                        ),
                        color=discord.Color.gold()
                    )
                    view = NewUserCounterView(cog=self.cog, claim_id=self.claim_id)
                    await dm.send(embed=embed, view=view)
                except discord.Forbidden:
                    pass

        await interaction.response.send_message("Counter-offer sent successfully.", ephemeral=True)


class NewUserCounterView(discord.ui.View):
    """
    Sent to the prospective new owner after the majority owner counters.
    The new user can accept or reject the new percentage.
    """
    def __init__(self, cog, claim_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.claim_id = claim_id

    @discord.ui.button(label="Accept Counter", style=discord.ButtonStyle.success)
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] != "countered":
            return await interaction.response.send_message("Claim not currently in 'countered' status.", ephemeral=True)

        counter_val = claim["counter_percentage"]
        await self.cog.bot.db.execute(
            """
            UPDATE claims
            SET requested_percentage=$1,
                sub_approved=TRUE,
                status='pending'
            WHERE id=$2
            """,
            counter_val,
            self.claim_id
        )

        # If staff or not
        if (not claim["require_staff_approval"]) or (claim["staff_approvals"] >= 2):
            await self.cog.finalize_claim(self.claim_id)
            await interaction.response.send_message("You accepted the counter-offer. Claim finalized!", ephemeral=True)
        else:
            await interaction.response.send_message(
                "You accepted the counter. Staff approval may still be needed.",
                ephemeral=True
            )

        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Reject Counter", style=discord.ButtonStyle.danger)
    async def reject_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] != "countered":
            return await interaction.response.send_message("Not currently in a 'countered' status.", ephemeral=True)

        # Deny the claim
        await self.cog.bot.db.execute(
            """
            UPDATE claims
            SET status='denied',
                rejection_reason='New user rejected the counter.'
            WHERE id=$1
            """,
            self.claim_id
        )

        # 24hr cooldown for the male (owner)
        await self.cog.apply_rejected_cooldown(claim["owner_id"])

        # Notify both parties
        await self.cog.notify_claim_status(
            self.claim_id,
            new_status="Denied",
            reason="The new user rejected the counter offer."
        )

        await interaction.response.send_message("You rejected the counter. Claim ended.", ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)


class MajorityRejectModal(discord.ui.Modal):
    """
    Majority owner rejects the partial claim entirely.
    """
    def __init__(self, cog, claim_id: int):
        super().__init__(title="Reject Claim")
        self.cog = cog
        self.claim_id = claim_id

        self.reason_input = discord.ui.InputText(
            label="Reason",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim not pending/countered anymore.", ephemeral=True)

        # Deny
        await self.cog.bot.db.execute(
            """
            UPDATE claims
            SET status='denied',
                rejection_reason=$1
            WHERE id=$2
            """,
            self.reason_input.value,
            self.claim_id
        )

        # 24hr cooldown for the male (owner)
        await self.cog.apply_rejected_cooldown(claim["owner_id"])

        # Notify both parties
        await self.cog.notify_claim_status(
            self.claim_id,
            new_status="Denied by Majority Owner",
            reason=self.reason_input.value
        )

        await interaction.response.send_message(
            "Claim rejected. The male is on 24h cooldown.",
            ephemeral=True
        )


class SubRejectModal(discord.ui.Modal):
    """
    Sub (female) rejects a direct claim from the prospective owner.
    """
    def __init__(self, cog, claim_id: int):
        super().__init__(title="Reject Claim")
        self.cog = cog
        self.claim_id = claim_id

        self.reason_input = discord.ui.InputText(
            label="Reason for Rejection",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim not pending/countered anymore.", ephemeral=True)

        # Deny
        await self.cog.bot.db.execute(
            """
            UPDATE claims
            SET status='denied',
                rejection_reason=$1
            WHERE id=$2
            """,
            self.reason_input.value,
            self.claim_id
        )

        # 24hr cooldown
        await self.cog.apply_rejected_cooldown(claim["owner_id"])

        # Notify both parties
        await self.cog.notify_claim_status(
            self.claim_id,
            new_status="Denied by Sub",
            reason=self.reason_input.value
        )

        await interaction.response.send_message(
            "Claim rejected. The male is on 24h cooldown.",
            ephemeral=True
        )

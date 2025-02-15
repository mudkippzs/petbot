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
    View for staff to approve or deny a legacy claim.
    The decision is delegated to the OwnershipCog’s methods:
      - staff_approve_claim(...)
      - staff_deny_claim(...)
    
    This view is considered ephemeral; it is intended for short‐lived staff interactions.
    """
    def __init__(self, bot: commands.Bot, claim_id: int, timeout: Optional[float] = None):
        """
        Initializes the staff view with the given bot and claim ID.
        
        :param bot: The bot instance.
        :param claim_id: The ID of the claim being reviewed.
        :param timeout: Optional timeout for the view.
        """
        super().__init__(timeout=timeout)
        self.bot = bot
        self.claim_id = claim_id

    @discord.ui.button(
        label="Approve Claim",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="claim_staff_approve"
    )
    async def approve_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when a staff member clicks the "Approve Claim" button.
        Delegates the approval to the OwnershipCog.
        """
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.staff_approve_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(
        label="Deny Claim",
        style=discord.ButtonStyle.danger,
        emoji="🚫",
        custom_id="claim_staff_deny"
    )
    async def deny_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when a staff member clicks the "Deny Claim" button.
        Delegates the denial to the OwnershipCog.
        """
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.staff_deny_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        # Disable all buttons to prevent further interaction.
        self.disable_all_items()
        await interaction.message.edit(view=self)


class OwnershipClaimSubView(discord.ui.View):
    """
    View for a sub (the claimed user) to approve or deny a legacy claim.
    Staff and the sub both must approve a claim.
    This view is ephemeral.
    """
    def __init__(self, bot: commands.Bot, claim_id: int, timeout: Optional[float] = None):
        """
        Initializes the sub view with the given bot and claim ID.
        
        :param bot: The bot instance.
        :param claim_id: The ID of the claim.
        :param timeout: Optional timeout for the view.
        """
        super().__init__(timeout=timeout)
        self.bot = bot
        self.claim_id = claim_id

    @discord.ui.button(
        label="Approve Claim",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="claim_sub_approve"
    )
    async def approve_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the sub clicks the "Approve Claim" button.
        Delegates the approval action to the OwnershipCog.
        """
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
        """
        Called when the sub clicks the "Deny" button.
        Delegates the denial action to the OwnershipCog.
        """
        cog = self.bot.get_cog("OwnershipCog")
        if cog:
            await cog.sub_deny_claim(self.claim_id, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)

# ------------------------------------------------------
# SingleUserOwnershipView (DM-based Evergreen View)
# ------------------------------------------------------

class SingleUserOwnershipView(discord.ui.View):
    """
    DM-based interactive view that displays ownership information for a single user.
    
    This view is considered "evergreen"—it is meant to persist (for a limited time)
    even across bot restarts. When first sent, its expiration time (e.g. 10 minutes)
    is recorded in the database. On bot reload the view is reattached with the remaining timeout.
    
    In addition, this view provides dynamic buttons:
      - Request DMs / Close DMs
      - Propose Claim (enabled only if conditions are met)
    """
    def __init__(self, bot: commands.Bot, target_user: discord.Member, viewer_user: discord.Member, timeout: Optional[float] = None, message_id: int = 0):
        """
        Initializes the DM-based view.
        
        :param bot: The bot instance.
        :param target_user: The user whose ownership details are being viewed.
        :param timeout: The timeout (in seconds) for the view.
        :param message_id: The ID of the message where this view is attached.
        """
        super().__init__(timeout=timeout)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        self.message_id = message_id  
        self.dms_active = False
        self.propose_claim_enabled = False

    async def refresh_button_label(self):
            """Check DB and update the button label, then re‐edit the original DM."""
            # 1) Figure out if your DM is open or not
            row = await self.bot.db.fetchrow(
                """
                SELECT active FROM open_dm_perms
                 WHERE (user1_id=$1 AND user2_id=$2) OR (user1_id=$2 AND user2_id=$1);
                """,
                # If you need the "viewer" or "invoker" ID, you might store that in the DB table
                # or pass it in. If you only track the target_user in your constructor,
                # you may need more logic here. For simplicity, assume you know the "viewer" or use
                # message.author_id if you're only dealing with your own DM.
                self.target_user.id, self.viewer_user.id 
            )
            dm_is_open = bool(row and row["active"])

            # 2) Update the button label
            request_dm_button = self.get_item("singleuser_request_DMs")
            if request_dm_button is not None:
                request_dm_button.label = "Close DMs" if dm_is_open else "Request DMs"

            # 3) Re‐edit the DM to reflect the updated label
            try:
                # Make sure you can fetch the DM channel for the relevant user
                dm_channel = await self.viewer_user.create_dm()
                msg = await dm_channel.fetch_message(self.message_id)
                await msg.edit(view=self)
            except Exception as e:
                print(f"Failed to refresh button label: {e}")

    async def update_view(self, interaction: discord.Interaction):
        """
        Dynamically updates button states based on current DM permissions, roles,
        and ownership status.
        """
        # Check whether open DM permissions exist.
        dm_row = await self.bot.db.fetchrow(
            """
            SELECT active
            FROM open_dm_perms
            WHERE (user1_id = $1 AND user2_id = $2) OR (user1_id = $2 AND user2_id = $1);
            """,
            interaction.user.id, self.target_user.id
        )
        logger.debug(f"{interaction}")
        self.dms_active = bool(dm_row and dm_row["active"])

        # Update the "Request DMs" button label accordingly.
        request_dm_button = self.get_item("singleuser_request_DMs")
        if request_dm_button:
            request_dm_button.label = "Close DMs" if self.dms_active else "Request DMs"
            request_dm_button.disabled = False

        # Retrieve the roles for both the invoking user and the target user.
        invoker_roles = await self.bot.db.fetchrow(
            "SELECT gender_role FROM user_roles WHERE user_id = $1;", interaction.user.id
        )
        target_roles = await self.bot.db.fetchrow(
            "SELECT gender_role FROM user_roles WHERE user_id = $1;", self.target_user.id
        )
        # Check if the invoker already has ownership of the target.
        ownership_row = await self.bot.db.fetchrow(
            "SELECT 1 FROM sub_ownership WHERE sub_id = $1 AND user_id = $2;",
            self.target_user.id, interaction.user.id
        )

        # Update the "Propose Claim" button: it is enabled only if conditions are met.
        propose_claim_button = self.get_item("singleuser_propose_claim")
        if propose_claim_button:
            if (
                not invoker_roles or
                not target_roles or
                ownership_row or  # Already owns the target.
                invoker_roles["gender_role"] != "Gentleman" or
                target_roles["gender_role"] != "Harlot" or
                not self.dms_active
            ):
                propose_claim_button.disabled = True
            else:
                propose_claim_button.disabled = False

        # Update the message with the modified view.
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Request DMs", style=discord.ButtonStyle.primary, custom_id="singleuser_request_DMs")
    async def request_dm_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Defer right away, so we won't blow up if we call something else that responds.
        await interaction.response.defer(ephemeral=True)

        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            return

        # toggle_dm_permissions calls handle_dm_request which might have responded, 
        # but we have already “deferred,” so that’s okay. The library sees our 
        # initial deferral as the “first response.”
        did_change, is_open, msg = await cog.toggle_dm_permissions(
            invoker=interaction.user,
            target=self.target_user,
            interaction=interaction,
            reason="user_toggle_via_single_view"
        )

        # Now we can do a follow-up message:
        await interaction.followup.send(msg, ephemeral=True)

        # Or just do your self.update_view if you want to re-edit a message:
        await self.update_view(interaction)


    @discord.ui.button(label="Propose Claim", style=discord.ButtonStyle.blurple, custom_id="singleuser_propose_claim")
    async def propose_claim_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Triggered when the "Propose Claim" button is clicked.
        Performs several validations (open DM, role checks, pending claim checks, cooldowns)
        and then opens the appropriate modal (partial or direct claim).
        """
        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            return

        # Verify that open DM permissions exist between the invoker and the target.
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
                f"DMs are not open between you and {self.target_user.display_name}. You must request DMs first.",
                ephemeral=True
            )

        # Fetch both members from the guild.
        if not cog.bot.guilds:
            return await interaction.response.send_message("Bot is not currently in any guilds!", ephemeral=True)
        guild = cog.bot.guilds[0]
        try:
            owner_member = await guild.fetch_member(interaction.user.id)
            sub_member = await guild.fetch_member(self.target_user.id)
        except discord.NotFound:
            return await interaction.response.send_message("Could not fetch both users from the guild.", ephemeral=True)

        # Role validation.
        if cog.owner_role_id not in [r.id for r in owner_member.roles]:
            return await interaction.response.send_message("You must be a Gentleman to claim a Harlot.", ephemeral=True)
        if cog.sub_role_id not in [r.id for r in sub_member.roles]:
            return await interaction.response.send_message(f"{self.target_user.display_name} is not a Harlot.", ephemeral=True)

        # Check for existing pending claims.
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
            return await interaction.response.send_message(f"{self.target_user.display_name} already has a pending claim!", ephemeral=True)

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
            return await interaction.response.send_message(f"You already have a pending claim on {self.target_user.display_name}.", ephemeral=True)

        if await cog.user_on_cooldown(interaction.user.id):
            cd_end = await cog.get_user_cooldown(interaction.user.id)
            remain_hrs = (cd_end - datetime.datetime.utcnow()).total_seconds() / 3600
            return await interaction.response.send_message(f"You are on cooldown for {remain_hrs:.1f} more hours.", ephemeral=True)

        # Decide whether to propose a partial or direct claim.
        majority_owner_id, majority_share = await cog.find_majority_owner(self.target_user.id)
        if majority_owner_id and majority_share >= 50:
            modal = PartialClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user,
                majority_owner_id=majority_owner_id
            )
            await interaction.response.send_modal(modal)
        else:
            modal = DirectClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user
            )
            await interaction.response.send_modal(modal)

    async def on_timeout(self):
        """
        When the view times out, disable all buttons and update the corresponding
        database record to mark the view as inactive.
        """
        self.disable_all_items()
        try:
            await self.bot.db.execute(
                "UPDATE dm_ownership_views SET active = FALSE WHERE message_id = $1;",
                self.message_id
            )
        except Exception as e:
            logger.error(f"Error updating dm_ownership_views on timeout: {e}")

# ------------------------------------------------------
# AskForDMApprovalView and Modal for DM Requests
# ------------------------------------------------------

class AskForDMApprovalView(discord.ui.View):
    """
    View presented to the sub or the majority owner so they can accept or deny
    a DM request from an owner. The decision is finalized via a modal for an optional justification.
    """
    def __init__(self, bot: commands.Bot, requestor: discord.Member, log_message: discord.Message):
        """
        Initializes the DM approval view.
        
        :param bot: The bot instance.
        :param requestor: The member requesting DM permission.
        :param log_message: The message in the log channel where the request is recorded.
        """
        super().__init__(timeout=None)
        self.bot = bot
        self.requestor = requestor
        self.log_message = log_message
        self.approval_action = None

    @discord.ui.button(label="Accept DM Request", emoji="✅", style=discord.ButtonStyle.success, custom_id="dm_approval_accept")
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the approver clicks "Accept". Opens a modal to optionally provide a justification.
        """
        self.approval_action = "accepted"
        await interaction.response.send_modal(
            AskForDMJustificationModal(parent_view=self, action="accepted")
        )

    @discord.ui.button(label="Deny DM Request", emoji="🚫", style=discord.ButtonStyle.danger, custom_id="dm_approval_deny")
    async def deny_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the approver clicks "Deny". Opens a modal for an optional justification.
        """
        self.approval_action = "denied"
        await interaction.response.send_modal(
            AskForDMJustificationModal(parent_view=self, action="denied")
        )

    async def finalize_request(self, interaction: discord.Interaction, action: str, justification: str):
        """
        Finalizes the DM request based on the approver’s decision and updates the log message.
        
        :param interaction: The interaction context.
        :param action: Either "accepted" or "denied".
        :param justification: An optional justification provided by the approver.
        """
        self.disable_all_items()
        await interaction.message.edit(view=self)

        # Update the log embed.
        original_embed = self.log_message.embeds[0]
        desc_lines = original_embed.description.split("\n")
        for i, line in enumerate(desc_lines):
            if "Status:" in line:
                desc_lines[i] = f"Status: **{action.title()}**"
                break
        new_desc = "\n".join(desc_lines)

        new_embed = discord.Embed(
            title=f"DM Request was {action.capitalize()}",
            description=new_desc,
            color=discord.Color.green() if action == "accepted" else discord.Color.red()
        )
        if justification.strip():
            new_embed.add_field(name="Justification", value=justification, inline=False)

        await self.log_message.edit(embed=new_embed)

        # If accepted, open DM permissions.
        if action == "accepted":
            cog = self.bot.get_cog("OwnershipCog")
            if cog:
                await cog.add_open_dm_pair(self.requestor.id, interaction.user.id, reason="approved_by_user_or_owner")

        await interaction.response.send_message(f"You have **{action}** the DM request.", ephemeral=True)


class AskForDMJustificationModal(discord.ui.Modal):
    """
    Modal for providing an optional justification when accepting or denying a DM request.
    """
    def __init__(self, parent_view: AskForDMApprovalView, action: str):
        """
        Initializes the modal with the appropriate title based on the action.
        
        :param parent_view: The parent AskForDMApprovalView.
        :param action: The action being taken ("accepted" or "denied").
        """
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
        """
        Called when the modal is submitted. Finalizes the DM request using the parent view.
        """
        reason = self.text_input.value.strip()
        await self.parent_view.finalize_request(interaction, self.action, reason)

# ------------------------------------------------------
# Ownership Browser and User Select (Ephemeral UI)
# ------------------------------------------------------

class OwnershipBrowserView(discord.ui.View):
    """
    An ephemeral slash-based UI for browsing a user's ownership details and performing actions:
      - Request or Close DMs
      - Initiate a Transaction
      - Propose a Claim

    The view includes a user select component to pick a target user.
    """
    def __init__(self, bot: commands.Bot):
        """
        Initializes the browser view with a 120-second timeout.
        
        :param bot: The bot instance.
        """
        super().__init__(timeout=120)
        self.bot = bot
        self.current_user_id: Optional[int] = None
        self.target_user: Optional[discord.Member] = None

        self.user_select = OwnershipUserSelect(self)
        self.add_item(self.user_select)

    @discord.ui.button(
    label="Request DMs",
    style=discord.ButtonStyle.primary,
    emoji="💬",
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

        # Use the new unified method
        did_change, is_open, msg = await cog.toggle_dm_permissions(
            invoker=interaction.user,
            target=target_member,
            interaction=interaction,
            reason="user_toggle_via_browseview"
        )

        # Show the ephemeral message returned
        await interaction.response.send_message(msg, ephemeral=True)

        # Optionally, update the button label right away, if ephemeral is still active
        button.label = "Close DMs" if is_open else "Request DMs"
        button.disabled = False
        # Attempt to edit if ephemeral is still valid
        try:
            await interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass  # ephemeral might be gone or "Interaction has already been acknowledged"

    @discord.ui.button(
        label="Transact",
        style=discord.ButtonStyle.secondary,
        emoji="💲",
        row=2,
        custom_id="browseview_transact_btn"
    )
    async def transact_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the "Transact" button is clicked. Opens a transaction modal.
        """
        if not self.current_user_id:
            return await interaction.response.send_message("Select a user first!", ephemeral=True)
        modal = TransactModal(target_user_id=self.current_user_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Propose Claim",
        emoji="🦮",
        style=discord.ButtonStyle.blurple,
        row=2,
        custom_id="browseview_propose_dynamic_btn"
    )
    async def propose_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the "Propose Claim" button is clicked.
        Verifies that DM permissions are open and that the roles are valid, then opens the appropriate modal.
        """
        cog = self.bot.get_cog("OwnershipCog")
        if not cog:
            return

        if not self.target_user:
            return await interaction.response.send_message("Select a user first!", ephemeral=True)

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
                f"DMs are not open between you and {self.target_user.display_name}. You must request DMs first.",
                ephemeral=True
            )

        if not cog.bot.guilds:
            return await interaction.response.send_message("Bot is not currently in any guilds!", ephemeral=True)
        guild = cog.bot.guilds[0]
        try:
            owner_member = await guild.fetch_member(interaction.user.id)
            sub_member = await guild.fetch_member(self.target_user.id)
        except discord.NotFound:
            return await interaction.response.send_message("Could not fetch both users from the guild.", ephemeral=True)

        if cog.owner_role_id not in [r.id for r in owner_member.roles]:
            return await interaction.response.send_message("You must be a Gentleman to claim a Harlot.", ephemeral=True)
        if cog.sub_role_id not in [r.id for r in sub_member.roles]:
            return await interaction.response.send_message(f"{self.target_user.display_name} is not a Harlot.", ephemeral=True)

        row_sub_claim = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE sub_id=$1 AND status IN('pending','countered');",
            self.target_user.id
        )
        if row_sub_claim:
            return await interaction.response.send_message(f"{self.target_user.display_name} already has a pending claim!", ephemeral=True)

        row_owner_sub = await self.bot.db.fetchrow(
            "SELECT 1 FROM claims WHERE owner_id=$1 AND sub_id=$2 AND status IN('pending','countered');",
            interaction.user.id, self.target_user.id
        )
        if row_owner_sub:
            return await interaction.response.send_message("You already have a pending claim on them.", ephemeral=True)

        if await cog.user_on_cooldown(interaction.user.id):
            cd_end = await cog.get_user_cooldown(interaction.user.id)
            remain_hrs = (cd_end - datetime.datetime.utcnow()).total_seconds() / 3600
            return await interaction.response.send_message(f"You are on cooldown for {remain_hrs:.1f} more hours.", ephemeral=True)

        majority_owner_id, majority_share = await cog.find_majority_owner(self.target_user.id)
        if majority_owner_id and majority_share >= 50:
            modal = PartialClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user,
                majority_owner_id=majority_owner_id
            )
            await interaction.response.send_modal(modal)
        else:
            modal = DirectClaimModal(
                cog=cog,
                prospective_owner=interaction.user,
                sub=self.target_user
            )
            await interaction.response.send_modal(modal)

    async def update_embed_for_user(self, interaction: discord.Interaction, user_id: int):
        """
        Called when the user selection changes. Updates the embed with detailed ownership and DM info.
        
        :param interaction: The interaction context.
        :param user_id: The ID of the newly selected user.
        """
        self.current_user_id = user_id
        target_member = interaction.guild.get_member(user_id)
        self.target_user = target_member

        embed = discord.Embed(
            title=f"User Browser: {target_member.display_name}",
            color=discord.Color.gold()
        )

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
        record = await self.bot.db.fetchrow(query, interaction.user.id, user_id)
        if not record:
            return

        owners_list = record["owners"] or []
        owner_names = []
        for owner_id in owners_list:
            owner_member = interaction.guild.get_member(owner_id)
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

        embed.add_field(name="Details", value=details_value, inline=False)
        embed.add_field(name="DMs", value=f"```{dm_status}```", inline=True)
        embed.add_field(name="DMs with you?", value=f"```{has_dm_permission}```", inline=True)
        embed.add_field(name="Owner(s)", value=f"```{owners_str}```", inline=False)
        embed.add_field(name="Wallet Balance", value=f"```${wallet_balance}```", inline=True)
        embed.set_thumbnail(url=target_member.display_avatar)

        # Update the Request DMs button label based on current DM permissions.
        request_dm_button = self.get_item("browseview_request_dm_btn")
        if request_dm_button:
            request_dm_button.label = "Close DMs" if has_dm_permission == "Yes" else "Request DMs"
            request_dm_button.disabled = False

        embed.set_footer(text="Use the buttons below to perform actions.")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """
        When the browser view times out, disable all buttons.
        As this is an ephemeral message, you may also choose to delete it.
        """
        for child in self.children:
            child.disabled = True
        try:
            await self.message.delete()
        except Exception:
            pass

class OwnershipUserSelect(discord.ui.Select):
    """
    A user-select component allowing the viewer to choose a user from the server.
    This selection triggers an update of the ownership details embed.
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
        """
        Called when a user is selected. Updates the parent view’s embed with the selected user’s info.
        """
        if not self.values:
            return
        selected_user_id = int(self.values[0].id)
        await self.parent_view.update_embed_for_user(interaction, selected_user_id)

# ------------------------------------------------------
# Transaction Modal
# ------------------------------------------------------

class TransactModal(discord.ui.Modal):
    """
    Modal for processing credit transactions between the user and a target.
    """
    def __init__(self, target_user_id: int):
        """
        Initializes the transaction modal.
        
        :param target_user_id: The ID of the target user receiving the credits.
        """
        super().__init__(title="Transaction")
        self.target_user_id = target_user_id

        self.amount_input = discord.ui.InputText(
            label="Amount",
            required=True
        )
        self.justification_input = discord.ui.InputText(
            label="Justification (optional)",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.amount_input)
        self.add_item(self.justification_input)

    async def callback(self, interaction: discord.Interaction):
        """
        Processes the submitted transaction.
        Validates the amount, checks balances, updates wallets, and logs the transaction.
        """
        cog = interaction.client.get_cog("OwnershipCog")
        if not cog:
            return await interaction.response.send_message("OwnershipCog not found.", ephemeral=True)
        try:
            amount = int(self.amount_input.value)
        except ValueError:
            return await interaction.response.send_message("Invalid amount, must be a number.", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("Amount must be greater than 0.", ephemeral=True)

        memo = self.justification_input.value or "(no memo)"
        sender_id = interaction.user.id
        if sender_id == self.target_user_id:
            return await interaction.response.send_message("You cannot transact with yourself!", ephemeral=True)

        sender_balance = await cog.user_balance(sender_id)
        if sender_balance < amount:
            return await interaction.response.send_message("You have insufficient funds.", ephemeral=True)

        # Deduct from sender and add to recipient.
        await interaction.client.db.execute(
            "UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;",
            amount, sender_id
        )
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

        await cog.log_transaction(sender_id, self.target_user_id, amount, memo)
        await interaction.response.send_message(f"Transaction success! {amount} credits sent to <@{self.target_user_id}>. Memo: {memo}", ephemeral=True)

# ------------------------------------------------------
# Partial / Direct Claim Modals
# ------------------------------------------------------

class PartialClaimModal(discord.ui.Modal):
    """
    Modal for proposing partial ownership when a sub already has a majority owner.
    The modal collects the desired ownership percentage and an optional justification.
    """
    def __init__(self, cog, prospective_owner: discord.Member, sub: discord.Member, majority_owner_id: int):
        """
        Initializes the partial claim modal.
        
        :param cog: The OwnershipCog instance.
        :param prospective_owner: The owner proposing the claim.
        :param sub: The sub (target user) being claimed.
        :param majority_owner_id: The user ID of the current majority owner.
        """
        super().__init__(title="Propose Partial Ownership")
        self.cog = cog
        self.prospective_owner = prospective_owner
        self.sub = sub
        self.majority_owner_id = majority_owner_id

        self.percentage_input = discord.ui.InputText(
            label="Desired ownership percent (1-99)",
            required=True
        )
        self.reason_input = discord.ui.InputText(
            label="Justification (optional)",
            style=discord.InputTextStyle.long,
            required=False
        )
        self.add_item(self.percentage_input)
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        """
        Processes the submitted partial claim. Creates a claim record and, if staff approval is required,
        posts to the staff channel. Then DM’s the majority owner with an interactive view.
        """
        try:
            requested_pct = int(self.percentage_input.value)
        except ValueError:
            return await interaction.response.send_message("Invalid percentage, must be a number.", ephemeral=True)
        if not (1 <= requested_pct < 100):
            return await interaction.response.send_message("Percentage must be between 1 and 99.", ephemeral=True)

        justification = self.reason_input.value or ""
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=self.cog.claim_expiry_hours)
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

        if self.cog.require_staff_approval:
            await self.cog.post_staff_verification(
                claim_id, self.prospective_owner, self.sub, requested_pct
            )

        majority_user = self.cog.bot.get_user(self.majority_owner_id)
        if majority_user:
            try:
                dm_channel = await majority_user.create_dm()
                embed = discord.Embed(
                    title=f"New Partial-Ownership Proposal #{claim_id}",
                    description=(
                        f"**New prospective owner:** {self.prospective_owner.mention}\n"
                        f"**Sub:** {self.sub.mention}\n"
                        f"**Requested %:** {requested_pct}%\n\n"
                        f"**Justification:**\n```\n{justification}\n```"
                    ),
                    color=discord.Color.orange()
                )
                view = MajorityOwnerClaimView(cog=self.cog, claim_id=claim_id)
                await dm_channel.send(
                    content=f"You are the majority owner for {self.sub.display_name}. Action required:",
                    embed=embed,
                    view=view
                )
            except discord.Forbidden:
                logger.warning("Could not DM the majority owner about a partial claim.")
        await interaction.response.send_message(
            f"Partial-ownership claim (#{claim_id}) created. The majority owner will be DM’d to act.",
            ephemeral=True
        )

class DirectClaimModal(discord.ui.Modal):
    """
    Modal for proposing direct (100%) ownership when no majority owner exists.
    The modal requires a justification.
    """
    def __init__(self, cog, prospective_owner: discord.Member, sub: discord.Member):
        """
        Initializes the direct claim modal.
        
        :param cog: The OwnershipCog instance.
        :param prospective_owner: The owner proposing the claim.
        :param sub: The sub (target user) being claimed.
        """
        super().__init__(title="Propose Direct Ownership")
        self.cog = cog
        self.prospective_owner = prospective_owner
        self.sub = sub

        self.reason_input = discord.ui.InputText(
            label="Justification",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        """
        Processes the submitted direct claim. Creates the claim record and DM’s the sub for approval.
        If staff approval is required, notifies staff.
        """
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
            logger.warning("Could not DM the sub about a direct claim.")

        if self.cog.require_staff_approval:
            await self.cog.post_staff_verification(
                claim_id, self.prospective_owner, self.sub, 100
            )
        await interaction.response.send_message(
            f"Direct-ownership claim (#{claim_id}) created. The sub will be DM’d for approval.",
            ephemeral=True
        )

# ------------------------------------------------------
# MajorityOwnerClaimView (for Partial Claims)
# ------------------------------------------------------

class MajorityOwnerClaimView(discord.ui.View):
    """
    View presented to the current majority owner in a partial claim scenario.
    The majority owner can accept, counter, or reject the proposed claim.
    """
    def __init__(self, cog, claim_id: int):
        """
        Initializes the majority owner claim view.
        
        :param cog: The OwnershipCog instance.
        :param claim_id: The ID of the claim.
        """
        super().__init__(timeout=None)
        self.cog = cog
        self.claim_id = claim_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        When clicked, marks the claim as approved by the sub (majority owner)
        and attempts to finalize the claim.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("This claim is not pending/countered.", ephemeral=True)
        await self.cog.bot.db.execute("UPDATE claims SET sub_approved=TRUE WHERE id=$1;", self.claim_id)
        if (not claim["require_staff_approval"]) or (claim["staff_approvals"] >= 2):
            await self.cog.finalize_claim(self.claim_id)
            await interaction.response.send_message("You accepted this partial claim. **Finalized**!", ephemeral=True)
        else:
            await interaction.response.send_message("You have accepted. Additional staff approval is required.", ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Counter", style=discord.ButtonStyle.primary)
    async def counter_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        When clicked, opens a counter-offer modal for the majority owner to propose a different percentage.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim is not currently pending/countered.", ephemeral=True)
        modal = CounterOfferModal(cog=self.cog, claim_id=self.claim_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        When clicked, opens a modal for the majority owner to reject the partial claim.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim is not currently pending/countered.", ephemeral=True)
        modal = MajorityRejectModal(cog=self.cog, claim_id=self.claim_id)
        await interaction.response.send_modal(modal)

# ------------------------------------------------------
# SubClaimView (for Direct Claims)
# ------------------------------------------------------

class SubClaimView(discord.ui.View):
    """
    View presented to the sub (target user) when a direct claim is proposed.
    The sub can accept or reject the claim.
    """
    def __init__(self, cog, claim_id: int):
        """
        Initializes the sub claim view.
        
        :param cog: The OwnershipCog instance.
        :param claim_id: The ID of the claim.
        """
        super().__init__(timeout=None)
        self.cog = cog
        self.claim_id = claim_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        When clicked, marks the claim as approved by the sub and attempts to finalize the claim.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("No valid pending claim found.", ephemeral=True)
        await self.cog.bot.db.execute("UPDATE claims SET sub_approved=TRUE WHERE id=$1;", self.claim_id)
        if (not claim["require_staff_approval"]) or (claim["staff_approvals"] >= 2):
            await self.cog.finalize_claim(self.claim_id)
            await interaction.response.send_message("You accepted. **Ownership** is finalized!", ephemeral=True)
        else:
            await interaction.response.send_message("You accepted. Staff approval may still be required.", ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        When clicked, opens a modal for the sub to reject the claim.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("No valid pending claim to reject.", ephemeral=True)
        modal = SubRejectModal(cog=self.cog, claim_id=self.claim_id)
        await interaction.response.send_modal(modal)

# ------------------------------------------------------
# Counter Offer Modal and New User Counter View
# ------------------------------------------------------

class CounterOfferModal(discord.ui.Modal):
    """
    Modal for the majority owner to propose a counter-offer on a partial claim.
    The majority owner enters a new percentage and an optional justification.
    """
    def __init__(self, cog, claim_id: int):
        """
        Initializes the counter-offer modal.
        
        :param cog: The OwnershipCog instance.
        :param claim_id: The ID of the claim being countered.
        """
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
        """
        Processes the counter-offer, updating the claim record and DMing the prospective owner.
        """
        try:
            new_pct = int(self.counter_input.value)
        except ValueError:
            return await interaction.response.send_message("Invalid percentage.", ephemeral=True)
        if not (1 <= new_pct <= 100):
            return await interaction.response.send_message("Percentage must be between 1 and 100.", ephemeral=True)

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
    View presented to the prospective new owner after the majority owner counters a partial claim.
    The new owner can accept or reject the new counter percentage.
    """
    def __init__(self, cog, claim_id: int):
        """
        Initializes the new user counter view.
        
        :param cog: The OwnershipCog instance.
        :param claim_id: The ID of the claim.
        """
        super().__init__(timeout=None)
        self.cog = cog
        self.claim_id = claim_id

    @discord.ui.button(label="Accept Counter", style=discord.ButtonStyle.success)
    async def accept_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the new owner accepts the counter-offer.
        Updates the claim record and attempts to finalize the claim.
        """
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
        if (not claim["require_staff_approval"]) or (claim["staff_approvals"] >= 2):
            await self.cog.finalize_claim(self.claim_id)
            await interaction.response.send_message("You accepted the counter-offer. Claim finalized!", ephemeral=True)
        else:
            await interaction.response.send_message("You accepted the counter. Staff approval may still be needed.", ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Reject Counter", style=discord.ButtonStyle.danger)
    async def reject_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """
        Called when the new owner rejects the counter-offer.
        Denies the claim and applies a cooldown.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] != "countered":
            return await interaction.response.send_message("Not currently in a 'countered' status.", ephemeral=True)
        await self.cog.bot.db.execute(
            """
            UPDATE claims
            SET status='denied',
                rejection_reason='New user rejected the counter.'
            WHERE id=$1
            """,
            self.claim_id
        )
        await self.cog.apply_rejected_cooldown(claim["owner_id"])
        await self.cog.notify_claim_status(
            self.claim_id,
            new_status="Denied",
            reason="The new user rejected the counter offer."
        )
        await interaction.response.send_message("You rejected the counter. Claim ended.", ephemeral=True)
        self.disable_all_items()
        await interaction.message.edit(view=self)

# ------------------------------------------------------
# MajorityRejectModal and SubRejectModal
# ------------------------------------------------------

class MajorityRejectModal(discord.ui.Modal):
    """
    Modal for the majority owner to completely reject a partial claim.
    Requires a justification for the rejection.
    """
    def __init__(self, cog, claim_id: int):
        """
        Initializes the modal.
        
        :param cog: The OwnershipCog instance.
        :param claim_id: The ID of the claim being rejected.
        """
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
        """
        Processes the rejection and updates the claim record.
        Applies a 24-hour cooldown to the owner and notifies both parties.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim not pending/countered anymore.", ephemeral=True)
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
        await self.cog.apply_rejected_cooldown(claim["owner_id"])
        await self.cog.notify_claim_status(
            self.claim_id,
            new_status="Denied by Majority Owner",
            reason=self.reason_input.value
        )
        await interaction.response.send_message("Claim rejected. The owner is on a 24-hour cooldown.", ephemeral=True)

class SubRejectModal(discord.ui.Modal):
    """
    Modal for the sub (target user) to reject a direct claim.
    Requires a justification for the rejection.
    """
    def __init__(self, cog, claim_id: int):
        """
        Initializes the sub rejection modal.
        
        :param cog: The OwnershipCog instance.
        :param claim_id: The ID of the claim being rejected.
        """
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
        """
        Processes the rejection by the sub, updates the claim record,
        applies a cooldown to the owner, and notifies both parties.
        """
        claim = await self.cog.bot.db.fetchrow("SELECT * FROM claims WHERE id=$1;", self.claim_id)
        if not claim or claim["status"] not in ("pending", "countered"):
            return await interaction.response.send_message("Claim not pending/countered anymore.", ephemeral=True)
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
        await self.cog.apply_rejected_cooldown(claim["owner_id"])
        await self.cog.notify_claim_status(
            self.claim_id,
            new_status="Denied by Sub",
            reason=self.reason_input.value
        )
        await interaction.response.send_message("Claim rejected. The owner is on a 24-hour cooldown.", ephemeral=True)

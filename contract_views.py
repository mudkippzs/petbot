# contract_views.py

import discord
from discord.ui import (
    View,
    Modal,
    InputText,
    Button,
    Select,
    button,
    select,
)
from typing import Callable, Optional, List


class ConfirmDeleteModal(Modal):
    """
    A simple confirmation modal for deleting an advert.
    """

    confirmation = InputText(
        label="Type 'DELETE' to confirm",
        placeholder="DELETE",
        required=True,
        style=discord.InputTextStyle.short,
        max_length=10,
    )

    def __init__(self, on_confirm: Callable[[discord.Interaction], None]):
        super().__init__(title="Delete Advert Confirmation")
        self.on_confirm = on_confirm

    async def callback(self, interaction: discord.Interaction) -> None:
        # Check user typed DELETE
        if self.confirmation.value.strip().upper() == "DELETE":
            await self.on_confirm(interaction)
        else:
            await interaction.response.send_message(
                "Advert not deleted (did not type DELETE).", 
                ephemeral=True,
                delete_after=30.0
            )


class AdvertView(View):
    """
    The view attached to a posted service Advert.
    Provides buttons for:
      [Make Offer] - opens a modal for potential buyers
      [Delete Advert] - prompts the poster with a confirm modal
    """

    def __init__(
        self,
        on_make_offer: Callable[[discord.Interaction], None],
        on_delete_advert: Callable[[discord.Interaction], None],
    ):
        super().__init__(timeout=None)
        self.on_make_offer = on_make_offer
        self.on_delete_advert = on_delete_advert

    @button(
        label="Make Offer", 
        style=discord.ButtonStyle.blurple, 
        emoji="🛒", 
        custom_id="advert_make_offer_btn"
    )
    async def make_offer_btn(
        self, 
        interaction: discord.Interaction, 
        button: Button
    ):
        if self.on_make_offer is not None:
            await self.on_make_offer(interaction)

    @button(
        label="Delete Advert",
        style=discord.ButtonStyle.danger,
        emoji="🗑",
        custom_id="advert_delete_btn"
    )
    async def delete_advert_btn(
        self, 
        interaction: discord.Interaction, 
        button: Button
    ):
        """
        When clicked, we present a confirmation modal 
        to ensure the user truly wants to delete the advert.
        """
        # Only the seller/creator should be allowed to proceed:
        # The callback in contract_escrow.py can double-check user perms as well.
        modal = ConfirmDeleteModal(on_confirm=self.on_delete_advert)
        await interaction.response.send_modal(modal)


class OfferCreationModal(Modal):
    """
    Pop-up modal for a potential buyer to fill in their offer details.
    """

    offer_message = InputText(
        label="Your Offer Message",
        placeholder="Describe the service you want or your terms",
        style=discord.InputTextStyle.long,
        required=True,
        max_length=1000
    )

    offer_price = InputText(
        label="Proposed Price",
        placeholder="e.g. 1000",
        style=discord.InputTextStyle.short,
        required=True
    )

    def __init__(self):
        super().__init__(title="Make an Offer")

    async def on_submit(self, interaction: discord.Interaction):
        """
        By default, we won't do any final handling here—your `contract_escrow.py`
        will hook a custom callback to `modal.on_submit`.
        """
        pass


class ConfirmFulfillModal(Modal):
    """
    A confirmation modal shown before finalizing 'Fulfill.'
    """

    note = InputText(
        label="Any final notes before fulfilling?",
        placeholder="(Optional) e.g. 'Thanks for your service!'",
        style=discord.InputTextStyle.long,
        required=False,
    )

    def __init__(self, on_confirm: Callable[[discord.Interaction, Optional[str]], None]):
        super().__init__(title="Confirm Contract Fulfillment")
        self.on_confirm = on_confirm

    async def on_submit(self, interaction: discord.Interaction):
        # Pass the note up to the callback
        await self.on_confirm(interaction, self.note.value)


class ConfirmCancelModal(Modal):
    """
    A confirmation modal for canceling the contract.
    """

    reason = InputText(
        label="Reason for Cancelation",
        placeholder="(Optional) Provide a reason or explain the cancellation",
        style=discord.InputTextStyle.long,
        required=False
    )

    def __init__(self, on_confirm: Callable[[discord.Interaction, Optional[str]], None]):
        super().__init__(title="Confirm Contract Cancelation")
        self.on_confirm = on_confirm

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_confirm(interaction, self.reason.value)


class DisputeReasonSelect(Select):
    """
    A select menu to choose a dispute reason. 
    Example advanced usage: letting users pick from a set of dispute types.
    """

    def __init__(self, on_dispute_confirm: Callable[[discord.Interaction, str], None]):
        options = [
            discord.SelectOption(
                label="Work not delivered / incomplete",
                description="Seller has not delivered or left the task incomplete"
            ),
            discord.SelectOption(
                label="Quality not as described",
                description="Service delivered, but quality was unacceptable"
            ),
            discord.SelectOption(
                label="Buyer withholding final approval",
                description="Buyer demands more than agreed / won't finalize"
            ),
            discord.SelectOption(
                label="Payment / Pricing disagreement",
                description="Payment or pricing was not agreed upon or changed"
            ),
        ]
        super().__init__(
            placeholder="Select the reason for your Dispute...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="dispute_reason_select"
        )
        self.on_dispute_confirm = on_dispute_confirm

    async def callback(self, interaction: discord.Interaction):
        reason = self.values[0]
        await self.on_dispute_confirm(interaction, reason)


class DisputeView(View):
    """
    A secondary view for collecting the reason for dispute.
    This is shown after user clicks "Dispute" on the main contract view.
    """

    def __init__(self, on_dispute_complete: Callable[[discord.Interaction, str], None]):
        super().__init__(timeout=None)
        self.on_dispute_complete = on_dispute_complete
        # We add our DisputeReasonSelect as an item in the view
        self.add_item(DisputeReasonSelect(self._user_selected_reason))

    async def _user_selected_reason(self, interaction: discord.Interaction, reason: str):
        """
        Called when the user picks an option from the dispute reasons.
        """
        if self.on_dispute_complete is not None:
            await self.on_dispute_complete(interaction, reason)


class ContractView(View):
    """
    The main view for an active contract, with:
      [Fulfill], [Cancel], [Dispute]
    Each button has an optional 'confirm' modal or flow for more clarity.
    """

    def __init__(
        self,
        buyer_id: int,
        seller_id: int,
        on_fulfill_complete: Callable[[discord.Interaction, Optional[str]], None],
        on_cancel_complete: Callable[[discord.Interaction, Optional[str]], None],
        on_dispute: Callable[[discord.Interaction], None]
    ):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.on_fulfill_complete = on_fulfill_complete
        self.on_cancel_complete = on_cancel_complete
        self.on_dispute = on_dispute

    @button(
        label="Fulfill",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="contract_fulfill_btn"
    )
    async def fulfill_btn(self, interaction: discord.Interaction, button: Button):
        """
        Called when either party presses [Fulfill]. 
        We show a short modal or ephemeral confirm before finalizing.
        """
        if self.on_fulfill_complete:
            modal = ConfirmFulfillModal(on_confirm=self.on_fulfill_complete)
            await interaction.response.send_modal(modal)

    @button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        emoji="🛑",
        custom_id="contract_cancel_btn"
    )
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        """
        Called when either party presses [Cancel]. 
        We show a short modal for the user to optionally provide a reason.
        """
        if self.on_cancel_complete:
            modal = ConfirmCancelModal(on_confirm=self.on_cancel_complete)
            await interaction.response.send_modal(modal)

    @button(
        label="Dispute",
        style=discord.ButtonStyle.secondary,
        emoji="⚠️",
        custom_id="contract_dispute_btn"
    )
    async def dispute_btn(self, interaction: discord.Interaction, button: Button):
        """
        Immediately flags the contract and collects reason via a special select-based flow.
        The logic in contract_escrow.py can handle this to notify staff.
        """
        if self.on_dispute:
            await self.on_dispute(interaction)

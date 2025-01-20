# auction.py

import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from typing import TYPE_CHECKING, Optional, List
import asyncio
import datetime

if TYPE_CHECKING:
    from main import MoguMoguBot

class AuctionCog(commands.Cog):
    """
    Manages ephemeral creation flows, scheduled start/end times, public bidding,
    staff overrides, plus calls the OwnershipCog for partial/full ownership transactions.
    """

    # This is the main slash command group
    auction_group = SlashCommandGroup("auction", "Create and manage auctions.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self.schedule_loop.add_exception_type(Exception)
        self.schedule_loop.start()

    # ─────────────────────────────────────────────────────────
    # Slash Commands - End User
    # ─────────────────────────────────────────────────────────

    @auction_group.command(name="create")
    async def create_auction_cmd(self, ctx: discord.ApplicationContext):
        """
        Start an ephemeral multi-step flow to create an auction (ownership, service, or lease).
        """
        await ctx.defer(ephemeral=True)
        # 1) Launch a multi-page ephemeral View:
        #    AuctionCreateFlowView will collect sub_id, type, shares_for_sale, etc.
        flow_view = AuctionCreateFlowView(bot=self.bot, user=ctx.author)
        await ctx.followup.send(
            "Let's set up your new auction! Fill out the fields below:",
            view=flow_view,
            ephemeral=True,
            delete_after=600.0
        )

    @auction_group.command(name="info")
    async def auction_info_cmd(self, ctx: discord.ApplicationContext, auction_id: int):
        """
        Show details about an auction (public or ephemeral).
        """
        await ctx.defer(ephemeral=True)
        # 1) Check DB for auction data, display ephemeral embed or show full if user is staff
        # 2) Might want to handle visibility logic (anonymous/limited/full)
        pass

    @auction_group.command(name="end")
    async def end_auction_cmd(self, ctx: discord.ApplicationContext, auction_id: int):
        """
        If user is the creator or staff, they can end an active auction early.
        """
        await ctx.defer(ephemeral=True)
        # 1) Check if user is the auction creator or staff
        # 2) Call self._finalize_auction(auction_id, triggered_by=ctx.author.id)
        pass

    # ─────────────────────────────────────────────────────────
    # Slash Commands - Staff Overrides (sub-group)
    # ─────────────────────────────────────────────────────────

    staff_auction_group = auction_group.create_subgroup("staff", "Staff-level auction overrides.")

    @staff_auction_group.command(name="pause")
    async def staff_pause_cmd(self, ctx: discord.ApplicationContext, auction_id: int):
        """Staff-only command to pause further bidding."""
        await ctx.defer(ephemeral=True)
        # set auction's "paused" status in DB
        # update embed in staff channel + public channel

    @staff_auction_group.command(name="reset_bids")
    async def staff_reset_bids_cmd(self, ctx: discord.ApplicationContext, auction_id: int):
        """Staff-only: wipe existing bids, revert to starting price."""
        await ctx.defer(ephemeral=True)

    @staff_auction_group.command(name="cancel")
    async def staff_cancel_cmd(self, ctx: discord.ApplicationContext, auction_id: int, refund: bool):
        """
        Staff forcibly cancels an auction, optionally refunding listing deposit.
        """
        await ctx.defer(ephemeral=True)
        # 1) Mark auction canceled
        # 2) If refund: return deposit to the user
        # 3) Update embed

    # ─────────────────────────────────────────────────────────
    # Auction Scheduling Loop
    # ─────────────────────────────────────────────────────────

    @tasks.loop(minutes=1)
    async def schedule_loop(self):
        """
        Periodically checks for auctions that need to:
          1) Start if their start_time is now or passed
          2) End if end_time is passed
        """
        now = datetime.datetime.utcnow()

        # 1) For each scheduled auction that hasn't started yet (start_time <= now)
        #    => post public embed, set 'active=TRUE'
        # 2) For each active auction whose end_time <= now => finalize
        #    => self._finalize_auction(auction_id, triggered_by=None)

    @schedule_loop.before_loop
    async def before_schedule_loop(self):
        await self.bot.wait_until_ready()
        print("Auction scheduling loop is about to start...")

    # ─────────────────────────────────────────────────────────
    # Finalization (private helper)
    # ─────────────────────────────────────────────────────────

    async def _finalize_auction(self, auction_id: int, triggered_by: Optional[int]):
        """
        Ends the auction, picks the highest bid, transfers funds, calls ownership if needed.
        triggered_by can be staff or user ID if forcibly ended, else None if auto-end.
        """
        # 1) fetch auction data
        # 2) fetch highest bid
        # 3) if no bids => mark ended, maybe no sale
        # 4) if ownership => call ownership_cog.transfer_partial_ownership(...) or full_ownership
        # 5) if service => distribute funds to owners
        # 6) mark auction ended, update embed

    # ─────────────────────────────────────────────────────────
    # Public Auction Embeds
    # ─────────────────────────────────────────────────────────

    async def post_public_auction_embed(self, auction_id: int, channel_id: int):
        """
        Post a public embed to the #auction channel with an AuctionView for bidding.
        """
        # 1) build embed
        # 2) create AuctionView (with a Bid button, Cancel if user is creator, etc.)
        # 3) send message, store message_id in DB
        pass

    async def update_auction_embed(self, auction_id: int):
        """
        Edit the existing auction embed message (public channel) to reflect new state
        (highest bid, time left, paused, etc.).
        """
        pass

    async def post_staff_embed(self, auction_id: int):
        """
        Post or update staff channel embed with AdminAuctionView providing staff controls:
        pause, reset, forced finalize, etc.
        """
        pass


# ─────────────────────────────────────────────────────────
# VIEW: Multi-Step Creation Flow
# ─────────────────────────────────────────────────────────

class AuctionCreateFlowView(discord.ui.View):
    """
    Ephemeral view that guides the user through creating an auction.
    Typically 2-4 steps: choose sub, type, start/end times, shares if ownership, etc.
    """
    def __init__(self, bot: "MoguMoguBot", user: discord.User):
        super().__init__(timeout=600)
        self.bot = bot
        self.user = user
        self.auction_data = {
            "sub_id": None,
            "type": None,  # "ownership", "service", "lease"
            "start_time": None,
            "end_time": None,
            "starting_price": None,
            "shares_for_sale": 100,
            # etc...
        }
        # Build initial UI items or set up page 1

    # You can define Selects, Buttons, etc.
    # Example:
    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # gather data from page 1, move to page 2
        await interaction.response.defer()

    # eventually, a "Finish" button:
    @discord.ui.button(label="Finish", style=discord.ButtonStyle.success)
    async def finish_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Validate collected data, insert DB row for the new Auction
        # if start_time <= now => post embed immediately
        await interaction.response.send_message("Your auction is created!", ephemeral=True, delete_after=30.0)
        self.stop()


# ─────────────────────────────────────────────────────────
# VIEW: Public Auction Bidding
# ─────────────────────────────────────────────────────────

class AuctionPublicView(discord.ui.View):
    """
    Attached to the public auction embed. Has "Place Bid" button, "Cancel" if user is creator,
    maybe "Info" button. This view is persistent (timeout=None).
    """
    def __init__(self, bot: "MoguMoguBot", auction_id: int, creator_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.auction_id = auction_id
        self.creator_id = creator_id

    @discord.ui.button(label="Place Bid", style=discord.ButtonStyle.green)
    async def place_bid_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # open ephemeral modal for user to input new bid
        modal = BidModal(bot=self.bot, auction_id=self.auction_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel Auction", style=discord.ButtonStyle.danger)
    async def cancel_auction_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # only visible if user == self.creator_id or staff
        # call self.bot.get_cog("AuctionCog")._finalize_auction(..., triggered_by=interaction.user.id) but handle partial or no sale
        pass

# ─────────────────────────────────────────────────────────
# MODAL for Bidding
# ─────────────────────────────────────────────────────────

class BidModal(discord.ui.Modal):
    """
    Simple modal to prompt user for a numeric bid.
    """
    bid_amount = discord.ui.InputText(
        label="Enter your bid:",
        style=discord.InputTextStyle.short,
        placeholder="Example: 500"
    )

    def __init__(self, bot: "MoguMoguBot", auction_id: int):
        super().__init__(title="Place a Bid")
        self.bot = bot
        self.auction_id = auction_id

    async def on_submit(self, interaction: discord.Interaction):
        # parse bid_amount
        try:
            amount = int(self.bid_amount.value)
        except ValueError:
            await interaction.response.send_message("Invalid bid amount.", ephemeral=True)
            return

        # Validate + record in DB + update embed
        await interaction.response.send_message(f"Bid of {amount} placed!", ephemeral=True)
        # Possibly do logic in AuctionCog to update highest bid, call update_auction_embed(...)


def setup(bot: "MoguMoguBot"):
    bot.add_cog(AuctionCog(bot))

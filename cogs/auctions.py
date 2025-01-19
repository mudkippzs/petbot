import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from discord import Option
from loguru import logger
from typing import TYPE_CHECKING, Optional
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from main import MoguMoguBot

class AuctionMarketplaceCog(commands.Cog):
    """
    Cog managing auctions and marketplace actions for subs and services.
    Supports:
    - Ownership auctions (full or partial)
    - Service auctions
    - Leasing auctions
    - Various visibility modes (full/limited/anonymous)
    - Direct offers to owners
    - Automatic ending of auctions after their end time
    """

    auction_group = SlashCommandGroup("auction", "Commands for the Auction.")
    offer_group = SlashCommandGroup("proposal", "Commands for sending proposals to owners.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        # Start background task to auto-end auctions after their end_time
        self.auction_check_loop.start()

    def cog_unload(self):
        self.auction_check_loop.cancel()

    async def sub_exists(self, sub_id: int) -> bool:
        """Check if a sub with the given ID exists."""
        row = await self.bot.db.fetchrow("SELECT id FROM subs WHERE id=$1;", sub_id)
        return row is not None

    async def is_owner(self, user_id: int, sub_id: int) -> bool:
        """Check if a user is an owner of the specified sub."""
        row = await self.bot.db.fetchrow("SELECT 1 FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;", sub_id, user_id)
        return row is not None

    async def is_primary_owner(self, user_id: int, sub_id: int) -> bool:
        """Check if a user is the primary owner of the specified sub."""
        row = await self.bot.db.fetchrow("SELECT id FROM subs WHERE id=$1 AND primary_owner_id=$2;", sub_id, user_id)
        return row is not None

    async def get_auction(self, auction_id: int):
        """Retrieve a single auction by its ID."""
        return await self.bot.db.fetchrow("SELECT * FROM auctions WHERE id=$1;", auction_id)

    async def get_current_highest_bid(self, auction_id: int) -> Optional[dict]:
        """Get the current highest bid (if any) for a given auction."""
        return await self.bot.db.fetchrow(
            "SELECT bidder_id, amount FROM bids WHERE auction_id=$1 ORDER BY amount DESC LIMIT 1;",
            auction_id
        )

    async def user_balance(self, user_id: int) -> int:
        """Get the user's current wallet balance, 0 if none found."""
        await self.ensure_wallet(user_id)
        w = await self.bot.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", user_id)
        return w["balance"] if w else 0

    async def ensure_wallet(self, user_id: int):
        """Ensure the user has a wallet row; create one with 0 balance if not."""
        exists = await self.bot.db.fetchrow("SELECT 1 FROM wallets WHERE user_id=$1;", user_id)
        if not exists:
            await self.bot.db.execute("INSERT INTO wallets (user_id, balance) VALUES ($1, 0);", user_id)

    async def distribute_funds_to_owners(self, sub_id: int, total_amount: int):
        """Distribute the given amount to the sub's owners proportionally."""
        owners = await self.bot.db.fetch("SELECT user_id, percentage FROM sub_ownership WHERE sub_id=$1;", sub_id)
        for o in owners:
            share = int((o["percentage"] / 100.0) * total_amount)
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", share, o["user_id"])

    async def partial_ownership_transfer(self, sub_id: int, buyer_id: int, sale_amount: int, shares_for_sale: int):
        """
        Perform a partial ownership transfer. Deduct shares_for_sale from the primary owner,
        give them to the buyer, and pay the primary owner the sale_amount.
        """
        primary_owner = await self.bot.db.fetchrow("SELECT primary_owner_id FROM subs WHERE id=$1;", sub_id)
        if not primary_owner:
            logger.error(f"No primary owner found for sub {sub_id}. Cannot perform partial ownership transfer.")
            return
        primary_owner_id = primary_owner["primary_owner_id"]

        po = await self.bot.db.fetchrow("SELECT percentage FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;", sub_id, primary_owner_id)
        if not po:
            logger.error(f"Primary owner {primary_owner_id} not found in sub_ownership for sub {sub_id}.")
            return

        primary_percentage = po["percentage"]
        if primary_percentage < shares_for_sale:
            # Should never happen if validated at auction creation
            logger.error(f"Primary owner {primary_owner_id} doesn't have enough shares to transfer {shares_for_sale}%.")
            return

        new_primary_shares = primary_percentage - shares_for_sale
        await self.bot.db.execute(
            "UPDATE sub_ownership SET percentage=$1 WHERE sub_id=$2 AND user_id=$3;",
            new_primary_shares, sub_id, primary_owner_id
        )

        existing = await self.bot.db.fetchrow("SELECT 1 FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;", sub_id, buyer_id)
        if existing:
            await self.bot.db.execute(
                "UPDATE sub_ownership SET percentage=percentage+$1 WHERE sub_id=$2 AND user_id=$3;",
                shares_for_sale, sub_id, buyer_id
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO sub_ownership (sub_id, user_id, percentage) VALUES ($1, $2, $3);",
                sub_id, buyer_id, shares_for_sale
            )

        # Transfer funds directly to the primary owner
        await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", sale_amount, primary_owner_id)

    @tasks.loop(minutes=1)
    async def auction_check_loop(self):
        """
        Periodic task that checks for auctions past their end_time and finalizes them.
        Runs every minute.
        """
        now = datetime.utcnow()
        ended_auctions = await self.bot.db.fetch("SELECT id FROM auctions WHERE active=TRUE AND end_time < $1;", now)
        for a in ended_auctions:
            await self.finalize_auction(a["id"])

    @auction_check_loop.before_loop
    async def before_auction_check_loop(self):
        await self.bot.wait_until_ready()
        logger.info("Auction auto-finalize loop started.")

    async def finalize_auction(self, auction_id: int, manual_actor_id: Optional[int] = None):
        """
        Finalize an auction after its end_time or if ended manually.
        Distribute funds and transfer ownership/services accordingly.
        """
        auction = await self.get_auction(auction_id)
        if not auction or not auction["active"]:
            return

        highest_bid = await self.get_current_highest_bid(auction_id)
        if not highest_bid:
            # No bids, no sale
            await self.bot.db.execute("UPDATE auctions SET active=FALSE WHERE id=$1;", auction_id)
            logger.info(f"Auction {auction_id} ended with no bids.")
            return

        winner_id = highest_bid["bidder_id"]
        sale_amount = highest_bid["amount"]
        auction_type = auction["type"]
        sub_id = auction["sub_id"]

        # Ensure winner wallet
        await self.ensure_wallet(winner_id)
        if await self.user_balance(winner_id) < sale_amount:
            # Winner no longer has funds
            await self.bot.db.execute("UPDATE auctions SET active=FALSE WHERE id=$1;", auction_id)
            logger.warning(f"Auction {auction_id}: Winner {winner_id} lacks funds. Auction closed with no sale.")
            return

        # Deduct funds from winner
        await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", sale_amount, winner_id)

        if auction_type == "ownership":
            shares_for_sale = auction["shares_for_sale"]
            if shares_for_sale == 100:
                # Full ownership transfer
                owners = await self.bot.db.fetch("SELECT user_id, percentage FROM sub_ownership WHERE sub_id=$1;", sub_id)
                for o in owners:
                    owner_share = int((o["percentage"] / 100) * sale_amount)
                    await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", owner_share, o["user_id"])
                await self.bot.db.execute("DELETE FROM sub_ownership WHERE sub_id=$1;", sub_id)
                await self.bot.db.execute("INSERT INTO sub_ownership (sub_id, user_id, percentage) VALUES ($1, $2, 100);", sub_id, winner_id)
                await self.bot.db.execute("UPDATE subs SET primary_owner_id=$1 WHERE id=$2;", winner_id, sub_id)
            else:
                # Partial ownership
                await self.partial_ownership_transfer(sub_id, winner_id, sale_amount, shares_for_sale)

        elif auction_type == "service":
            # Distribute to owners
            await self.distribute_funds_to_owners(sub_id, sale_amount)
            # Additional logic for "service_id" if needed can be placed here.

        elif auction_type == "leasing":
            # Distribute funds and note the lease duration
            await self.distribute_funds_to_owners(sub_id, sale_amount)
            lease_days = auction["lease_duration_days"]
            logger.info(f"User {winner_id} leased sub {sub_id} for {lease_days} days from auction {auction_id}.")
            # Assigning roles or other lease mechanics could go here.

        # Mark auction ended
        await self.bot.db.execute("UPDATE auctions SET active=FALSE WHERE id=$1;", auction_id)
        logger.info(f"Auction {auction_id} finalized. Winner: {winner_id}, Amount: {sale_amount}, Type: {auction_type}, Manual: {bool(manual_actor_id)}")

    @auction_group.command(name="create", description="Create a new auction.")
    @commands.has_any_role("Gentleman", "Boss")
    async def auction_create(self,
                             ctx: discord.ApplicationContext,
                             sub_id: int,
                             type: Option(str, "Type of auction", choices=["ownership", "service", "leasing"]),
                             starting_price: int,
                             visibility: Option(str, "Visibility mode", choices=["full", "limited", "anonymous"], default="full"),
                             duration_minutes: Option(int, "Auction duration in minutes", default=60),
                             shares_for_sale: Option(int, "For ownership auctions: how many % shares to sell", required=False),
                             service_id: Option(int, "For service auctions: ID of the service to sell", required=False),
                             lease_duration_days: Option(int, "For leasing auctions: Number of days", required=False)):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if not await self.sub_exists(sub_id):
            await ctx.followup.send("Sub not found.")
            return

        if not await self.is_owner(ctx.author.id, sub_id):
            await ctx.followup.send("Only a sub owner can create auctions.")
            return

        if starting_price < 0:
            await ctx.followup.send("Starting price must be non-negative.")
            return

        end_time = datetime.utcnow() + timedelta(minutes=duration_minutes)
        shares_for_sale_val = 100
        service_id_val = None
        lease_days_val = None

        if type == "ownership":
            shares_for_sale_val = shares_for_sale if shares_for_sale is not None else 100
            if shares_for_sale_val < 1 or shares_for_sale_val > 100:
                await ctx.followup.send("shares_for_sale must be between 1 and 100 for ownership auctions.")
                return

            # Check primary owner's shares
            primary_owner = await self.bot.db.fetchrow("SELECT primary_owner_id FROM subs WHERE id=$1;", sub_id)
            if not primary_owner:
                await ctx.followup.send("Sub has no primary owner, cannot create ownership auction.")
                return
            po = await self.bot.db.fetchrow("SELECT percentage FROM sub_ownership WHERE sub_id=$1 AND user_id=$2;", sub_id, primary_owner["primary_owner_id"])
            if not po or po["percentage"] < shares_for_sale_val:
                await ctx.followup.send("Primary owner doesn't have enough shares to sell this amount.")
                return

        elif type == "service":
            if service_id is None:
                await ctx.followup.send("service_id is required for service auctions.")
                return
            svc = await self.bot.db.fetchrow("SELECT 1 FROM sub_services WHERE sub_id=$1 AND id=$2;", sub_id, service_id)
            if not svc:
                await ctx.followup.send("Service not found for this sub.")
                return
            service_id_val = service_id

        elif type == "leasing":
            if lease_duration_days is None or lease_duration_days < 1:
                await ctx.followup.send("lease_duration_days must be a positive integer for leasing auctions.")
                return
            lease_days_val = lease_duration_days

        try:
            row = await self.bot.db.fetchrow(
                """
                INSERT INTO auctions (sub_id, type, visibility, starting_price, end_time, active, creator_id, shares_for_sale, service_id, lease_duration_days)
                VALUES ($1, $2, $3, $4, $5, TRUE, $6, $7, $8, $9)
                RETURNING id;
                """,
                sub_id, type, visibility, starting_price, end_time, ctx.author.id, shares_for_sale_val, service_id_val, lease_days_val
            )
            auction_id = row["id"]
            await ctx.followup.send(f"Auction #{auction_id} created successfully for sub {sub_id}.")
            logger.info(f"Auction {auction_id} created by {ctx.author.id} for sub {sub_id}, type={type}, visibility={visibility}.")
        except Exception as e:
            logger.exception(f"Failed to create auction for sub {sub_id}: {e}")
            await ctx.followup.send("Failed to create auction. Please try again later.")

    @auction_group.command(name="bid", description="Place a bid on an active auction.")
    @commands.has_any_role("Gentleman", "Boss")
    async def auction_bid(self, ctx: discord.ApplicationContext, auction_id: int, amount: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        auction = await self.get_auction(auction_id)
        if not auction:
            await ctx.followup.send("Auction not found.")
            return

        if not auction["active"]:
            await ctx.followup.send("This auction is no longer active.")
            return

        if auction["end_time"] and datetime.utcnow() > auction["end_time"]:
            # Auto-finalize if ended
            await self.finalize_auction(auction_id)
            await ctx.followup.send("This auction has just ended.")
            return

        highest_bid = await self.get_current_highest_bid(auction_id)
        current_highest = highest_bid["amount"] if highest_bid else auction["starting_price"]

        if amount <= current_highest:
            await ctx.followup.send(f"Your bid must exceed the current highest bid of {current_highest}.")
            return

        balance = await self.user_balance(ctx.author.id)
        if balance < amount:
            await ctx.followup.send("You don't have enough balance to place this bid.")
            return

        await self.bot.db.execute("INSERT INTO bids (auction_id, bidder_id, amount) VALUES ($1, $2, $3);", auction_id, ctx.author.id, amount)
        await ctx.followup.send(f"Your bid of {amount} has been placed on auction #{auction_id}.")
        logger.info(f"User {ctx.author.id} placed bid {amount} on auction {auction_id}.")

    @auction_group.command(name="end", description="Manually end an auction and finalize results.")    
    @commands.has_any_role("Gentleman", "Boss")
    async def auction_end(self, ctx: discord.ApplicationContext, auction_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        auction = await self.get_auction(auction_id)
        if not auction:
            await ctx.followup.send("Auction not found.")
            return

        if not auction["active"]:
            await ctx.followup.send("This auction is already ended.")
            return

        sub_id = auction["sub_id"]
        if not (await self.is_primary_owner(ctx.author.id, sub_id) or auction["creator_id"] == ctx.author.id):
            await ctx.followup.send("You must be the primary owner or the auction creator to end this auction.")
            return

        await self.finalize_auction(auction_id, manual_actor_id=ctx.author.id)
        await ctx.followup.send(f"Auction #{auction_id} has been ended and finalized.")

    @auction_group.command(name="info", description="View information about an ongoing auction.")
    @commands.has_any_role("Gentleman", "Boss")
    async def auction_info(self, ctx: discord.ApplicationContext, auction_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        auction = await self.get_auction(auction_id)
        if not auction:
            await ctx.followup.send("Auction not found.")
            return

        sub_id = auction["sub_id"]
        end_time = auction["end_time"].strftime("%Y-%m-%d %H:%M:%S UTC") if auction["end_time"] else "N/A"
        visibility = auction["visibility"]
        auction_type = auction["type"]

        is_owner_or_creator = (await self.is_owner(ctx.author.id, sub_id)) or (auction["creator_id"] == ctx.author.id)

        bids = await self.bot.db.fetch("SELECT bidder_id, amount FROM bids WHERE auction_id=$1 ORDER BY amount DESC;", auction_id)

        embed = discord.Embed(title=f"Auction #{auction_id}", color=0x2F3136)
        embed.add_field(name="Sub ID", value=str(sub_id), inline=True)
        embed.add_field(name="Type", value=auction_type, inline=True)
        embed.add_field(name="Ends At", value=end_time, inline=False)
        embed.add_field(name="Starting Price", value=str(auction["starting_price"]), inline=True)
        embed.add_field(name="Active", value=str(auction["active"]), inline=True)
        embed.add_field(name="Visibility", value=visibility, inline=True)

        if auction_type == "ownership":
            shares_for_sale = auction["shares_for_sale"]
            embed.add_field(name="Shares for Sale", value=f"{shares_for_sale}%", inline=True)
        elif auction_type == "service":
            svc_id = auction["service_id"]
            if svc_id:
                embed.add_field(name="Service ID", value=str(svc_id), inline=True)
        elif auction_type == "leasing":
            lease_days = auction["lease_duration_days"]
            if lease_days:
                embed.add_field(name="Lease Duration (days)", value=str(lease_days), inline=True)

        if not bids:
            embed.add_field(name="Bids", value="No bids yet.", inline=False)
        else:
            if visibility == "full":
                bids_str = "\n".join([f"<@{b['bidder_id']}>: {b['amount']}" for b in bids])
            elif visibility == "limited":
                if is_owner_or_creator:
                    bids_str = "\n".join([f"<@{b['bidder_id']}>: {b['amount']}" for b in bids])
                else:
                    bids_str = "\n".join([f"Anonymous: {b['amount']}" for b in bids])
            else:  # anonymous
                # If still active, all anonymous. If ended, reveal identities.
                if auction["active"]:
                    bids_str = "\n".join([f"Anonymous: {b['amount']}" for b in bids])
                else:
                    bids_str = "\n".join([f"<@{b['bidder_id']}>: {b['amount']}" for b in bids])

            embed.add_field(name="Bids", value=bids_str, inline=False)

        await ctx.followup.send(embed=embed)


    @offer_group.command(name="send", description="Send a direct offer to a sub's owners.")    
    @commands.has_any_role("Gentleman")
    async def offer_send(self,
                         ctx: discord.ApplicationContext,
                         sub_id: int,
                         amount: int,
                         anonymous: Option(bool, "Send the offer anonymously?", default=False)):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if not await self.sub_exists(sub_id):
            await ctx.followup.send("Sub not found.")
            return

        if amount < 0:
            await ctx.followup.send("Offer amount cannot be negative.")
            return

        await self.ensure_wallet(ctx.author.id)
        if await self.user_balance(ctx.author.id) < amount:
            await ctx.followup.send("You don't have enough balance to make this offer.")
            return

        await self.bot.db.execute(
            "INSERT INTO offers (sub_id, sender_id, amount, anonymous, status) VALUES ($1, $2, $3, $4, 'pending');",
            sub_id, ctx.author.id, amount, anonymous
        )
        await ctx.followup.send(f"Your offer of {amount} for sub {sub_id} has been sent to the owners.")
        logger.info(f"User {ctx.author.id} made an offer of {amount} to sub {sub_id}, anonymous={anonymous}.")

    @offer_group.command(name="accept", description="Accept a pending offer made for your sub.")    
    @commands.has_any_role("Gentleman")
    async def offer_accept(self, ctx: discord.ApplicationContext, offer_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        offer = await self.bot.db.fetchrow("SELECT * FROM offers WHERE id=$1;", offer_id)
        if not offer:
            await ctx.followup.send("Offer not found.")
            return

        if offer["status"] != "pending":
            await ctx.followup.send("This offer is not pending.")
            return

        sub_id = offer["sub_id"]
        if not await self.is_owner(ctx.author.id, sub_id):
            await ctx.followup.send("Only an owner can accept offers.")
            return

        sender_id = offer["sender_id"]
        amount = offer["amount"]

        await self.ensure_wallet(sender_id)
        if await self.user_balance(sender_id) < amount:
            await ctx.followup.send("The offer maker no longer has sufficient funds.")
            await self.bot.db.execute("UPDATE offers SET status='failed' WHERE id=$1;", offer_id)
            return

        # Deduct from sender
        await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, sender_id)

        # Distribute to owners
        owners = await self.bot.db.fetch("SELECT user_id, percentage FROM sub_ownership WHERE sub_id=$1;", sub_id)
        for o in owners:
            share = int((o["percentage"] / 100.0) * amount)
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", share, o["user_id"])

        # Transfer full ownership to sender
        await self.bot.db.execute("DELETE FROM sub_ownership WHERE sub_id=$1;", sub_id)
        await self.bot.db.execute("INSERT INTO sub_ownership (sub_id, user_id, percentage) VALUES ($1, $2, 100);", sub_id, sender_id)
        await self.bot.db.execute("UPDATE subs SET primary_owner_id=$1 WHERE id=$2;", sender_id, sub_id)
        await self.bot.db.execute("UPDATE offers SET status='accepted' WHERE id=$1;", offer_id)

        await ctx.followup.send(f"Offer #{offer_id} accepted. <@{sender_id}> now owns sub {sub_id}.")
        logger.info(f"Offer {offer_id} accepted by {ctx.author.id}. Sub {sub_id} transferred to {sender_id}.")

    @offer_group.command(name="deny", description="Deny a pending offer made for your sub.")    
    @commands.has_any_role("Gentleman", "Harlot", "Boss")
    async def offer_deny(self, ctx: discord.ApplicationContext, offer_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        offer = await self.bot.db.fetchrow("SELECT * FROM offers WHERE id=$1;", offer_id)
        if not offer:
            await ctx.followup.send("Offer not found.")
            return

        if offer["status"] != "pending":
            await ctx.followup.send("This offer is not pending.")
            return

        sub_id = offer["sub_id"]
        if not await self.is_owner(ctx.author.id, sub_id):
            await ctx.followup.send("Only an owner can deny offers.")
            return

        await self.bot.db.execute("UPDATE offers SET status='denied' WHERE id=$1;", offer_id)
        await ctx.followup.send(f"Offer #{offer_id} has been denied.")
        logger.info(f"Offer {offer_id} denied by {ctx.author.id}.")

def setup(bot: "MoguMoguBot"):
    bot.add_cog(AuctionMarketplaceCog(bot))

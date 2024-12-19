# ./cogs/contract_escrow.py
import discord
from discord.ext import commands
from discord import Option
from loguru import logger
from typing import TYPE_CHECKING, Optional, List, Dict
from datetime import datetime

if TYPE_CHECKING:
    from main import MoguMoguBot

class ContractEscrowCog(commands.Cog):
    """
    Cog to manage service contracts between buyers and sub owners, with milestone-based payments held in escrow.
    Buyers escrow full payment, and funds are released upon milestone approvals.
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def sub_exists(self, sub_id: int) -> bool:
        """Check if a sub exists."""
        row = await self.bot.db.fetchrow("SELECT id FROM subs WHERE id=$1;", sub_id)
        return row is not None

    async def service_exists_for_sub(self, sub_id: int, service_id: int) -> bool:
        """Check if a service exists for the given sub."""
        row = await self.bot.db.fetchrow("SELECT 1 FROM sub_services WHERE sub_id=$1 AND id=$2;", sub_id, service_id)
        return row is not None

    async def get_sub_primary_owner(self, sub_id: int) -> Optional[int]:
        """Get the primary owner user_id of a sub."""
        row = await self.bot.db.fetchrow("SELECT primary_owner_id FROM subs WHERE id=$1;", sub_id)
        return row["primary_owner_id"] if row else None

    async def user_balance(self, user_id: int) -> int:
        """Get user's wallet balance."""
        w = await self.bot.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", user_id)
        return w["balance"] if w else 0

    async def ensure_wallet(self, user_id: int):
        """Ensure user has a wallet row, create if not exist."""
        exists = await self.bot.db.fetchrow("SELECT 1 FROM wallets WHERE user_id=$1;", user_id)
        if not exists:
            await self.bot.db.execute("INSERT INTO wallets (user_id, balance) VALUES ($1,0);", user_id)

    async def is_staff(self, member: discord.Member) -> bool:
        """Check if member has a staff role."""
        staff_roles = await self.bot.db.fetch("SELECT role_id FROM staff_roles;")
        staff_role_ids = [r["role_id"] for r in staff_roles]
        if not staff_role_ids:
            return False
        return any(role.id in staff_role_ids for role in member.roles)

    async def get_contract(self, contract_id: int):
        return await self.bot.db.fetchrow("SELECT * FROM contracts WHERE id=$1;", contract_id)

    async def get_milestones(self, contract_id: int) -> List[Dict]:
        rows = await self.bot.db.fetch("SELECT * FROM contract_milestones WHERE contract_id=$1 ORDER BY id;", contract_id)
        return [dict(r) for r in rows]

    @commands.slash_command(name="contract", description="Manage service contracts and escrow.")
    async def contract_group(self, ctx: discord.ApplicationContext):
        """Base command for contract-related operations."""
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)

    @contract_group.sub_command(name="create", description="Create a new contract with escrowed payment and milestones.")
    async def contract_create(self,
                              ctx: discord.ApplicationContext,
                              sub_id: int,
                              service_id: int,
                              total_price: int,
                              milestones: Option(str, "Comma-separated descriptions of milestones, e.g. 'Draft,Review,Final'")):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if not await self.sub_exists(sub_id):
            await ctx.followup.send("Sub not found.")
            return

        if not await self.service_exists_for_sub(sub_id, service_id):
            await ctx.followup.send("Service not found for this sub.")
            return

        if total_price <= 0:
            await ctx.followup.send("Total price must be greater than 0.")
            return

        milestone_list = [m.strip() for m in milestones.split(",") if m.strip()]
        if not milestone_list:
            await ctx.followup.send("You must provide at least one milestone.")
            return

        seller_id = await self.get_sub_primary_owner(sub_id)
        if seller_id is None:
            await ctx.followup.send("Sub has no primary owner. Cannot create contract.")
            return

        # Ensure buyer has enough balance to escrow full amount
        await self.ensure_wallet(ctx.author.id)
        buyer_balance = await self.user_balance(ctx.author.id)
        if buyer_balance < total_price:
            await ctx.followup.send("You don't have enough balance to escrow this contract.")
            return

        # Deduct escrow from buyer
        await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", total_price, ctx.author.id)

        # Create contract record
        row = await self.bot.db.fetchrow(
            "INSERT INTO contracts (buyer_id, sub_id, service_id, total_price, escrow_amount, status) VALUES ($1, $2, $3, $4, $5, 'active') RETURNING id;",
            ctx.author.id, sub_id, service_id, total_price, total_price
        )
        contract_id = row["id"]

        # Insert milestones
        for m in milestone_list:
            await self.bot.db.execute(
                "INSERT INTO contract_milestones (contract_id, description) VALUES ($1, $2);",
                contract_id, m
            )

        await ctx.followup.send(f"Contract #{contract_id} created and escrowed. {len(milestone_list)} milestones added.")
        logger.info(f"Contract {contract_id} created by buyer {ctx.author.id} for sub {sub_id}, service {service_id}, price {total_price}.")

    @contract_group.sub_command(name="approve_milestone", description="Approve a contract milestone as buyer or seller.")
    async def contract_approve_milestone(self,
                                         ctx: discord.ApplicationContext,
                                         contract_id: int,
                                         milestone_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        contract = await self.get_contract(contract_id)
        if not contract:
            await ctx.followup.send("Contract not found.")
            return

        if contract["status"] not in ("active", "disputed"):
            await ctx.followup.send("This contract is not active or is already completed/closed.")
            return

        milestones = await self.get_milestones(contract_id)
        milestone = next((m for m in milestones if m["id"] == milestone_id), None)
        if not milestone:
            await ctx.followup.send("Milestone not found.")
            return

        buyer_id = contract["buyer_id"]
        seller_id = await self.get_sub_primary_owner(contract["sub_id"])
        if seller_id is None:
            await ctx.followup.send("Seller not found. Cannot proceed.")
            return

        # Check if ctx.author is buyer or seller
        if ctx.author.id not in (buyer_id, seller_id):
            await ctx.followup.send("Only the buyer or the seller can approve milestones.")
            return

        # Update approval status
        if ctx.author.id == buyer_id and not milestone["approved_by_buyer"]:
            await self.bot.db.execute("UPDATE contract_milestones SET approved_by_buyer=TRUE WHERE id=$1;", milestone_id)
        elif ctx.author.id == seller_id and not milestone["approved_by_seller"]:
            await self.bot.db.execute("UPDATE contract_milestones SET approved_by_seller=TRUE WHERE id=$1;", milestone_id)
        else:
            await ctx.followup.send("You have already approved this milestone or there's nothing to approve.")
            return

        await ctx.followup.send(f"Milestone {milestone_id} approved.")
        logger.info(f"User {ctx.author.id} approved milestone {milestone_id} in contract {contract_id}.")

        # Re-fetch milestones to ensure fresh data
        updated_milestones = await self.get_milestones(contract_id)
        all_approved = all(m["approved_by_buyer"] and m["approved_by_seller"] for m in updated_milestones)

        if all_approved:
            # Release funds to seller
            total_price = contract["total_price"]
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", total_price, seller_id)
            await self.bot.db.execute("UPDATE contracts SET status='completed' WHERE id=$1;", contract_id)
            await ctx.followup.send(
                f"All milestones approved! Contract #{contract_id} completed. Seller has been paid {total_price}.",
                ephemeral=True
            )
            logger.info(f"Contract {contract_id} completed. Seller {seller_id} paid {total_price}.")

    @contract_group.sub_command(name="dispute", description="Raise a dispute for a contract.")
    async def contract_dispute(self,
                               ctx: discord.ApplicationContext,
                               contract_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        contract = await self.get_contract(contract_id)
        if not contract:
            await ctx.followup.send("Contract not found.")
            return

        if contract["status"] not in ("active", "disputed"):
            await ctx.followup.send("This contract is not currently active, so no dispute can be raised.")
            return

        buyer_id = contract["buyer_id"]
        seller_id = await self.get_sub_primary_owner(contract["sub_id"])
        if seller_id is None:
            await ctx.followup.send("Seller not found. Cannot proceed.")
            return

        if ctx.author.id not in (buyer_id, seller_id):
            await ctx.followup.send("Only the buyer or the seller can raise a dispute.")
            return

        await self.bot.db.execute("UPDATE contracts SET status='disputed' WHERE id=$1;", contract_id)
        await ctx.followup.send(f"Contract #{contract_id} is now in dispute. A staff member will resolve it.")
        logger.info(f"Contract {contract_id} disputed by {ctx.author.id}.")

    @contract_group.sub_command(name="resolve_dispute", description="Staff command to resolve a disputed contract.")
    async def contract_resolve_dispute(self,
                                       ctx: discord.ApplicationContext,
                                       contract_id: int,
                                       outcome: Option(str, "Resolution outcome: 'buyer_refund', 'seller_payout', 'split'",
                                                       choices=["buyer_refund", "seller_payout", "split"])):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        contract = await self.get_contract(contract_id)
        if not contract:
            await ctx.followup.send("Contract not found.")
            return

        if contract["status"] != "disputed":
            await ctx.followup.send("This contract is not in disputed status.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can resolve disputes.")
            return

        buyer_id = contract["buyer_id"]
        seller_id = await self.get_sub_primary_owner(contract["sub_id"])
        if seller_id is None:
            await ctx.followup.send("Cannot identify seller. Cannot resolve dispute this way.")
            return

        escrow_amount = contract["escrow_amount"]
        if escrow_amount <= 0:
            await ctx.followup.send("No escrow amount to distribute.")
            return

        # Ensure wallets
        await self.ensure_wallet(buyer_id)
        await self.ensure_wallet(seller_id)

        if outcome == "buyer_refund":
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", escrow_amount, buyer_id)
            await self.bot.db.execute("UPDATE contracts SET status='closed' WHERE id=$1;", contract_id)
            await ctx.followup.send(f"Contract #{contract_id} dispute resolved: All {escrow_amount} returned to buyer.")
        elif outcome == "seller_payout":
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", escrow_amount, seller_id)
            await self.bot.db.execute("UPDATE contracts SET status='closed' WHERE id=$1;", contract_id)
            await ctx.followup.send(f"Contract #{contract_id} dispute resolved: All {escrow_amount} paid to seller.")
        else:  # split
            half = escrow_amount // 2
            remainder = escrow_amount % 2
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", half, buyer_id)
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", half + remainder, seller_id)
            await self.bot.db.execute("UPDATE contracts SET status='closed' WHERE id=$1;", contract_id)
            await ctx.followup.send(
                f"Contract #{contract_id} dispute resolved: {half} to buyer, {half + remainder} to seller."
            )

        logger.info(f"Staff {ctx.author.id} resolved dispute for contract {contract_id} with outcome {outcome}.")

    @contract_group.sub_command(name="info", description="View contract details including milestones and statuses.")
    async def contract_info(self, ctx: discord.ApplicationContext, contract_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        contract = await self.get_contract(contract_id)
        if not contract:
            await ctx.followup.send("Contract not found.")
            return

        milestones = await self.get_milestones(contract_id)
        buyer_id = contract["buyer_id"]
        seller_id = await self.get_sub_primary_owner(contract["sub_id"])
        seller_str = f"<@{seller_id}>" if seller_id else "Unknown"

        embed = discord.Embed(title=f"Contract #{contract_id}", color=0x2F3136)
        embed.add_field(name="Sub ID", value=str(contract["sub_id"]), inline=True)
        embed.add_field(name="Service ID", value=str(contract["service_id"]), inline=True)
        embed.add_field(name="Status", value=contract["status"], inline=True)
        embed.add_field(name="Buyer", value=f"<@{buyer_id}>", inline=False)
        embed.add_field(name="Seller", value=seller_str, inline=False)
        embed.add_field(name="Total Price", value=str(contract["total_price"]), inline=True)
        embed.add_field(name="Escrowed Amount", value=str(contract["escrow_amount"]), inline=True)

        if milestones:
            m_str = ""
            for m in milestones:
                check_buyer = "✔" if m["approved_by_buyer"] else "✘"
                check_seller = "✔" if m["approved_by_seller"] else "✘"
                m_str += f"**#{m['id']}**: {m['description']}\nBuyer: {check_buyer}, Seller: {check_seller}\n"
            embed.add_field(name="Milestones", value=m_str, inline=False)

        await ctx.followup.send(embed=embed)

def setup(bot: "MoguMoguBot"):
    bot.add_cog(ContractEscrowCog(bot))

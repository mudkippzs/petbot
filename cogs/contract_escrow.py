# contract_escrow.py
import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup
from typing import TYPE_CHECKING, Optional
from loguru import logger
import asyncio
import datetime

from contract_views import AdvertView, OfferCreationModal, ContractView

if TYPE_CHECKING:
    from main import MoguMoguBot


FEATURES = {
    "enable_milestones": False,
    "enable_partial_refund": False,
    "enable_auto_cancel_timeout": False,
    "enable_dispute_split": False,
}


class ContractEscrowCog(commands.Cog):
    """
    A cog to manage a contract/escrow system for buying and selling member services, 
    with optional advanced features (milestones, partial refunds, etc.).
    """

    # Slash command groups
    contract_user_group = SlashCommandGroup(
        "contract",
        "User commands for creating adverts and handling offers/contracts."
    )
    contract_staff_group = SlashCommandGroup(
        "staff_contract",
        "Staff commands for moderating and resolving contract disputes."
    )

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        # In a real environment, you might read toggles from e.g. self.bot.config["escrow_features"]
        self.features = FEATURES

    # ---------------------------- USER COMMANDS ----------------------------
    @contract_user_group.command(name="advert", description="Post a service advert that potential buyers can respond to.")
    @commands.has_any_role("Gentleman", "Harlot")
    async def advert_cmd(self, ctx: discord.ApplicationContext):
        """
        Creates an embed in the #the-trading channel (or current channel) with an 'AdvertView.'
        The user who ran this command is treated as the 'seller.'
        """
        await ctx.defer(ephemeral=True)

        # Build the embed
        seller = ctx.author
        embed = discord.Embed(
            title="Service Advert",
            description=(
                f"**Seller:** {seller.mention}\n\n"
                "React with 'Make Offer' if you're interested in hiring!"
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Contract & Escrow System")
        embed.set_author(name=str(seller), icon_url=seller.display_avatar.url)

        def make_offer_callback(interaction: discord.Interaction):
            """
            Called when a potential buyer clicks 'Make Offer.'
            We'll open a modal to gather info from them.
            """
            if interaction.user.id == seller.id:
                # Seller can't make an offer to themselves
                return asyncio.create_task(interaction.response.send_message(
                    "You can't buy your own service!", ephemeral=True
                ))

            modal = OfferCreationModal()
            # Once they submit, we handle the result in a follow-up callback:
            async def modal_callback():
                # This function runs after the user closes the modal
                offer_msg = modal.offer_message.value
                offer_price_str = modal.offer_price.value
                # Validate price
                try:
                    offer_price = int(offer_price_str)
                except ValueError:
                    await interaction.followup.send(
                        f"Invalid offer price: `{offer_price_str}`", 
                        ephemeral=True
                    )
                    return

                # Check buyer's balance, etc.
                buyer_id = interaction.user.id
                buyer_balance = await self.get_user_balance(buyer_id)
                if buyer_balance < offer_price:
                    await interaction.followup.send(
                        f"You don't have enough balance ({buyer_balance}) for this offer.",
                        ephemeral=True
                    )
                    return

                # DM the seller with the offer details
                seller_user = seller  # ctx.author
                try:
                    dm_channel = await seller_user.create_dm()
                    accept_msg = (
                        f"{interaction.user.mention} offers **{offer_price}**.\n\n"
                        f"Message:\n```{offer_msg}```\n\n"
                        "React ✅ to accept, ❌ to decline."
                    )
                    sent_dm = await dm_channel.send(accept_msg)

                    # Wait for reaction in DM
                    await sent_dm.add_reaction("✅")
                    await sent_dm.add_reaction("❌")

                    def check_reaction(r, u):
                        return (
                            r.message.id == sent_dm.id 
                            and u.id == seller_user.id
                            and str(r.emoji) in ["✅", "❌"]
                        )

                    try:
                        reaction, user = await self.bot.wait_for(
                            "reaction_add",
                            timeout=60 * 30,  # 30 min 
                            check=check_reaction
                        )
                        if str(reaction.emoji) == "✅":
                            # Seller accepted => create the contract
                            await self.create_contract(
                                seller_id=seller_user.id,
                                buyer_id=buyer_id,
                                amount=offer_price,
                                description=offer_msg,
                                interaction=interaction
                            )
                        else:
                            # Seller declined
                            await dm_channel.send("You have **declined** the offer.")
                            await interaction.followup.send(
                                "Seller declined your offer.", ephemeral=True
                            )
                    except asyncio.TimeoutError:
                        await dm_channel.send("Offer timed out. No action taken.")
                        await interaction.followup.send(
                            "Offer timed out—seller didn’t respond.", ephemeral=True
                        )
                except discord.Forbidden:
                    # Seller's DMs might be off
                    await interaction.followup.send(
                        f"Could not DM {seller_user.mention}. They may have DMs disabled.",
                        ephemeral=True
                    )

            # Present the modal to the buyer
            asyncio.create_task(interaction.response.send_modal(modal))
            # Then we attach an on_complete to handle after they click submit
            modal.wait()  # The modal flow
            modal.on_submit = modal_callback  # Assign the callback for post-submit

        def delete_advert_callback(interaction: discord.Interaction):
            """
            Called when the seller (or authorized user) clicks 'Delete Advert.'
            """
            if interaction.user.id != seller.id:
                return asyncio.create_task(
                    interaction.response.send_message(
                        "Only the seller can delete this advert.", ephemeral=True
                    )
                )
            # Delete the original advert message
            asyncio.create_task(interaction.message.delete())

        advert_view = AdvertView(
            on_make_offer=make_offer_callback,
            on_delete_advert=delete_advert_callback
        )

        # Post the embed + view to the channel. 
        # In your environment, you might want a #the-trading channel specifically.
        channel = ctx.channel
        sent_msg = await channel.send(embed=embed, view=advert_view)
        await ctx.followup.send("Advert posted!", ephemeral=True)

    # ---------------------------- CONTRACT CREATION ----------------------------
    async def create_contract(self, seller_id: int, buyer_id: int, amount: int, description: str, interaction: discord.Interaction):
        """
        Deducts buyer's funds (escrow) and posts a contract embed with a ContractView.
        Called when the seller accepts an offer.
        """
        # 1) Deduct funds from the buyer
        success = await self.deduct_user_balance(buyer_id, amount)
        if not success:
            await interaction.followup.send(
                "Failed to deduct funds from the buyer’s wallet—contract aborted.",
                ephemeral=True
            )
            return

        # 2) Insert DB record for contract. 
        #    For demonstration, we skip the actual DB code and just show an embed.
        contract_id = await self.db_insert_contract_record(
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount=amount,
            description=description
        )

        # 3) Build an embed for the contract
        buyer_mention = f"<@{buyer_id}>"
        seller_mention = f"<@{seller_id}>"
        embed = discord.Embed(
            title=f"Contract #{contract_id}",
            description=(
                f"**Seller:** {seller_mention}\n"
                f"**Buyer:** {buyer_mention}\n\n"
                f"**Amount:** {amount}\n\n"
                f"**Description:**\n```{description}```"
            ),
            color=discord.Color.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Contract is held in escrow until completed or canceled.")

        # 4) Create the ContractView
        contract_view = ContractView(
            buyer_id=buyer_id,
            seller_id=seller_id,
            on_fulfill_complete=self.on_fulfill_complete,
            on_cancel_complete=self.on_cancel_complete,
            on_dispute=self.on_dispute
        )

        # 5) Post to #the-trading or another channel
        channel = interaction.channel
        await channel.send(embed=embed, view=contract_view)
        await interaction.followup.send(
            f"Contract #{contract_id} created. Escrow of {amount} deducted from buyer.",
            ephemeral=True
        )

    async def on_fulfill_complete(self, interaction: discord.Interaction):
        """
        Both parties pressed 'Fulfill,' so we release escrow to the seller.
        """
        # Identify contract from message or embed if needed
        # For simplicity, assume contract_id is embedded in the message or parse it
        contract_id = self.parse_contract_id_from_embed(interaction.message.embeds[0])
        # Mark in DB as completed
        contract_data = await self.db_get_contract(contract_id)
        if not contract_data:
            return await interaction.followup.send("Contract record not found. Something's off.", ephemeral=True)

        buyer_id = contract_data["buyer_id"]
        seller_id = contract_data["seller_id"]
        amount = contract_data["amount"]
        # Release funds to seller
        await self.add_user_balance(seller_id, amount)

        await self.db_update_contract_status(contract_id, "completed")
        await interaction.response.send_message(
            f"Contract #{contract_id} is now fulfilled! {amount} was paid to <@{seller_id}>.",
            ephemeral=False
        )

    async def on_cancel_complete(self, interaction: discord.Interaction):
        """
        Both parties pressed 'Cancel,' so we return funds to the buyer.
        """
        contract_id = self.parse_contract_id_from_embed(interaction.message.embeds[0])
        contract_data = await self.db_get_contract(contract_id)
        if not contract_data:
            return await interaction.followup.send("Contract record not found. Something's off.", ephemeral=True)

        buyer_id = contract_data["buyer_id"]
        seller_id = contract_data["seller_id"]
        amount = contract_data["amount"]

        # Refund buyer
        await self.add_user_balance(buyer_id, amount)

        await self.db_update_contract_status(contract_id, "canceled")
        await interaction.response.send_message(
            f"Contract #{contract_id} canceled. Refunded {amount} back to <@{buyer_id}>.",
            ephemeral=False
        )

    async def on_dispute(self, interaction: discord.Interaction):
        """
        Either party pressed 'Dispute.' We alert staff in a staff-only channel or do the direct staff flow.
        """
        contract_id = self.parse_contract_id_from_embed(interaction.message.embeds[0])
        contract_data = await self.db_get_contract(contract_id)
        if not contract_data:
            return await interaction.response.send_message("Contract record not found.", ephemeral=True)

        buyer_id = contract_data["buyer_id"]
        seller_id = contract_data["seller_id"]
        amount = contract_data["amount"]

        # Mark DB as 'disputed'
        await self.db_update_contract_status(contract_id, "disputed")

        staff_channel_id = 123456789012345678  # Replace with your staff channel
        staff_channel = self.bot.get_channel(staff_channel_id)
        if not staff_channel:
            return await interaction.response.send_message(
                "Staff channel not configured properly. Dispute noted but no staff alert sent.",
                ephemeral=True
            )

        embed = discord.Embed(
            title=f"Contract Dispute #{contract_id}",
            description=(
                f"**Buyer:** <@{buyer_id}>\n"
                f"**Seller:** <@{seller_id}>\n"
                f"**Amount:** {amount}\n"
                f"**Status:** Disputed"
            ),
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Staff, please resolve via /contractstaff commands if needed.")

        await staff_channel.send(content="A dispute has been raised:", embed=embed)
        await interaction.response.send_message(
            "Dispute raised. Staff has been notified. Contract is on hold.", ephemeral=True
        )

    @contract_staff_group.command(name="resolve_dispute", description="Resolve a disputed contract by forcibly awarding or refunding.")
    @commands.has_any_role("Boss", "Underboss", "Consigliere")
    async def staff_resolve_dispute(self, ctx: discord.ApplicationContext, contract_id: int, resolution: str):
        """
        Admin-only command to forcibly resolve a disputed contract.
        'resolution' can be 'refund_buyer', 'pay_seller', or 'split' if you want partial.
        """
        await ctx.defer(ephemeral=True)
        contract_data = await self.db_get_contract(contract_id)
        if not contract_data:
            return await ctx.followup.send("Contract not found.", ephemeral=True)

        if contract_data["status"] != "disputed":
            return await ctx.followup.send("Contract is not in a 'disputed' state.", ephemeral=True)

        buyer_id = contract_data["buyer_id"]
        seller_id = contract_data["seller_id"]
        amount = contract_data["amount"]

        if resolution == "refund_buyer":
            await self.add_user_balance(buyer_id, amount)
            await self.db_update_contract_status(contract_id, "staff_refund")
            await ctx.followup.send(
                f"Contract #{contract_id} forcibly refunded to buyer <@{buyer_id}>.",
                ephemeral=True
            )
        elif resolution == "pay_seller":
            await self.add_user_balance(seller_id, amount)
            await self.db_update_contract_status(contract_id, "staff_payout")
            await ctx.followup.send(
                f"Contract #{contract_id} forcibly paid out to seller <@{seller_id}>.",
                ephemeral=True
            )
        elif resolution == "split" and self.features.get("enable_dispute_split", False):
            # Example partial logic: 50/50
            half = amount // 2
            remainder = amount % 2
            await self.add_user_balance(buyer_id, half)
            await self.add_user_balance(seller_id, half + remainder)
            await self.db_update_contract_status(contract_id, "staff_split")
            await ctx.followup.send(
                f"Contract #{contract_id} forcibly split: Buyer got {half}, Seller got {half + remainder}.",
                ephemeral=True
            )
        else:
            await ctx.followup.send("Invalid resolution or 'split' feature not enabled.", ephemeral=True)

    async def get_user_balance(self, user_id: int) -> int:
        """
        Example method for retrieving a user's wallet balance from your DB.
        Replace with your actual DB calls or self.bot.db usage.
        """
        # Pseudo-code:
        row = await self.bot.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", user_id)
        return row["balance"] if row else 0

    async def add_user_balance(self, user_id: int, amount: int) -> bool:
        """
        Add 'amount' to user's wallet. Return True if success, else False.
        """
        try:
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", amount, user_id)
            return True
        except Exception as e:
            logger.exception(f"Failed to add balance: {e}")
            return False

    async def deduct_user_balance(self, user_id: int, amount: int) -> bool:
        """
        Subtract 'amount' from user's wallet. Return True if success, else False.
        """
        # You might want to check the user's existing balance and if not enough, fail.
        try:
            balance = await self.get_user_balance(user_id)
            if balance < amount:
                return False
            await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, user_id)
            return True
        except Exception as e:
            logger.exception(f"Failed to deduct balance: {e}")
            return False

    async def db_insert_contract_record(self, buyer_id: int, seller_id: int, amount: int, description: str) -> int:
        """
        Create a row in 'contracts' table, return the contract_id. 
        Adjust fields as needed for your schema.
        """
        row = await self.bot.db.fetchrow(
            """
            INSERT INTO contracts (buyer_id, seller_id, amount, description, status)
            VALUES ($1, $2, $3, $4, 'active')
            RETURNING id
            """,
            buyer_id, seller_id, amount, description
        )
        return row["id"]

    async def db_update_contract_status(self, contract_id: int, status: str):
        """
        Update contract status in DB.
        """
        await self.bot.db.execute(
            "UPDATE contracts SET status=$1 WHERE id=$2;", status, contract_id
        )

    async def db_get_contract(self, contract_id: int) -> Optional[dict]:
        """
        Retrieve a contract record from DB by id.
        """
        row = await self.bot.db.fetchrow("SELECT * FROM contracts WHERE id=$1;", contract_id)
        return dict(row) if row else None

    def parse_contract_id_from_embed(self, embed: discord.Embed) -> Optional[int]:
        """
        Helper to parse contract ID from an embed's title or content.
        E.g., if embed.title is "Contract #123"
        """
        if embed.title and "Contract #" in embed.title:
            try:
                return int(embed.title.split("#")[1])
            except:
                pass
        return None

def setup(bot: "MoguMoguBot"):
    bot.add_cog(ContractEscrowCog(bot))

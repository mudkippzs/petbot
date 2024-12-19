import discord
from discord.ext import commands
from discord import Option, Interaction
from loguru import logger
from typing import TYPE_CHECKING, Optional, Any, Dict, List

if TYPE_CHECKING:
    from main import MoguMoguBot

class EconomyCog(commands.Cog):
    """
    Cog to handle economy operations such as tipping, transfers, and staff approvals.
    Supports predefined tip options from config and handles economy modes:
    - open: transactions happen instantly if user has funds
    - moderated: transactions above a certain amount (e.g. >1000) need staff approval
    - strict: all transactions require staff approval
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def get_economy_mode(self) -> str:
        row = await self.bot.db.fetchrow("SELECT value FROM server_config WHERE key='economy_mode';")
        if not row:
            return "open"
        return row["value"].get("mode", "open")

    async def set_economy_mode(self, mode: str):
        await self.bot.db.execute(
            "INSERT INTO server_config (key, value) VALUES ('economy_mode', $1) ON CONFLICT (key) DO UPDATE SET value=$1;",
            {"mode": mode}
        )

    async def sub_exists(self, sub_id: int) -> bool:
        row = await self.bot.db.fetchrow("SELECT id FROM subs WHERE id=$1;", sub_id)
        return row is not None

    async def user_exists(self, user_id: int) -> bool:
        w = await self.bot.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", user_id)
        if not w:
            await self.bot.db.execute("INSERT INTO wallets (user_id, balance) VALUES ($1,0) ON CONFLICT DO NOTHING;", user_id)
        return True

    async def is_staff(self, member: discord.Member) -> bool:
        staff_roles = await self.bot.db.fetch("SELECT role_id FROM staff_roles;")
        staff_role_ids = [r["role_id"] for r in staff_roles]
        if not staff_role_ids:
            return False
        return any(role.id in staff_role_ids for role in member.roles)

    async def user_balance(self, user_id: int) -> int:
        row = await self.bot.db.fetchrow("SELECT balance FROM wallets WHERE user_id=$1;", user_id)
        if row:
            return row["balance"]
        await self.bot.db.execute("INSERT INTO wallets (user_id, balance) VALUES ($1,0);", user_id)
        return 0

    async def create_transaction(self, sender_id: int, recipient_id: Optional[int], amount: int, justification: str, status: str) -> int:
        row = await self.bot.db.fetchrow(
            "INSERT INTO transactions (sender_id, recipient_id, amount, justification, status) VALUES ($1,$2,$3,$4,$5) RETURNING id;",
            sender_id, recipient_id, amount, justification, status
        )
        return row["id"]

    async def distribute_to_sub_owners(self, sub_id: int, amount: int):
        owners = await self.bot.db.fetch("SELECT user_id, percentage FROM sub_ownership WHERE sub_id=$1;", sub_id)
        for o in owners:
            share = int((o["percentage"] / 100) * amount)
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", share, o["user_id"])

    async def approve_transaction(self, tx_id: int):
        tx = await self.bot.db.fetchrow("SELECT * FROM transactions WHERE id=$1;", tx_id)
        if not tx or tx["status"] != "pending":
            return False, "Transaction not found or not pending."

        sender_id = tx["sender_id"]
        recipient_id = tx["recipient_id"]
        amount = tx["amount"]
        justification = tx["justification"]

        # Check sender balance again before approval
        sender_balance = await self.user_balance(sender_id)
        if sender_balance < amount:
            return False, "Sender no longer has enough funds."

        if justification.startswith("sub:"):
            # Tip to sub owners
            sub_id = int(justification.split(':',1)[1])
            await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, sender_id)
            await self.distribute_to_sub_owners(sub_id, amount)
        else:
            # User-to-user transfer
            await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, sender_id)
            if recipient_id is not None:
                await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", amount, recipient_id)

        await self.bot.db.execute("UPDATE transactions SET status='completed' WHERE id=$1;", tx_id)
        return True, "Transaction approved and completed."

    async def deny_transaction(self, tx_id: int):
        tx = await self.bot.db.fetchrow("SELECT * FROM transactions WHERE id=$1;", tx_id)
        if not tx or tx["status"] != "pending":
            return False, "Transaction not found or not pending."
        await self.bot.db.execute("UPDATE transactions SET status='denied' WHERE id=$1;", tx_id)
        return True, "Transaction denied."

    def needs_approval(self, economy_mode: str, amount: int) -> bool:
        if economy_mode == "open":
            return False
        elif economy_mode == "moderated":
            return amount > 1000
        elif economy_mode == "strict":
            return True
        return False

    @commands.slash_command(name="economy_info", description="Learn about the current economy mode and rules.")
    async def economy_info(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        mode = await self.get_economy_mode()
        msg = (
            f"**Current Economy Mode:** {mode}\n\n"
            "**Mode Details:**\n"
            "- **open:** All transactions are instant if you have sufficient funds.\n"
            "- **moderated:** Transactions above a certain threshold (e.g. 1000) require staff approval.\n"
            "- **strict:** All transactions require staff approval.\n\n"
            "If your transaction is pending, it means staff needs to approve it before completion."
        )
        await ctx.followup.send(msg)

    @commands.slash_command(name="tip", description="Tip a user or sub. Use 'sub:<id>' to tip a sub.")
    async def tip_cmd(self,
                      ctx: discord.ApplicationContext,
                      recipient: Option(str, "User mention or 'sub:<id>'"),
                      amount: Option(int, "Amount to tip, or leave empty to choose from predefined options", required=False)):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        # Parse recipient
        if recipient.startswith("sub:"):
            try:
                sub_id = int(recipient.split(':', 1)[1])
            except ValueError:
                await ctx.followup.send("Invalid sub syntax. Use 'sub:<id>'.")
                return
            if not await self.sub_exists(sub_id):
                await ctx.followup.send("Sub not found.")
                return
            justification = f"sub:{sub_id}"
            recipient_id = None
        else:
            # User recipient
            user_id = None
            if recipient.isdigit():
                user_id = int(recipient)
            else:
                if recipient.startswith("<@") and recipient.endswith(">"):
                    inner = recipient.strip("<@>")
                    if inner.isdigit():
                        user_id = int(inner)
            if user_id is None:
                await ctx.followup.send("Invalid recipient. Use a mention or 'sub:<id>'.")
                return
            await self.user_exists(user_id)
            justification = "user_transfer"
            recipient_id = user_id
            if recipient_id == ctx.author.id:
                await ctx.followup.send("You cannot tip yourself.")
                return

        economy_mode = await self.get_economy_mode()
        sender_id = ctx.author.id

        if amount is not None:
            # User specified amount directly
            if amount <= 0:
                await ctx.followup.send("Amount must be greater than 0.")
                return
            sender_balance = await self.user_balance(sender_id)
            if economy_mode == "open" and sender_balance < amount:
                await ctx.followup.send("You don't have enough balance.")
                return

            if self.needs_approval(economy_mode, amount):
                # create pending tx
                tx_id = await self.create_transaction(sender_id, recipient_id, amount, justification, "pending")
                await ctx.followup.send(
                    f"Transaction created and is pending staff approval (Amount: {amount}, TX: {tx_id})."
                )
            else:
                if sender_balance < amount:
                    await ctx.followup.send("You don't have enough balance.")
                    return
                # Deduct/add funds immediately
                if recipient_id is None:
                    # Tipping a sub
                    await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, sender_id)
                    await self.distribute_to_sub_owners(sub_id, amount)
                    tx_id = await self.create_transaction(sender_id, recipient_id, amount, justification, "completed")
                    await ctx.followup.send(f"Tip of {amount} sent to sub {sub_id} owners! (TX: {tx_id})")
                else:
                    # User to user
                    await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, sender_id)
                    await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", amount, recipient_id)
                    tx_id = await self.create_transaction(sender_id, recipient_id, amount, justification, "completed")
                    await ctx.followup.send(f"Tip of {amount} sent to <@{recipient_id}>! (TX: {tx_id})")
        else:
            # No amount specified, show predefined tip options
            tip_options = self.bot.config.get("tip_options", [])
            if not tip_options:
                await ctx.followup.send("No predefined tip options are configured.")
                return

            class TipButton(discord.ui.Button):
                def __init__(self, label: str, amount: int, recipient_id: Optional[int], justification: str, emoji: Optional[str]):
                    super().__init__(style=discord.ButtonStyle.primary, label=f"{amount}", emoji=emoji)
                    self.amount = amount
                    self.recipient_id = recipient_id
                    self.justification = justification

                async def callback(self, interaction: Interaction):
                    # Process transaction on button press
                    sender_id_local = interaction.user.id
                    economy_mode_local = await interaction.client.get_cog("EconomyCog").get_economy_mode()
                    sender_balance_local = await interaction.client.get_cog("EconomyCog").user_balance(sender_id_local)

                    if economy_mode_local == "open" and sender_balance_local < self.amount:
                        await interaction.response.edit_message(content="You don't have enough balance.", view=None)
                        return

                    cog = interaction.client.get_cog("EconomyCog")
                    if cog.needs_approval(economy_mode_local, self.amount):
                        tx_id_local = await cog.create_transaction(sender_id_local, self.recipient_id, self.amount, self.justification, "pending")
                        await interaction.response.edit_message(
                            content=f"Transaction pending approval (Amount: {self.amount}, TX: {tx_id_local}).",
                            view=None
                        )
                    else:
                        # immediate
                        if sender_balance_local < self.amount:
                            await interaction.response.edit_message(content="You don't have enough balance.", view=None)
                            return
                        if self.justification.startswith("sub:"):
                            sub_id_local = int(self.justification.split(':',1)[1])
                            await cog.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", self.amount, sender_id_local)
                            await cog.distribute_to_sub_owners(sub_id_local, self.amount)
                            tx_id_local = await cog.create_transaction(sender_id_local, None, self.amount, self.justification, "completed")
                            await interaction.response.edit_message(
                                content=f"Tip of {self.amount} sent to sub {sub_id_local} owners! (TX: {tx_id_local})",
                                view=None
                            )
                        else:
                            await cog.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", self.amount, sender_id_local)
                            await cog.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", self.amount, self.recipient_id)
                            tx_id_local = await cog.create_transaction(sender_id_local, self.recipient_id, self.amount, self.justification, "completed")
                            await interaction.response.edit_message(
                                content=f"Tip of {self.amount} sent! (TX: {tx_id_local})",
                                view=None
                            )

            view = discord.ui.View()
            for opt in tip_options:
                emoji = opt.get("emoji", None)
                amt = opt.get("amount", 0)
                if amt > 0:
                    view.add_item(TipButton(label=str(amt), amount=amt, recipient_id=recipient_id, justification=justification, emoji=emoji))

            await ctx.followup.send("Choose a tip amount:", view=view)

    @commands.slash_command(name="transfer", description="Transfer funds to another user.")
    async def transfer_cmd(self, ctx: discord.ApplicationContext, user: discord.User, amount: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if amount <= 0:
            await ctx.followup.send("Amount must be greater than 0.")
            return

        sender_id = ctx.author.id
        recipient_id = user.id
        if recipient_id == sender_id:
            await ctx.followup.send("You cannot transfer to yourself.")
            return

        economy_mode = await self.get_economy_mode()
        sender_balance = await self.user_balance(sender_id)
        if economy_mode == "open" and sender_balance < amount:
            await ctx.followup.send("You don't have enough balance.")
            return

        justification = "user_transfer"
        if self.needs_approval(economy_mode, amount):
            tx_id = await self.create_transaction(sender_id, recipient_id, amount, justification, "pending")
            await ctx.followup.send(f"Transfer pending staff approval (Amount: {amount}, TX: {tx_id}).")
        else:
            if sender_balance < amount:
                await ctx.followup.send("You don't have enough balance.")
                return
            await self.bot.db.execute("UPDATE wallets SET balance=balance-$1 WHERE user_id=$2;", amount, sender_id)
            await self.bot.db.execute("UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;", amount, recipient_id)
            tx_id = await self.create_transaction(sender_id, recipient_id, amount, justification, "completed")
            await ctx.followup.send(f"Transfer of {amount} to <@{recipient_id}> completed! (TX: {tx_id})")

    @commands.slash_command(name="staff", description="Staff-only economy approvals.")
    async def staff_group(self, ctx: discord.ApplicationContext):
        # Base group; no direct action
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)

    @staff_group.sub_command(name="approve_transaction", description="Approve a pending transaction.")
    async def staff_approve(self, ctx: discord.ApplicationContext, tx_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("You must be staff to use this command.")
            return

        success, message = await self.approve_transaction(tx_id)
        if success:
            await ctx.followup.send(f"Transaction {tx_id} approved.")
            logger.info(f"Staff {ctx.author.id} approved transaction {tx_id}.")
        else:
            await ctx.followup.send(f"Failed to approve transaction: {message}")

    @staff_group.sub_command(name="deny_transaction", description="Deny a pending transaction.")
    async def staff_deny(self, ctx: discord.ApplicationContext, tx_id: int):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("You must be staff to use this command.")
            return

        success, message = await self.deny_transaction(tx_id)
        if success:
            await ctx.followup.send(f"Transaction {tx_id} denied.")
            logger.info(f"Staff {ctx.author.id} denied transaction {tx_id}.")
        else:
            await ctx.followup.send(f"Failed to deny transaction: {message}")

    @commands.slash_command(name="config", description="Server configuration commands.")
    async def config_group(self, ctx: discord.ApplicationContext):
        # This is a parent group for config-related commands defined in another file
        # We'll ensure no conflicts arise as previously planned.
        if ctx.guild is None:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)

    @config_group.sub_command(name="economy_mode", description="Set the server's economy mode.")
    async def config_economy_mode(self, ctx: discord.ApplicationContext,
                                  mode: Option(str, "Economy mode: open, moderated, strict", choices=["open", "moderated", "strict"])):
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member or not await self.is_staff(member):
            await ctx.followup.send("Only staff can change economy mode.")
            return

        await self.set_economy_mode(mode)
        await ctx.followup.send(f"Economy mode set to {mode}.")
        logger.info(f"Economy mode changed to {mode} by staff {ctx.author.id}.")

def setup(bot: "MoguMoguBot"):
    bot.add_cog(EconomyCog(bot))

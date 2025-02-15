import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup, Option
import hashlib
from loguru import logger
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from main import MoguMoguBot

class Economy(commands.Cog):
    """
    A production-ready economy system with concurrency-safe wallet updates, 
    transaction ledger with blockchain-like hashing, tip reactions, 
    and now posting logs to a 'blockchain' channel on each transaction.
    """

    economy_group = SlashCommandGroup("economy", "Check and transfer credits.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self._wallets_checked = False

        # Load tip config from config.json
        self.tip_map = {}
        tip_options = self.bot.config.get("tip_options", [])
        for option in tip_options:
            self.tip_map[option["emoji"]] = option["amount"]

        # The channel for transaction logs. 
        # Example config key: "blockchain_transaction_channel_id": 1234567890123456
        self.blockchain_channel_id = self.bot.config.get("blockchain_transaction_channel_id", None)

    # ----------------------------------------------------------------------
    # LISTENERS
    # ----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure wallets for all existing members (runs only once)."""
        if self._wallets_checked:
            return
        self._wallets_checked = True

        total_created = 0
        for guild in self.bot.guilds:
            for member in guild.members:
                if not member.bot:
                    if await self.ensure_wallet_exists(member.id):
                        total_created += 1

        logger.debug(f"Completed wallet checks. Created {total_created} new wallets.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Create wallet for new members on join."""
        if member.bot:
            return
        if await self.ensure_wallet_exists(member.id):
            logger.info(f"[Economy] Created wallet for new member {member.id} ({member.display_name}).")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        If a user reacts with a recognized tip emoji, do a concurrency-safe tip 
        from the reactor -> message author, unless they are the same user or a bot.
        """
        if payload.user_id == self.bot.user.id:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in self.tip_map:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # skip if the same user or msg author is a bot
        if message.author.bot or message.author.id == payload.user_id:
            return

        tip_amount = self.tip_map[emoji_str]
        tipper_id = payload.user_id
        tippee_id = message.author.id

        success = await self.handle_tip_add(tipper_id, tippee_id, message, emoji_str, tip_amount)
        if not success:
            # remove the reaction if tip fails
            tipper_member = guild.get_member(tipper_id)
            if tipper_member:
                try:
                    await message.remove_reaction(payload.emoji, tipper_member)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        If user removes a tip reaction, we attempt a concurrency-safe 'refund' 
        from the message author -> the user, if that tip was recorded.
        """
        if payload.user_id == self.bot.user.id:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in self.tip_map:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        if message.author.bot or message.author.id == payload.user_id:
            return

        tip_amount = self.tip_map[emoji_str]
        tipper_id = payload.user_id
        tippee_id = message.author.id

        await self.handle_tip_remove(tipper_id, tippee_id, message, emoji_str, tip_amount)

    # ----------------------------------------------------------------------
    # TIP HELPERS
    # ----------------------------------------------------------------------

    async def handle_tip_add(self, tipper_id: int, tippee_id: int,
                             message: discord.Message,
                             emoji_str: str, tip_amount: int) -> bool:
        """
        concurrency-safe tip from tipper->tippee. 
        Insert row in reaction_tips to track it for refunds on reaction remove.
        """
        # check if tip already recorded
        logger.debug(f"[DEBUG] Tip triggered: {tipper_id} - {tipper_id} - {message} - {emoji_str} - {tip_amount}")
        row = await self.bot.db.fetchrow(
            """
            SELECT 1 FROM reaction_tips
             WHERE tipper_id=$1 AND message_id=$2 AND emoji=$3
            """,
            tipper_id, message.id, emoji_str
        )
        if row:
            # user already tipped
            return False

        # do the concurrency-safe transfer
        success = await self.transfer_balance(
            sender_id=tipper_id,
            recipient_id=tippee_id,
            amount=tip_amount,
            justification=f"Tip {emoji_str} on msg {message.id}"
        )

        logger.debug(f"[DEBUG] {sender_id} - {recipient_id} - {amount} - {justification}")
        if not success:
            return False

        # record in reaction_tips
        await self.bot.db.execute(
            """
            INSERT INTO reaction_tips (tipper_id, message_id, emoji, tip_amount, tippee_id)
            VALUES ($1, $2, $3, $4, $5)
            """,
            tipper_id, message.id, emoji_str, tip_amount, tippee_id
        )
        return True

    async def handle_tip_remove(self, tipper_id: int, tippee_id: int,
                                message: discord.Message,
                                emoji_str: str, tip_amount: int):
        """
        concurrency-safe 'refund' from tippee->tipper if row found in reaction_tips.
        """
        row = await self.bot.db.fetchrow(
            """
            SELECT 1 FROM reaction_tips
             WHERE tipper_id=$1 AND message_id=$2 AND emoji=$3
            """,
            tipper_id, message.id, emoji_str
        )
        if not row:
            return

        refund_ok = await self.transfer_balance(
            sender_id=tippee_id,
            recipient_id=tipper_id,
            amount=tip_amount,
            justification=f"Refund tip {emoji_str} on msg {message.id}"
        )
        if refund_ok:
            await self.bot.db.execute(
                """
                DELETE FROM reaction_tips
                 WHERE tipper_id=$1 AND message_id=$2 AND emoji=$3
                """,
                tipper_id, message.id, emoji_str
            )
        else:
            # The tippee might not have enough funds to refund
            logger.warning(
                f"[Economy] Could not refund tip removal for user {tipper_id} on msg {message.id}. "
                f"Tippee {tippee_id} might have spent the funds."
            )

    # ----------------------------------------------------------------------
    # WALLET/DB
    # ----------------------------------------------------------------------

    async def ensure_wallet_exists(self, user_id: int) -> bool:
        row = await self.bot.db.fetchrow(
            "SELECT user_id FROM wallets WHERE user_id=$1;", user_id
        )
        if row:
            return False
        await self.bot.db.execute(
            "INSERT INTO wallets (user_id, balance) VALUES ($1, 0);",
            user_id
        )
        return True

    async def get_balance(self, user_id: int) -> int:
        await self.ensure_wallet_exists(user_id)
        row = await self.bot.db.fetchrow(
            "SELECT balance FROM wallets WHERE user_id=$1;",
            user_id
        )
        if not row:
            return 0
        return row["balance"]

    async def add_balance(self, user_id: int, amount: int, reason: str = "") -> bool:
        if amount < 0:
            logger.error(f"[Economy] add_balance called with negative amount: {amount}")
            return False

        await self.ensure_wallet_exists(user_id)
        try:
            await self.bot.db.execute(
                "UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;",
                amount, user_id
            )
            await self.log_transaction(
                sender_id=0,
                recipient_id=user_id,
                amount=amount,
                justification=reason or "manual add_balance",
                status="completed"
            )
            return True
        except Exception as e:
            logger.exception(f"[Economy] Failed to add balance for {user_id}: {e}")
            return False

    async def deduct_balance(self, user_id: int, amount: int, reason: str = "") -> bool:
        if amount < 0:
            logger.error(f"[Economy] deduct_balance called with negative: {amount}")
            return False
        await self.ensure_wallet_exists(user_id)
        try:
            result = await self.bot.db.execute(
                """
                UPDATE wallets
                   SET balance=balance-$1
                 WHERE user_id=$2
                   AND balance >= $1
                """,
                amount,
                user_id
            )
            if "UPDATE 1" not in result:
                return False
            await self.log_transaction(
                sender_id=user_id,
                recipient_id=0,
                amount=amount,
                justification=reason or "manual deduct_balance",
                status="completed"
            )
            return True
        except Exception as e:
            logger.exception(f"[Economy] Failed to deduct balance for {user_id}: {e}")
            return False

    async def transfer_balance(
        self,
        sender_id: int,
        recipient_id: int,
        amount: int,
        justification: str = ""
    ) -> bool:
        if amount <= 0:
            logger.error(f"[Economy] transfer_balance called with non-positive: {amount}")
            return False

        await self.ensure_wallet_exists(sender_id)
        await self.ensure_wallet_exists(recipient_id)

        # concurrency safe transaction
        async with self.bot.db.pool.acquire() as conn:
            async with conn.transaction():
                deduct_result = await conn.execute(
                    """
                    UPDATE wallets
                       SET balance=balance-$1
                     WHERE user_id=$2
                       AND balance >= $1
                    """,
                    amount,
                    sender_id
                )
                if "UPDATE 1" not in deduct_result:
                    return False

                # add to recipient
                await conn.execute(
                    "UPDATE wallets SET balance=balance+$1 WHERE user_id=$2;",
                    amount,
                    recipient_id
                )

        await self.log_transaction(
            sender_id=sender_id,
            recipient_id=recipient_id,
            amount=amount,
            justification=justification or "transfer_balance",
            status="completed"
        )
        return True

    # ----------------------------------------------------------------------
    # LOGGING TRANSACTIONS
    # ----------------------------------------------------------------------

    async def log_transaction(
        self,
        sender_id: int,
        recipient_id: int,
        amount: int,
        justification: str,
        status: str = "pending"
    ):
        """
        Insert a row in 'transactions', chain the hash, THEN post an embed 
        to the 'blockchain' channel with the details (like we did in Ownership).
        """
        last_tx = await self.bot.db.fetchrow(
            "SELECT id, hash FROM transactions ORDER BY id DESC LIMIT 1;"
        )
        logger.debug(f"[DEBUG] logging txn: {sender_id} - {recipient_id} - {amount} - {justification} - {status}")
        prev_hash = last_tx["hash"] if last_tx else "0"

        tx_row = await self.bot.db.fetchrow(
            """
            INSERT INTO transactions (sender_id, recipient_id, amount, justification, status)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            sender_id,
            recipient_id,
            amount,
            justification,
            status
        )
        tx_id = tx_row["id"]

        # Build new hash
        to_hash = f"{tx_id}{sender_id}{recipient_id}{amount}{justification}{prev_hash}"
        tx_hash = hashlib.sha256(to_hash.encode()).hexdigest()

        # Update DB
        await self.bot.db.execute(
            "UPDATE transactions SET hash=$1 WHERE id=$2;",
            tx_hash, tx_id
        )

        logger.info(
            f"[Economy] Transaction #{tx_id} from {sender_id} -> {recipient_id}, amount={amount}, hash={tx_hash[:8]}..."
        )

        # 1) Build an embed
        embed = discord.Embed(
            title="Transaction Logged",
            description=(
                f"**ID:** {tx_id}\n"
                f"**Sender:** {sender_id if sender_id!=0 else 'System'}\n"
                f"**Recipient:** {recipient_id if recipient_id!=0 else 'System'}\n"
                f"**Amount:** {amount}\n"
                f"**Justification:** {justification}\n"
                f"**Hash:** `{tx_hash[:16]}...`\n"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Blockchain-like ledger")

        # 2) Post to the configured blockchain channel if available
        if self.blockchain_channel_id:
            channel = self.bot.get_channel(self.blockchain_channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as e:
                    logger.warning(
                        f"[Economy] Failed to send transaction #{tx_id} log to channel {channel.id}: {e}"
                    )

    # ----------------------------------------------------------------------
    # OPTIONAL: BASIC SLASH COMMANDS
    # ----------------------------------------------------------------------

    @economy_group.command(name="balance", description="Check your current credit balance.")
    async def balance_cmd(self, ctx: discord.ApplicationContext):
        """Let's the user see their current wallet balance (ephemeral)."""
        await ctx.defer(ephemeral=True)
        bal = await self.get_balance(ctx.user.id)
        await ctx.followup.send(f"Your balance is **{bal}** credits.", ephemeral=True)

    @economy_group.command(name="transfer", description="Transfer credits to another user.")
    async def transfer_cmd(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Recipient"),
        amount: Option(int, "Amount to transfer", min_value=1)
    ):
        """Slash-based ephemeral command for direct user->user transfers."""
        await ctx.defer(ephemeral=True)

        if member.id == ctx.user.id:
            return await ctx.followup.send("You can’t transfer to yourself!", ephemeral=True)

        ok = await self.transfer_balance(
            sender_id=ctx.user.id,
            recipient_id=member.id,
            amount=amount,
            justification="Slash-based user->user transfer"
        )
        if ok:
            await ctx.followup.send(
                f"Transferred {amount} credits to {member.mention}.",
                ephemeral=True
            )
        else:
            await ctx.followup.send(
                "Transfer failed (possibly insufficient funds).",
                ephemeral=True
            )

def setup(bot: commands.Bot):
    bot.add_cog(Economy(bot))

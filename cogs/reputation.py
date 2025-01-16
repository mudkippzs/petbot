# ./cogs/reputation.py
import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from discord import Option
from loguru import logger
from typing import TYPE_CHECKING, Optional, List, Dict

if TYPE_CHECKING:
    from main import MoguMoguBot

class ReputationCog(commands.Cog):
    """
    Cog for managing reputation and reviews of subs.
    Allows users to add ratings and comments, and view aggregated reviews.
    """

    review_group = SlashCommandGroup("reputation", "Add a review and rating for someone.")

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def sub_exists(self, sub_id: int) -> bool:
        """Check if a sub with the given ID exists."""
        row = await self.bot.db.fetchrow("SELECT id FROM subs WHERE id=$1;", sub_id)
        return row is not None

    async def get_reviews(self, sub_id: int) -> List[Dict]:
        """Get all reviews for a given sub."""
        rows = await self.bot.db.fetch(
            "SELECT rating, comment, user_id, timestamp FROM reviews WHERE sub_id=$1 ORDER BY timestamp DESC;",
            sub_id
        )
        return [dict(r) for r in rows]

    @review_group.command(name="add", description="Add a review and rating for a sub.")
    async def review_add(self,
                         ctx: discord.ApplicationContext,
                         sub_id: int,
                         rating: Option(int, "Your rating (1 to 5)"),
                         comment: Option(str, "Your review comment", default=None)):
        """
        Add a new review for a sub, including a rating and optional comment.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if not await self.sub_exists(sub_id):
            await ctx.followup.send("Sub not found.")
            return

        if rating < 1 or rating > 5:
            await ctx.followup.send("Rating must be between 1 and 5.")
            return

        # Insert review
        await self.bot.db.execute(
            "INSERT INTO reviews (sub_id, user_id, rating, comment) VALUES ($1, $2, $3, $4);",
            sub_id, ctx.author.id, rating, comment
        )

        await ctx.followup.send("Thank you for your review!")
        logger.info(f"User {ctx.author.id} added a review for sub {sub_id}, rating={rating}, comment={comment}")

    @review_group.command(name="view", description="View aggregated ratings and recent reviews for a sub.")
    async def review_view(self,
                          ctx: discord.ApplicationContext,
                          sub_id: int):
        """
        View the average rating and recent reviews for a given sub.
        Shows up to the 5 most recent reviews.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        if not await self.sub_exists(sub_id):
            await ctx.followup.send("Sub not found.")
            return

        reviews = await self.get_reviews(sub_id)
        if not reviews:
            await ctx.followup.send("No reviews found for this sub.")
            return

        # Calculate average rating
        avg_rating = sum(r["rating"] for r in reviews) / len(reviews)
        avg_rating_str = f"{avg_rating:.2f} / 5.00"

        # Show up to the 5 most recent reviews
        recent_reviews = reviews[:5]

        embed = discord.Embed(title=f"Sub {sub_id} Reviews", color=0x2F3136)
        embed.add_field(name="Average Rating", value=avg_rating_str, inline=False)
        embed.add_field(name="Total Reviews", value=str(len(reviews)), inline=False)

        for r in recent_reviews:
            user_id = r["user_id"]
            rating = r["rating"]
            comment = r["comment"] or "No comment provided."
            embed.add_field(name=f"Rating: {rating}/5 by <@{user_id}>",
                            value=comment,
                            inline=False)

        await ctx.followup.send(embed=embed)

def setup(bot: "MoguMoguBot"):
    bot.add_cog(ReputationCog(bot))

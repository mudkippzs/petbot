# ./cogs/help.py
import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
from typing import TYPE_CHECKING, List
from loguru import logger

if TYPE_CHECKING:
    from main import MoguMoguBot

class Help(commands.Cog):
    """
    A cog that provides a help command listing all available slash commands and their descriptions.
    Staff-only commands are hidden from non-staff users.
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot

    async def is_staff(self, member: discord.Member) -> bool:
        """Check if the given member is staff by querying staff_roles in DB."""
        staff_roles = await self.bot.db.fetch("SELECT role_id FROM staff_roles;")
        staff_role_ids = [r["role_id"] for r in staff_roles]
        if not staff_role_ids:
            return False
        return any(role.id in staff_role_ids for role in member.roles)

    def is_staff_command(self, cmd: commands.Command) -> bool:
        """
        Determine if a command (or its top-level group) is staff-only.
        This is a heuristic. We consider commands under 'staff' group as staff-only,
        and certain config sub-commands requiring staff checks as staff-only.
        
        Adjust this logic if you have a more robust way to mark staff commands.
        """
        # Identify command's top-level group name (if any)
        # For slash commands, the command hierarchy is in cmd.full_parent_name or cmd.root_parent.
        # We can inspect cmd.extras or cmd.__dict__ as well if we had annotations.
        # For simplicity, we check command or its parents name.
        parents = []
        cur = cmd
        while hasattr(cur, 'parent') and cur.parent is not None:
            parents.append(cur.parent.name)
            cur = cur.parent

        # Check if 'staff' is in the command's lineage
        if 'staff' in parents:
            return True

        # Check if 'config' is a parent and the command likely requires staff
        # From previous files, config changes require staff.
        if 'config' in parents:
            return True

        return False

    @commands.slash_command(name='help', description='View a list of all server commands.')
    async def help_cmd(self, ctx: discord.ApplicationContext):
        """
        Respond with an embedded message listing all available slash commands and their descriptions.
        Staff-only commands are hidden from non-staff users.
        """
        await ctx.defer(ephemeral=True)
        if ctx.guild is None:
            await ctx.followup.send("This command can only be used in a server.")
            return

        strings = self.bot.strings
        theme = self.bot.theme

        help_title = strings.get("help_title", "Help Menu")
        help_description = strings.get("help_description", "Below is a list of all available commands.")
        embed_color_hex = theme.get("embed_color", "#2F3136")
        try:
            embed_color = int(embed_color_hex.lstrip('#'), 16)
        except ValueError:
            embed_color = 0x2F3136  # Default Discord dark gray

        author_name = self.bot.user.name if self.bot.user else "MoguMoguBot"
        author_icon = self.bot.user.avatar.url if (self.bot.user and self.bot.user.avatar) else None
        footer_text = f"Requested by {ctx.author.display_name}"
        footer_icon = ctx.author.avatar.url if ctx.author.avatar else None

        embed = discord.Embed(
            title=help_title,
            description=help_description,
            color=embed_color
        )
        embed.set_author(name=author_name, icon_url=author_icon)
        embed.set_footer(text=footer_text, icon_url=footer_icon)

        # Filter commands: Only show non-staff commands to non-staff users
        # self.bot.tree.get_commands() can be used, but here we rely on self.bot.commands for now.
        commands_list = self.bot.commands
        has_commands = False
        for cmd in commands_list:
            # Slash commands in discord.py 2.0 are ApplicationCommands. If needed, we can adapt.
            # Assuming all cogs use slash commands, cmd should be an ApplicationCommand object.
            # Check if this command should be hidden from non-staff users:
            if self.is_staff_command(cmd) and not user_is_staff:
                continue

            # Show the command name and description
            # For slash commands, cmd.name and cmd.description should be available
            if not cmd.hidden:
                embed.add_field(
                    name=f"/{cmd.name}",
                    value=cmd.description or "No description provided.",
                    inline=False
                )
                has_commands = True

        if not has_commands:
            embed.add_field(
                name="No Commands Found",
                value="No public commands are currently available.",
                inline=False
            )

        await ctx.followup.send(embed=embed)

def setup(bot: "MoguMoguBot"):
    bot.add_cog(Help(bot))

import discord
import json
from discord.ext import commands
from loguru import logger
from typing import Optional, List


class RulesCog(commands.Cog):
    """
    Production-ready rules flow:
    - Pinned message shows "Main Rules" from final_notes
    - Ephemeral acceptance flow (3 pages): SSC, RACK, PRICK
    - Logs acceptance & unaccept in DB + staff channel
    - Admin commands: /rules send, /rules edit
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rules_channel_id = bot.config.get(
            "rules_channel_id")    # Channel ID for pinned rules
        self.rules_message_id = bot.config.get(
            "rules_message_id")    # Pinned message ID
        self.staff_channel_log_id = bot.config.get(
            "staff_channel_rules_log_id")  # Staff logs channel
        self.setup_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        """On bot start, re-attach pinned rules message so buttons remain interactive."""
        if self.setup_done:
            return
        self.setup_done = True

        if not self.rules_channel_id or not self.rules_message_id:
            return

        channel = self.bot.get_channel(self.rules_channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(self.rules_message_id)
        except discord.NotFound:
            return

        # Fetch rules from DB
        row = await self.bot.db.fetchrow("SELECT * FROM rules_text LIMIT 1;")
        if not row:
            # No rules => skip
            return

        pinned_embed, ephemeral_pages = self.build_rules_embeds(row)
        # Re-attach pinned message with the two-button view
        view = RulesEntryPointView(
            bot=self.bot,
            ephemeral_pages=ephemeral_pages,  # only the 3 pages for the ephemeral flow
            staff_channel_id=self.staff_channel_log_id
        )
        # We just re-attach; no need to .edit() since the message embed probably matches DB already
        self.bot.add_view(view, message_id=msg.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        logger.debug(f"[DEBUG] Member Joined: {member.display_name}")
        if guild:
            rules_role = discord.utils.get(guild.roles, name="Unverified")
            if rules_role:
                await member.add_roles(rules_role)
                logger.debug(
                    f"[DEBUG] Member Joined: Added {rules_role.name} to {member.display_name}")

    # ─────────────────────────────────────────────────────────────────
    # HELPER: Build pinned embed + ephemeral pages
    # ─────────────────────────────────────────────────────────────────
    def build_rules_embeds(self, row) -> (discord.Embed, List[discord.Embed]):
        """
        Returns:
            pinned_embed: from row["final_notes"] (the main server rules)
            ephemeral_pages: a list of 3 pages [SSC, RACK, PRICK]
        """
        # 1) pinned_embed is the "main rules" (previously 'final_notes')
        pinned_embed = discord.Embed(
            title="Server Rules",
            description=row["final_notes"],
            color=discord.Color.blurple()
        )

        # 2) ephemeral 3 pages: SSC, RACK, PRICK
        embed_ssc = discord.Embed(
            title="SSC – Safe, Sane, Consensual",
            description=row["ssc"],
            color=discord.Color.blurple()
        )
        embed_rack = discord.Embed(
            title="RACK – Risk-Aware Consensual Kink",
            description=row["rack"],
            color=discord.Color.blurple()
        )
        embed_prick = discord.Embed(
            title="PRICK – Personal Responsibility In Consensual Kink",
            description=row["prick"],
            color=discord.Color.blurple()
        )
        ephemeral_pages = [embed_ssc, embed_rack, embed_prick]

        return pinned_embed, ephemeral_pages

    # ─────────────────────────────────────────────────────────────────
    # ADMIN COMMAND: /rules send
    # ─────────────────────────────────────────────────────────────────
    @commands.slash_command(name="rules_send", description="(Admin) Send or update the pinned rules message.")
    @commands.has_permissions(administrator=True)
    async def rules_send(self, ctx: discord.ApplicationContext):
        """
        Creates or re-edits the pinned rules message. 
        The pinned message embed is the "main rules", 
        with two buttons: 'Begin' (3-page flow) & 'Unaccept'.
        """
        await ctx.defer(ephemeral=True)

        # 1) Ensure we have a row in rules_text
        row = await self.bot.db.fetchrow("SELECT * FROM rules_text LIMIT 1;")
        if not row:
            # Insert defaults if missing
            await self.bot.db.execute("""
                INSERT INTO rules_text (ssc, rack, prick, final_notes)
                VALUES ($1, $2, $3, $4)
            """,
                                      "Default SSC text",
                                      "Default RACK text",
                                      "Default PRICK text",
                                      "Final disclaimers here."
                                      )
            row = await self.bot.db.fetchrow("SELECT * FROM rules_text LIMIT 1;")

        if not row:
            return await ctx.followup.send("No rules text found or created in DB.", ephemeral=True, delete_after=30.0)

        # 2) Build the pinned embed + ephemeral pages
        pinned_embed, ephemeral_pages = self.build_rules_embeds(row)

        channel = self.bot.get_channel(self.rules_channel_id)
        if not channel:
            return await ctx.followup.send("Invalid rules_channel_id in config.", ephemeral=True, delete_after=30.0)

        # 3) If we already have a pinned message, try editing
        if self.rules_message_id:
            try:
                msg = await channel.fetch_message(self.rules_message_id)
                view = RulesEntryPointView(
                    bot=self.bot,
                    ephemeral_pages=ephemeral_pages,
                    staff_channel_id=self.staff_channel_log_id
                )
                await msg.edit(
                    content="Please read these rules. Then you may begin acceptance or unaccept below.",
                    embed=pinned_embed,
                    view=view
                )
                return await ctx.followup.send(f"Rules message updated: {msg.jump_url}", ephemeral=True, delete_after=30.0)
            except discord.NotFound:
                pass

        # 4) Otherwise, create a new pinned message
        view = RulesEntryPointView(
            bot=self.bot,
            ephemeral_pages=ephemeral_pages,
            staff_channel_id=self.staff_channel_log_id
        )
        sent = await channel.send(
            content="Please read these rules. Then you may begin acceptance or unaccept below.",
            embed=pinned_embed,
            view=view
        )

        self.rules_message_id = sent.id
        self.bot.config["rules_message_id"] = self.rules_message_id
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.bot.config, f, indent=4)

        await ctx.followup.send(f"New rules message pinned at {sent.jump_url}", ephemeral=True, delete_after=30.0)

    # ─────────────────────────────────────────────────────────────────
    # ADMIN COMMAND: /rules edit
    # ─────────────────────────────────────────────────────────────────
    @commands.slash_command(name="rules_edit", description="(Admin) Edit the text of SSC, RACK, PRICK, final notes.")
    @commands.has_permissions(administrator=True)
    async def rules_edit(self, ctx: discord.ApplicationContext):
        """Opens a Modal with four text fields for editing the DB-stored rules text."""
        # IMPORTANT: Do NOT defer if you plan to send a modal right away.
        row = await self.bot.db.fetchrow("SELECT * FROM rules_text LIMIT 1;")
        if not row:
            # Insert defaults if none exist
            await self.bot.db.execute("""
                INSERT INTO rules_text (ssc, rack, prick, final_notes)
                VALUES ($1, $2, $3, $4)
            """,
                                      "Default SSC text",
                                      "Default RACK text",
                                      "Default PRICK text",
                                      "Final disclaimers."
                                      )
            row = await self.bot.db.fetchrow("SELECT * FROM rules_text LIMIT 1;")

        ssc_def = row["ssc"]
        rack_def = row["rack"]
        prick_def = row["prick"]
        final_def = row["final_notes"]

        modal = RulesEditModal(ssc_def, rack_def, prick_def, final_def)
        # Directly send the modal as the single response
        await ctx.send_modal(modal)
        # (Optional) No ephemeral follow-up here, or do a small followup
        # For older PyCord, you can do a second .followup, but typically we skip it.


def setup(bot: commands.Bot):
    bot.add_cog(RulesCog(bot))


# ─────────────────────────────────────────────────────────────────
# VIEW: The pinned message (two buttons: Begin + Unaccept)
# ─────────────────────────────────────────────────────────────────
class RulesEntryPointView(discord.ui.View):
    """
    Pinned message:
      - Begin → ephemeral multi-page with ephemeral_pages (SSC, RACK, PRICK)
      - Unaccept → if user is accepted, remove acceptance
    """

    def __init__(self, bot: commands.Bot, ephemeral_pages: List[discord.Embed], staff_channel_id: Optional[int]):
        super().__init__(timeout=None)
        self.bot = bot
        self.ephemeral_pages = ephemeral_pages
        self.staff_channel_id = staff_channel_id

    @discord.ui.button(label="Begin", style=discord.ButtonStyle.primary, custom_id="rules_begin")
    async def begin_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        row = await self.bot.db.fetchrow(
            "SELECT accepted_at FROM rules_acceptance WHERE user_id=$1",
            interaction.user.id
        )
        if row:
            return await interaction.response.send_message(
                "You have already accepted the rules!",
                ephemeral=True,
                delete_after=30.0
            )

        # Not accepted -> ephemeral multi-page (only the 3 pages)
        view = MultiPageRulesView(
            bot=self.bot,
            user=interaction.user,
            pages=self.ephemeral_pages,
            staff_channel_id=self.staff_channel_id
        )
        await interaction.response.send_message(
            embed=self.ephemeral_pages[0],  # start on SSC
            view=view,
            ephemeral=True,
            delete_after=30.0
        )

    @discord.ui.button(label="Unaccept", style=discord.ButtonStyle.danger, custom_id="rules_unaccept")
    async def unaccept_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        row = await self.bot.db.fetchrow(
            "SELECT accepted_at FROM rules_acceptance WHERE user_id=$1",
            interaction.user.id
        )
        if not row:
            return await interaction.response.send_message(
                "You haven’t accepted the rules yet!",
                ephemeral=True,
                delete_after=30.0
            )

        # Remove from rules_acceptance
        await self.bot.db.execute("DELETE FROM rules_acceptance WHERE user_id=$1", interaction.user.id)
        # Insert a row in rules_acceptance_log with event='unaccepted'
        await self.bot.db.execute(
            "INSERT INTO rules_acceptance_log (user_id, event) VALUES ($1, 'unaccepted')",
            interaction.user.id
        )

        # Roles: remove Verified, add Unverified
        guild = interaction.guild
        if guild:
            rules_role = discord.utils.get(guild.roles, name="Rules Accepted")
            if rules_role and rules_role in interaction.user.roles:
                await interaction.user.remove_roles(rules_role)

        # Staff log
        if self.staff_channel_id:
            staff_ch = self.bot.get_channel(self.staff_channel_id)
            if staff_ch:
                embed = discord.Embed(
                    title="User Unaccepted Rules",
                    description=(
                        f"**User:** {interaction.user.mention} (ID: {interaction.user.id})\n"
                        f"**Timestamp:** <t:{int(discord.utils.utcnow().timestamp())}>"
                    ),
                    color=discord.Color.red()
                )
                await staff_ch.send(embed=embed)

        await interaction.response.send_message(
            "You have **unaccepted** the rules. Your community access is revoked.",
            ephemeral=True,
            delete_after=30.0
        )


# ─────────────────────────────────────────────────────────────────
# VIEW: Ephemeral multi-page acceptance (3 pages)
# ─────────────────────────────────────────────────────────────────
class MultiPageRulesView(discord.ui.View):
    """
    3 ephemeral pages: SSC, RACK, PRICK.
    On last page, "I Accept" → logs DB, staff channel, updates roles.
    """

    def __init__(self, bot: commands.Bot, user: discord.Member, pages: List[discord.Embed], staff_channel_id: Optional[int]):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user
        self.pages = pages
        self.staff_channel_id = staff_channel_id
        self.current_page = 0

        self.prev_button.disabled = True  # first page
        # only enable if there's 1 page or on last page
        self.accept_button.disabled = (len(self.pages) > 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This isn't your rules session!", ephemeral=True, delete_after=30.0)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def prev_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1

        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = False
        # if not last page, disable accept
        self.accept_button.disabled = (
            self.current_page != len(self.pages) - 1)

        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1

        # If last page, disable next & enable accept
        if self.current_page == len(self.pages) - 1:
            self.next_button.disabled = True
            self.accept_button.disabled = False
        else:
            self.next_button.disabled = False
            self.accept_button.disabled = True

        self.prev_button.disabled = False
        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=self
        )

    @discord.ui.button(label="I Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 1) Upsert acceptance
        await self.bot.db.execute("""
            INSERT INTO rules_acceptance (user_id, accepted_at)
            VALUES ($1, NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET accepted_at = EXCLUDED.accepted_at
        """, interaction.user.id)

        # 2) Log acceptance
        await self.bot.db.execute("""
            INSERT INTO rules_acceptance_log (user_id, event)
            VALUES ($1, 'accepted')
        """, interaction.user.id)

        # 3) Roles
        guild = interaction.guild
        if guild:
            rules_role = discord.utils.get(guild.roles, name="Rules Accepted")
            if rules_role:
                await interaction.user.add_roles(rules_role)

        # 4) Staff log
        if self.staff_channel_id:
            staff_ch = self.bot.get_channel(self.staff_channel_id)
            if staff_ch:
                embed = discord.Embed(
                    title="User Accepted Rules",
                    description=(
                        f"**User:** {interaction.user.mention} (ID: {interaction.user.id})\n"
                        f"**Time:** <t:{int(discord.utils.utcnow().timestamp())}>"
                    ),
                    color=discord.Color.green()
                )
                await staff_ch.send(embed=embed)

        # 5) Disable buttons
        for c in self.children:
            c.disabled = True

        support_channel = interaction.client.get_channel(
            interaction.client.config["support_channel_id"])
        await interaction.response.edit_message(
            content=f"You have accepted the rules! Please open a {support_channel.mention} to get verified to have full access to the community!",
            embed=self.pages[self.current_page],
            view=self
        )


# ─────────────────────────────────────────────────────────────────
# MODAL: Admin editing of the 4 rules fields
# ─────────────────────────────────────────────────────────────────
class RulesEditModal(discord.ui.Modal):
    """
    4 InputText fields for ssc, rack, prick, final_notes.
    We read the DB in /rules_edit, pass them here, and assign them to ._value
    for older PyCord versions that don't support default=... param.
    """

    def __init__(self, ssc_default: str, rack_default: str, prick_default: str, final_default: str):
        super().__init__(title="Edit Rules Text")

        # Field 1: SSC
        self.ssc_input = discord.ui.InputText(
            label="SSC Text",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.ssc_input._value = ssc_default

        # Field 2: RACK
        self.rack_input = discord.ui.InputText(
            label="RACK Text",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.rack_input._value = rack_default

        # Field 3: PRICK
        self.prick_input = discord.ui.InputText(
            label="PRICK Text",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.prick_input._value = prick_default

        # Field 4: Final Notes
        self.final_input = discord.ui.InputText(
            label="Final Notes (pinned rules)",
            style=discord.InputTextStyle.long,
            required=True
        )
        self.final_input._value = final_default

        self.add_item(self.ssc_input)
        self.add_item(self.rack_input)
        self.add_item(self.prick_input)
        self.add_item(self.final_input)

    async def callback(self, interaction: discord.Interaction):
        # New text from modal
        ssc_val = self.ssc_input.value.strip()
        rack_val = self.rack_input.value.strip()
        prick_val = self.prick_input.value.strip()
        final_val = self.final_input.value.strip()

        # Update DB
        await interaction.client.db.execute("""
            INSERT INTO rules_text (id, ssc, rack, prick, final_notes)
            VALUES (1, $1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE
               SET ssc=EXCLUDED.ssc,
                   rack=EXCLUDED.rack,
                   prick=EXCLUDED.prick,
                   final_notes=EXCLUDED.final_notes
        """, ssc_val, rack_val, prick_val, final_val)

        # Confirm ephemeral
        await interaction.response.send_message(
            "Rules text updated. Attempting to refresh pinned message.",
            ephemeral=True,
            delete_after=30.0
        )

        # Attempt pinned message refresh
        cog = interaction.client.get_cog("RulesCog")
        if not cog:
            return

        row = await interaction.client.db.fetchrow("SELECT * FROM rules_text WHERE id=1;")
        if not row:
            return

        pinned_embed, ephemeral_pages = cog.build_rules_embeds(row)

        if not (cog.rules_channel_id and cog.rules_message_id):
            return

        channel = interaction.client.get_channel(cog.rules_channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(cog.rules_message_id)
        except discord.NotFound:
            return

        view = RulesEntryPointView(
            bot=interaction.client,
            ephemeral_pages=ephemeral_pages,
            staff_channel_id=cog.staff_channel_log_id
        )
        await msg.edit(
            content="Please read these rules. Then you may begin acceptance or unaccept below.",
            embed=pinned_embed,
            view=view
        )

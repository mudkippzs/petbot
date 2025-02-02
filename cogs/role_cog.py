import discord
import json
from discord.ext import commands
from discord.commands import SlashCommandGroup
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Set
from loguru import logger

if TYPE_CHECKING:
    from main import MoguMoguBot

##############################################################################
# SELECT OPTIONS
##############################################################################

# Page 1: Age, Gender, Location
GENDER_OPTIONS = [
    discord.SelectOption(label="Gentleman", value="Gentleman", emoji="🤵"),
    discord.SelectOption(label="Harlot", value="Harlot", emoji="👰"),
]

AGE_OPTIONS = [
    discord.SelectOption(label="18-20", value="18-20", emoji="🔞"),
    discord.SelectOption(label="21-29", value="21-29", emoji="🍻"),
    discord.SelectOption(label="30-39", value="30-39", emoji="✨"),
    discord.SelectOption(label="40+", value="40+", emoji="✨"),
]

LOCATION_OPTIONS = [
    discord.SelectOption(label="Africa", value="Africa", emoji="🌍"),
    discord.SelectOption(label="Australia", value="Australia", emoji="🌏"),
    discord.SelectOption(label="Asia", value="Asia", emoji="🌏"),
    discord.SelectOption(label="Europe", value="Europe", emoji="🌍"),
    discord.SelectOption(label="North America", value="North America", emoji="🌎"),
    discord.SelectOption(label="South America", value="South America", emoji="🌎"),
]

# Page 2: Orientation, Here For
ORIENTATION_OPTIONS = [
    discord.SelectOption(label="Straight", value="Straight", emoji="👫"),
    discord.SelectOption(label="Gay/Lesbian", value="Gay/Lesbian", emoji="🌈"),
    discord.SelectOption(label="Bi/Bicurious", value="Bisexual/Bicurious", emoji="🔀"),
    discord.SelectOption(label="Pansexual", value="Pansexual", emoji="🍳"),
    discord.SelectOption(label="Asexual", value="Asexual", emoji="🎈"),
]

HERE_FOR_OPTIONS = [
    discord.SelectOption(label="Friendship", value="Friendship", emoji="👥"),
    discord.SelectOption(label="Online Play", value="Online Play", emoji="🎉"),
    discord.SelectOption(label="IRL Play", value="Irl Play", emoji="🎲"),
]

# Page 3: DM Status, Ping Roles
DM_STATUS_OPTIONS = [
    discord.SelectOption(label="Closed", value="Closed DMs", emoji="🚫"),
    discord.SelectOption(label="Open", value="Open DMs", emoji="✅"),
    discord.SelectOption(label="Ask to DM", value="Ask To DM", emoji="❓"),
    discord.SelectOption(label="Ask Owner to DM", value="Ask Owner to DM", emoji="❗"),
]

PING_ROLES_OPTIONS = [
    discord.SelectOption(label="Exhibition", value="Exhibition", emoji="📢"),
    discord.SelectOption(label="Events", value="Events", emoji="📢"),
    discord.SelectOption(label="Tasks", value="Tasks", emoji="🎁"),
    discord.SelectOption(label="VC", value="VC", emoji="📅"),
]

# Page 4: Kinks
KINKS_BONDAGE = [
    discord.SelectOption(label="None of these", value="n0t_a_r0le_bondage", emoji="❌"),
    discord.SelectOption(label="Bondage", value="bondage", emoji="🪢"),
    discord.SelectOption(label="Confinement", value="confinement", emoji="🎁"),
    discord.SelectOption(label="Gags", value="gags", emoji="🔇"),
    discord.SelectOption(label="Collar & Leash", value="collar & leash", emoji="🐶"),
    discord.SelectOption(label="Sensory Deprivation", value="sensory deprivation", emoji="🕶️"),
    discord.SelectOption(label="Clothing Control", value="clothing control", emoji="👕"),
    discord.SelectOption(label="Breath Play", value="breath play", emoji="💨"),
    discord.SelectOption(label="Latex", value="latex", emoji="⚫"),
    discord.SelectOption(label="Leather", value="leather", emoji="🧥"),
]

KINKS_BODY_PHYSICAL = [
    discord.SelectOption(label="None of these", value="n0t_a_r0le_physical", emoji="❌"),
    discord.SelectOption(label="Anal", value="anal", emoji="🍑"),
    discord.SelectOption(label="Rimming", value="rimming", emoji="🍑"),
    discord.SelectOption(label="Foot Fetish", value="foot fetish", emoji="🦶"),
    discord.SelectOption(label="Impacts", value="impacts", emoji="🔨"),
    discord.SelectOption(label="Rough Sex", value="rough sex", emoji="💥"),
    discord.SelectOption(label="Overstim", value="overstim", emoji="⚡"),
    discord.SelectOption(label="S&M", value="s&m", emoji="🔗"),
    discord.SelectOption(label="Face Fucking", value="face fucking", emoji="👄"),
    discord.SelectOption(label="Oral Fixation", value="oral fixation", emoji="👅"),
    discord.SelectOption(label="High Heels", value="high heels", emoji="👠"),
    discord.SelectOption(label="Body Worship", value="body worship", emoji="🧎"),
    discord.SelectOption(label="Pet Play", value="pet play", emoji="🐾"),
    discord.SelectOption(label="Medical", value="medical", emoji="🩺"),
    discord.SelectOption(label="Primal", value="primal", emoji="🐺"),
    discord.SelectOption(label="Group Sex", value="group sex", emoji="👥"),
    discord.SelectOption(label="Exhibitionism", value="exhibitionism", emoji="👁️"),
    discord.SelectOption(label="Lactation", value="lactation", emoji="🥛"),
    discord.SelectOption(label="Enemas", value="enemas", emoji="🚿"),
    discord.SelectOption(label="Watersports", value="watersports", emoji="💦"),
    discord.SelectOption(label="Breeding", value="breeding", emoji="🤰🏻"),
    discord.SelectOption(label="Lovense Toys", value="lovense toys", emoji="📱"),
    discord.SelectOption(label="Temperature Play", value="temperature play", emoji="🌡️"),
    discord.SelectOption(label="Figging", value="figging", emoji="🌶️"),
]

KINKS_PSYCH = [
    discord.SelectOption(label="None of these", value="n0t_a_r0le_psychic", emoji="❌"),
    discord.SelectOption(label="Bullying", value="bullying", emoji="👊"),
    discord.SelectOption(label="Insults", value="insults", emoji="💢"),
    discord.SelectOption(label="Fear", value="fear", emoji="😱"),
    discord.SelectOption(label="Gaslighting/Mindfucking", value="gaslighting/mindfucking", emoji="🌀"),
    discord.SelectOption(label="Degradation", value="degradation", emoji="🧟‍♂️"),
    discord.SelectOption(label="Humiliation", value="humiliation", emoji="😳"),
    discord.SelectOption(label="Denial", value="denial", emoji="❌"),
    discord.SelectOption(label="Begging", value="begging", emoji="🙏"),
    discord.SelectOption(label="Hypnosis", value="hypnosis", emoji="🌀"),
    discord.SelectOption(label="Dollification", value="dollification", emoji="🎎"),
    discord.SelectOption(label="Bimbo", value="bimbo", emoji="💁"),
    discord.SelectOption(label="Domestic Service", value="domestic service", emoji="🛎️"),
    discord.SelectOption(label="Food Control", value="food control", emoji="🍴"),
    discord.SelectOption(label="Financial Control", value="financial control", emoji="💰"),
    discord.SelectOption(label="Orgasm Control", value="orgasm control", emoji="⏳"),
    discord.SelectOption(label="Role Play", value="role play", emoji="🎭"),
    discord.SelectOption(label="Tears Crying", value="tears/crying", emoji="😭"),
    discord.SelectOption(label="Human Furniture", value="human furniture", emoji="🪑"),
]

KINKS_EDGE_EXTREME = [
    discord.SelectOption(label="None of these", value="n0t_a_r0le_extreme", emoji="❌"),
    discord.SelectOption(label="Abduction", value="abduction", emoji="🤏"),
    discord.SelectOption(label="Amputation", value="amputation", emoji="🦾"),
    discord.SelectOption(label="Blood Play", value="blood play", emoji="🧛‍♂️"),
    discord.SelectOption(label="Branding/Marking", value="branding/marking", emoji="✒️"),
    discord.SelectOption(label="Body Modification", value="body modification", emoji="🔧"),
    discord.SelectOption(label="CNC", value="cnc", emoji="⛔"),
    discord.SelectOption(label="Extreme/Edge Play", value="extreme/edge play", emoji="🗡️"),
    discord.SelectOption(label="Guns", value="guns", emoji="🔫"),
    discord.SelectOption(label="Knives", value="knives", emoji="🔪"),
    discord.SelectOption(label="Needles", value="needles", emoji="💉"),
    discord.SelectOption(label="Forced Intox", value="forced intox", emoji="🍸"),
    discord.SelectOption(label="Fire", value="fire", emoji="🔥"),
    discord.SelectOption(label="TPE", value="TPE", emoji="🎮"),
]

ADVANCED_KINK_VALUES = {
    "abduction", "amputation", "blood play", "body modification", "cnc",
    "extreme/edge play", "guns", "knives", "needles", "forced intox", "fire", "TPE"
}

##############################################################################
# COG
##############################################################################

class MultiUserRoleSelectCog(commands.Cog):
    """
    This cog posts a persistent "Role Setup" message with two buttons:
     1) Choose Roles (4-page flow)
     2) Edit/Remove Roles (4-page flow pre-filled with user’s current roles).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.role_setup_view = RoleSetupView(bot)
        self._reattached = False

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Optionally reattach to the existing "Role Setup" message if we have IDs in config.json.
        """
        if self._reattached:
            return
        self._reattached = True

        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            logger.info("No config.json found; skipping reattachment.")
            return

        msg_id = config_data.get("role_select_message_id")
        channel_id = config_data.get("role_select_channel_id")
        if not (msg_id and channel_id):
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Channel {channel_id} not found; cannot reattach.")
            return

        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(view=self.role_setup_view)
            self.bot.add_view(self.role_setup_view)
            logger.debug(f"Reattached to existing role setup message {msg_id}.")
        except discord.NotFound:
            logger.warning(f"Message {msg_id} not found.")
        except discord.Forbidden:
            logger.warning(f"No access to channel {channel_id}.")
        except Exception as e:
            logger.exception(f"Error reattaching: {e}")

    # Slash Command Group
    roles = SlashCommandGroup("roles", "Manage role preferences")

    @roles.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_role_message(self, ctx: discord.ApplicationContext):
        """
        Post the public "Choose / Edit Roles" message in this channel.
        """
        await ctx.defer(ephemeral=True)

        embed = discord.Embed(
            title="Choose your Roles!",
            description=(
                "Click **Choose Roles** to open an **ephemeral** menu where you can choose "
                "or edit your role selection!\n"
            ),
            color=discord.Color.blurple()
        )

        sent_msg = await ctx.channel.send(embed=embed, view=self.role_setup_view)

        # Save the message/channel IDs for re-attachment on restart
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = {}

        config_data["role_select_message_id"] = sent_msg.id
        config_data["role_select_channel_id"] = ctx.channel.id

        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)

        self.bot.add_view(self.role_setup_view)
        await ctx.respond("Role setup message created!", ephemeral=True, delete_after=30.0)


##############################################################################
# PUBLIC VIEW: RoleSetupView with two buttons
##############################################################################

class RoleSetupView(discord.ui.View):
    """
    The public message's view with 2 buttons:
     1) Choose Roles (fresh 4-page flow)
     2) Edit/Remove Roles (4-page flow pre-filled from DB).
    """
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Choose Roles", custom_id="roles-choose", style=discord.ButtonStyle.primary)
    async def choose_roles(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Error: Not a guild member.", ephemeral=True, delete_after=30.0)

        # Fetch existing record if any
        row = await self.bot.db.fetchrow("SELECT * FROM user_roles WHERE user_id=$1", interaction.user.id)
        if not row:
            # none found -> build empty
            row = {
                "gender_role": None,
                "age_range": None,
                "location": None,
                "orientation": None,
                "dm_status": None,
                "here_for": [],
                "ping_roles": [],
                "kinks": [],
            }
        else:
            row = dict(row)

        view = RolesFlowView(bot=self.bot, user=interaction.user, old_record=row)
        await interaction.response.send_message(
            content="**Select your roles & kinks** and click Finish on the final page when you're done:",
            view=view,
            ephemeral=True, 
            delete_after=600.0
        )


##############################################################################
# 4-PAGE FLOW: RolesFlowView
##############################################################################

class RolesFlowView(discord.ui.View):
    """
    A 4-page ephemeral flow for both "Choose Roles" and "Edit/Remove Roles."
    On "Finish," the user’s selections are stored in DB and synced as Discord roles.
    """

    def __init__(self, bot: commands.Bot, user: discord.Member, old_record: Dict[str, Any]):
        super().__init__(timeout=600)
        self.bot = bot
        self.user = user
        self.old_record = old_record

        # new_data starts from old_record
        self.new_data = {
            "gender_role": old_record.get("gender_role"),
            "age": old_record.get("age_range"),
            "location": old_record.get("location"),
            "orientation": old_record.get("orientation"),
            "dm_status": old_record.get("dm_status"),
            "here_for": list(old_record.get("here_for", [])),
            "ping_roles": list(old_record.get("ping_roles", [])),
            "kinks": list(old_record.get("kinks", [])),
        }

        self.page = 1
        self.render_page_1()

    # ─────────────────────────────────────────────────────────────────────
    # Page navigation
    # ─────────────────────────────────────────────────────────────────────
    def render_page_1(self):
        self.clear_items()
        self.page = 1

        # Page 1: Age, Gender, Location
        self.add_item(AgeSelect(self))
        self.add_item(GenderSelect(self))
        self.add_item(LocationSelect(self))
        self.add_item(Page1NextButton(self))

    def render_page_2(self):
        self.clear_items()
        self.page = 2

        # Page 2: Orientation, Here For
        self.add_item(OrientationSelect(self))
        self.add_item(HereForSelect(self))
        self.add_item(Page2BackButton(self))
        self.add_item(Page2NextButton(self))

    def render_page_3(self):
        self.clear_items()
        self.page = 3

        # Page 3: DM Status, Pingable Roles
        self.add_item(DMStatusSelect(self))
        self.add_item(PingRolesSelect(self))
        self.add_item(Page3BackButton(self))
        self.add_item(Page3NextButton(self))

    def render_page_4(self):
        self.clear_items()
        self.page = 4

        # Page 4: Kinks + Finish
        # We need to specify row indices so we don't exceed 5 rows total.
        self.add_item(BondageRestraintsSelect(self, row=0))
        self.add_item(BodyPhysicalSelect(self, row=1))
        self.add_item(PsychEmotionalSelect(self, row=2))
        self.add_item(EdgeExtremeSelect(self, row=3))
        # Put both buttons on the same row (row=4)
        self.add_item(Page4BackButton(self, row=4))
        self.add_item(FinishButton(self, row=4))

    async def next_page(self, interaction: discord.Interaction):
        if self.page == 1:
            self.render_page_2()
        elif self.page == 2:
            self.render_page_3()
        elif self.page == 3:
            self.render_page_4()
        await interaction.response.edit_message(view=self)

    async def previous_page(self, interaction: discord.Interaction):
        if self.page == 2:
            self.render_page_1()
        elif self.page == 3:
            self.render_page_2()
        elif self.page == 4:
            self.render_page_3()
        await interaction.response.edit_message(view=self)

    # ─────────────────────────────────────────────────────────────────────
    # Storing selections
    # ─────────────────────────────────────────────────────────────────────
    async def store_single_value(self, interaction: discord.Interaction, field_name: str, value: str):
        self.new_data[field_name] = value
        await interaction.response.defer()

    async def store_multi_value(self, interaction: discord.Interaction, field_name: str, values: List[str]):
        self.new_data[field_name] = values
        await interaction.response.defer()

    async def store_kinks_from_category(self, interaction: discord.Interaction, cat_values: List[str], chosen: List[str]):
        """
        For a given category (bondage, physical, etc.), remove old selections from that category,
        then add the newly chosen ones.
        """
        old_set = set(self.new_data["kinks"])
        # Remove old kinks from this category
        old_set = {k for k in old_set if k not in cat_values}
        # Add newly chosen
        new_set = old_set.union(chosen)
        self.new_data["kinks"] = list(new_set)
        await interaction.response.defer()

    # ─────────────────────────────────────────────────────────────────────
    # Finish Flow: upsert DB + remove/add Discord roles
    # ─────────────────────────────────────────────────────────────────────
    async def finish_flow(self, interaction: discord.Interaction):
        logger.debug("[finish_flow] Starting for user=%s", interaction.user.display_name)
        await interaction.response.defer(ephemeral=True)

        new = self.new_data
        logger.debug(f"[finish_flow] new_data={new}")

        # Check advanced kinks
        advanced_selected = [k for k in new["kinks"] if k.lower() in ADVANCED_KINK_VALUES]
        disclaimers = ""
        if advanced_selected:
            disclaimers = (
                "**Safety Disclaimer**\n"
                f"You have selected these edge/high-risk kinks: {', '.join(advanced_selected)}.\n"
                "By proceeding, you confirm you understand the associated risks.\n\n"
            )

        # Upsert
        upsert_query = """
            INSERT INTO user_roles (
                user_id,
                gender_role,
                age_range,
                location,
                orientation,
                dm_status,
                here_for,
                ping_roles,
                kinks
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (user_id) DO UPDATE
              SET gender_role = EXCLUDED.gender_role,
                  age_range   = EXCLUDED.age_range,
                  location    = EXCLUDED.location,
                  orientation = EXCLUDED.orientation,
                  dm_status   = EXCLUDED.dm_status,
                  here_for    = EXCLUDED.here_for,
                  ping_roles  = EXCLUDED.ping_roles,
                  kinks       = EXCLUDED.kinks,
                  updated_at  = NOW();
        """
        await self.bot.db.execute(
            upsert_query,
            self.user.id,
            new["gender_role"],
            new["age"],
            new["location"],
            new["orientation"],
            new["dm_status"],
            new["here_for"],
            new["ping_roles"],
            new["kinks"],
        )

        # Fetch updated record
        fresh = await self.bot.db.fetchrow("SELECT * FROM user_roles WHERE user_id=$1", self.user.id)
        if not fresh:
            logger.warning("[finish_flow] No record found after upsert.")
            fresh = {
                "gender_role": None,
                "age_range": None,
                "location": None,
                "orientation": None,
                "dm_status": None,
                "here_for": [],
                "ping_roles": [],
                "kinks": [],
            }
        else:
            fresh = dict(fresh)

        # Remove old roles, add new roles
        old = self.old_record
        member = self.user

        # Single-value fields
        single_map = {
            "gender_role": "gender",
            "age_range":   "age",
            "location":    "location",
            "orientation": "orientation",
            "dm_status":   "dm_status",
        }

        for db_column, field_label in single_map.items():
            old_val = old.get(db_column)
            new_val = fresh.get(db_column)

            if old_val and old_val != new_val:
                old_role = discord.utils.get(member.guild.roles, name=old_val)
                if old_role and old_role in member.roles:
                    try:
                        await member.remove_roles(old_role, reason=f"Removing old {field_label}")
                    except Exception as e:
                        logger.warning(f"Failed to remove role {old_val}: {e}")

            if new_val and new_val != old_val:
                new_role = discord.utils.get(member.guild.roles, name=new_val)
                if new_role:
                    try:
                        await member.add_roles(new_role, reason=f"Adding new {field_label}")
                    except Exception as e:
                        logger.warning(f"Failed to add role {new_val}: {e}")

        # Multi-value fields
        multi_fields = ["here_for", "ping_roles", "kinks"]
        for field in multi_fields:
            old_vals = set(old.get(field, []))
            new_vals = set(fresh.get(field, []))
            to_remove = old_vals - new_vals
            to_add = new_vals - old_vals

            for val in to_remove:
                role = discord.utils.get(member.guild.roles, name=val)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason=f"Remove {field}")
                    except Exception as e:
                        logger.warning(f"Failed removing {field} role {val}: {e}")

            for val in to_add:
                role = discord.utils.get(member.guild.roles, name=val)
                if role:
                    try:
                        await member.add_roles(role, reason=f"Add {field}")
                    except Exception as e:
                        logger.warning(f"Failed adding {field} role {val}: {e}")

        # Remove placeholders
        for placeholder in (
            "n0t_a_r0le_bondage",
            "n0t_a_r0le_physical",
            "n0t_a_r0le_psychic",
            "n0t_a_r0le_extreme"
        ):
            if placeholder in fresh["kinks"]:
                fresh["kinks"].remove(placeholder)

        # Summarize
        summary_list = [
            f"**Title**: {fresh['gender_role'] or 'None'}",
            f"**Age**: {fresh['age_range'] or 'None'}",
            f"**Location**: {fresh['location'] or 'None'}",
            f"**Orientation**: {fresh['orientation'] or 'None'}",
            f"**DM Status**: {fresh['dm_status'] or 'None'}",
            f"**Here For**: {', '.join(fresh['here_for']) or 'None'}",
            f"**Ping Roles**: {', '.join(fresh['ping_roles']) or 'None'}",
            f"**Kinks**: {', '.join(fresh['kinks']) or 'None'}",
        ]
        summary_str = "\n".join(summary_list)

        final_msg = f"{disclaimers}**Your final selections**:\n{summary_str}\n\nPreferences saved!"

        # Show ephemeral final result
        await interaction.followup.send(final_msg, ephemeral=True, delete_after=30.0)

        # Disable the view
        self.clear_items()
        await interaction.followup.edit_message(message_id=interaction.message.id, view=self)
        self.stop()


##############################################################################
# PAGE 1 SELECTS
##############################################################################

class AgeSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_value = parent_view.new_data["age"]
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value == current_value)
            )
            for o in AGE_OPTIONS
        ]
        super().__init__(placeholder="Select Age...", options=opts, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "age", self.values[0])


class GenderSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_value = parent_view.new_data["gender_role"]
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value == current_value)
            )
            for o in GENDER_OPTIONS
        ]
        super().__init__(placeholder="Select 'Gentleman' or 'Harlot'...", options=opts, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "gender_role", self.values[0])


class LocationSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_value = parent_view.new_data["location"]
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value == current_value)
            )
            for o in LOCATION_OPTIONS
        ]
        super().__init__(placeholder="Select Location...", options=opts, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "location", self.values[0])


class Page1NextButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView):
        super().__init__(label="Next", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.next_page(interaction)

##############################################################################
# PAGE 2 SELECTS
##############################################################################

class OrientationSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_value = parent_view.new_data["orientation"]
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value == current_value)
            )
            for o in ORIENTATION_OPTIONS
        ]
        super().__init__(placeholder="Select Orientation...", options=opts, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "orientation", self.values[0])


class HereForSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_set = set(parent_view.new_data["here_for"])
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value in current_set)
            )
            for o in HERE_FOR_OPTIONS
        ]
        super().__init__(placeholder="Select what you're here for...", options=opts, max_values=len(opts))
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_multi_value(interaction, "here_for", self.values)


class Page2BackButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.previous_page(interaction)


class Page2NextButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView):
        super().__init__(label="Next", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.next_page(interaction)

##############################################################################
# PAGE 3 SELECTS
##############################################################################

class DMStatusSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_value = parent_view.new_data["dm_status"]
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value == current_value)
            )
            for o in DM_STATUS_OPTIONS
        ]
        super().__init__(placeholder="Select DM Status...", options=opts, max_values=1)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "dm_status", self.values[0])


class PingRolesSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView):
        current_set = set(parent_view.new_data["ping_roles"])
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value in current_set)
            )
            for o in PING_ROLES_OPTIONS
        ]
        super().__init__(placeholder="Select Ping Roles...", options=opts, max_values=len(opts))
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_multi_value(interaction, "ping_roles", self.values)


class Page3BackButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.previous_page(interaction)


class Page3NextButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView):
        super().__init__(label="Next", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.next_page(interaction)

##############################################################################
# PAGE 4 SELECTS
##############################################################################

class BondageRestraintsSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView, row: int = 0):
        current_kinks = set(parent_view.new_data["kinks"])
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value in current_kinks)
            )
            for o in KINKS_BONDAGE
        ]
        super().__init__(
            placeholder="Bondage & Restraints",
            options=opts,
            max_values=len(opts),
            row=row
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [o.value for o in KINKS_BONDAGE]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)


class BodyPhysicalSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView, row: int = 0):
        current_kinks = set(parent_view.new_data["kinks"])
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value in current_kinks)
            )
            for o in KINKS_BODY_PHYSICAL
        ]
        super().__init__(
            placeholder="Body & Physical",
            options=opts,
            max_values=len(opts),
            row=row
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [o.value for o in KINKS_BODY_PHYSICAL]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)


class PsychEmotionalSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView, row: int = 0):
        current_kinks = set(parent_view.new_data["kinks"])
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value in current_kinks)
            )
            for o in KINKS_PSYCH
        ]
        super().__init__(
            placeholder="Psych & Emotional",
            options=opts,
            max_values=len(opts),
            row=row
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [o.value for o in KINKS_PSYCH]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)


class EdgeExtremeSelect(discord.ui.Select):
    def __init__(self, parent_view: RolesFlowView, row: int = 0):
        current_kinks = set(parent_view.new_data["kinks"])
        opts = [
            discord.SelectOption(
                label=o.label, value=o.value, emoji=o.emoji,
                default=(o.value in current_kinks)
            )
            for o in KINKS_EDGE_EXTREME
        ]
        super().__init__(
            placeholder="Edge & Extreme",
            options=opts,
            max_values=len(opts),
            row=row
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [o.value for o in KINKS_EDGE_EXTREME]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)


class Page4BackButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView, row: int = 4):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=row)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.previous_page(interaction)


class FinishButton(discord.ui.Button):
    def __init__(self, parent_view: RolesFlowView, row: int = 4):
        super().__init__(label="Finish", style=discord.ButtonStyle.success, row=row)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.finish_flow(interaction)


##############################################################################
# SETUP
##############################################################################

def setup(bot: commands.Bot):
    """
    Standard function for loading the cog.
    """
    bot.add_cog(MultiUserRoleSelectCog(bot))

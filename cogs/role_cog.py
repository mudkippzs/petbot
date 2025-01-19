import discord
import json
from discord.ext import commands
from discord.commands import SlashCommandGroup
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Set
from loguru import logger

if TYPE_CHECKING:
    from main import MoguMoguBot

##############################################################################
# SELECT OPTIONS (unchanged from your snippet)
##############################################################################

AGE_OPTIONS = [
    discord.SelectOption(label="18-20", value="18-20", emoji="🔞"),
    discord.SelectOption(label="21-29", value="21-29", emoji="🍻"),
    discord.SelectOption(label="30-39", value="30-39", emoji="✨"),
    discord.SelectOption(label="40+", value="40+", emoji="✨"),
]

RELATIONSHIP_OPTIONS = [
    discord.SelectOption(label="Single", value="Single", emoji="💕"),
    discord.SelectOption(label="In a relationship", value="In A Relationship", emoji="💖"),
    discord.SelectOption(label="Open relationship (Closed)", value="In a poly relationship (Closed)", emoji="🔒"),
    discord.SelectOption(label="Open relationship (Open)", value="In a poly relationship (Open)", emoji="🔓"),
    discord.SelectOption(label="It's Complicated", value="It's Complicated", emoji="❓"),
    discord.SelectOption(label="Owned Off Server", value="Owned Off Server", emoji="👥"),
]

LOCATION_OPTIONS = [
    discord.SelectOption(label="Africa", value="Africa", emoji="🌍"),
    discord.SelectOption(label="Australia", value="Australia", emoji="🌏"),
    discord.SelectOption(label="Asia", value="Asia", emoji="🌏"),
    discord.SelectOption(label="Europe", value="Europe", emoji="🌍"),
    discord.SelectOption(label="North America", value="North America", emoji="🌎"),
    discord.SelectOption(label="South America", value="South America", emoji="🌎"),
]

ORIENTATION_OPTIONS = [
    discord.SelectOption(label="Straight", value="Straight", emoji="👫"),
    discord.SelectOption(label="Gay/Lesbian", value="Gay/Lesbian", emoji="🌈"),
    discord.SelectOption(label="Bi/Bicurious", value="Bisexual/Bicurious", emoji="🔀"),
    discord.SelectOption(label="Pansexual", value="Pansexual", emoji="🍳"),
    discord.SelectOption(label="Asexual", value="Asexual", emoji="🎈"),
]

DM_STATUS_OPTIONS = [
    discord.SelectOption(label="Closed", value="Closed", emoji="🚫"),
    discord.SelectOption(label="Open", value="Open", emoji="✅"),
    discord.SelectOption(label="Ask to DM", value="Ask", emoji="❓"),
    discord.SelectOption(label="Ask Owner to DM", value="ask owner To Dm", emoji="❗"),
]

HERE_FOR_OPTIONS = [
    discord.SelectOption(label="Friendship", value="Friendship", emoji="👥"),
    discord.SelectOption(label="Online Play", value="Online Play", emoji="🎉"),
    discord.SelectOption(label="IRL Play", value="Irl Play", emoji="🎲"),
]

PING_ROLES_OPTIONS = [
    discord.SelectOption(label="Exhibition", value="Exhibition", emoji="📢"),
    discord.SelectOption(label="Events", value="Events", emoji="📢"),
    discord.SelectOption(label="Tasks", value="Tasks", emoji="🎁"),
    discord.SelectOption(label="VC", value="VC", emoji="📅"),
]

# Kink categories
KINKS_BONDAGE = [
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
    discord.SelectOption(label="Tpe", value="tpe", emoji="🤝"),
    discord.SelectOption(label="Role Play", value="role play", emoji="🎭"),
    discord.SelectOption(label="Tears Crying", value="tears/crying", emoji="😭"),
    discord.SelectOption(label="Human Furniture", value="human furniture", emoji="🪑"),
]

KINKS_EDGE_EXTREME = [
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

# If you need disclaimers for advanced kinks:
ADVANCED_KINK_VALUES = {
    "abduction", "amputation", "blood play", "body modification", "cnc",
    "extreme/edge play", "guns", "knives", "needles", "forced intox", "fire"
}

##############################################################################
# UTILITY: Saving & Removing roles
##############################################################################

async def assign_roles(bot: "MoguMoguBot", member: discord.Member, chosen_kinks: List[str]):
    """Assign kink roles if they exist in the guild."""
    for kink in chosen_kinks:
        role = discord.utils.get(member.guild.roles, name=kink)
        if role:
            try:
                await member.add_roles(role, reason=f"[Auto-assign] Kink: {kink}")
            except discord.Forbidden:
                logger.warning(f"Forbidden: cannot assign role {role.name} to {member.display_name}")
            except Exception as ex:
                logger.exception(f"Error assigning role {role.name}: {ex}")

async def remove_roles(bot: "MoguMoguBot", member: discord.Member, roles_to_remove: Set[str]):
    """Remove kink roles if the user has them."""
    for kink in roles_to_remove:
        role = discord.utils.get(member.guild.roles, name=kink)
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason=f"[Auto-remove] {kink}")
            except discord.Forbidden:
                pass
            except Exception as ex:
                logger.exception(f"Error removing role {role.name}: {ex}")

async def save_user_to_db(bot: "MoguMoguBot", user_id: int, record: Dict[str, Any]):
    """
    Example function for saving to DB.
    You can adapt to your own database logic.
    """
    try:
        query = """
            INSERT INTO user_roles (
                user_id, age_range, relationship, location, orientation, dm_status,
                here_for, ping_roles, kinks
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (user_id) DO UPDATE
              SET age_range    = EXCLUDED.age_range,
                  relationship = EXCLUDED.relationship,
                  location     = EXCLUDED.location,
                  orientation  = EXCLUDED.orientation,
                  dm_status    = EXCLUDED.dm_status,
                  here_for     = EXCLUDED.here_for,
                  ping_roles   = EXCLUDED.ping_roles,
                  kinks        = EXCLUDED.kinks,
                  updated_at   = NOW();
        """
        await bot.db.execute(
            query,
            user_id,
            record["age"],
            record["relationship"],
            record["location"],
            record["orientation"],
            record["dm_status"],
            record["here_for"],
            record["ping_roles"],
            record["kinks"],
        )
    except Exception as e:
        logger.exception(f"Failed to save user {user_id} to DB: {e}")

##############################################################################
# EPHEMERAL 3-PAGE VIEW (for a single user)
##############################################################################

class ThreePageRoleViewEphemeral(discord.ui.View):
    """
    A ephemeral, multi-page role selection flow.
    Each instance is used by exactly ONE user.
    """

    def __init__(self, bot: "MoguMoguBot", user: discord.Member):
        super().__init__(timeout=600)  # 10 minute timeout
        self.bot = bot
        self.user = user

        # This dictionary holds the user’s chosen data
        self.data = {
            "age": None,
            "relationship": None,
            "location": None,
            "orientation": None,
            "dm_status": None,
            "here_for": [],
            "ping_roles": [],
            "kinks": []
        }

        # Start on page 1
        self.page = 1
        self.render_page_1()

    # ──────────────────────────────────────────────────────────────────────────
    # PAGE RENDERING
    # ──────────────────────────────────────────────────────────────────────────
    def render_page_1(self):
        self.clear_items()
        self.page = 1
        self.add_item(AgeSelectEphemeral(self))
        self.add_item(RelationshipSelectEphemeral(self))
        self.add_item(LocationSelectEphemeral(self))
        self.add_item(OrientationSelectEphemeral(self))
        self.add_item(Page1NextButtonEphemeral(self))

    def render_page_2(self):
        self.clear_items()
        self.page = 2
        self.add_item(DMStatusSelectEphemeral(self))
        self.add_item(HereForSelectEphemeral(self))
        self.add_item(PingRolesSelectEphemeral(self))
        self.add_item(Page2BackButtonEphemeral(self))
        self.add_item(Page2NextButtonEphemeral(self))

    def render_page_3(self):
        self.clear_items()
        self.page = 3
        self.add_item(BondageRestraintsSelectEphemeral(self))
        self.add_item(BodyPhysicalSelectEphemeral(self))
        self.add_item(PsychEmotionalSelectEphemeral(self))
        self.add_item(EdgeExtremeSelectEphemeral(self))
        self.add_item(Page3BackButtonEphemeral(self))
        self.add_item(FinishButtonEphemeral(self))

    async def next_page(self, interaction: discord.Interaction):
        if self.page == 1:
            self.render_page_2()
        elif self.page == 2:
            self.render_page_3()
        await interaction.response.edit_message(view=self)

    async def previous_page(self, interaction: discord.Interaction):
        if self.page == 2:
            self.render_page_1()
        elif self.page == 3:
            self.render_page_2()
        await interaction.response.edit_message(view=self)

    # ──────────────────────────────────────────────────────────────────────────
    # FINAL STEP
    # ──────────────────────────────────────────────────────────────────────────
    async def finish_form(self, interaction: discord.Interaction):
        await interaction.response.defer()
        record = self.data
        user_id = self.user.id

        # Possibly check advanced kinks
        advanced_selected = [k for k in record["kinks"] if k.lower() in ADVANCED_KINK_VALUES]
        if advanced_selected:
            disclaimer = (
                "**Edge/Advanced Kink Disclaimer**\n"
                f"You chose: {', '.join(advanced_selected)}.\n"
                "These are considered higher-risk or extreme. By proceeding, you confirm you understand the risks."
            )
            await interaction.followup.send(disclaimer, ephemeral=True)

        # Assign single-value roles (Age, Relationship, etc.)
        # Make sure we have member object (we do: self.user).
        member = self.user

        # Age role
        if record["age"]:
            age_role = discord.utils.get(member.guild.roles, name=record["age"])
            if age_role:
                try:
                    await member.add_roles(age_role, reason=f"[Auto-assign] Age: {record['age']}")
                except Exception as e:
                    logger.warning(f"Could not assign age role: {e}")

        # Relationship role
        if record["relationship"]:
            rel_role = discord.utils.get(member.guild.roles, name=record["relationship"])
            if rel_role:
                try:
                    await member.add_roles(rel_role, reason=f"[Auto-assign] Relationship: {record['relationship']}")
                except Exception as e:
                    logger.warning(f"Could not assign relationship role: {e}")

        # Location role
        if record["location"]:
            loc_role = discord.utils.get(member.guild.roles, name=record["location"])
            if loc_role:
                try:
                    await member.add_roles(loc_role, reason=f"[Auto-assign] Location: {record['location']}")
                except Exception as e:
                    logger.warning(f"Could not assign location role: {e}")

        # Orientation role
        if record["orientation"]:
            orient_role = discord.utils.get(member.guild.roles, name=record["orientation"])
            if orient_role:
                try:
                    await member.add_roles(orient_role, reason=f"[Auto-assign] Orientation: {record['orientation']}")
                except Exception as e:
                    logger.warning(f"Could not assign orientation role: {e}")

        # DM Status
        if record["dm_status"]:
            dm_role = discord.utils.get(member.guild.roles, name=record["dm_status"])
            if dm_role:
                try:
                    await member.add_roles(dm_role, reason=f"[Auto-assign] DM status: {record['dm_status']}")
                except Exception as e:
                    logger.warning(f"Could not assign DM status role: {e}")

        # "Here For" roles
        for hf in record["here_for"]:
            role = discord.utils.get(member.guild.roles, name=hf)
            if role:
                try:
                    await member.add_roles(role, reason=f"[Auto-assign] Here For: {hf}")
                except Exception as e:
                    logger.warning(f"Could not assign HereFor role {hf}: {e}")

        # "Ping Roles"
        for pr in record["ping_roles"]:
            role = discord.utils.get(member.guild.roles, name=pr)
            if role:
                try:
                    await member.add_roles(role, reason=f"[Auto-assign] Ping role: {pr}")
                except Exception as e:
                    logger.warning(f"Could not assign Ping role {pr}: {e}")

        # Finally, the kinks:
        await assign_roles(self.bot, member, record["kinks"])

        # Save to DB
        await save_user_to_db(self.bot, user_id, record)

        # Build a summary
        summary_list = [
            f"**Age**: {record['age'] or 'None'}",
            f"**Relationship**: {record['relationship'] or 'None'}",
            f"**Location**: {record['location'] or 'None'}",
            f"**Orientation**: {record['orientation'] or 'None'}",
            f"**DM Status**: {record['dm_status'] or 'None'}",
            f"**Here For**: {', '.join(record['here_for']) or 'None'}",
            f"**Ping Roles**: {', '.join(record['ping_roles']) or 'None'}",
            f"**Kinks**: {', '.join(record['kinks']) if record['kinks'] else 'None'}",
        ]
        summary_str = "\n".join(summary_list)

        await interaction.followup.send(
            f"**Your final selections**:\n{summary_str}\n\nPreferences saved!",
            ephemeral=True
        )

        # Then disable the view so user can't keep clicking
        self.clear_items()
        await interaction.edit_original_response(view=self)
        self.stop()

    # ──────────────────────────────────────────────────────────────────────────
    # HELPER METHODS FOR SELECTS
    # ──────────────────────────────────────────────────────────────────────────
    async def store_single_value(self, interaction: discord.Interaction, field_name: str, value: str):
        self.data[field_name] = value
        await interaction.response.defer()

    async def store_multi_value(self, interaction: discord.Interaction, field_name: str, values: List[str]):
        self.data[field_name] = values
        await interaction.response.defer()

    async def store_kinks_from_category(self, interaction: discord.Interaction, category_options: List[str], chosen: List[str]):
        # Remove old kinks from this category if present
        old_set = set(self.data["kinks"])
        # Filter out anything from this category
        old_set = {k for k in old_set if k not in category_options}
        # Add the newly chosen ones
        new_set = old_set.union(chosen)
        self.data["kinks"] = list(new_set)
        await interaction.response.defer()


##############################################################################
# PAGE 1 SELECTS (Ephemeral)
##############################################################################

class AgeSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select your Age...",
            options=AGE_OPTIONS,
            max_values=1
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "age", self.values[0])

class RelationshipSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select Relationship...",
            options=RELATIONSHIP_OPTIONS,
            max_values=1
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "relationship", self.values[0])

class LocationSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select Location...",
            options=LOCATION_OPTIONS,
            max_values=1
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "location", self.values[0])

class OrientationSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select Orientation...",
            options=ORIENTATION_OPTIONS,
            max_values=1
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "orientation", self.values[0])

class Page1NextButtonEphemeral(discord.ui.Button):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(label="Next", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.next_page(interaction)

##############################################################################
# PAGE 2 SELECTS (Ephemeral)
##############################################################################

class DMStatusSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select DM Status...",
            options=DM_STATUS_OPTIONS,
            max_values=1
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_single_value(interaction, "dm_status", self.values[0])

class HereForSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select what you're here for...",
            options=HERE_FOR_OPTIONS,
            max_values=len(HERE_FOR_OPTIONS)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_multi_value(interaction, "here_for", self.values)

class PingRolesSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Select Ping Roles...",
            options=PING_ROLES_OPTIONS,
            max_values=len(PING_ROLES_OPTIONS)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.store_multi_value(interaction, "ping_roles", self.values)

class Page2BackButtonEphemeral(discord.ui.Button):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.previous_page(interaction)

class Page2NextButtonEphemeral(discord.ui.Button):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(label="Next", style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.next_page(interaction)

##############################################################################
# PAGE 3 SELECTS (Ephemeral)
##############################################################################

class BondageRestraintsSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Bondage & Restraints",
            options=KINKS_BONDAGE,
            max_values=len(KINKS_BONDAGE)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # List of all values in this category
        cat_values = [opt.value for opt in self.options]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)

class BodyPhysicalSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Body & Physical",
            options=KINKS_BODY_PHYSICAL,
            max_values=len(KINKS_BODY_PHYSICAL)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [opt.value for opt in self.options]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)

class PsychEmotionalSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Psych & Emotional",
            options=KINKS_PSYCH,
            max_values=len(KINKS_PSYCH)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [opt.value for opt in self.options]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)

class EdgeExtremeSelectEphemeral(discord.ui.Select):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(
            placeholder="Edge & Extreme",
            options=KINKS_EDGE_EXTREME,
            max_values=len(KINKS_EDGE_EXTREME)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        cat_values = [opt.value for opt in self.options]
        await self.parent_view.store_kinks_from_category(interaction, cat_values, self.values)

class Page3BackButtonEphemeral(discord.ui.Button):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.previous_page(interaction)

class FinishButtonEphemeral(discord.ui.Button):
    def __init__(self, parent_view: ThreePageRoleViewEphemeral):
        super().__init__(label="Finish", style=discord.ButtonStyle.success)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.finish_form(interaction)

##############################################################################
# EDIT/REMOVE KINKS VIEW
##############################################################################

class EditOrRemoveKinksView(discord.ui.View):
    """
    (Optional) For the 'Edit/Remove Roles' button. 
    This could open either the same 3-page flow with pre-filled data,
    or a simpler "remove only" ephemeral.

    For simplicity, here’s a minimal 'remove' approach:
    - We fetch the user's current kinks from DB (or memory).
    - We present them as a multi-select default=selected.
    - The user can uncheck to remove. 
    - As soon as they confirm, we remove from DB and roles.
    """
    def __init__(self, bot: "MoguMoguBot", user: discord.Member, current_kinks: List[str]):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.current_kinks = current_kinks

        if not current_kinks:
            return  # user has no kinks -> maybe just show a label "No kinks."

        # Build a multi-select with all current kinks defaulted
        opts = [
            discord.SelectOption(label=k, value=k, default=True)
            for k in current_kinks
        ]
        self.add_item(RemoveKinksSelect(self, opts))

class RemoveKinksSelect(discord.ui.Select):
    def __init__(self, parent_view: EditOrRemoveKinksView, opts: List[discord.SelectOption]):
        super().__init__(
            placeholder="Uncheck any kinks you wish to remove",
            options=opts,
            min_values=0,
            max_values=len(opts)
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        removed = set(self.default_values) - set(self.values)
        still_selected = set(self.values)

        # Remove from roles if the user has them
        if isinstance(self.parent_view.user, discord.Member):
            await remove_roles(
                self.parent_view.bot,
                self.parent_view.user,
                removed
            )

        # Update the DB to reflect the changed kink list
        new_kinks = list(still_selected)
        user_id = self.parent_view.user.id

        # If you have other columns in DB, fetch them. 
        # For now, we’ll just do a partial update:
        record = {
            "age": None,
            "relationship": None,
            "location": None,
            "orientation": None,
            "dm_status": None,
            "here_for": [],
            "ping_roles": [],
            "kinks": new_kinks,
        }
        await save_user_to_db(self.parent_view.bot, user_id, record)

        # Send ephemeral summary
        await interaction.response.send_message(
            f"Removed: {', '.join(removed) if removed else 'None'}\n"
            f"Still have: {', '.join(still_selected) if still_selected else 'None'}",
            ephemeral=True
        )
        # Stop the view so it can't be changed again
        self.view.stop()

##############################################################################
# THE ROLE-SETUP VIEW (Public message with two buttons)
##############################################################################

class RoleSetupView(discord.ui.View):
    """
    This is the public message's view that sits in a channel. 
    It has two buttons:
    1) "Choose Roles" → spawns ephemeral 3-page flow
    2) "Edit/Remove Roles" → spawns ephemeral menu to remove kinks (or re-open 3-page flow).
    """
    def __init__(self, bot: "MoguMoguBot"):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Choose Roles", custom_id="roles-view-choose-roles-button", style=discord.ButtonStyle.primary)
    async def choose_roles(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if not isinstance(interaction.user, discord.Member):
            return await interaction.respond("Error: Not a guild member.", ephemeral=True)
        
        view = ThreePageRoleViewEphemeral(self.bot, interaction.user)
        await interaction.respond(
            "**Select your roles & kinks:**",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Edit/Remove Roles", custom_id="roles-view-edit-delete-roles-button", style=discord.ButtonStyle.secondary)
    async def edit_roles(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if not isinstance(interaction.user, discord.Member):
            return await interaction.respond("Error: Not a guild member.", ephemeral=True)
        
        # For simplicity, let's say we fetch current kinks from the DB for the user:
        user_id = interaction.user.id
        # You need to do your own DB fetch. For example:
        # row = await self.bot.db.fetchrow("SELECT kinks FROM user_roles WHERE user_id=$1", user_id)
        # if row: current_kinks = row["kinks"]
        # else: current_kinks = []
        # We'll just pretend for now:
        current_kinks = []
        # ^^^ Replace above with actual DB or memory fetch

        view = EditOrRemoveKinksView(self.bot, interaction.user, current_kinks)
        if not current_kinks:
            return await interaction.respond("You currently have no kinks to remove!", ephemeral=True)

        await interaction.respond(
            "Uncheck any kinks you wish to remove:",
            view=view,
            ephemeral=True
        )

##############################################################################
# THE COG
##############################################################################

class MultiUserRoleSelectCog(commands.Cog):
    """
    Creates a single 'setup' message with two buttons. 
    Each user who clicks gets their own ephemeral multi-page flow or remove flow.
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self.role_setup_view = RoleSetupView(bot)
        self._reattached = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Optionally reattach to existing message if you stored IDs
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
            logger.info(f"Reattached to existing role setup message {msg_id}.")
        except discord.NotFound:
            logger.warning(f"Message {msg_id} not found.")
        except discord.Forbidden:
            logger.warning(f"No access to channel {channel_id}.")
        except Exception as e:
            logger.exception(f"Error reattaching: {e}")

    # Optionally a slash command to create the setup message
    roles = SlashCommandGroup("roles", "Manage role preferences")

    @roles.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_role_message(self, ctx: discord.ApplicationContext):
        """
        Creates the public 'Choose Roles / Edit Roles' message in this channel.
        """
        await ctx.defer(ephemeral=True)

        embed = discord.Embed(
            title="Get Your Roles!",
            description=(
                "Click **Choose Roles** to open an **ephemeral** multi-page menu where you can select your roles.\n"
                "Click **Edit/Remove Roles** to remove (uncheck) any of your previously selected kinks."
            ),
            color=discord.Color.blurple()
        )

        sent_msg = await ctx.channel.send(embed=embed, view=self.role_setup_view)

        # Save the message & channel IDs so we can reattach on bot restart
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
        await ctx.respond("Role setup message created!", ephemeral=True)


def setup(bot: "MoguMoguBot"):
    bot.add_cog(MultiUserRoleSelectCog(bot))

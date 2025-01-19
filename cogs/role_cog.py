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

# Page 1: We keep these as you had before
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

# Page 2:
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

# Page 3: We divide kinks into 4 categories, each with <= 25 items

# 1) Bondage & Restraints
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

# 2) Body & Physical
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

# 3) Psych & Emotional
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

# 4) Edge & Extreme (Advanced)
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

# If you need disclaimers for advanced kinks
ADVANCED_KINK_VALUES = {
    "Abduction", "Amputation", "Blood Play", "Body Modification", "CNC",
    "Edge Play", "Extreme Edge Play", "Guns", "Knives", "Needles", 
    "Forced Intox", "Fire"
}

##############################################################################
# THE THREE-PAGE VIEW
##############################################################################

class ThreePageRoleView(discord.ui.View):
    """
    Page 1: Age, Relationship, Location, Orientation
    Page 2: DM Status, Here For, Ping Roles
    Page 3: Kink categories (4 selects) + Finish
    """

    def __init__(self, bot: "MoguMoguBot"):        
        super().__init__(timeout=None)
        self.bot = bot
        self.page = 1
        # user_data[user_id] = {...}
        self.user_data: Dict[int, Dict[str, Any]] = {}
        self._render_page_1()

    # Ensure user record
    def _ensure_user_record(self, user_id: int):
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                "age": None,
                "relationship": None,
                "location": None,
                "orientation": None,
                "dm_status": None,
                "here_for": [],
                "ping_roles": [],
                # We'll store a combined list of all chosen kinks from the 4 category selects
                "kinks": [],
            }

    # DB saving example

    async def _save_user_to_db(self, user_id: int, record: Dict[str, Any]):
        """
        Example of saving to DB. Adjust to your code.
        """
        try:
            query = """
                INSERT INTO user_roles (
                  user_id, age_range, relationship, location, orientation, dm_status,
                  here_for, ping_roles, kinks
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (user_id) DO UPDATE
                    SET kinks = EXCLUDED.kinks,
                        updated_at = NOW();
            """
            await self.bot.db.execute(
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
            print(f"Failed to save user {user_id} to DB: {e}")


    async def _assign_roles(self, member: discord.Member, chosen_kinks: List[str]):
        """
        Example: If your server has roles named the same as the kink values.
        """
        for kink in chosen_kinks:
            role = discord.utils.get(member.guild.roles, name=kink)
            if role:
                try:
                    await member.add_roles(role, reason=f"[Auto-assign] Role: {kink}")
                except discord.Forbidden:
                    logger.warning(f"Forbidden: cannot assign role {role.name} to {member.display_name}")
                except Exception as ex:
                    logger.exception(f"Error assigning role {role.name}: {ex}")
    
    async def _remove_roles(self, member: discord.Member, removed_kinks: Set[str]):
        for kink in removed_kinks:
            # If your actual role names match the kink strings, adjust as needed
            role_name = kink  # e.g. "foot fetish" => "foot fetish"
            role = discord.utils.get(member.guild.roles, name=role_name)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="[Auto-remove] Role removal")
                except discord.Forbidden:
                    pass
                except Exception as ex:
                    print(f"Error removing role {role.name}: {ex}")

    ########################################################################
    # PAGE RENDERING
    ########################################################################

    def _render_page_1(self):
        self.clear_items()
        self.page = 1

        self.add_item(AgeSelect())
        self.add_item(RelationshipSelect())
        self.add_item(LocationSelect())
        self.add_item(OrientationSelect())

        self.add_item(Page1NextButton())

    def _render_page_2(self):
        self.clear_items()
        self.page = 2

        self.add_item(DMStatusSelect())
        self.add_item(HereForSelect())
        self.add_item(PingRolesSelect())

        self.add_item(Page2BackButton())
        self.add_item(Page2NextButton())

    def _render_page_3(self):
        self.clear_items()
        self.page = 3

        # 4 categories, each a select. Each is assigned row=0..3, then Finish is row=4
        self.add_item(BondageRestraintsSelect())
        self.add_item(BodyPhysicalSelect())
        self.add_item(PsychEmotionalSelect())
        self.add_item(EdgeExtremeSelect())

        self.add_item(Page3BackButton())
        self.add_item(FinishButton())

    async def next_page(self, interaction: discord.Interaction):
        if self.page == 1:
            self._render_page_2()
        elif self.page == 2:
            self._render_page_3()

        await interaction.response.edit_message(view=self)

    async def previous_page(self, interaction: discord.Interaction):
        """Handles Back button transitions."""
        if self.page == 2:
            self._render_page_1()
        elif self.page == 3:
            self._render_page_2()

        await interaction.response.edit_message(view=self)

    async def finish_form(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        self._ensure_user_record(user_id)
        record = self.user_data[user_id]

        # 1) Kinks
        chosen_kinks = record["kinks"]

        # 2) Single-value fields
        age = record["age"]
        relationship = record["relationship"]
        location = record["location"]
        orientation = record["orientation"]

        # 3) Multi-value fields
        dm_status = record["dm_status"]      # single-value
        here_for  = record["here_for"]       # list
        ping_roles = record["ping_roles"]    # list

        # (Optional) Show disclaimers for advanced kinks
        advanced_selected = [k for k in chosen_kinks if k in ADVANCED_KINK_VALUES]
        if advanced_selected:
            disclaimer = (
                "**Edge/Advanced Kink Disclaimer**\n"
                f"You chose: {', '.join(advanced_selected)}.\n"
                "These are considered higher-risk or extreme. By proceeding, you confirm you understand the risks."
            )
            await interaction.response.send_message(disclaimer, ephemeral=True)
        else:
            await interaction.response.defer(ephemeral=True)

        # Because the user is an Interaction user, we can check if they're actually a Member
        if isinstance(interaction.user, discord.Member):
            member = interaction.user

            if age:  # e.g. "18-20"
                age_role = discord.utils.get(member.guild.roles, name=age)
                if age_role:
                    await member.add_roles(age_role, reason=f"[Auto-assign] Age role: {age}")

            if relationship:  # e.g. "Single" / "In a Relationship"
                rel_role = discord.utils.get(member.guild.roles, name=relationship)
                if rel_role:
                    await member.add_roles(rel_role, reason=f"[Auto-assign] Relationship role: {relationship}")

            if location:  # e.g. "Asia"
                loc_role = discord.utils.get(member.guild.roles, name=location)
                if loc_role:
                    await member.add_roles(loc_role, reason=f"[Auto-assign] Location role: {location}")

            if orientation:  # e.g. "Straight", "Bisexual/Bicurious", etc.
                orient_role = discord.utils.get(member.guild.roles, name=orientation)
                if orient_role:
                    await member.add_roles(orient_role, reason=f"[Auto-assign] Orientation role: {orientation}")

            if dm_status:  # e.g. "Open", "Closed"
                dm_role = discord.utils.get(member.guild.roles, name=dm_status)
                if dm_role:
                    await member.add_roles(dm_role, reason=f"[Auto-assign] DM status: {dm_status}")

            # If you have roles for "here for" or "ping roles," assign them too:
            for hf in here_for:  # e.g. "Friendship", "IRL Play"
                role = discord.utils.get(member.guild.roles, name=hf)
                if role:
                    await member.add_roles(role, reason=f"[Auto-assign] Here For role: {hf}")

            for pr in ping_roles:  # e.g. "Exhibition", "Events"
                role = discord.utils.get(member.guild.roles, name=pr)
                if role:
                    await member.add_roles(role, reason=f"[Auto-assign] Ping Role: {pr}")

            # Finally, assign the kink roles:
            await self._assign_roles(member, chosen_kinks)

        # Save user to DB
        await self._save_user_to_db(user_id, record)

        # Then send the summary
        summary_list = [
            f"**Age**: {age or 'None'}",
            f"**Relationship**: {relationship or 'None'}",
            f"**Location**: {location or 'None'}",
            f"**Orientation**: {orientation or 'None'}",
            f"**DM Status**: {dm_status or 'None'}",
            f"**Here For**: {', '.join(here_for) or 'None'}",
            f"**Ping Roles**: {', '.join(ping_roles) or 'None'}",
            f"**Kinks**: {', '.join(chosen_kinks) if chosen_kinks else 'None'}",
        ]
        summary_str = "\n".join(summary_list)

        await interaction.followup.send(
            f"**Your final selections**:\n{summary_str}\n\n"
            "Preferences saved. Use `/roles remove` to remove any kinks later.",
            ephemeral=True
        )

    async def handle_selection(
        self,
        interaction: discord.Interaction,
        field_name: str,
        values: List[str],
        multiple: bool = True
    ):
        # Always "defer" or "send_message" within 3 seconds so the interaction doesn't time out

        user_id = interaction.user.id
        self._ensure_user_record(user_id)

        # Actually store the selected values
        if multiple:
            self.user_data[user_id][field_name] = values
        else:
            self.user_data[user_id][field_name] = values[0] if values else None

        # Optional: print/log it so you confirm it’s being saved
        logger.info(f"[DEBUG] {field_name} set to {values} for user {user_id}")

    async def handle_kinks_selection(
        self,
        interaction: discord.Interaction,
        chosen_values: List[str],
        category_values: List[str]
    ):
        user_id = interaction.user.id
        self._ensure_user_record(user_id)

        old_kinks = set(self.user_data[user_id]["kinks"])

        # Remove any from this category that the user had previously
        # (since we want to "replace" the category)
        old_kinks = {k for k in old_kinks if k not in category_values}

        # Now add the newly chosen ones
        new_kinks = old_kinks.union(chosen_values)

        # Store back in user_data
        self.user_data[user_id]["kinks"] = list(new_kinks)


##############################################################################
# PAGE 1 SELECTS
##############################################################################

class AgeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Select your Age...", options=AGE_OPTIONS, custom_id="role-view-select-age", max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view  # type: ignore
        await view.handle_selection(interaction, "age", self.values, multiple=False)

class RelationshipSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Select Relationship...", options=RELATIONSHIP_OPTIONS, custom_id="role-view-select-relationship", max_values=1, row=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view  # type: ignore
        await view.handle_selection(interaction, "relationship", self.values, multiple=False)

class LocationSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Select Location...", options=LOCATION_OPTIONS, custom_id="role-view-select-location", max_values=1, row=2)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view  # type: ignore
        await view.handle_selection(interaction, "location", self.values, multiple=False)

class OrientationSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Select Orientation...", options=ORIENTATION_OPTIONS, custom_id="role-view-select-orientation", max_values=1, row=3)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view  # type: ignore
        await view.handle_selection(interaction, "orientation", self.values, multiple=False)

class Page1NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next",
            style=discord.ButtonStyle.primary,
            custom_id="p1_next_button"
        )

    async def callback(self, interaction: discord.Interaction):
        view: ThreePageRoleView = self.view  # type: ignore
        await view.next_page(interaction)

##############################################################################
# PAGE 2 SELECTS
##############################################################################

class DMStatusSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Select DM Status...", options=DM_STATUS_OPTIONS, custom_id="role-view-select-dm", max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view
        await view.handle_selection(interaction, "dm_status", self.values, multiple=False)

class HereForSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select what you're here for...",
            options=HERE_FOR_OPTIONS,
            custom_id="role-view-select-here-for", 
            max_values=len(HERE_FOR_OPTIONS),
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view  # type: ignore
        await view.handle_selection(interaction, "here_for", self.values, multiple=True)

class PingRolesSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select Ping Roles...",
            options=PING_ROLES_OPTIONS,            
            custom_id="role-view-select-ping-roles", 
            max_values=len(PING_ROLES_OPTIONS),
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view: ThreePageRoleView = self.view  # type: ignore
        await view.handle_selection(interaction, "ping_roles", self.values, multiple=True)

class Page2BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Back",
            style=discord.ButtonStyle.secondary,
            custom_id="p2_back_button"
        )

    async def callback(self, interaction: discord.Interaction):
        view: ThreePageRoleView = self.view  # type: ignore
        await view.previous_page(interaction)

class Page2NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Next",
            style=discord.ButtonStyle.primary,
            custom_id="p2_next_button"
        )

    async def callback(self, interaction: discord.Interaction):
        view: ThreePageRoleView = self.view  # type: ignore
        await view.next_page(interaction)

##############################################################################
# PAGE 3: KINKS - 4 SELECTS (each category ≤ 25 items)
##############################################################################

class BondageRestraintsSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Bondage & Restraints",
            options=KINKS_BONDAGE,        
            custom_id="role-view-select-kinks-1", 
            max_values=len(KINKS_BONDAGE),
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except:
            pass
        view: ThreePageRoleView = self.view  # type: ignore
        # Grab all possible values for this category from self.options
        possible_values = [opt.value for opt in self.options]

        # Pass both the chosen values (`self.values`) and
        # the entire category's possible values (`possible_values`)
        await view.handle_kinks_selection(
            interaction,
            chosen_values=self.values,
            category_values=possible_values
        )


class BodyPhysicalSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Body & Physical",
            options=KINKS_BODY_PHYSICAL,           
            custom_id="role-view-select-kinks-2", 
            max_values=len(KINKS_BODY_PHYSICAL),
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except:
            pass
        view: ThreePageRoleView = self.view  # type: ignore
        # Grab all possible values for this category from self.options
        possible_values = [opt.value for opt in self.options]

        # Pass both the chosen values (`self.values`) and
        # the entire category's possible values (`possible_values`)
        await view.handle_kinks_selection(
            interaction,
            chosen_values=self.values,
            category_values=possible_values
        )

class PsychEmotionalSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Psych & Emotional",
            options=KINKS_PSYCH,           
            custom_id="role-view-select-kinks-3", 
            max_values=len(KINKS_PSYCH),
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except:
            pass
        view: ThreePageRoleView = self.view  # type: ignore
        # Grab all possible values for this category from self.options
        possible_values = [opt.value for opt in self.options]

        # Pass both the chosen values (`self.values`) and
        # the entire category's possible values (`possible_values`)
        await view.handle_kinks_selection(
            interaction,
            chosen_values=self.values,
            category_values=possible_values
        )

class EdgeExtremeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Edge & Extreme",
            options=KINKS_EDGE_EXTREME,           
            custom_id="role-view-select-kinks-4", 
            max_values=len(KINKS_EDGE_EXTREME),
            row=4
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except:
            pass
        view: ThreePageRoleView = self.view  # type: ignore
        # Grab all possible values for this category from self.options
        possible_values = [opt.value for opt in self.options]

        # Pass both the chosen values (`self.values`) and
        # the entire category's possible values (`possible_values`)
        await view.handle_kinks_selection(
            interaction,
            chosen_values=self.values,
            category_values=possible_values
        )

class Page3BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Back",
            style=discord.ButtonStyle.secondary,
            custom_id="p3_back_button"
        )

    async def callback(self, interaction: discord.Interaction):
        view: ThreePageRoleView = self.view  # type: ignore
        await view.previous_page(interaction)

class FinishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Finish",
            style=discord.ButtonStyle.success,
            custom_id="finish_button"
        )

    async def callback(self, interaction: discord.Interaction):
        view: ThreePageRoleView = self.view  # type: ignore
        await view.finish_form(interaction)

##############################################################################
# KINK REMOVAL (EPHEMERAL) VIEW
##############################################################################

class KinkRemovalView(discord.ui.View):
    def __init__(
        self,
        bot: "MoguMoguBot",
        user_id: int,
        user_data: Dict[str, Any],
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.user_data = user_data

        # Just add the select, no confirm button
        self.add_item(KinkRemovalSelect(bot, user_id, user_data))


class KinkRemovalSelect(discord.ui.Select):
    """
    Pre-select all current kinks; user unchecks any they want to remove.
    
    As soon as the user changes the selection, we finalize the removal.
    """
    def __init__(self, bot: "MoguMoguBot", user_id: int, user_data: Dict[str, Any]):
        self.bot = bot
        self.user_id = user_id
        self.user_data = user_data
        
        current_kinks = user_data["kinks"]
        opts = [
            discord.SelectOption(label=k, value=k, default=True)
            for k in current_kinks
        ]
        super().__init__(
            placeholder="Uncheck any kinks you wish to remove...",
            options=opts,
            min_values=0,
            max_values=len(opts)
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # The old set of kinks
        old_kinks = set(self.user_data["kinks"])
        # The new set is whatever the user kept checked
        still_selected = set(self.values)
        # The removed set is whatever was old but not in the new selection
        removed = old_kinks - still_selected

        # Update user_data in memory
        self.user_data["kinks"] = list(still_selected)

        # If we can remove roles from the user
        if isinstance(interaction.user, discord.Member):
            # Remove the just-unchecked roles
            await _remove_roles(interaction.user, removed)

        # Then save user data to the DB
        await _save_user_to_db(interaction.user.id, self.user_data)

        # Respond ephemerally with a summary
        await interaction.response.followup(
            f"Removed: {', '.join(removed) if removed else 'None'}\n"
            f"Still have: {', '.join(still_selected) if still_selected else 'None'}",
            ephemeral=True
        )
        
        # Finally, we can end the view so it doesn’t keep responding
        self.view.stop()

##############################################################################
# THE COG
##############################################################################

class RoleSelectCog(commands.Cog):
    """
    Provides a 3-page persistent role selection message with chunked kink categories.
    Also includes `/roles remove` for ephemeral kink removal.
    """

    def __init__(self, bot: "MoguMoguBot"):
        self.bot = bot
        self.view = ThreePageRoleView(bot)
        self._reattached = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._reattached:
            return
        self._reattached = True

        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            logger.info("No config.json found; skipping role view reattachment. Admin can run `/roles setup`.")
            return

        msg_id = config_data.get("role_select_message_id")
        channel_id = config_data.get("role_select_channel_id")
        if not (msg_id and channel_id):
            logger.info("No stored roles message ID or channel ID. Admin can run `/roles setup`.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Channel {channel_id} not found; cannot reattach role view.")
            return

        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(view=self.view)
            self.bot.add_view(self.view)
            logger.info(f"Reattached 3-page role view to message {msg_id}.")
        except discord.NotFound:
            logger.warning(f"Message {msg_id} not found—possibly deleted. Admin can run `/roles setup` again.")
        except discord.Forbidden:
            logger.warning(f"Forbidden to access message {msg_id} in channel {channel_id}.")
        except Exception as e:
            logger.exception(f"Error reattaching role view: {e}")

    # Slash command group
    roles = SlashCommandGroup("roles", "Manage role preferences")

    @roles.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_role_message(self, ctx: discord.ApplicationContext):
        """
        Creates the persistent 3-page role selection message in this channel.
        """
        await ctx.defer(ephemeral=True)

        embed = discord.Embed(
            title="Choose Your Roles & Kinks!",
            description=(
                "**Page 1**: Age, Relationship, Location, Orientation\n"
                "**Page 2**: DM Status, Here For, Ping Roles\n"
                "**Page 3**: Kinks\n\n"
                "Click **Next** to proceed. Finally, click **Finish** at the end.\n"
                "*(If you click **Back** to return to a previous page, ensure you re-select all roles on that page.)*"
            ),
            color=discord.Color.blurple()
        )

        sent_msg = await ctx.channel.send(embed=embed, view=self.view)

        # Save in config
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = {}

        config_data["role_select_message_id"] = sent_msg.id
        config_data["role_select_channel_id"] = ctx.channel.id

        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)

        self.bot.add_view(self.view)

    @roles.command(name="remove")
    async def remove_kinks(self, ctx: discord.ApplicationContext):
        """
        Opens an ephemeral menu to uncheck and remove any of your selected kinks.
        """
        user_id = ctx.user.id
        self.view._ensure_user_record(user_id)
        user_data = self.view.user_data[user_id]

        if not user_data["kinks"]:
            return await ctx.respond("You currently have no kinks selected!", ephemeral=True)

        # Just pass the user_data into our new view
        view = KinkRemovalView(self.bot, user_id, user_data)
        await ctx.respond(
            "Uncheck any kinks you wish to remove:",
            view=view,
            ephemeral=True
        )


def setup(bot: "MoguMoguBot"):
    bot.add_cog(RoleSelectCog(bot))

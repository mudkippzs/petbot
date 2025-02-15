# MoguMoguBot - Handover & Documentation

Welcome to the **MoguMoguBot** codebase. This repository manages a production-ready Discord bot with multiple features:

- **Ownership** system (claiming “subs/pets”)
- **Economy** with tipping and credit transactions
- **Moderation** (ban, kick, mute, etc.)
- **Contract & Escrow** logic for auctions and service agreements
- **Support Ticket** system
- **Role selection** flows for server members
- **Backup** and database management
- **Verification** flow

Below is a comprehensive overview of each file, the classes and functions within, unfinished work, a checklist for completion, and known bugs or issues.

---

## Table of Contents
1. [Project Structure Overview](#project-structure-overview)
2. [Detailed File Explanations](#detailed-file-explanations)
   - [1. `./main.py`](#1-mainpy)
   - [2. `./db.py`](#2-dbpy)
   - [3. `./utils.py`](#3-utilspy)
   - [4. `./strings.json`](#4-stringsjson)
   - [5. `./config.json` and `./theme.json`](#5-configjson-and-themejson)
   - [6. `./contract_views.py`](#6-contract_viewspy)
   - [7. `./ownership_views.py`](#7-ownership_viewspy)
   - [8. Cogs Directory](#8-cogs-directory)
     - [8.1 `cogs/ownership.py`](#81-cogsownershippy)
     - [8.2 `cogs/economy.py`](#82-cogseconomypy)
     - [8.3 `cogs/moderation.py`](#83-cogsmoderationpy)
     - [8.4 `cogs/contract_escrow.py`](#84-cogscontract_escrowpy)
     - [8.5 `cogs/rules.py`](#85-cogsrulespy)
     - [8.6 `cogs/backup.py`](#86-cogsbackuppy)
     - [8.7 `cogs/role_cog.py`](#87-cogsrole_cogpy)
     - [8.8 `cogs/reputation.py`](#88-cogsreputationpy)
     - [8.9 `cogs/help.py`](#89-cogshelppy)
     - [8.10 `cogs/management.py`](#810-cogsmanagementpy)
     - [8.11 `cogs/events.py`](#811-cogseventspy)
     - [8.12 `cogs/support_ticket.py`](#812-cogssupport_ticketpy)
     - [8.13 `cogs/auctions.py`](#813-cogsauctionspy)
3. [Unfinished Work & Placeholders](#unfinished-work--placeholders)
4. [Checklist of Features & Tasks to Finalize](#checklist-of-features--tasks-to-finalize)
5. [Known Bugs & Issues](#known-bugs--issues)

---

## Project Structure Overview

The project is primarily organized as follows:

- **`main.py`**: Entry point for the bot. Initializes the bot, loads config, connects to DB, and loads cogs.
- **`db.py`**: Database interface (PostgreSQL) using `asyncpg`. Contains table creation and backup logic.
- **`utils.py`**: Utility functions for JSON/CSV reads and writes, plus small helper utilities.
- **`strings.json`** & **`theme.json`**: Shared user-facing text strings and theming (colors, emojis).
- **`config.json`**: Main configuration file (bot token, channel IDs, roles, database credentials, etc.).
- **`contract_views.py`** & **`ownership_views.py`**: Modular UI (Discord `View`/`Modal`) classes that handle user interactions around contracts, ownership claims, or partial claims.
- **`cogs/`**: Directory containing separate modules (cogs) that group functionality such as moderation, economy, backup, events, etc. Each cog is a self-contained sub-feature.

Below is a deep dive into each file.

---

## Detailed File Explanations

### 1. `main.py`
**Purpose**: This is the bot’s main entry script.

**Key Points**:
- **`MoguMoguBot` class** extends `commands.Bot`.  
- Initializes with `command_prefix`, loads `config`, `strings`, `theme`.  
- Manages the lifecycle (`on_ready`, `on_error`, `close`) and ensures DB is connected.
- At the end (`if __name__ == '__main__':`), it calls `asyncio.run(main())` which:
  - Loads config files
  - Creates the bot instance
  - Connects the DB (`bot.db.connect()`)
  - Dynamically loads all `.py` files in `cogs/` as bot extensions
  - Finally starts the bot using `bot.start(token)`

**Notable Functions**:
- `async def on_ready(self)`: Called when the bot finishes connecting.  
- `async def on_error(self, event_method, *args, **kwargs)`: Global exception logger.

**Algorithm**:
- The main event loop is standard for Discord bots: connect → load cogs → run until process ends.

---

### 2. `db.py`
**Purpose**: Handles all database operations and schema setup. Uses `asyncpg`.

**Key Classes & Methods**:
- **`class Database:`**  
  - `__init__(config)`: Accepts DB credentials from config.
  - `connect()`: Creates a connection pool and ensures tables exist by calling `ensure_tables()`.
  - `close()`: Gracefully closes the pool.
  - `fetchrow(query, *args)`, `fetch(query, *args)`, `fetchval(query, *args)`, `execute(query, *args)`: Core query methods returning different result structures.
  - `ensure_tables()`: Creates all necessary tables if not found. The SQL statements define the entire schema for the bot’s features.
  - `backup_database()`: Uses `pg_dump` to produce an SQL dump of the database.

**Algorithmic Complexity**:
- Primarily standard SQL operations. Nothing particularly complex (O(1) to O(n) typical queries).

---

### 3. `utils.py`
**Purpose**: Contains small helper utilities for JSON, CSV, and dictionary tasks.

**Functions**:
- `load_json_config(file)`: Asynchronous read of a JSON file into a dictionary. Logs errors if not found or invalid JSON.
- `write_json_config(file, config)`: Async write dictionary to JSON file.
- `write_csv_file(file, data)`: Async CSV writer using `asyncio.to_thread` to offload I/O.
- `get_highest_dict_key(dictionary)`: Finds the key with the highest value in a dictionary.

**Algorithms**:
- Basic I/O. The dictionary max-key logic is `max()` with a custom lambda. O(n) in dict size.

---

### 4. `strings.json`
A basic JSON file containing user-facing text strings.  
**Keys**:
- `welcome_message`, `help_title`, `help_description`, etc.

Allows for dynamic or multi-lingual expansions.

---

### 5. `config.json` and `theme.json`
- **`config.json`**: Holds environment variables and IDs:
  - Bot token, channel IDs, role IDs, DB creds, staff roles, tip options, etc.
- **`theme.json`**: UI styling, e.g. `embed_color`, certain emojis for success/error, etc.

**Security Note**: Real credentials (token, DB pass) are shown here.  
**Recommendation**: In production, ensure these are excluded from version control or replaced with environment variables.

---

### 6. `contract_views.py`
**Purpose**: Contains Discord UI classes (`discord.ui.View`, `discord.ui.Modal`) that handle the user flow for creating or fulfilling contracts in an escrow-based system.

**Classes**:
- `ConfirmDeleteModal`: A modal for confirming deletion of an advert.
- `AdvertView`: Allows users to “Make Offer” or “Delete Advert”.
- `OfferCreationModal`: Collects details (price, message) from a potential buyer.
- `ConfirmFulfillModal`, `ConfirmCancelModal`: Final modals for fulfilling or canceling a contract.
- `DisputeReasonSelect` & `DisputeView`: Gathers the reason for a dispute.  
- `ContractView`: The main active contract UI with [Fulfill], [Cancel], [Dispute] buttons.

**Algorithm**:
- The logic for each button callback is delegated to callbacks in `contract_escrow.py`.  
- Each view is persistent.  
- No heavy computations, only user interaction flows.

---

### 7. `ownership_views.py`
**Purpose**: Provides Discord UI flows for ownership claims. Sub-systems: staff approvals, user approvals, DM toggles, partial claims.

**Key Classes**:
- `OwnershipClaimStaffView`, `OwnershipClaimSubView`: Let staff or the sub user Approve/Deny a claim.
- `SingleUserOwnershipView`: DMs the user with an interactive embed showing ownership details, toggling DM permissions, etc.
- `AskForDMApprovalView`, `AskForDMJustificationModal`: Another ephemeral flow for “Ask to DM” approvals.
- `OwnershipBrowserView`, `OwnershipUserSelect`: Slash-based ephemeral UI to browse user ownership info.
- `TransactModal`: For direct credit transactions.
- `PartialClaimModal`, `DirectClaimModal`: Collect details for partial or direct ownership claims.
- `MajorityOwnerClaimView`, `SubClaimView`: Show majority owner or sub to approve/counter/reject the claim.
- `CounterOfferModal`, `NewUserCounterView`, `MajorityRejectModal`, `SubRejectModal`: Additional flows for claims, rejections, counters.

**Algorithm**:
- Multi-step interactive flows using Discord modals, select menus, buttons.  
- Underlying logic is handled in `cogs/ownership.py`.

---

### 8. Cogs Directory
Each `.py` inside `cogs/` is a specialized feature cog. They use the Discord `commands.Cog` architecture and register slash commands.

#### 8.1 `cogs/ownership.py`
Manages sub ownership claims, partial ownership transfers, DM permission toggling, cooldowns, staff approvals, etc.

**Key Elements**:
- **`OwnershipCog`**:  
  - Slash commands: `/ownership browse`, `/ownership transfer_full`, `/ownership propose`, etc.
  - `connect` to DB for all ownership data: `sub_ownership`, `claims`.
  - Methods to handle new claims, partial vs. direct, staff approvals, sub approvals.
  - DM permission toggles: `toggle_dm_permissions`, `handle_dm_request`.
  - Auction-like or direct BFS logic for finding majority owner if partial ownership is requested.

**Algorithms**:
- `apply_rejected_cooldown`, `apply_success_cooldowns` impose cooldown logic.  
- Database ensures no double-claim or concurrency issues.  
- Ownership claims rely on role checks (Harlot vs. Gentleman) and staff final approval.

---

#### 8.2 `cogs/economy.py`
Implements a concurrency-safe wallet system with **transfer_balance**, **tips** (reaction-based), and a “blockchain-like” ledger.

**Features**:
- Reaction tipping: if user reacts with certain emojis, automatically transfers credits from tipper to tippee.
- Slash commands: `/economy balance`, `/economy transfer`.
- Logs transactions in a `transactions` table with hashed links for a “blockchain-like” approach.

**Functions**:
- `on_raw_reaction_add`, `on_raw_reaction_remove`: handle tip add and refunds.
- `ensure_wallet_exists`, `get_balance`, `transfer_balance`: Key DB operations.

---

#### 8.3 `cogs/moderation.py`
Standard moderation commands for staff:
- `/moderation ban`, `/moderation kick`, `/moderation mute`, etc.
- Logs each action to `moderation_logs`.

**Notes**:
- Also includes a `warn` command storing user warnings.
- Basic checks for role hierarchy to avoid banning higher-level staff by mistake.

---

#### 8.4 `cogs/contract_escrow.py`
Manages the creation and usage of **contracts** (paid services, fulfilling, canceling, disputes). Ties in with the UI from `contract_views.py`.

**Key Flows**:
- `/contract advert`: Post a new advert (with an `AdvertView`).
- Potential buyers “Make Offer” → triggers a modal → sends DM to the seller for acceptance or decline → upon acceptance, a contract is created, escrow is deducted from buyer, etc.
- `ContractView`: [Fulfill], [Cancel], [Dispute] logic. On fulfill, releases escrow to the seller; on cancel, refunds buyer; on dispute, notifies staff.

**Algorithms**:
- Basic state machine for contract status: `active`, `canceled`, `disputed`, `completed`.

---

#### 8.5 `cogs/rules.py`
Implements a rules acceptance flow with multiple pages (SSC, RACK, PRICK). Users who accept get the “Verified” role, logs acceptance in DB.

**Key Classes**:
- `RulesCog`:  
  - Maintains a pinned message (the main rules) with ephemeral “Begin” or “Unaccept” buttons.  
  - The ephemeral multi-page acceptance is handled by `MultiPageRulesView`.
- Integrates with a `rules_text` table in DB.

---

#### 8.6 `cogs/backup.py`
Automates database backup every X minutes, distributing `.sql` dumps to staff channels and DM recipients.

**Core**:
- **`BackupCog`** with a `tasks.loop` that calls `do_backup()`:
  - `backup_database()` from `db.py`
  - DMs staff recipients, posts in a staff channel, also creates a “fallback JSON”.

**Also**: Provides slash commands to manually `/backup now` or restore from a given SQL dump URL.

---

#### 8.7 `cogs/role_cog.py`
Implements a multi-page ephemeral flow for members to pick roles (age, gender, location, orientation, DM status, kinks, etc.). Persists to a `user_roles` table. Also applies or removes matching Discord roles.

**Classes**:
- `MultiUserRoleSelectCog`  
  - Has a “role setup message” that calls `RoleSetupView`.  
- `RoleSetupView`: The public message with “Choose Roles” button → ephemeral 4-page UI.
- `RolesFlowView`: Detailed multi-step collection, finishing with updating DB and applying roles with progress feedback.

---

#### 8.8 `cogs/reputation.py`
Handles sub “reputation” or review system:
- `/reputation add sub_id rating comment?` → logs rating in `reviews`.
- `/reputation view sub_id` → shows average rating, top 5 reviews.

---

#### 8.9 `cogs/help.py`
A custom help command listing slash commands, optionally hiding staff commands from non-staff.  
**`Help` Cog** uses `slash_command(name='help')` to gather commands dynamically.

---

#### 8.10 `cogs/management.py`
Server management commands for staff. Examples:
- Toggling features, adding staff roles, setting backup intervals, exporting/importing permissions.

**Key**:
- Exports roles and channel overwrites to JSON, can re-import them.  
- Potentially large chunk-based rate-limited updates.

---

#### 8.11 `cogs/events.py`
Sub owners can create temporary event channels (voice or text) that auto-delete after a specified end time.

**Key**:
- `events` slash command group.  
- Stored in `events` DB table with `end_time`. A background loop checks for expired events and deletes the channels.

---

#### 8.12 `cogs/support_ticket.py`
Implements a basic support ticket system with private threads, and a verification flow if a user is unverified:
- The user can “Get Support” (which creates a private thread in a `support_channel_id`).
- Or “Get Verified” (which logs staff approvals, can auto-kick on rejection, etc.).

**Core**:
- `SupportTicketCog`, a background task to close inactive tickets after `inactivity_limit`.
- `SplashContactView` pinned in the support channel. Buttons lead to ephemeral modals.

**Verification**:
- `VerificationModal` collects answers and an image link, logs in DB.
- Staff do a 2-approval flow. If success, user is given “Verified” role. If rejected, can be kicked.

---

#### 8.13 `cogs/auctions.py`
**WIP** for a new “auction” feature, presumably letting users or owners auction sub ownership or services. 
**`AuctionCog`** has placeholders:
- `/auction create`: ephemeral multi-step
- `schedule_loop`: to automatically start/end auctions
- `_finalize_auction(...)`: partial or no code
- `post_public_auction_embed(...)`, `update_auction_embed(...)`: placeholders
- The `AuctionCreateFlowView` and “bidding” UI are present but incomplete.

---

## Unfinished Work & Placeholders

1. **Auction System (`cogs/auctions.py`)**:
   - Most endpoints are placeholders (`create_auction_cmd`, `auction_info_cmd`, `end_auction_cmd`).
   - The scheduling loop references planned DB logic but is incomplete.
   - `_finalize_auction` and embed posting are skeleton methods.

2. **Advanced Contract Handling**:
   - Some advanced features (partial refunds, milestone-based contracts) are toggled in `FEATURES` but not fully implemented.

3. **Verification**:
   - The code is robust, but final “kick on rejection” or role-based separation might need more testing. 
   - No direct user interface to re-try after rejection is described.

4. **Event Cog**:
   - The code is functional but might need deeper testing of concurrency or checks for invalid sub ID.

5. **Help Cog**:
   - The help cog attempts to hide staff commands from non-staff but the logic in `is_staff_command` is basic. 
   - The actual referencing of `user_is_staff` is incomplete (`user_is_staff` is not clearly implemented in the file).

6. **Import/Export of Permissions**:
   - Possibly needs more robust handling of concurrency, large guilds, or rate-limits.

7. **Economy**:
   - Reaction-based tip removal might fail if the recipient already spent the balance. 
   - No fallback or partial refund logic is present if the tippee is out of credits.

8. **“Magical Strings”**:
   - Certain strings or references (like “Harlot” or “Gentleman”) are domain-specific. If the server wants different naming, might require refactors or config expansions.

9. **Testing**:
   - Full end-to-end tests for major flows like partial ownership claims, advanced dispute handling, or the new Auction system are not in place.

---

## Checklist of Features & Tasks to Finalize

1. **Auction Module Completion**  
   - [ ] Implement DB schema expansions (`auction` table partial references are in `db.py`, but fully define usage).  
   - [ ] Finish `create_auction_cmd` ephemeral flow:
     - Collect `start_time`, `end_time`, `sub_id`, `type`, etc.  
     - Insert DB record.  
     - Immediately or later post embed if `start_time <= now`.  
   - [ ] Implement `schedule_loop` to start/stop auctions automatically.  
   - [ ] Implement `_finalize_auction` to handle highest bid, transferring ownership or awarding sub shares.  
   - [ ] Add a `Bid` table in DB with concurrency checks.  

2. **Economy**  
   - [ ] Possibly handle negative balance scenarios for tip removal more gracefully.  
   - [ ] Add partial or “insufficient funds” logic if the tippee cannot refund a removed tip.  

3. **Ownership**  
   - [ ] More robust staff approval logic for partial claims (some code is present, but re-check if the required staff threshold is 2 or more, how to handle re-votes).  
   - [ ] Unit-tests for edge cases: removing partial shares if user tries to claim more than available.

4. **Contract Escrow**  
   - [ ] Fully implement advanced features in `FEATURES` (partial refunds, milestone-based payments, auto-cancel).  
   - [ ] Thoroughly test dispute flows with staff forced resolution.

5. **Rules Cog**  
   - [ ] Provide an admin UI or slash command to tweak the 3 pages (SSC, RACK, PRICK) without direct DB editing. There's a partial `/rules_edit` command, but confirm if it needs expansions.  

6. **Help Cog**  
   - [ ] Confirm the staff vs. public command filtering. Possibly implement a robust permission check.  

7. **Support Ticket**  
   - [ ] Additional features: add co-owners or multiple staff?  
   - [ ] More logging or transcript formats (HTML or PDF?).  

8. **Testing & QA**  
   - [ ] End-to-end tests on a staging server to confirm flows, especially partial claims, auctions, verification.  
   - [ ] Expand error handling for concurrency or DB failures.  

---

## Known Bugs & Issues

1. **Help Cog Staff Check**  
   - The `help` command references a `user_is_staff` variable or function not defined. This can lead to a NameError or skip the staff filtering logic.

2. **Auction Code**  
   - Currently incomplete, placeholders might break if a user attempts to run `/auction create` or the scheduling loop tries to fetch data from the DB. The relevant tables exist but the logic is not robust.

3. **Tip Refund**  
   - If a user tips someone, then removes the reaction, the code attempts to refund. If the tippee’s balance is insufficient (already spent), the transaction fails. This is partially logged but no user feedback is provided beyond a log warning.

4. **Role Cog**  
   - Attempting to add or remove roles that do not exist in the guild can fail silently. There's partial logging, but no user feedback if a role mismatch occurs.

5. **DM Toggles**  
   - If a user tries to toggle DMs but has no entry in `open_dm_perms`, there's a chance of confusion. The code attempts to handle this, but concurrency edge cases may cause unexpected results.  

6. **Unverified/Escrow Edge Cases**  
   - If a user is forced out of a contract, some references to partial data may remain.  

7. **Database Backup**  
   - If `pg_dump` or `psql` is not in PATH, backups or restore will fail with limited fallback.

8. **Large Channel/Role Imports**  
   - The chunk-based approach in `management.py` is a best effort. Extremely large servers could still face rate limits or partial failures if Discord’s concurrency is exceeded.  

---

**End of Document** 

---

This **README** aims to give a full understanding of each component, highlight missing features, and outline tasks for completion. For further clarifications on any specific module or deeper architectural questions, see inline docstrings or contact the original developer.
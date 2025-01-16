Below is a comprehensive blueprint that outlines the entire bot's design, architecture, features, and implementation details. This document is intended as a master reference before and during development. It reflects all previously discussed ideas, including asynchronous operations, flexible economy modes, auctions, ownership structure, service menus, reputation, server management, and a robust backup system.

---

## High-Level Overview

**Goal:** Build a versatile Discord bot that supports a fun “sub ownership” economy. It manages auctions, multi-owner weighted ownership of subs, subscriptions, escrow contracts, services, tipping, and events, all configurable by staff with strict or lenient modes. It also features periodic database backups, theming, logging, and a well-structured codebase.

**Key Principles:**
- **Asynchronous Everywhere:** Use `async/await` for all I/O, including database operations, HTTP requests, file reads/writes, and Discord API interactions.  
- **Modular Cogs & Separation of Concerns:** Each major feature is a separate cog. Cogs communicate through shared references (e.g., `bot.db`, `bot.config`).  
- **Configurable & Extensible:** Feature toggles, economy modes, roles/permissions, theming, and backup recipients are all defined in JSON config files, allowing easy changes without code modifications.  
- **User-Friendly & Polished:** Slash commands, intuitive embed UIs, brandable themes (color, emojis), and responsive error handling to provide a professional feel.  
- **Performance & Scalability:** Using `asyncpg` for efficient DB operations, possibly caching frequently accessed data, and carefully handling concurrency.  
- **Data Backup & Reliability:** A periodic backup task ensures the database is regularly saved offsite and delivered to staff members.

---

## Features & Cogs

### 1. **Ownership & Sub Cog**
- **Purpose:** Manage subs, their owners, subscribers, and service menus.
- **Key Features:**
  - **Subs:** Each sub has a unique ID, name, optional description, and associated owners.
  - **Multi-Owner Weighted Shares:** One primary owner controls the distribution of ownership percentages to other owners or investors.
  - **Subscribers:** Users who pay into the sub’s pot regularly instead of receiving dividends. This creates a recurring income stream for the owners.
  - **Service Menus:** A sub can have a list of services (e.g., voice performance, custom images) with set prices. Owners with permission can add, edit, or remove these entries.
- **Commands:**
  - `/sub create <name>`: Create a new sub.
  - `/sub info <sub_id>`: Display sub ownership, subscribers, services, and profile.
  - `/sub ownership add <sub_id> <@user> <percentage>`: Add an owner.
  - `/sub ownership remove <sub_id> <@user>`: Remove an owner.
  - `/sub subscriber add <sub_id> <@user>`: Add a subscriber.
  - `/sub subscriber remove <sub_id> <@user>`: Remove a subscriber.
  - `/service add <sub_id> <name> <price> <description>`: Add a service.
  - `/service remove <sub_id> <service_id>`: Remove a service.
- **Database Tables:**
  - `subs(id SERIAL, name TEXT, description TEXT, primary_owner_id BIGINT, ... )`
  - `sub_ownership(sub_id INT, user_id BIGINT, percentage INT)`
  - `sub_subscribers(sub_id INT, user_id BIGINT, next_payment_due TIMESTAMP)`
  - `sub_services(id SERIAL, sub_id INT, name TEXT, price INT, description TEXT)`

### 2. **Auction & Marketplace Cog**
- **Purpose:** Auctions for sub ownership, services, or other custom offerings.
- **Key Features:**
  - **Auction Types:** Full ownership transfer, partial ownership, leasing (renting a sub’s time), or one-off services (e.g., a silly dance video).
  - **Visibility Modes:** Full visibility (everyone sees bidders), limited (only seller sees bidders), anonymous (identities revealed post-sale).
  - **Direct Offers:** Make private offers through the bot without DMing.
- **Commands:**
  - `/auction create <sub_id> <type=ownership/service> <starting_price> [visibility=...]`
  - `/auction bid <auction_id> <amount>`
  - `/auction end <auction_id>`
  - `/offer send <sub_id> <amount>`: Send a direct offer to a sub’s owner(s).
- **Database Tables:**
  - `auctions(id SERIAL, sub_id INT, type TEXT, visibility TEXT, starting_price INT, active BOOLEAN, end_time TIMESTAMP)`
  - `bids(id SERIAL, auction_id INT, bidder_id BIGINT, amount INT, timestamp TIMESTAMP)`
  - `offers(id SERIAL, sub_id INT, sender_id BIGINT, amount INT, anonymous BOOLEAN, status TEXT)`

### 3. **Contract & Escrow Cog**
- **Purpose:** Manage long-term service agreements, milestone-based payments, and escrowed funds.
- **Key Features:**
  - **Milestones:** Contracts define multiple milestones that require both buyer and seller approval before releasing funds.
  - **Disputes:** Staff can resolve conflicts if a milestone is contested.
- **Commands:**
  - `/contract create <sub_id> <service_id> <price> <milestones...>`
  - `/contract approve_milestone <contract_id> <milestone_id>`
  - `/contract dispute <contract_id>`
- **Database Tables:**
  - `contracts(id SERIAL, buyer_id BIGINT, sub_id INT, service_id INT, total_price INT, escrow_amount INT, status TEXT)`
  - `contract_milestones(id SERIAL, contract_id INT, description TEXT, approved_by_buyer BOOLEAN, approved_by_seller BOOLEAN)`

### 4. **Events & Temporary Voice Channels Cog**
- **Purpose:** Subs/owners host special events (voice or text), gain temporary mod perms in those channels.
- **Key Features:**
  - Temporary voice channels that auto-delete after an event.
  - Owner permissions to mute/deafen/kick in that event channel only.
- **Commands:**
  - `/event create <sub_id> <type=voice/text> <duration>`
  - `/event end <event_id>`
- **Database Tables:**
  - `events(id SERIAL, sub_id INT, channel_id BIGINT, end_time TIMESTAMP)`

### 5. **Reputation Cog**
- **Purpose:** Track ratings and reviews of subs (and possibly owners).
- **Key Features:**
  - Post-service rating & review. Aggregate scores visible on sub profiles.
- **Commands:**
  - `/review add <sub_id> <rating> <comment>`
  - `/review view <sub_id>`
- **Database Tables:**
  - `reviews(id SERIAL, sub_id INT, user_id BIGINT, rating INT, comment TEXT, timestamp TIMESTAMP)`

### 6. **Tips & Economy Cog**
- **Purpose:** Handle wallets, tipping, subscriptions, and payment distribution.
- **Key Features:**
  - Every user has a wallet. Tips and payments are distributed according to ownership shares.
  - Subscribers pay recurring fees.
  - Economy modes (open, moderated, strict) where large or all transactions require staff approval.
- **Commands:**
  - `/tip <@user|sub_id> <amount>`
  - `/transfer <@user> <amount>`
  - `/staff approve_transaction <tx_id>`
  - `/staff deny_transaction <tx_id>`
  - `/config economy_mode set <open|moderated|strict>`
- **Database Tables:**
  - `wallets(user_id BIGINT PRIMARY KEY, balance INT)`
  - `transactions(id SERIAL, sender_id BIGINT, recipient_id BIGINT, amount INT, timestamp TIMESTAMP, status TEXT, justification TEXT)`

### 7. **Server Management Cog**
- **Purpose:** Central configuration for toggles, roles, permissions, theme settings, and backup parameters.
- **Key Features:**
  - Toggle features on/off.
  - Set staff roles and their permissions.
  - Change economy mode.
  - Manage backup recipients and intervals.
- **Commands:**
  - `/config feature <feature_name> on|off`
  - `/config add_staff_role @Role`
  - `/config remove_staff_role @Role`
  - `/config backup add_user <user_id>`
  - `/config backup remove_user <user_id>`
  - `/config backup channel <channel_id>`
  - `/config backup interval <minutes>`
- **Database Tables:**
  - `server_config(key TEXT PRIMARY KEY, value JSONB)`
  - `staff_roles(role_id BIGINT)`
  - `backup_recipients(user_id BIGINT)`

### 8. **Backup & Utility Cog**
- **Purpose:** Regular backups of the database, logging, searching, reminders, notifications.
- **Key Features:**
  - Every X minutes (default 15) perform an async backup of the database.
  - Post backup file in a staff channel and DM configured backup users.
  - Provide logging through `loguru`.
  - Possibly caching common queries and providing search functionalities.
- **Commands:**
  - None user-facing by default, except possibly `/logs` or `/search`.
- **Database (No new tables needed for backups)**

---

## Data Flow & Operations

**User Interactions:**
1. A user tries to tip a sub:  
   - `/tip <sub> <amount>` → Check sub owners, split amount according to shares, possibly require approval if in strict mode. Update wallets & log transaction.

2. Owner creates an auction for their sub’s time:  
   - `/auction create ...` → Insert into `auctions`, start a background task to end it after a set time.

3. A buyer sets up a contract with milestones:  
   - `/contract create ...` → Insert contract, hold total price in escrow (deduct from buyer’s wallet), release funds incrementally on milestone approvals.

4. A backup task runs every 15 minutes:  
   - Export DB snapshot as JSON or SQL dump. Post to staff channel and DM specified backup recipients. Store in two locations.

---

## Configuration & Theming

- **JSON Config Files:**  
  `config.json` and `strings.json` loaded at startup.  
  `config.json` for token, DB creds, backup settings, economy mode, etc.  
  `strings.json` for user-facing strings (welcome messages, help text), embed titles, etc.

- **Theming & Emojis:**  
  A JSON file for emojis and colors: `theme.json`.  
  A dictionary mapping keys like `"currency_emoji"` to an actual emoji.  
  Allows changing branding easily.

- **Localization:**  
  Future-ready: you can add another `strings_<lang>.json` for language support. Just load the correct file at startup.

---

## Database & Backup

- **Async with `asyncpg`:**  
  Initialize a connection pool on startup.  
  Perform queries using async/await in a `Database` class.

- **Backup Process:**
  - A background task (loop) every `config["backup"]["interval_minutes"]`.
  - `pg_dump` or a custom export (JSON dump of all tables) run asynchronously.
  - Store backup file locally or in a cloud storage.
  - Post the file in the staff Discord channel and DM backup recipients.

- **Schema Migrations:**
  Use a simple migration script or a tool like Alembic if needed.  
  Migrations ensure the database schema stays up-to-date.

---

## Concurrency & Performance

- **Async File Operations:**  
  Use `aiofiles` to handle JSON/CVS reads and writes asynchronously.  
  For backups, `asyncio.create_subprocess_exec` to run `pg_dump` without blocking.

- **Caching & Rate Limits:**
  Cache frequently accessed sub profiles in memory. Invalidate cache on updates.  
  Respect Discord rate limits by using the official HTTP client in discord.py.

- **Scalability:**
  The architecture is stateless aside from the DB, allowing horizontal scaling if needed. Multiple bot instances can share the same database.

---

## Logging & Error Handling

- **Logging:**
  - Use `loguru` for rich logging (console + rotating file logs).
  - Logs stored in `logs/` directory, rotated daily, kept for a configured retention period.

- **Error Handling:**
  - Global `on_error` and `on_command_error` handlers.
  - Show user-friendly error messages in Discord.
  - Log exceptions to help staff debug.

---

## Example Folder Structure

```
project/
├─ main.py
├─ config.json
├─ strings.json
├─ theme.json
├─ db.py
├─ utils.py
├─ logs/
├─ cogs/
│  ├─ help.py
│  ├─ backup.py
│  ├─ ownership_sub.py
│  ├─ auction_marketplace.py
│  ├─ contract_escrow.py
│  ├─ events.py
│  ├─ reputation.py
│  ├─ economy.py
│  ├─ management.py
```

---

## Conclusion

This blueprint provides a comprehensive, production-ready design for your Discord bot, ensuring all requested features—multi-owner subs, flexible economy, auctions, contracts, events, reputations, backups, theming, and configuration—are considered. By following this plan, you can implement the bot incrementally, starting with the core database and config setup, then adding each cog and ensuring all aspects remain asynchronous, scalable, and user-friendly.
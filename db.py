# ./db.py
import asyncpg
import json
from loguru import logger
import asyncio
import subprocess
from typing import Any, Dict, Optional, List


class Database:
    """
    A database manager utilizing asyncpg for asynchronous PostgreSQL operations.

    Attributes:
        config (dict): Bot configuration dictionary that includes database credentials.
        pool (asyncpg.pool.Pool): Connection pool for the database.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pool: Optional[asyncpg.pool.Pool] = None

    async def connect(self) -> None:
        """
        Create a connection pool to the PostgreSQL database and ensure all required tables exist.
        """
        db_conf = self.config["db_creds"]
        try:
            self.pool = await asyncpg.create_pool(
                database=db_conf["dbname"],
                user=db_conf["user"],
                password=db_conf["pass"],
                host=db_conf["host"],
                max_size=10
            )
            logger.info(
                "Database connected and connection pool created successfully.")
            await self.ensure_tables()
        except Exception as e:
            logger.exception(f"Failed to connect to the database: {e}")
            raise

    async def close(self) -> None:
        """
        Close the connection pool gracefully.
        """
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.")

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        """
        Execute a SQL query to fetch a single record.

        Parameters:
            query (str): The SQL query string.
            *args (Any): Parameters for the SQL query.

        Returns:
            Optional[asyncpg.Record]: A single record if found, otherwise None.
        """
        if not self.pool:
            logger.error("Database pool not initialized. Cannot fetch row.")
            return None
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args: Any) -> List[asyncpg.Record]:
        """
        Execute a SQL query to fetch multiple records.

        Parameters:
            query (str): The SQL query string.
            *args (Any): Parameters for the SQL query.

        Returns:
            List[asyncpg.Record]: A list of database records.
        """
        if not self.pool:
            logger.error("Database pool not initialized. Cannot fetch rows.")
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """
        Execute a SQL query and return a single value from the first record.
        
        Parameters:
            query (str): The SQL query string.
            *args (Any): Parameters for the SQL query.

        Returns:
            Any: The value of the first column of the first row, or None if no rows.
        """
        if not self.pool:
            logger.error("Database pool not initialized. Cannot fetch value.")
            return None
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        """
        Execute a SQL command (INSERT, UPDATE, DELETE, etc.).

        Parameters:
            query (str): The SQL command.
            *args (Any): Parameters for the SQL command.

        Returns:
            str: A status message indicating the number of rows affected.
        """
        if not self.pool:
            logger.error(
                "Database pool not initialized. Cannot execute query.")
            return "ERROR"
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def ensure_tables(self) -> None:
        """
        Create all required tables if they do not exist. This function ensures the database schema
        is ready for use by the bot.
        """
        create_statements = [
            # Tables without foreign key dependencies        
            """
            CREATE TABLE IF NOT EXISTS wallets (
                user_id BIGINT PRIMARY KEY,
                balance INT DEFAULT 0
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS server_config (
                key TEXT PRIMARY KEY,
                value JSONB
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS backup_recipients (
                user_id BIGINT PRIMARY KEY
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id SERIAL PRIMARY KEY,
                moderator_id BIGINT,
                user_id BIGINT,
                action TEXT,          -- e.g. 'ban', 'kick', 'mute', etc.
                reason TEXT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                moderator_id BIGINT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id BIGINT PRIMARY KEY,
                age_range TEXT,
                gender_role TEXT,
                relationship TEXT,
                location TEXT,
                orientation TEXT,
                dm_status TEXT,
                here_for TEXT[],
                ping_roles TEXT[],
                kinks TEXT[],
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS rules_acceptance (
                user_id BIGINT PRIMARY KEY,
                accepted_at TIMESTAMP NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS rules_text (
                id SERIAL PRIMARY KEY,
                ssc TEXT NOT NULL,
                rack TEXT NOT NULL,
                prick TEXT NOT NULL,
                final_notes TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_cooldowns (
                user_id BIGINT PRIMARY KEY,
                global_cooldown_until TIMESTAMP
            );
            """,

            # Add open_dm_perms table
            """
            CREATE TABLE IF NOT EXISTS open_dm_perms (
                user1_id BIGINT NOT NULL,
                user2_id BIGINT NOT NULL,
                PRIMARY KEY (user1_id, user2_id),
                CHECK (user1_id < user2_id)  -- Enforce user1_id is always less than user2_id
            );
            """,

            # Tables with foreign key dependencies
            """
            CREATE TABLE IF NOT EXISTS sub_ownership (
                sub_id BIGINT NOT NULL,
                user_id BIGINT,
                percentage INT,
                PRIMARY KEY (sub_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sub_subscribers (
                sub_id BIGINT NOT NULL,
                user_id BIGINT,
                next_payment_due TIMESTAMP,
                PRIMARY KEY (sub_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sub_services (
                id SERIAL PRIMARY KEY,
                sub_id BIGINT NOT NULL,
                name TEXT,
                price INT,
                description TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS auctions (
                id SERIAL PRIMARY KEY,
                sub_id BIGINT NOT NULL,
                type TEXT,
                visibility TEXT,
                starting_price INT,
                active BOOLEAN DEFAULT TRUE,
                end_time TIMESTAMP,
                creator_id BIGINT,
                shares_for_sale INT DEFAULT 100,
                service_id INT REFERENCES sub_services(id) ON DELETE SET NULL,
                lease_duration_days INT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS bids (
                id SERIAL PRIMARY KEY,
                auction_id INT REFERENCES auctions(id) ON DELETE CASCADE,
                bidder_id BIGINT,
                amount INT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS contracts (
                id SERIAL PRIMARY KEY,
                buyer_id BIGINT,
                sub_id BIGINT NOT NULL,
                service_id INT REFERENCES sub_services(id) ON DELETE CASCADE,
                total_price INT,
                escrow_amount INT,
                status TEXT DEFAULT 'active'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS contract_milestones (
                id SERIAL PRIMARY KEY,
                contract_id INT REFERENCES contracts(id) ON DELETE CASCADE,
                description TEXT,
                approved_by_buyer BOOLEAN DEFAULT FALSE,
                approved_by_seller BOOLEAN DEFAULT FALSE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                sub_id BIGINT NOT NULL,
                channel_id BIGINT,
                end_time TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                sub_id BIGINT NOT NULL,
                user_id BIGINT,
                rating INT,
                comment TEXT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS offers (
                id SERIAL PRIMARY KEY,
                sub_id BIGINT NOT NULL,
                sender_id BIGINT,
                amount INT,
                anonymous BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'pending'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS claims (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                sub_id BIGINT NOT NULL,
                staff_approvals INT DEFAULT 0,
                sub_approved BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'pending',
                staff_msg_id BIGINT,
                sub_msg_id BIGINT,                
                majority_owner_id BIGINT,
                requested_percentage INT,
                counter_percentage INT,
                justification TEXT,
                counter_justification TEXT,
                rejection_reason TEXT,
                expires_at TIMESTAMP,
                cooldown_exempt BOOLEAN DEFAULT FALSE,
                require_staff_approval BOOLEAN DEFAULT FALSE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS claims_staff_approvals (
                claim_id INT REFERENCES claims(id) ON DELETE CASCADE,
                staff_id BIGINT,
                PRIMARY KEY (claim_id, staff_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS dm_ownership_views (
                message_id BIGINT PRIMARY KEY,
                user_id BIGINT,
                target_user_id BIGINT,
                active BOOLEAN DEFAULT TRUE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                sender_id BIGINT NOT NULL,
                recipient_id BIGINT NOT NULL,
                status TEXT DEFAULT 'pending',
                amount INT NOT NULL,
                justification TEXT,
                hash TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS rules_acceptance_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                event TEXT NOT NULL,       
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS verification_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                q1 TEXT NOT NULL,
                q2 TEXT NOT NULL,
                q3 TEXT NOT NULL,
                status TEXT DEFAULT 'pending',  -- e.g. "pending", "approved", "rejected"
                staff_approvals INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                log_message_id BIGINT DEFAULT 0
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS verification_approvals (
                verification_id INT NOT NULL REFERENCES verification_requests(id) ON DELETE CASCADE,
                staff_id BIGINT NOT NULL,
                PRIMARY KEY (verification_id, staff_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,              -- user who opened ticket
                channel_id BIGINT,           -- Discord channel ID for the ticket
                status TEXT DEFAULT 'open',  -- e.g. open, closed
                created_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS ticket_participants (
                ticket_id INT REFERENCES tickets(id) ON DELETE CASCADE,
                user_id BIGINT,
                added_by BIGINT,            -- who added this user (optional)
                joined_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (ticket_id, user_id)
            );
            """
        ]


        if not self.pool:
            logger.error("Database pool not initialized. Cannot ensure tables.")
            return

        async with self.pool.acquire() as conn:
            for statement in create_statements:
                await conn.execute(statement)

        logger.info("All tables ensured (created if missing, altered if needed).")

    async def backup_database(self) -> Optional[str]:
        """
        Perform a database backup using pg_dump. The returned data is the raw SQL dump.

        Returns:
            Optional[str]: A string containing the database backup SQL if successful, else None.
        """
        db_conf = self.config["db_creds"]
        cmd = [
            "pg_dump",
            "-U", db_conf["user"],
            "-h", db_conf["host"],
            db_conf["dbname"]
        ]

        env = {"PGPASSWORD": db_conf["pass"]}

        logger.info("Starting database backup using pg_dump...")
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace')
                logger.error(f"Database backup failed: {error_msg}")
                return None

            backup_data = stdout.decode('utf-8', errors='replace')
            logger.info("Database backup completed successfully.")
            return backup_data
        except FileNotFoundError:
            logger.error(
                "pg_dump not found. Please ensure it is installed and in PATH.")
        except Exception as e:
            logger.exception(f"Unexpected error during database backup: {e}")

        return None

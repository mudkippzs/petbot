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
            logger.info("Database connected and connection pool created successfully.")
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
            logger.error("Database pool not initialized. Cannot execute query.")
            return "ERROR"
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def ensure_tables(self) -> None:
        """
        Create all required tables if they do not exist. This function ensures the database schema
        is ready for use by the bot.
        """
        create_statements = [
            # Subs & Ownership
            """
            CREATE TABLE IF NOT EXISTS subs (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                primary_owner_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sub_ownership (
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                user_id BIGINT,
                percentage INT,
                PRIMARY KEY (sub_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sub_subscribers (
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                user_id BIGINT,
                next_payment_due TIMESTAMP,
                PRIMARY KEY (sub_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sub_services (
                id SERIAL PRIMARY KEY,
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                name TEXT,
                price INT,
                description TEXT
            );
            """,

            # Auctions & Marketplace
            """
            CREATE TABLE IF NOT EXISTS auctions (
                id SERIAL PRIMARY KEY,
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                type TEXT,
                visibility TEXT,
                starting_price INT,
                active BOOLEAN DEFAULT TRUE,
                end_time TIMESTAMP
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
            CREATE TABLE IF NOT EXISTS offers (
                id SERIAL PRIMARY KEY,
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                sender_id BIGINT,
                amount INT,
                anonymous BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'pending'
            );
            """,

            # Contracts & Escrow
            """
            CREATE TABLE IF NOT EXISTS contracts (
                id SERIAL PRIMARY KEY,
                buyer_id BIGINT,
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
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

            # Events & Temporary Channels
            """
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                channel_id BIGINT,
                end_time TIMESTAMP
            );
            """,

            # Reputation & Reviews
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                sub_id INT REFERENCES subs(id) ON DELETE CASCADE,
                user_id BIGINT,
                rating INT,
                comment TEXT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,

            # Tips & Economy
            """
            CREATE TABLE IF NOT EXISTS wallets (
                user_id BIGINT PRIMARY KEY,
                balance INT DEFAULT 0
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                sender_id BIGINT,
                recipient_id BIGINT,
                amount INT,
                timestamp TIMESTAMP DEFAULT NOW(),
                status TEXT DEFAULT 'completed',
                justification TEXT
            );
            """,

            # Server Management & Config
            """
            CREATE TABLE IF NOT EXISTS server_config (
                key TEXT PRIMARY KEY,
                value JSONB
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS staff_roles (
                role_id BIGINT PRIMARY KEY
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS backup_recipients (
                user_id BIGINT PRIMARY KEY
            );
            """
        ]

        if not self.pool:
            logger.error("Database pool not initialized. Cannot ensure tables.")
            return

        async with self.pool.acquire() as conn:
            for stmt in create_statements:
                await conn.execute(stmt)

            # Add missing columns to auctions if they don't exist:
            # creator_id, shares_for_sale, service_id, lease_duration_days
            await conn.execute("""
                ALTER TABLE auctions
                ADD COLUMN IF NOT EXISTS creator_id BIGINT,
                ADD COLUMN IF NOT EXISTS shares_for_sale INT DEFAULT 100,
                ADD COLUMN IF NOT EXISTS service_id INT REFERENCES sub_services(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS lease_duration_days INT;
            """)

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
            logger.error("pg_dump not found. Please ensure it is installed and in PATH.")
        except Exception as e:
            logger.exception(f"Unexpected error during database backup: {e}")

        return None

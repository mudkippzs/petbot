#!/usr/bin/env bash

# Database setup script
# This script attempts to create the PostgreSQL database and user required by the bot.
# Requirements:
# - psql installed
# - Environment variables DB_NAME, DB_USER, DB_PASS must be set, or edit the script manually.

if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASS" ]; then
    echo "Please set DB_NAME, DB_USER, and DB_PASS environment variables."
    echo "Example:"
    echo "export DB_NAME=petbot_db"
    echo "export DB_USER=petbot_user"
    echo "export DB_PASS=someSecurePass"
    exit 1
fi

# Attempt to create user
echo "Creating user $DB_USER..."
psql -U postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null

# Grant user createdb if needed
psql -U postgres -c "ALTER USER $DB_USER CREATEDB;" 2>/dev/null

# Create database if not exists
echo "Creating database $DB_NAME..."
psql -U postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null

echo "Database setup completed. If no errors appeared, the DB and user should be ready."

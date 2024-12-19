#!/usr/bin/env bash
set -e

# Placeholder values - replace with your actual repo URL and desired defaults
REPO_URL="https://github.com/username/mogumogu-bot.git"
BOT_DIR="mogumogu-bot"
DB_NAME="mogumogubotdb"
DB_USER="mogumoguuser"
CONFIG_FILE="config.json"
STRINGS_FILE="strings.json"
THEME_FILE="theme.json"

MODE="install"

# Parse arguments
while [[ $# -gt 0 ]]
do
    key="$1"
    case $key in
        --mode)
        MODE="$2"
        shift; shift;
        ;;
        -m)
        MODE="$2"
        shift; shift;
        ;;
        *)
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
done

echo "============================================================"
echo "MoguMogu Bot Manager"
echo "Mode: $MODE"
echo "============================================================"

# Function to check if a command exists
command_exists () {
    command -v "$1" >/dev/null 2>&1
}

OS="$(uname -s 2>/dev/null || echo Unknown)"
echo "Detected OS: $OS"

if [[ "$OS" == "Linux" ]]; then
    # Linux environment

    # Ensure git, python, pip, jq installed if possible
    if ! command_exists git; then
        echo "Installing git..."
        sudo apt-get update && sudo apt-get install -y git
    fi

    if ! command_exists python3; then
        echo "Installing Python3..."
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
    fi

    if ! command_exists jq; then
        echo "Installing jq..."
        sudo apt-get update && sudo apt-get install -y jq
    fi

    if [ "$MODE" == "install" ]; then
        # Clone repo if not present
        if [ ! -d "$BOT_DIR" ]; then
            echo "Cloning repo..."
            git clone "$REPO_URL" "$BOT_DIR"
        else
            echo "Bot directory already exists. Using existing directory."
        fi

        cd "$BOT_DIR"

        # Install requirements
        echo "Installing Python dependencies..."
        python3 -m pip install --upgrade pip setuptools wheel
        python3 -m pip install -r requirements.txt

        # Setup PostgreSQL if not installed
        if ! command_exists psql; then
            echo "Installing PostgreSQL..."
            sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib
        fi
        sudo service postgresql start || true

        # Create DB and user if not exist
        DB_PASS=$(openssl rand -base64 18)
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" || true
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || true

        cat <<EOF > creds.txt
Database Credentials:
Host: localhost
Database: $DB_NAME
User: $DB_USER
Password: $DB_PASS
EOF

        echo "Database credentials saved to creds.txt."

        # Ask user for config values and write to config.json
        echo "Please enter the bot token:"
        read BOT_TOKEN

        echo "Please enter the Tenor API key:"
        read TENOR_KEY

        echo "Enter staff channel ID for backups (optional):"
        read STAFF_CHANNEL_ID

        echo "Enter backup interval in minutes (default 15):"
        read BACKUP_INTERVAL
        BACKUP_INTERVAL=${BACKUP_INTERVAL:-15}

        echo "Enter comma-separated user IDs for backup recipients (or leave blank):"
        read BACKUP_RECIPIENTS_INPUT
        # Convert to JSON array
        if [ -n "$BACKUP_RECIPIENTS_INPUT" ]; then
            IFS=',' read -r -a arr <<< "$BACKUP_RECIPIENTS_INPUT"
            BACKUP_RECIPIENTS_JSON=$(printf '%s\n' "${arr[@]}" | jq -R . | jq -s .)
        else
            BACKUP_RECIPIENTS_JSON="[]"
        fi

        echo "Enter staff role IDs (comma-separated) or leave blank:"
        read STAFF_ROLES_INPUT
        if [ -n "$STAFF_ROLES_INPUT" ]; then
            IFS=',' read -r -a sarr <<< "$STAFF_ROLES_INPUT"
            STAFF_ROLES_JSON=$(printf '%s\n' "${sarr[@]}" | jq -R . | jq -s .)
        else
            STAFF_ROLES_JSON="[]"
        fi

        echo "Enter tip options as amount:emoji pairs (e.g. 100:💰,200:🔥) or leave blank:"
        read TIP_OPTIONS_INPUT
        # Convert to array of objects { "amount": X, "emoji": "Y" }
        if [ -n "$TIP_OPTIONS_INPUT" ]; then
            IFS=',' read -r -a tarr <<< "$TIP_OPTIONS_INPUT"
            TIP_OPTIONS_JSON="[]"
            for opt in "${tarr[@]}"; do
                AMOUNT=$(echo "$opt" | cut -d':' -f1)
                EMOJI=$(echo "$opt" | cut -d':' -f2)
                TIP_OPTIONS_JSON=$(echo "$TIP_OPTIONS_JSON" | jq ". + [{\"amount\": $AMOUNT, \"emoji\": \"$EMOJI\"}]")
            done
        else
            TIP_OPTIONS_JSON="[]"
        fi

        # Write config.json
        jq -n \
          --arg token "$BOT_TOKEN" \
          --arg key "$TENOR_KEY" \
          --argjson recipients "$BACKUP_RECIPIENTS_JSON" \
          --argjson staffroles "$STAFF_ROLES_JSON" \
          --argjson tipOptions "$TIP_OPTIONS_JSON" \
          --arg staffChannelID "$STAFF_CHANNEL_ID" \
          --argjson backupInterval "{\"interval_minutes\":$BACKUP_INTERVAL}" \
          --arg dbname "$DB_NAME" \
          --arg dbuser "$DB_USER" \
          --arg dbpass "$DB_PASS" \
          '{
             "token": $token,
             "db_creds": {"dbname": $dbname, "user": $dbuser, "pass": $dbpass, "host": "localhost"},
             "backup": {"staff_channel_id": ($staffChannelID|tonumber?), "backup_recipients": $recipients, "interval_minutes": (.backupInterval.interval_minutes)},
             "tip_options": $tipOptions,
             "staff_roles": $staffroles,
             "tenor_api_key": $key
          }' > $CONFIG_FILE

        # If strings.json or theme.json don't exist, create defaults
        if [ ! -f $STRINGS_FILE ]; then
            echo '{"welcome_message": "Welcome to MoguMogu Bot!", "help_title": "Help Menu", "help_description": "Commands list"}' > $STRINGS_FILE
        fi
        if [ ! -f $THEME_FILE ]; then
            echo '{"embed_color": "#2F3136"}' > $THEME_FILE
        fi

        echo "Installation complete. Run with:"
        echo "bash bot_manager.sh --mode run"

    elif [ "$MODE" == "update" ]; then
        if [ ! -d "$BOT_DIR" ]; then
            echo "Bot directory not found. Run install first."
            exit 1
        fi
        cd "$BOT_DIR"
        echo "Pulling latest changes..."
        git pull origin main

        # Merge config changes if a default config exists upstream (e.g., config.template.json)
        if [ -f "config.template.json" ] && [ -f $CONFIG_FILE ]; then
            # Merge user config with template to add new fields
            jq -s '.[0] * .[1]' config.template.json $CONFIG_FILE > config.merged.json
            mv config.merged.json $CONFIG_FILE
            echo "Config merged successfully."
        fi

        # Reinstall dependencies
        python3 -m pip install --upgrade pip setuptools wheel
        python3 -m pip install -r requirements.txt

        echo "Update complete. Run with:"
        echo "bash bot_manager.sh --mode run"

    elif [ "$MODE" == "run" ]; then
        if [ ! -d "$BOT_DIR" ]; then
            echo "Bot directory not found. Run install first."
            exit 1
        fi
        cd "$BOT_DIR"
        echo "Starting the bot..."
        python3 main.py

    elif [ "$MODE" == "uninstall" ]; then
        if [ -d "$BOT_DIR" ]; then
            read -p "Are you sure you want to uninstall? This will remove the bot directory and drop the database! (y/N): " CONFIRM
            if [[ $CONFIRM =~ ^[Yy]$ ]]; then
                # Stop any running bot instances (if you have a systemd service, stop it here)
                # For now, we assume just killing main.py if running
                pkill -f "python3 main.py" || true

                # Drop database
                sudo -u postgres psql -c "DROP DATABASE $DB_NAME;" || true
                sudo -u postgres psql -c "DROP USER $DB_USER;" || true

                # Remove directory
                rm -rf "$BOT_DIR"
                rm -f creds.txt

                echo "Uninstall complete."
            else
                echo "Uninstall aborted."
            fi
        else
            echo "No bot directory found, nothing to uninstall."
        fi
    else
        echo "Invalid mode: $MODE"
        exit 1
    fi

elif [[ "$OS" == "MINGW"* || "$OS" == "CYGWIN"* || "$OS" == "MSYS"* ]]; then
    # Windows environment (Git Bash/Cygwin)
    echo "Windows environment detected."
    echo "Please perform manual steps:"
    echo "- For install: git clone, python install, psql setup, etc."
    echo "- For update: git pull, pip install -r requirements.txt, manually merge configs."
    echo "- For run: python3 main.py"
    echo "- For uninstall: remove directory, drop DB."
    exit 0
else
    echo "Unknown OS: $OS. Cannot proceed."
    exit 1
fi

echo "============================================================"
echo "Operation $MODE complete!"
echo "============================================================"

#!/usr/bin/bash

echo "Creating the new layered structure under v2/ ..."

# 1) Create top-level subdir for v2
mkdir -p v2
mkdir -p v2/src
mkdir -p v2/src/bot
mkdir -p v2/src/cogs
mkdir -p v2/src/services
mkdir -p v2/src/repositories
mkdir -p v2/src/domain
mkdir -p v2/src/utils
mkdir -p v2/src/infrastructure

# 2) Copy relevant files into v2/src/bot
if [ -f main.py ]; then
  cp main.py v2/src/bot/
fi

if [ -f config.json ]; then
  cp config.json v2/src/bot/
fi

if [ -f strings.json ]; then
  cp strings.json v2/src/bot/
fi

if [ -f theme.json ]; then
  cp theme.json v2/src/bot/
fi

# 3) Copy cogs if cogs/ exists
if [ -d cogs ]; then
  cp cogs/*.py v2/src/cogs/
fi

# 4) Copy db.py to infrastructure if present
if [ -f db.py ]; then
  cp db.py v2/src/infrastructure/
fi

# 5) Copy utils.py to v2/src/utils if present
if [ -f utils.py ]; then
  cp utils.py v2/src/utils/
fi

# 6) Provide placeholders for new service & repository files
touch v2/src/services/ownership_service.py
touch v2/src/repositories/ownership_repository.py
touch v2/src/services/contract_service.py
touch v2/src/repositories/contract_repository.py
touch v2/src/services/auction_service.py
touch v2/src/repositories/auction_repository.py

echo "v2 structure created! You can now refactor your code in v2/src/."

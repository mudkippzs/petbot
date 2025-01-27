#!/bin/bash

# Remove existing combined.txt if it exists
rm -f combined.txt

# Check if arguments are provided
if [ "$#" -gt 0 ]; then
  # Iterate over provided file names
  for name in "$@"; do
    # Find .py and .json files matching the name and process them
    find . -type f \( -name "${name}.py" -o -name "${name}.json" \) | while read -r file; do
      echo "$file" >> combined.txt
      echo "<code>" >> combined.txt
      cat "$file" >> combined.txt
      echo "</code>" >> combined.txt
      echo "" >> combined.txt
    done
  done
else
  # No arguments provided, process all .py and .json files
  find . -type f \( -name "*.py" -o -name "*.json" \) | while read -r file; do
    echo "$file" >> combined.txt
    echo "<code>" >> combined.txt
    cat "$file" >> combined.txt
    echo "</code>" >> combined.txt
    echo "" >> combined.txt
  done
fi

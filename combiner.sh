#!/bin/bash

# Remove existing combined.txt if it exists
rm -f combined.txt

# Find all .py and .json files and process them
find . -type f \( -name "*.py" \) | while read -r file; do
  echo $file >> combined.txt
  echo "<code>" >> combined.txt
  cat $file >> combined.txt
  echo "</code>" >> combined.txt
  echo "" >> combined.txt
done
#!/bin/bash
set -euo pipefail

echo "=== commit_and_push.sh ==="

git config user.name "Bay Area Digest Bot"
git config user.email "actions@github.com"

# Fetch latest remote state so we're never behind
echo "Fetching origin..."
git fetch origin

# Reset to the latest remote main (keeps our generated files as changes)
echo "Resetting to origin/main..."
git reset --soft origin/main

# Stage the generated/updated files
echo "Staging files..."
git add index.html stories_latest.json digest_data.json

# Only commit if there are actual changes
if git diff --staged --quiet; then
  echo "No changes to commit."
  exit 0
fi

echo "Committing..."
git commit -m "🗞 Auto-refresh: $(date -u '+%B %d, %Y %H:%M UTC')"

echo "Pushing..."
git push origin HEAD:main

echo "=== Done ==="

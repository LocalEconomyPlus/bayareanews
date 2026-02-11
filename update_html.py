#!/usr/bin/env python3
"""
Bay Area News Digest — HTML Updater
Reads digest_data.json and injects story data + timestamp into index.html.
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# Load the new data
with open(SCRIPT_DIR / "digest_data.json") as f:
    data = json.load(f)

# Load the existing HTML
html_path = SCRIPT_DIR / "index.html"
with open(html_path) as f:
    html = f.read()

# Build the new STORIES JS variable
stories_json = json.dumps(data["stories"], indent=None)
generated_at = data["generated_at"]

# Replace the STORIES array using string find/replace
stories_start = html.find('var STORIES = [')
stories_end = html.find('];\n', stories_start) + 2
new_stories_line = f'var STORIES = {stories_json};'
html = html[:stories_start] + new_stories_line + html[stories_end:]

# Replace the GENERATED_AT timestamp
gen_start = html.find('var GENERATED_AT = "')
gen_end = html.find('";', gen_start) + 2
new_gen_line = f'var GENERATED_AT = "{generated_at}";'
html = html[:gen_start] + new_gen_line + html[gen_end:]

# Write back
with open(html_path, "w") as f:
    f.write(html)

print(f"✅ HTML updated with {len(data['stories'])} stories")
print(f"   Generated at: {generated_at}")

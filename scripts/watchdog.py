#!/usr/bin/env python3
"""
Ghostwriter Watchdog — checks Gmail for VIP emails.
Writes output to /tmp/ghostwriter_output.txt AND stdout when emails found.
Zero-token on no-match (silent exit).

To adapt for your VIP: change the QUERY variable below.
"""

import subprocess, json, sys, os
from datetime import datetime, timezone

# ── CONFIGURE THIS ──────────────────────────────────
QUERY = 'from:vip@example.com is:unread'
# ────────────────────────────────────────────────────

OUTPUT_FILE = "/tmp/ghostwriter_output.txt"
GAPI = f"{os.path.expanduser('~')}/.hermes/hermes-agent/venv/bin/python3"
GAPI += " " + os.path.expanduser('~') + "/.hermes/skills/productivity/google-workspace/scripts/google_api.py"

result = subprocess.run(
    f'{GAPI} gmail search "{QUERY}" --max 5',
    shell=True, capture_output=True, text=True, timeout=15
)

if result.returncode != 0:
    print(f"ERROR: Gmail search failed: {result.stderr}")
    sys.exit(0)

try:
    emails = json.loads(result.stdout)
except json.JSONDecodeError:
    sys.exit(0)  # Silent — no matching emails

if not emails or (isinstance(emails, dict) and not emails):
    sys.exit(0)  # Silent — no matching emails

# Found emails — fetch full content, write to output file AND stdout
output_lines = [f"# Ghostwriter Watchdog Output — {datetime.now(timezone.utc).isoformat()}"]
for email in emails:
    r = subprocess.run(
        f'{GAPI} gmail get {email["id"]}',
        shell=True, capture_output=True, text=True, timeout=15
    )
    if r.returncode == 0:
        try:
            full = json.loads(r.stdout)
            output_lines.append("--- VIP EMAIL ---")
            output_lines.append(f"ID: {full.get('id')}")
            output_lines.append(f"Subject: {full.get('subject')}")
            output_lines.append(f"Date: {full.get('date')}")
            output_lines.append(f"From: {full.get('from')}")
            output_lines.append(f"ThreadID: {full.get('threadId')}")
            output_lines.append(f"Body: {full.get('body', '')}")
            output_lines.append("--- END ---")
        except json.JSONDecodeError:
            output_lines.append(f"VIP EMAIL — ID: {email['id']} — Subject: {email.get('subject', 'unknown')}")

output_text = "\n".join(output_lines)

# Write to temp file for processor
with open(OUTPUT_FILE, "w") as f:
    f.write(output_text)

# Also write to stdout (for cron logging)
print(output_text)

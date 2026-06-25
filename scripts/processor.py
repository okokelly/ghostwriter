#!/usr/bin/env python3
"""
Ghostwriter Processor — reads watchdog output, spawns LLM only when emails exist.
Zero-token on no emails. Delegates to hermes chat -q when VIP emails found.

v2: no-agent script. Replaces the v1 Processor (LLM cron job that burned ~3,500 tokens
even on empty ticks). Now: script reads /tmp/ghostwriter_output.txt → empty or stale?
silent exit (0 tokens). Fresh VIP emails? → spawn hermes chat -q → draft + send.

To customize: edit VOICE_GUIDELINES and RECIPIENT below.
"""

import subprocess, sys, os
from datetime import datetime, timezone, timedelta

# ── CONFIGURE THESE ─────────────────────────────────
RECIPIENT = "person@example.com"
VOICE_GUIDELINES = """Draft replies in the user's voice:
- Warm, direct, concise
- No corporate AI-isms ("I hope this finds you well", "I'd be happy to assist")
- Use contractions (I'll, don't, it's)
- Natural American English
- Be specific, not hand-wavy
- Own your opinions"""
SIGNATURE = "<p>Cheers,</p><p>Name</p>"
ALT_SIGNATURE = "<p>Best,</p><p>Name</p>"  # For sad/serious/bad news
# ────────────────────────────────────────────────────

OUTPUT_FILE = "/tmp/ghostwriter_output.txt"
MAX_AGE_MINUTES = 10  # Ignore watchdog output older than this

# Check if watchdog output exists and is fresh
if not os.path.exists(OUTPUT_FILE):
    sys.exit(0)  # No watchdog run yet — silent

mtime = datetime.fromtimestamp(os.path.getmtime(OUTPUT_FILE), tz=timezone.utc)
age = datetime.now(timezone.utc) - mtime
if age > timedelta(minutes=MAX_AGE_MINUTES):
    sys.exit(0)  # Stale output — already processed or watchdog stopped

with open(OUTPUT_FILE) as f:
    watchdog_output = f.read().strip()

if not watchdog_output or "--- VIP EMAIL ---" not in watchdog_output:
    sys.exit(0)  # No VIP emails — silent, zero tokens

# VIP emails found — spawn Hermes to process
PROMPT = f"""You are the Ghostwriter Processor. Below is output from the Ghostwriter Watchdog containing unread VIP emails.

{watchdog_output}

{VOICE_GUIDELINES}

For EACH email block (--- VIP EMAIL ---):
1. Read the full email body (already provided in context).
2. Draft a reply. 
3. Format as clean HTML — use <p> for paragraphs, NO manual <br> tags.
4. SIGNATURE: Default {SIGNATURE}. Only use {ALT_SIGNATURE} if the email is sad/serious/bad news.
5. Send using gmail send with --html and --thread-id:
   GAPI="{os.path.expanduser('~')}/.hermes/hermes-agent/venv/bin/python3 {os.path.expanduser('~')}/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
   $GAPI gmail send --to "{RECIPIENT}" --subject "Re: <original subject>" --body "<html body with signature>" --html --thread-id "<threadId from email>"
6. Mark the ORIGINAL email as read, then archive (two separate calls):
   $GAPI gmail modify <ID> --remove-labels UNREAD
   $GAPI gmail modify <ID> --remove-labels INBOX
7. IMPORTANT: For gmail modify, each --remove-labels call handles ONE label only. Use two separate calls.

After processing all emails, output a brief summary: which emails you replied to, subjects."""

result = subprocess.run(
    ["hermes", "chat", "-q", PROMPT],
    capture_output=True, text=True, timeout=300
)

print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)
sys.exit(result.returncode)

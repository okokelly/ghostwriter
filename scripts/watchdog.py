#!/usr/bin/env python3
"""
Ghostwriter v3 Watchdog — multi-tenant email polling.
Reads ~/.ghostwriter/config.yaml, searches Gmail for all Tier 1 contacts,
writes trigger file when unread emails found.

Zero-token: no_agent=true cron job. Pure Python, no LLM.
v3: multi-contact from config.yaml (replaces v2's single VIP hardcode).
"""

import json
import os
import subprocess
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────
GHOSTWRITER_HOME = Path.home() / ".ghostwriter"
CONFIG_PATH = GHOSTWRITER_HOME / "config.yaml"
TRIGGER_FILE = Path("/tmp/ghostwriter_v3_trigger.json")

GAPI = " ".join([
    str(Path.home() / ".hermes/hermes-agent/venv/bin/python3"),
    str(Path.home() / ".hermes/skills/productivity/google-workspace/scripts/google_api.py"),
])

MAX_EMAILS_PER_CONTACT = 5  # Fetch up to 5 unread per contact per tick


def load_config():
    """Load config.yaml. Exit if not found or no Tier 1 contacts."""
    if not CONFIG_PATH.exists():
        sys.exit(0)  # Not initialized yet — silent

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    contacts = config.get("contacts", [])
    # Only Tier 1 + not paused
    active = [c for c in contacts if c.get("tier") == 1 and not c.get("paused")]

    if not active:
        sys.exit(0)  # No Tier 1 contacts — silent

    return active


def search_gmail(email):
    """Search for unread emails from a specific address. Returns list of message objects."""
    query = f"from:{email} is:unread"
    result = subprocess.run(
        f'{GAPI} gmail search "{query}" --max {MAX_EMAILS_PER_CONTACT}',
        shell=True, capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        print(f"WARNING: Gmail search failed for {email}: {result.stderr}", file=sys.stderr)
        return []

    try:
        return json.loads(result.stdout) or []
    except json.JSONDecodeError:
        return []  # No results or non-JSON response


def fetch_full(email_id):
    """Fetch full email content by ID. Returns dict or None."""
    result = subprocess.run(
        f'{GAPI} gmail get {email_id}',
        shell=True, capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def main():
    contacts = load_config()

    all_emails = []
    for contact in contacts:
        emails = search_gmail(contact["email"])
        for email in emails:
            full = fetch_full(email["id"])
            if full:
                all_emails.append({
                    "id": full.get("id"),
                    "subject": full.get("subject", "(no subject)"),
                    "date": full.get("date", ""),
                    "from": full.get("from", ""),
                    "body": full.get("body", ""),
                    "thread_id": full.get("threadId", ""),
                    "contact_name": contact["name"],
                    "contact_email": contact["email"],
                    "tier": contact["tier"],
                    "voice_guidelines": contact.get("voice_guidelines", ""),
                    "signature": contact.get("signature", "<p>Cheers,</p><p>Name</p>"),
                })
            else:
                # Partial info — at least record we saw it
                all_emails.append({
                    "id": email.get("id", ""),
                    "subject": email.get("subject", "(no subject)"),
                    "from": email.get("from", ""),
                    "contact_name": contact["name"],
                    "contact_email": contact["email"],
                    "tier": contact["tier"],
                    "voice_guidelines": contact.get("voice_guidelines", ""),
                    "signature": contact.get("signature", "<p>Cheers,</p><p>Name</p>"),
                })

    if not all_emails:
        sys.exit(0)  # No emails — silent, zero cost

    # Write trigger file for processor
    trigger = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "emails": all_emails,
    }

    with open(TRIGGER_FILE, "w") as f:
        json.dump(trigger, f, indent=2)

    # Also dump to stdout for cron logging
    print(json.dumps(trigger, indent=2))


if __name__ == "__main__":
    main()

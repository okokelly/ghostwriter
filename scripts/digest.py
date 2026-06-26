#!/usr/bin/env python3
"""
Ghostwriter v3 Digest — Tier 3 daily digest of non-VIP emails.
Searches Gmail for unread emails NOT from Tier 1/2 contacts,
batches them to LLM for summary + priority scoring,
delivers formatted digest to Telegram.

Zero-token on empty days. no_agent=true cron job.
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

HERMES_HOME = Path.home() / ".hermes"
GAPI = " ".join([
    str(HERMES_HOME / "hermes-agent/venv/bin/python3"),
    str(HERMES_HOME / "skills/productivity/google-workspace/scripts/google_api.py"),
])

MAX_EMAILS = 30  # Max emails to include in a digest batch


def load_excluded_emails():
    """Return set of emails to exclude (all Tier 1 + Tier 2 contacts, not paused)."""
    if not CONFIG_PATH.exists():
        return set()

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    contacts = config.get("contacts", [])
    # Exclude Tier 1 and Tier 2 contacts (even paused — to be safe)
    return {c["email"].lower() for c in contacts if c.get("tier") in (1, 2)}


def build_query(excluded):
    """Build Gmail search query excluding managed contacts."""
    query = "is:unread"
    for email in sorted(excluded):
        query += f" -from:{email}"
    return query


def search_strangers(query):
    """Search Gmail for unread emails not from managed contacts."""
    result = subprocess.run(
        f'{GAPI} gmail search "{query}" --max {MAX_EMAILS}',
        shell=True, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"ERROR: Gmail search failed: {result.stderr}", file=sys.stderr)
        return []

    try:
        return json.loads(result.stdout) or []
    except json.JSONDecodeError:
        return []


def fetch_snippet(email_id):
    """Fetch email subject + first 600 chars of body."""
    result = subprocess.run(
        f'{GAPI} gmail get {email_id}',
        shell=True, capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        return {"subject": "(unknown)", "from": "(unknown)", "snippet": ""}

    try:
        full = json.loads(result.stdout)
        body = (full.get("body") or "")[:600]
        return {
            "subject": full.get("subject", "(no subject)"),
            "from": full.get("from", "(unknown)"),
            "date": full.get("date", ""),
            "snippet": body,
        }
    except json.JSONDecodeError:
        return {"subject": "(unknown)", "from": "(unknown)", "snippet": ""}


def build_digest_prompt(emails_data):
    """Build LLM prompt for digest summarization."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = []
    sections.append(f"You are the Ghostwriter Digest Agent. Generate a daily email digest for the user.")
    sections.append(f"Current time: {now}")
    sections.append("")
    sections.append(f"## Inbox Snapshot: {len(emails_data)} unread emails from unknown senders")
    sections.append("")

    for i, email in enumerate(emails_data, 1):
        sections.append(f"### Email {i}")
        sections.append(f"From: {email['from']}")
        sections.append(f"Subject: {email['subject']}")
        sections.append(f"Date: {email.get('date', '')}")
        if email.get("snippet"):
            sections.append(f"Preview: {email['snippet']}")
        sections.append("")

    sections.append("## Instructions")
    sections.append("")
    sections.append("1. Group emails by sender. For each sender, provide:")
    sections.append("   - **One-line summary** of what they want")
    sections.append("   - **Priority** (🟢 low / 🟡 medium / 🔴 high)")
    sections.append("   - **Category** (e.g., pitch, networking, spam, client, vendor, personal, unknown)")
    sections.append("   - **Recommendation** (ignore / skim / read later / reply today / urgent)")
    sections.append("")
    sections.append("2. At the top, give an executive summary: total emails, top 2-3 that deserve attention, any patterns.")
    sections.append("")
    sections.append("3. Format for Telegram Markdown:")
    sections.append("   - Use `**bold**` for names and key points")
    sections.append("   - Use `## headers` for sections")
    sections.append("   - Use emoji for priority (🟢🟡🔴) but keep it clean")
    sections.append("   - Use `---` to separate senders")
    sections.append("")
    sections.append("4. At the bottom, note: \"Reply to any? `ghostwriter promote --email <email> --name <name> --tier 1` to add them.\"")
    sections.append("")
    sections.append("Output the digest now. Be concise — this is a morning scan, not a deep read.")

    return "\n".join(sections)


def main():
    excluded = load_excluded_emails()
    query = build_query(excluded)

    emails = search_strangers(query)

    if not emails:
        # No emails from strangers — either silent or a quick "nothing" note
        # Silent is fine for daily cron. Manual trigger should say something.
        if os.environ.get("GHOSTWRITER_DIGEST_VERBOSE"):
            print("📭 No unread emails from unknown senders.")
        sys.exit(0)

    # Fetch snippets for all emails
    emails_data = []
    for email in emails:
        data = fetch_snippet(email["id"])
        emails_data.append(data)

    # Build prompt and spawn LLM
    prompt = build_digest_prompt(emails_data)

    result = subprocess.run(
        ["hermes", "chat", "-q", prompt],
        capture_output=True, text=True, timeout=300,
    )

    # Output the digest (cron delivers this to Telegram)
    # hermes chat -q echoes the prompt before the response.
    # Strip everything before the formatted output marker.
    output = result.stdout or ""
    marker = "╭─"
    if marker in output:
        output = output[output.index(marker):]
    if output:
        print(output.strip())
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

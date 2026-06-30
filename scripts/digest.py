#!/usr/bin/env python3
"""
Ghostwriter v4 Digest — Tier 3 daily digest of non-VIP emails.
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
# List form (no shell=True): args passed as argv, never reinterpreted by a shell.
GAPI = [
    str(HERMES_HOME / "hermes-agent/venv/bin/python3"),
    str(HERMES_HOME / "skills/productivity/google-workspace/scripts/google_api.py"),
]

MAX_EMAILS = 30  # Max emails to include in a digest batch

# Explicit sentinels we control — the LLM wraps its final digest between these.
# Robust to hermes CLI rendering changes (no longer parses on a decorative char).
DIGEST_START = "<<<GHOSTWRITER_DIGEST_START>>>"
DIGEST_END = "<<<GHOSTWRITER_DIGEST_END>>>"


def load_excluded_emails():
    """Return set of emails to exclude from the digest (managed Tier 1 contacts)."""
    if not CONFIG_PATH.exists():
        return set()

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}

    contacts = config.get("contacts", [])
    # Exclude managed (Tier 1) contacts so the user's own / forwarded mail
    # doesn't show up in the stranger digest. (Tier 2 was removed.)
    return {c["email"].lower() for c in contacts if c.get("tier") == 1}


def build_query(excluded):
    """Build Gmail search query excluding managed contacts."""
    query = "is:unread"
    for email in sorted(excluded):
        query += f" -from:{email}"
    return query


def search_strangers(query):
    """Search Gmail for unread emails not from managed contacts."""
    result = subprocess.run(
        GAPI + ["gmail", "search", query, "--max", str(MAX_EMAILS)],
        capture_output=True, text=True, timeout=30,
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
        GAPI + ["gmail", "get", email_id],
        capture_output=True, text=True, timeout=20,
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
    sections.append("You are the Ghostwriter Digest Agent. Generate a daily email digest for the user.")
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
    sections.append("4. At the bottom, note: \"Want any of these auto-handled? `ghostwriter promote --email <email> --name <name>` (only addresses you control).\"")
    sections.append("")
    sections.append("Output the digest now. Be concise — this is a morning scan, not a deep read.")
    sections.append("")
    sections.append(
        "IMPORTANT: Wrap ONLY the final digest between the exact markers "
        f"{DIGEST_START} and {DIGEST_END}, each on its own line. "
        "Put nothing else between them."
    )

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

    # Output the digest (cron delivers this to Telegram).
    # Extract only what the LLM wrapped between our explicit sentinels.
    # Fallback: if sentinels are missing (e.g. LLM ignored them), deliver the
    # full output and warn — never silently send an empty digest.
    raw = result.stdout or ""
    start = raw.find(DIGEST_START)
    end = raw.find(DIGEST_END)
    if start != -1 and end != -1 and end > start:
        output = raw[start + len(DIGEST_START):end].strip()
    else:
        output = raw.strip()
        print(
            "WARNING: digest sentinels not found in LLM output; "
            "delivering full output as fallback.",
            file=sys.stderr,
        )

    if output:
        print(output)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

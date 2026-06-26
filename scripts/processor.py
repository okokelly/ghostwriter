#!/usr/bin/env python3
"""
Ghostwriter v3 Processor — reads watchdog trigger, processes Tier 1 emails.
Only spawns LLM when emails exist. Zero-token on empty ticks.

v3: multi-tenant from config.yaml. Per-contact voice + signature.
    Updates state/<name>.json after each send.
    Tier 2 processing is deferred to v4.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────
GHOSTWRITER_HOME = Path.home() / ".ghostwriter"
STATE_DIR = GHOSTWRITER_HOME / "state"
TRIGGER_FILE = Path("/tmp/ghostwriter_v3_trigger.json")
MAX_AGE_MINUTES = 10  # Ignore trigger files older than this

HERMES_HOME = Path.home() / ".hermes"
GAPI = " ".join([
    str(HERMES_HOME / "hermes-agent/venv/bin/python3"),
    str(HERMES_HOME / "skills/productivity/google-workspace/scripts/google_api.py"),
])


def trigger_is_fresh():
    """Check if trigger file exists and is recent enough."""
    if not TRIGGER_FILE.exists():
        return False

    mtime = datetime.fromtimestamp(TRIGGER_FILE.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    return age <= timedelta(minutes=MAX_AGE_MINUTES)


def load_trigger():
    """Load and parse the trigger file. Returns list of email dicts."""
    with open(TRIGGER_FILE) as f:
        data = json.load(f)
    return data.get("emails", [])


def update_state(name, email, success=True):
    """Update state/<name>.json after processing."""
    state_file = STATE_DIR / f"{name}.json"
    state = {}
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)

    state["last_processed"] = datetime.now(timezone.utc).isoformat()
    state["total_processed"] = state.get("total_processed", 0) + 1
    state["paused"] = state.get("paused", False)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def build_llm_prompt(emails):
    """Build the prompt for hermes chat -q with all Tier 1 emails."""
    # Group by contact
    by_contact = {}
    for e in emails:
        name = e["contact_name"]
        by_contact.setdefault(name, []).append(e)

    sections = []
    sections.append("You are the Ghostwriter v3 Processor. Process each Tier 1 email below.\n")

    for name, contact_emails in by_contact.items():
        first = contact_emails[0]
        voice = first.get("voice_guidelines", "Warm, direct, concise. No AI-isms.")
        signature = first.get("signature", "<p>Cheers,</p><p>Name</p>")
        recipient = first.get("contact_email", "")

        sections.append(f"## Contact: {name} ({recipient})")
        sections.append(f"Voice: {voice}")
        sections.append(f"Signature (HTML): {signature}\n")

        for i, email in enumerate(contact_emails, 1):
            sections.append(f"### Email {i}: {email.get('subject', '(no subject)')}")
            sections.append(f"ID: {email.get('id')}")
            sections.append(f"ThreadID: {email.get('thread_id')}")
            sections.append(f"From: {email.get('from')}")
            sections.append(f"Date: {email.get('date')}")
            sections.append(f"Body:\n{email.get('body', '(empty)')}")
            sections.append("---\n")

    sections.append("## Instructions")
    sections.append("For EACH email above:")
    sections.append("1. Read the full body (provided in context).")
    sections.append("2. Draft a reply in the contact's voice (see Voice above each contact).")
    sections.append("3. Format as clean HTML using <p> tags. NO manual <br> tags.")
    sections.append("4. Append the contact's Signature (HTML) at the end of the reply.")
    sections.append("5. Send via Gmail API:")
    sections.append(f'   $GAPI gmail send --to "<recipient>" --subject "Re: <subject>" \\')
    sections.append(f'     --body "<html>" --html --thread-id "<threadId>"')
    sections.append("6. Mark original as read + archive (two separate calls):")
    sections.append(f"   $GAPI gmail modify <ID> --remove-labels UNREAD")
    sections.append(f"   $GAPI gmail modify <ID> --remove-labels INBOX")
    sections.append("")
    sections.append(f"GAPI path: {GAPI}")
    sections.append("")
    sections.append("After processing all emails, output a summary: which emails you replied to, subjects, any issues.\n")

    return "\n".join(sections)


def main():
    if not trigger_is_fresh():
        sys.exit(0)  # No fresh trigger — silent, zero tokens

    emails = load_trigger()

    if not emails:
        sys.exit(0)  # Empty trigger — silent

    # Filter to Tier 1 only (v3 scope)
    tier1_emails = [e for e in emails if e.get("tier") == 1]
    if not tier1_emails:
        # All emails are Tier 2+ — not our job in v3
        sys.exit(0)

    # Build prompt and spawn LLM
    prompt = build_llm_prompt(tier1_emails)

    result = subprocess.run(
        ["hermes", "chat", "-q", prompt],
        capture_output=True, text=True, timeout=300,
    )

    # Print LLM output for cron logging
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Update state for each processed contact
    processed_names = set()
    for e in tier1_emails:
        name = e.get("contact_name", "unknown")
        if name not in processed_names:
            update_state(name, e.get("contact_email", ""))
            processed_names.add(name)

    # Remove trigger file to prevent re-processing
    TRIGGER_FILE.unlink(missing_ok=True)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

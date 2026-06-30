#!/usr/bin/env python3
"""
Ghostwriter v4 — shared Gmail send helper.

The recipient is ALWAYS supplied by the caller (which reads it from
config.yaml), never chosen by the LLM. This keeps the send target locked to the
user's own configured address: no email body — including a forwarded chain that
says "send this to bob@x.com" — can redirect where a reply goes.

Uses list-form subprocess (no shell=True), so addresses/subjects/bodies are
passed as argv and never interpreted by a shell.
"""

import subprocess
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
GAPI = [
    str(HERMES_HOME / "hermes-agent/venv/bin/python3"),
    str(HERMES_HOME / "skills/productivity/google-workspace/scripts/google_api.py"),
]


def send_reply(to, subject, body_html, thread_id=None, timeout=30):
    """Send an HTML reply via the Gmail API.

    `to` is the locked recipient supplied by the caller (from config), never the
    LLM. Returns (ok: bool, detail: str).
    """
    if not to:
        return False, "no recipient supplied"

    cmd = GAPI + [
        "gmail", "send",
        "--to", to,
        "--subject", subject,
        "--body", body_html,
        "--html",
    ]
    if thread_id:
        cmd += ["--thread-id", thread_id]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "send timed out"

    if result.returncode != 0:
        return False, (result.stderr or "send failed").strip()
    return True, (result.stdout or "").strip()


def mark_read_archive(email_id, timeout=20):
    """Remove UNREAD + INBOX labels from a message. Returns (ok: bool, detail: str)."""
    if not email_id:
        return False, "no email id"

    ok_all = True
    details = []
    for label in ("UNREAD", "INBOX"):
        cmd = GAPI + ["gmail", "modify", email_id, "--remove-labels", label]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            ok_all = False
            details.append(f"{label}: timed out")
            continue
        if r.returncode != 0:
            ok_all = False
            details.append(f"{label}: {(r.stderr or '').strip()}")
    return ok_all, "; ".join(details)

---
name: ghostwriter
description: Autonomous email management — zero-token watchdog/processor/digest cron pipeline. Tier 1 auto-replies to your own configured address (recipient locked); Tier 3 gives a daily digest of everyone else.
version: 4.0.1
category: email
---

# Ghostwriter

Autonomous email management via a no-agent cron pipeline reading from
`~/.ghostwriter/config.yaml`. Tier 1 mail gets an auto-drafted reply sent back to
your own configured address; Tier 3 (everyone else) gets a daily digest. The LLM
only runs when there is real work — **$0 idle cost**.

## Tier model

| Tier | Behavior | Scope |
|------|----------|-------|
| Tier 1 | Auto-draft a reply; Python sends it to your configured address | You. Your own mail + chains you forward to the agent. |
| Tier 3 | Never auto-reply. Rolled into a daily digest. | Everyone not configured (newsletters, cold outreach). |

There is no Tier 2. "Draft → approve → send to a third party" was intentionally
not built: because every reply is sent only to your own address, a reply to a
forwarded chain lands in your inbox for you to forward onward — the same
human-in-the-loop, with no approval machinery and no risk of the model emailing
the wrong person.

## Architecture

```
~/.ghostwriter/config.yaml     ← source of truth (your address, voice, signature)
        │
        ▼
cron: watchdog.py (every 5 min, no_agent=true)
  → reads config.yaml
  → Gmail search: from:<your Tier 1 address> is:unread
  → atomic-writes /tmp/ghostwriter_v4_trigger.json
        │
        ▼
cron: processor.py (every 5 min, +1 offset, no_agent=true)
  → flock + claim trigger before spawning (no double-send)
  → per email: LLM drafts the reply BODY only
               Python appends signature + SENDS to the config address
               Python archives the original, records the real result
        │
cron: digest.py (daily, no_agent=true)
  → summarizes unread mail NOT from a managed contact → your chat
```

The recipient is taken from `config.yaml` by Python, never chosen by the model.
Email bodies are passed to the model as untrusted data.

## Config

`config.yaml` is the source of truth — copy `config.example.yaml` to
`~/.ghostwriter/config.yaml` and edit it directly. Minimal Tier 1 entry:

```yaml
contacts:
  - name: me
    email: you@example.com          # replies are always sent here
    tier: 1
    signature: "<p>Cheers,</p><p>Your Name</p>"
    voice_guidelines: "Warm, direct, concise. No AI-isms."
    paused: false
```

## Voice & signature

Two per-contact fields in `config.yaml` shape a reply (both optional — generic
defaults apply if omitted):

| Field | Role | Example |
|-------|------|---------|
| `voice_guidelines` | Free text handed to the model when drafting | `Warm, direct, concise. No AI-isms.` |
| `signature` | HTML appended verbatim after the drafted body | `<p>Cheers,</p>` |

## Cron jobs

Three `no_agent=true` jobs (create with `hermes cron create`, see README):
a watchdog (every 5 min), a processor (every 5 min, +1 offset), and a daily
digest. All exit silently with zero tokens when there is nothing to do.

## Files

| File | Role |
|------|------|
| `scripts/watchdog.py` | Gmail poller → atomic trigger write |
| `scripts/processor.py` | Drafts via LLM, sends via Python to the config address |
| `scripts/send_email.py` | Shared Gmail send / archive helper (locked recipient) |
| `scripts/digest.py` | Daily Tier 3 digest |
| `config.example.yaml` | Config template |
| `references/` | Voice / format reference notes |

## Pitfalls

- **`gmail modify` takes ONE label per call** — UNREAD and INBOX are removed in two separate calls.
- **Use `gmail send --html`, never `gmail reply`** — plain text gets mangled in some clients.
- **Keep the scripts `no_agent=true`** — wrapping them in an LLM agent cron job destroys the $0 idle.
- **Deploy `send_email.py` alongside `processor.py`** — the processor imports it.

## Changelog

**v4.0.1** — Closed the re-enqueue double-reply window with message-id dedup
(`state/sent_ids.json`), recorded the instant a send succeeds. Watchdog/digest
Gmail calls converted to list-form `subprocess` (no `shell=True`). Digest no
longer references the removed `ghostwriter promote` CLI — it points users to
`config.yaml`. Documented the "agent mailbox ≠ Tier 1 address" prerequisite.
Dropped the unused `voice:` config field. Empty-body / duplicate messages no
longer inflate `total_failed`.

**v4.0.0** — LLM now drafts only; Python performs the send to the address in
`config.yaml` (recipient locked — no email body can redirect it). Added
`send_email.py`. Email bodies treated as untrusted. Removed Tier 2. Hardening:
`flock` single-instance lock, claim-trigger-before-spawn (no double-send),
atomic trigger write, real send/fail state, sentinel-based digest parsing.

**v3.0.0** — Config-driven multi-tenant watchdog + processor reading from
`~/.ghostwriter/config.yaml`. Tier 1 auto-reply + Tier 3 digest.

**v2.0.0** — Processor changed from LLM agent to no-agent script (~97% idle token reduction).

**v1.0.0** — Initial two-job architecture.

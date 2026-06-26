# Ghostwriter v3 → v4 — Handover Note

> Generated: 2026-06-26 | By: Amber (with Kelly) | Session: Telegram DM
>
> 🎯 **v3 is built and running.** Scope: Tier 1 (multi-contact auto-reply) + Tier 3 (daily digest). Tier 2 (draft → approve → send) is the v4 deliverable. This note is for the session that builds v4.

## What was built in v3 (Phase 1 + Phase 2)

### CLI (`ghostwriter`)

Installed at `~/.local/bin/ghostwriter`. Python, zero extra deps (pyyaml is in Hermes venv).

```
ghostwriter init                           # Create ~/.ghostwriter/
ghostwriter add --email <e> --name <n> --tier <1|2> [--voice personal|professional] [--signature "..."]
ghostwriter list                           # Table: name, email, tier, status, voice, processed
ghostwriter show <name>                    # Full contact details + stats
ghostwriter edit <name> [--tier] [--voice] [--signature] [--email]
ghostwriter pause <name>                   # Skip in cron ticks
ghostwriter resume <name>
ghostwriter remove <name>                  # Remove contact + state files
ghostwriter stats                          # Overview
ghostwriter digest                         # Manual Tier 3 trigger (runs digest.py)
ghostwriter promote --email <e> --name <n> --tier 1  # Convenience: add from digest
```

Voice presets: `personal` (Cheers, Kelly) and `professional` (Best regards, Kelly).

### Config & data

```
~/.ghostwriter/
├── config.yaml          # Source of truth — all contacts and tiers
├── state/               # Per-contact JSON: total_processed, last_processed, paused
├── drafts/              # Empty — reserved for v4 Tier 2 drafts
├── history/             # Empty — reserved for v3.1
```

Config schema:
```yaml
contacts:
  - name: kelly
    email: kellyjiashuyao@outlook.com
    tier: 1
    voice: personal
    signature: <p>Cheers,</p><p>Kelly</p>
    voice_guidelines: Warm, direct, concise...
    added: '2026-06-26T...'
    paused: false
```

Currently one contact: `kelly` (Tier 1, personal voice).

### Cron jobs (all running)

| Job ID | Name | Script | Schedule | Deliver | no_agent |
|--------|------|--------|----------|---------|----------|
| `3c51678f31cb` | Ghostwriter v3 Watchdog | `ghostwriter_v3_watchdog.py` | Every 5min (0,5,10...) | local | ✓ |
| `fddc50ba1109` | Ghostwriter v3 Processor | `ghostwriter_v3_processor.py` | Every 5min +1 (1,6,11...) | local | ✓ |
| `7f93985e52ad` | Ghostwriter v3 Digest | `ghostwriter_v3_digest.py` | Daily 9am | origin (Telegram) | ✓ |

All three are `no_agent=true` — **$0 idle cost**. LLM only spawns when work exists.

### v2 jobs (paused, not deleted)

| Job ID | Name | Status |
|--------|------|--------|
| `0d85b66d14a6` | Kelly Watchdog | ⏸ Paused |
| `ddaa0fee446e` | Kelly Processor | ⏸ Paused |

Can be deleted once v3 has processed a real Tier 1 email. Don't delete until validated.

### Pipeline flow

```
Watchdog (every 5min, no_agent)
  → Reads ~/.ghostwriter/config.yaml
  → Searches Gmail: (from:tier1_email1 OR ...) is:unread
  → Writes /tmp/ghostwriter_v3_trigger.json (JSON with per-email metadata)

Processor (every 5min +1, no_agent)
  → Reads trigger file (checks freshness: ≤10min old)
  → Tier 1 emails → spawns `hermes chat -q` → draft + send + archive
  → Updates state/<name>.json
  → Deletes trigger file

Digest (daily 9am, no_agent)
  → Reads config.yaml → build exclusion query: is:unread -from:{all tier1+2}
  → Fetches subject + 600-char snippet per email (max 30)
  → Spawns `hermes chat -q` → per-sender summary + 🟢🟡🔴 priority + recommendation
  → Delivers to Telegram (origin)
```

### Source files

| File | Role |
|------|------|
| `~/amber-os/_Projects/ghostwriter-cli-v3/scripts/watchdog.py` | Multi-tenant Gmail poller |
| `~/amber-os/_Projects/ghostwriter-cli-v3/scripts/processor.py` | Tier 1 auto-reply + state update |
| `~/amber-os/_Projects/ghostwriter-cli-v3/scripts/digest.py` | Tier 3 daily digest |
| `~/.local/bin/ghostwriter` | CLI (the deployed copy — edit this, not the project) |
| `~/.hermes/scripts/ghostwriter_v3_*.py` | Cron copies (updated via `cp` from project scripts) |
| `~/.ghostwriter/config.yaml` | Contact config |
| `~/.ghostwriter/state/*.json` | Per-contact runtime state |

### Verified

- Watchdog dry-run: silent exit on empty inbox ✓
- Processor: not tested with real emails yet (Kelly hasn't emailed herself since deploy)
- Digest dry-run: found 4 emails, produced formatted Telegram digest with priorities ✓
- CLI all commands: tested ✓
- `ghostwriter promote`: tested ✓

## v4 Scope: Tier 2 Approval Flow

### What needs to be built

Tier 2 contacts get: **Agent drafts → Kelly approves → Agent sends**. No auto-send.

### The flow

```
processor cron tick → detect Tier 2 email
  → LLM drafts reply → writes drafts/<name>-<date>-<id>.txt (or .json)
  → Amber (via Telegram): "New Tier 2 email from <name>. Draft ready. [show draft]"

Kelly: "send" / "change X"
  → If "send": ghostwriter approve → CLI sends via Gmail API directly
  → If "change": Amber revises draft → re-confirm → send
```

### CLI commands to add

```bash
ghostwriter pending                       # Show all pending drafts
ghostwriter approve <name> [--id <id>]    # Send a draft
ghostwriter reject <name> [--id <id>]     # Discard a draft
```

### Hard problems for v4

#### 1. Approval flow + cron model conflict

Cron jobs run and exit. They can't "wait for approval."

**Solution from design:** processor only drafts (never sends for Tier 2). CLI handles the actual send via `ghostwriter approve`. This means CLI needs direct Gmail API access.

#### 2. Draft state machine

A Tier 2 email goes through: `detected → drafted → notified → (edited? redrafted?) → approved → sent`.

Each state must be on disk so crashes don't lose context. Edge cases:
- Same email detected twice by processor → must not create duplicate drafts
- Sending fails → state must roll back to "drafted", not get lost
- Kelly ignores notification for days → drafts pile up → need cleanup/presentation logic

#### 3. Modularize Gmail send logic

**CRITICAL:** CLI must be able to send emails via Gmail API directly for Tier 2 approve. Both processor.py (auto-send for Tier 1) and CLI (manual send for Tier 2) must share the same send function. Otherwise format drift between auto and manual sends.

Current send logic is embedded in the LLM prompt (`hermes chat -q`). For v4, extract a `send_email()` function that both processor.py and the CLI can call.

#### 4. How does Kelly's Telegram "send" / "change X" route back?

This is the load-bearing open question from the v3 design.

The processor drafts and notifies via Telegram. Kelly responds "send" in the Telegram chat. But how does that Telegram message trigger `ghostwriter approve`?

Options:
- **A: Hermes is always listening** — Kelly's "send" in Telegram is a normal Hermes interaction. Amber receives it, understands context, runs `ghostwriter approve`. This is the natural Hermes model but requires Amber to be active.
- **B: Watchdog polls for approval** — A separate cron job checks for some "approval signal" file or state. Clunky.
- **C: Telegram bot webhook** — Over-engineering for v4.

**Recommendation: A.** Kelly's Telegram "send" triggers Amber (normal Hermes interaction), who then calls `ghostwriter approve`. The draft context is passed in the Telegram notification message, so Amber has everything needed.

#### 5. Draft notification format

When processor detects a Tier 2 email and drafts a reply, it needs to notify Kelly via Telegram. The notification must include enough context for Kelly to decide without opening another app:

```
📬 Tier 2: Bob (bob@vc.com)
Subject: Re: Q3 portfolio review
Draft:
> Hey Bob — thanks for the update. The Q3 numbers look strong...
> [full draft]

Reply with "send" to send, or "change [your edit]" to revise.
```

Currently, the processor outputs to stdout (deliver=local). For v4, Tier 2 notifications need to go to Telegram. Options:
- Change processor deliver to "origin" — but then Tier 1 processing output also goes to Telegram (noisy)
- Have the processor call a separate notification mechanism
- Have a separate Tier 2 notification cron job

#### 6. Duplicate detection

The processor must not create duplicate drafts for the same email. Use the email ID as the dedup key. Store processed IDs in state or a separate tracking file.

### What NOT to do in v4

- Don't make Tier 2 auto-send — approval must be explicit
- Don't use file-based IPC for the approval flow — use Telegram conversation
- Don't break the existing v3 cron jobs — they're running in production
- Don't introduce npm/Node.js — Python only
- Don't add multi-round conversation state (conversation.md) — deferred to v3.1
- Don't over-engineer — v4 MVP should work for 2-3 Tier 2 contacts

### Files to create/modify for v4

| File | Action |
|------|--------|
| `scripts/processor.py` | Add Tier 2 branch: draft → save to `drafts/` → notify (no send) |
| `scripts/send_email.py` | **NEW** — shared `send_email()` function (extracted from processor LLM prompt) |
| `~/.local/bin/ghostwriter` | Add `pending`, `approve`, `reject` subcommands + Gmail send logic |
| `~/.ghostwriter/drafts/` | Tier 2 drafts stored here |
| `~/.ghostwriter/state/<name>.json` | Extend with draft tracking fields |
| `SKILL.md` | Update for v4 |

### Open questions from v3 (still relevant)

- **Hard Problem #8**: Per-contact memory storage. Recommendation: `state/<name>.md` — not urgent, can land anytime in v4.
- **Hard Problem #6**: Cron timing with multi-tenant Gmail query. Watchdog now builds complex `-from:` queries. Verify the 1-minute offset still holds when 10+ contacts exist. Not tested yet — only one contact (kelly).
- **Hard Problem #7**: Token budget. Currently preserved ($0 idle). v4's Tier 2 notifications add cost — ensure they don't burn tokens on empty ticks.

## Context to load in a new v4 session

1. **This HANDOVER note** (obviously)
2. `~/amber-os/_Projects/ghostwriter-cli-v3/HANDOVER.md` — original v3 design (Tier 2 specs are there)
3. `~/.local/bin/ghostwriter` — understand the CLI architecture
4. `scripts/processor.py` — understand the Tier 1 branch (Tier 2 branch goes next to it)
5. `scripts/watchdog.py` — understand the trigger file format (Tier 2 emails are already in it, just ignored by processor)
6. `scripts/digest.py` — understand the Gmail query building pattern
7. `~/.ghostwriter/config.yaml` — see live config

## Key context: who's who

- **Kelly Jia = the human** (kellyjiashuyao@outlook.com)
- **Amber = the AI agent** — runs on Hermes, executes ghostwriter operations. Never use "Amber" in public-facing work
- Gmail API operations account: amber.jia.1024@gmail.com
- Gmail API path: `~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/productivity/google-workspace/scripts/google_api.py`
- Communication: Kelly ↔ Amber via Telegram DM
- Hermes venv: `~/.hermes/hermes-agent/venv/bin/python3`

## Voice & signature (don't change)

- **Tier 1 signature:** `Cheers,\nKelly` (warm, casual, inner circle)
- **Tier 2 signature:** `Best regards,\nKelly` (polished, professional)
- Signatures are intentionally different — do not unify them
- Voice: warm, direct, no AI-isms, contractions, natural American English

## Quick diagnostic commands

```bash
ghostwriter list                           # See all contacts
ghostwriter stats                          # Overview
ghostwriter show <name>                    # Full contact details
cat ~/.ghostwriter/config.yaml             # Raw config
ls ~/.ghostwriter/state/                   # State files
cat /tmp/ghostwriter_v3_trigger.json       # Latest trigger (if exists)
hermes cron list | grep -i ghost           # See all ghostwriter cron jobs
```

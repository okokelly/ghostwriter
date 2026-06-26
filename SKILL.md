---
name: ghostwriter
description: Autonomous email auto-reply pipeline — multi-tenant CLI + zero-token watchdog/processor. Manages Tier 1 auto-reply and Tier 3 daily digest. Tier 2 approval deferred to v4.
version: 3.0.0
category: email
---

# Ghostwriter v3

Multi-tenant autonomous email management via a Python CLI (`ghostwriter`) + two-job no-agent cron pipeline. Tier 1 contacts get fully autonomous replies. Tier 3 (strangers) get a daily digest. Tier 2 (approval) is deferred to v4.

## Quick reference: Tier model

| Tier | Behavior | Scope |
|------|----------|-------|
| Tier 1 | Auto-draft + auto-send, zero friction | Inner circle. v2 behavior, multi-contact. |
| Tier 2 | Draft → notify → approve → send | Deferred to v4. |
| Tier 3 | Never auto-reply. Daily digest. | Strangers, cold outreach. |

## Architecture

```
~/.ghostwriter/config.yaml     ← Source of truth (CLI manages)
        │
        ▼
cron: watchdog.py (every 5min, no_agent=true)
  → Reads config.yaml
  → Gmail search: (from:tier1_email1 OR from:tier1_email2 ...) is:unread
  → Writes /tmp/ghostwriter_v3_trigger.json
        │
        ▼
cron: processor.py (every 6min, offset +1, no_agent=true)
  → Reads trigger file
  → Tier 1 → spawns `hermes chat -q` → draft + send + archive
  → Updates state/<name>.json
```

Both scripts are no_agent=true — **$0 idle cost**. LLM only spawns when trigger file has emails.

## CLI commands

```bash
ghostwriter init                           # Create ~/.ghostwriter/
ghostwriter add --email <e> --name <n> --tier <1|2> [--voice personal|professional] [--signature "..."]
ghostwriter list                           # Table: name, email, tier, status, voice, processed
ghostwriter show <name>                    # Full contact details + stats
ghostwriter edit <name> [--tier <1|2>] [--voice <preset>] [--signature "..."] [--email <e>]
ghostwriter pause <name>                   # Skip in cron ticks
ghostwriter resume <name>
ghostwriter remove <name>                  # Remove contact + state
ghostwriter stats                          # Overview
ghostwriter digest                         # Manual Tier 3 trigger (Phase 2)
```

CLI is installed at `~/.local/bin/ghostwriter`.

## Voice presets

| Preset | Signature | Use case |
|--------|-----------|----------|
| `personal` | `<p>Cheers,</p><p>Name</p>` | Inner circle, warm, casual |
| `professional` | `<p>Best regards,</p><p>Name</p>` | Colleagues, investors |

Custom signatures supported via `--signature` on `add` or `edit`.

## Cron jobs (v3)

| Job | Schedule | Script |
|-----|----------|--------|
| Ghostwriter v3 Watchdog (`3c51678f31cb`) | Every 5min (0,5,10...) | `ghostwriter_v3_watchdog.py` |
| Ghostwriter v3 Processor (`fddc50ba1109`) | Every 5min +1 (1,6,11...) | `ghostwriter_v3_processor.py` |

v2 jobs (`Kelly Watchdog` ... and `Kelly Processor` ...) are **paused** — v3 handles the same contacts.

## Files

| File | Role |
|------|------|
| `~/.local/bin/ghostwriter` | CLI entry point |
| `scripts/watchdog.py` | Multi-tenant Gmail poller |
| `scripts/processor.py` | Tier 1 auto-reply engine |
| `references/processor-prompt.md` | Legacy voice reference (v2) |
| `references/standing-rules.md` | Standing rules template |

## Pitfalls

- **`gmail modify` takes ONE label per call** — use two separate invocations for UNREAD + INBOX
- **Use `gmail send --html`, never `gmail reply`** — plain text gets mangled in Outlook
- **Don't wrap processor or watchdog in LLM agent cron jobs** — they must be `no_agent=true` to preserve $0 idle
- **Don't make Tier 2 auto-send** — approval must be explicit (deferred to v4)

## Changelog

**v3.0.0** — Multi-tenant CLI (`ghostwriter`). Config-driven watchdog + processor reading from `~/.ghostwriter/config.yaml`. Tier model: Tier 1 auto-reply, Tier 2 deferred, Tier 3 digest (Phase 2).

**v2.0.0** — Processor changed from LLM agent to no-agent script. ~97% token reduction on idle days.

**v1.0.0** — Initial release. Two-job architecture: no-agent watchdog + LLM agent processor.

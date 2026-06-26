# Ghostwriter

> Autonomous email management for Hermes Agent — multi-contact auto-reply + daily digest. **$0 idle cost.**

Ghostwriter monitors your inbox, auto-replies to your inner circle in your voice, and gives you a daily digest of everything else. All three cron jobs are pure Python scripts with no LLM agent — the LLM only wakes when there's actual work.

```
┌─────────────────────────────────────────────────────┐
│                   GHOSTWRITER v3                     │
│                                                      │
│  ┌──────────┐                                        │
│  │   CLI    │  ghostwriter add/list/pause/digest...  │
│  │ (Python) │  Manages ~/.ghostwriter/config.yaml    │
│  └──────────┘                                        │
│                                                      │
│  ┌──────────┐  every 5min   ┌──────────────────────┐ │
│  │ Watchdog │ ── no match ─▶│ Silent ($0)           │ │
│  │ (script) │               └──────────────────────┘ │
│  │          │ ── match ────▶ /tmp/trigger.json       │
│  └──────────┘               └──────────┬───────────┘ │
│                                        │              │
│  ┌──────────┐  every 5min+1            │              │
│  │ Processor│ ◀────────────────────────┘              │
│  │ (script) │  Tier 1 → draft + send + archive       │
│  │          │  Tier 2 → draft + notify (v4)          │
│  └──────────┘                                        │
│                                                      │
│  ┌──────────┐  daily 9am                             │
│  │  Digest  │  Tier 3 → summary + priority → TG      │
│  │ (script) │                                        │
│  └──────────┘                                        │
└─────────────────────────────────────────────────────┘
```

## Three tiers

| Tier | Behavior | Use case |
|------|----------|----------|
| **Tier 1** | Fully autonomous: draft + send, zero friction | Your inner circle |
| **Tier 2** | Draft → notify → approve → send *(v4)* | Important contacts |
| **Tier 3** | Never auto-reply. Daily digest with priority scoring | Strangers, cold outreach |

## Quick start

### Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com) with Google Workspace configured
- Python 3.9+ with `pyyaml`

### 1. Install the CLI

```bash
cp ghostwriter ~/.local/bin/ghostwriter
chmod +x ~/.local/bin/ghostwriter
```

### 2. Initialize

```bash
ghostwriter init
```

### 3. Add a Tier 1 contact

```bash
ghostwriter add --email friend@example.com --name friend --tier 1 --voice personal
```

### 4. Deploy the cron jobs

```bash
cp scripts/watchdog.py ~/.hermes/scripts/ghostwriter_watchdog.py
cp scripts/processor.py ~/.hermes/scripts/ghostwriter_processor.py
cp scripts/digest.py ~/.hermes/scripts/ghostwriter_digest.py

# Watchdog — scans Gmail every 5 minutes
hermes cron create \
  --name "Ghostwriter Watchdog" \
  --schedule "0,5,10,15,20,25,30,35,40,45,50,55 * * * *" \
  --no-agent true \
  --script "ghostwriter_watchdog.py"

# Processor — drafts and sends Tier 1 replies
hermes cron create \
  --name "Ghostwriter Processor" \
  --schedule "1,6,11,16,21,26,31,36,41,46,51,56 * * * *" \
  --no-agent true \
  --script "ghostwriter_processor.py"

# Digest — daily 9am summary of non-VIP emails
hermes cron create \
  --name "Ghostwriter Digest" \
  --schedule "0 9 * * *" \
  --no-agent true \
  --script "ghostwriter_digest.py" \
  --deliver origin
```

That's it. Your Tier 1 contacts get auto-replies in your voice. You get a digest every morning. Zero cost when nothing's happening.

## CLI reference

```bash
# Contact management
ghostwriter add --email <e> --name <n> --tier <1|2> [--voice personal|professional]
ghostwriter list                           # Table view
ghostwriter show <name>                    # Full details + stats
ghostwriter edit <name> --tier 2           # Change tier
ghostwriter pause <name>                   # Skip in cron ticks
ghostwriter resume <name>
ghostwriter remove <name>

# Tier 3 digest
ghostwriter digest                          # Manual trigger
ghostwriter promote --email <e> --name <n> --tier 1  # Promote from digest

# Overview
ghostwriter stats
```

## Voice presets

| Preset | Tone | Signature |
|--------|------|-----------|
| `personal` | Warm, direct, casual | `Cheers,\nName` |
| `professional` | Polished but not stiff | `Best regards,\nName` |

Custom signatures supported via `--signature`.

## Architecture

All three cron scripts are `no_agent=true` — **$0 LLM tokens on empty ticks**.

| Script | What it does | When |
|--------|-------------|------|
| `watchdog.py` | Reads config, searches Gmail for Tier 1+2 emails, writes trigger file | Every 5 min |
| `processor.py` | Reads trigger, Tier 1 → `hermes chat -q` → draft + send + archive | Every 5 min +1 |
| `digest.py` | Excludes managed contacts, LLM batch summarizes rest, pushes to Telegram | Daily 9am |

Data lives in `~/.ghostwriter/config.yaml` (source of truth) and `~/.ghostwriter/state/*.json` (per-contact stats).

## What NOT to do

- Don't wrap processor/digest in an LLM agent cron job — they're `no_agent=true` scripts. The $0-idle property depends on this.
- Don't use `gmail reply` — plain text mangles in Outlook. Always `gmail send --html --thread-id`.
- Don't combine `gmail modify` labels — one `--remove-labels` per call.

## Files

| File | Role |
|------|------|
| `ghostwriter` | CLI entry point |
| `scripts/watchdog.py` | Multi-tenant Gmail poller |
| `scripts/processor.py` | Tier 1 auto-reply engine |
| `scripts/digest.py` | Tier 3 daily digest |
| `SKILL.md` | Hermes skill definition |
| `references/` | Voice templates and standing rules |

## License

MIT

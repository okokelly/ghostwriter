# Ghostwriter v2

Autonomous email auto-reply for Hermes Agent. Two-job pipeline — **both no-agent scripts** — that monitors a VIP inbox, drafts replies in your voice, and sends them without lifting a finger. Zero LLM tokens when there's nothing to do.

```
┌─────────────────────────────────────────────────────────┐
│                      GHOSTWRITER v2                      │
│                                                          │
│  ┌──────────┐  every 5min   ┌─────────────────────────┐ │
│  │ Watchdog │ ─── no match ─▶│ Silent ($0)             │ │
│  │ (script) │               └─────────────────────────┘ │
│  │          │                                           │
│  │          │ ─── match ───▶ /tmp/ghostwriter_output.txt│
│  └──────────┘               └──────────┬──────────────┘ │
│                                        │                 │
│  ┌──────────┐  every 6min              │                 │
│  │ Processor│ ◀────────────────────────┘                 │
│  │ (script) │                                           │
│  │          │ ─── no file / stale ──▶ Silent ($0)       │
│  │          │ ─── fresh emails ─────▶ hermes chat -q    │
│  │          │                         1. Read email     │
│  │          │                         2. Draft reply    │
│  │          │                         3. Send           │
│  │          │                         4. Archive        │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

## The idea

Hermes can already send email. But polling a Gmail inbox with an LLM agent every 5 minutes burns tokens even when there's nothing new.

Ghostwriter splits the work into two scripts — neither one touches an LLM unless there's actual work. A lightweight **Watchdog** script (Python, no LLM) searches Gmail every 5 minutes. When it finds a matching email, a **Processor** script (also Python, no LLM) reads the output and spawns `hermes chat -q` to draft and send a reply. When there's nothing, both scripts exit silently — zero tokens, zero cost.

**v2 improvement:** The Processor used to be an LLM agent cron job that burned ~3,500 tokens even on empty ticks (just to read the empty context and respond "."). Now it's a no-agent script — same as the Watchdog. True zero-token idle.

## Quick start

### 1. Prerequisites

Hermes Agent with Google Workspace configured. Verify:
```bash
GAPI="$HOME/.hermes/hermes-agent/venv/bin/python3 $HOME/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
$GAPI gmail search "is:unread" --max 1
```

### 2. Configure your VIP

Copy both scripts and edit them:

```bash
cp scripts/watchdog.py ~/.hermes/scripts/ghostwriter_watchdog.py
cp scripts/processor.py ~/.hermes/scripts/ghostwriter_processor.py
```

In `ghostwriter_watchdog.py`, change the Gmail query:
```python
QUERY = 'from:vip@example.com is:unread'  # ← your VIP's email
```

In `ghostwriter_processor.py`, set the recipient and customize the voice:
```python
RECIPIENT = "person@example.com"          # ← your VIP's email
VOICE_GUIDELINES = """..."""              # ← how replies should sound
SIGNATURE = "<p>Cheers,</p><p>Name</p>"   # ← your name
```

### 3. Create the cron jobs

```bash
# Watchdog — zero tokens, script only
hermes cron create \
  --name "Ghostwriter Watchdog" \
  --schedule "0,5,10,15,20,25,30,35,40,45,50,55 * * * *" \
  --no-agent true \
  --script "ghostwriter_watchdog.py"

# Processor — zero tokens unless email found
hermes cron create \
  --name "Ghostwriter Processor" \
  --schedule "1,6,11,16,21,26,31,36,41,46,51,56 * * * *" \
  --no-agent true \
  --script "ghostwriter_processor.py"
```

> **Why 1-minute offset?** The processor fires 1 minute after the watchdog. Using explicit cron expressions (`0,5,10...` / `1,6,11...`) guarantees they stay in lockstep.

### 4. Done

Your VIP gets auto-replies in your voice. You get silence unless something happens.

## Adapting for multiple VIPs

Copy both scripts with new filenames, change the query and recipient, and create a second watchdog + processor cron pair. Set a different `OUTPUT_FILE` path in each pair (e.g., `/tmp/ghostwriter_investor.txt`).

## Cost (v2)

| Pattern | Nothing happening | Per email |
|---------|------------------|-----------|
| Single agent polling every 5min | ~$0.30–0.50/day | ~$0.002 |
| Ghostwriter v1 | ~$0.03/day | ~$0.002 |
| **Ghostwriter v2** | **$0.00/day** | ~$0.002 |

When there are no emails, v2 burns zero LLM tokens. The Watchdog and Processor are both pure Python scripts. The LLM only wakes when there's actual work to do.

## Voice

Ghostwriter drafts replies in whatever voice you specify in the processor script. The default assumes:
- Warm, direct, concise
- No corporate AI-isms
- Contractions (I'll, don't)
- Natural American English

Edit `VOICE_GUIDELINES` in `processor.py` to match your voice.

## Files

| File | What |
|------|------|
| `SKILL.md` | Hermes skill definition |
| `scripts/watchdog.py` | Watchdog script — edit the Gmail query |
| `scripts/processor.py` | Processor script — edit voice + recipient |
| `references/processor-prompt.md` | Reference: the voice/format guide |
| `references/standing-rules.md` | Standing rules template |

## License

MIT

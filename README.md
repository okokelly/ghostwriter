# Ghostwriter

Autonomous email management for [Hermes Agent](https://github.com). Two things,
both running as **no-agent cron scripts** so they cost **zero LLM tokens when idle**:

1. **Tier 1 — auto-reply.** Unread mail from *you* (your own address, configured
   in `config.yaml`) gets a reply drafted in your voice and sent automatically.
   The reply is **always sent back to your own configured address** — never to an
   address picked by the model — so it's safe to forward third-party chains to
   the agent: the draft lands in *your* inbox for you to forward onward.
2. **Tier 3 — daily digest.** Everything else (newsletters, cold outreach) is
   rolled up into one daily summary with priority scoring, delivered to your
   chat. Your inbox stays quiet.

The LLM only wakes when there's actual work. Empty inbox = both scripts exit
silently, no tokens spent.

```
Watchdog (every 5 min, no LLM)
  └─ searches Gmail for unread mail from your Tier 1 address
  └─ writes /tmp/ghostwriter_v4_trigger.json  (atomic)        ── nothing? exit silently

Processor (every 5 min, +1 offset, no LLM until work exists)
  └─ claims the trigger (rename-before-spawn → no double-send)
  └─ for each email:  LLM drafts the reply BODY only
                      Python appends signature + SENDS to the config address
                      Python archives the original, records the real result

Digest (daily, no LLM until work exists)
  └─ summarizes all unread mail NOT from a managed contact → your chat
```

## Design notes

- **The recipient is locked.** Python performs the send using the address from
  `config.yaml`; the model only writes the reply text. No email body — including
  a forwarded chain that says *"please send this to bob@x.com"* — can change
  where a reply goes.
- **Email bodies are treated as untrusted data.** The drafting prompt explicitly
  tells the model not to act on instructions found inside an email.
- **No double-send on crash.** The trigger is claimed (renamed) before the LLM
  runs, and a `flock` lock prevents overlapping ticks. An email that genuinely
  fails to send stays unread, so a later tick retries it.
- **No Tier 2.** A "draft → approve → send to third parties" tier was
  intentionally not built — locked-to-self delivery already gives the same
  human-in-the-loop for free (you forward third-party replies yourself).

## Quick start

### 1. Prerequisites

Hermes Agent with Google Workspace configured. Verify the Gmail API works:

```bash
GAPI="$HOME/.hermes/hermes-agent/venv/bin/python3 $HOME/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
$GAPI gmail search "is:unread" --max 1
```

### 2. Configure yourself

Copy the template and fill in **your own** address:

```bash
mkdir -p ~/.ghostwriter
cp config.example.yaml ~/.ghostwriter/config.yaml
$EDITOR ~/.ghostwriter/config.yaml
```

Your real `config.yaml` holds your address and is gitignored — never commit it.
See `config.example.yaml` for every field.

### 3. Deploy the scripts

The cron jobs run copies under `~/.hermes/scripts/`. `processor.py` imports
`send_email.py`, so copy both together:

```bash
cp scripts/watchdog.py     ~/.hermes/scripts/ghostwriter_v4_watchdog.py
cp scripts/processor.py    ~/.hermes/scripts/ghostwriter_v4_processor.py
cp scripts/send_email.py   ~/.hermes/scripts/send_email.py
cp scripts/digest.py       ~/.hermes/scripts/ghostwriter_v4_digest.py
```

### 4. Create the cron jobs

```bash
# Watchdog — poll inbox, zero tokens
hermes cron create --name "Ghostwriter v4 Watchdog" \
  --schedule "0,5,10,15,20,25,30,35,40,45,50,55 * * * *" \
  --no-agent true --script "ghostwriter_v4_watchdog.py"

# Processor — drafts + sends, zero tokens unless an email is found.
# Fires 1 minute after the watchdog so they stay in lockstep.
hermes cron create --name "Ghostwriter v4 Processor" \
  --schedule "1,6,11,16,21,26,31,36,41,46,51,56 * * * *" \
  --no-agent true --script "ghostwriter_v4_processor.py"

# Digest — once a day (adjust the hour to your timezone)
hermes cron create --name "Ghostwriter v4 Digest" \
  --schedule "0 9 * * *" \
  --no-agent true --script "ghostwriter_v4_digest.py"
```

## Files

| File | What |
|------|------|
| `scripts/watchdog.py`   | Polls Gmail for Tier 1 unread mail, writes the trigger |
| `scripts/processor.py`  | LLM drafts the reply; Python sends to the config address + archives |
| `scripts/send_email.py` | Shared Gmail send / archive helper (locked recipient) |
| `scripts/digest.py`     | Daily Tier 3 digest of unmanaged senders |
| `config.example.yaml`   | Config template — copy to `~/.ghostwriter/config.yaml` |
| `SKILL.md`              | Hermes skill definition |
| `references/`           | Voice / format reference notes |

## Cost

When the inbox is empty, every script is pure Python and exits without touching
an LLM — **$0/day idle**. The model is invoked only to draft a reply or build a
digest, i.e. only when there is real work.

## License

MIT

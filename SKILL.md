---
name: ghostwriter
description: Autonomous email auto-reply pipeline — zero-token watchdog + zero-token processor. Only burns LLM tokens when there's actual email to reply to.
version: 2.0.0
category: email
---

# Ghostwriter v2

Set up an autonomous email auto-reply pipeline for a VIP contact. Two-job architecture, **both no-agent scripts** — zero LLM tokens when there's nothing to do. The processor only spawns an LLM (`hermes chat -q`) when the watchdog has found fresh emails.

## When to use

- "Set up auto-reply for [person]"
- "I want Hermes to handle [person]'s emails automatically"
- "Ghostwriter for [new contact]"

## Architecture

```
Watchdog (no_agent, script only)
  every 5min → searches Gmail for VIP emails → writes to /tmp/ghostwriter_output.txt
  ├─ No match → silent exit → $0
  └─ Match → writes email data → $0 (still no LLM!)

Processor (no_agent, script only) — NEW in v2
  every 6min, offset by 1min → reads /tmp/ghostwriter_output.txt
  ├─ No file / stale file / no emails → silent exit → $0
  └─ Fresh emails found → spawns `hermes chat -q` → draft + send (~8K tokens)
```

### Why v2 changed the Processor

v1 used an LLM agent cron job with `context_from` pointing at the Watchdog. Even when there were no emails, the agent burned ~3,500 tokens just to read the empty context and respond ".".

v2 makes the Processor a no-agent Python script — same pattern as the Watchdog. The script reads the Watchdog's output file. No LLM is invoked until there's actual work to do.

**Token savings: ~97%.** From ~1M tokens/day wasted on empty ticks → 0 tokens when no email.

## Prerequisites

Google Workspace must be authenticated. Verify:
```bash
GAPI="$HOME/.hermes/hermes-agent/venv/bin/python3 $HOME/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
$GAPI gmail search "is:unread" --max 1
```

## Step-by-step setup

### 1. Copy and configure the scripts

Copy both scripts to `~/.hermes/scripts/`:

```bash
cp scripts/watchdog.py ~/.hermes/scripts/ghostwriter_watchdog.py
cp scripts/processor.py ~/.hermes/scripts/ghostwriter_processor.py
```

Edit `~/.hermes/scripts/ghostwriter_watchdog.py`:
```python
QUERY = 'from:vip@example.com is:unread'  # ← change to your VIP
```

Edit `~/.hermes/scripts/ghostwriter_processor.py`:
```python
RECIPIENT = "person@example.com"          # ← change to your VIP's email
VOICE_GUIDELINES = """..."""              # ← customize the reply voice
SIGNATURE = "<p>Cheers,</p><p>Name</p>"   # ← your name
```

### 2. Create the cron jobs

```bash
# Watchdog — zero tokens, script only
hermes cron create \
  --name "Ghostwriter Watchdog" \
  --schedule "0,5,10,15,20,25,30,35,40,45,50,55 * * * *" \
  --no-agent true \
  --script "ghostwriter_watchdog.py"

# Processor — zero tokens unless email found (NEW in v2)
hermes cron create \
  --name "Ghostwriter Processor" \
  --schedule "1,6,11,16,21,26,31,36,41,46,51,56 * * * *" \
  --no-agent true \
  --script "ghostwriter_processor.py"
```

> The processor fires 1 minute after the watchdog. Using explicit cron expressions guarantees they stay synchronized — `every 5m`/`every 6m` can drift apart.

### 3. Add standing rules (optional)

If using the `email-hq` skill, add the contact to standing rules:

```markdown
- **Name** (`email@domain.com`): Full autonomy — read, draft reply in user's voice, SEND directly. No preview. Never archive, never ignore.
```

## How the scripts work

### Watchdog (`watchdog.py`)

- **No matching emails:** Silent exit (exit 0, no stdout) → cron records nothing → $0
- **Matching emails found:** Fetches full content, writes to `/tmp/ghostwriter_output.txt` AND stdout — both paths so cron has a log AND processor has structured data
- **API errors:** Outputs error message, exits gracefully

### Processor (`processor.py`)

- **No /tmp/ghostwriter_output.txt:** Silent exit → $0
- **File older than 10 minutes:** Stale data → silent exit (already processed) → $0
- **File exists, fresh, but no "--- VIP EMAIL ---" block:** Silent exit → $0
- **Fresh VIP emails found:** Spawns `hermes chat -q` with full email context + voice guidelines → drafts reply → sends → archives → ~8K tokens

## Reply conventions

- Use `gmail send --html --thread-id` (NOT `gmail reply` — plain text gets mangled in Outlook)
- Mark original as read, then archive (two separate `gmail modify` calls — one label per invocation)
- Sign every reply with appropriate valediction

## Pitfalls

### `gmail modify` takes ONE label at a time
```bash
# Wrong — only the last --remove-labels takes effect:
$GAPI gmail modify ID --remove-labels UNREAD --remove-labels INBOX

# Correct — two separate calls:
$GAPI gmail modify ID --remove-labels UNREAD
$GAPI gmail modify ID --remove-labels INBOX
```

### Use `gmail send --html`, never `gmail reply`
`gmail reply` sends plain text that Outlook mangles. Always:
```bash
$GAPI gmail send --to "person@email.com" --subject "Re: Original" \
  --body "<p>Reply text.</p><p>Cheers,</p><p>Name</p>" --html --thread-id "<threadId>"
```

### Watchdog ThreadID output
The watchdog script outputs `ThreadID` — the processor needs it for `--thread-id` to maintain proper email threading.

### Watchdog + Processor timing
Use explicit cron expressions with a fixed 1-minute offset:
- Watchdog: `0,5,10,15,...`
- Processor: `1,6,11,16,...`

## Multiple VIPs

Duplicate BOTH scripts with different filenames and queries. Each VIP needs their own watchdog + processor pair with a unique output file (edit `OUTPUT_FILE` in both scripts).

## Cost (v2)

| Pattern | No-match cost/day | Per email |
|---------|------------------|-----------|
| Single agent polling every 5min | ~$0.30–0.50 | ~$0.002 |
| Ghostwriter v1 (LLM processor) | ~$0.03 | ~$0.002 |
| **Ghostwriter v2 (script processor)** | **~$0.00** | ~$0.002 |

When there are no emails, v2 burns zero LLM tokens — both Watchdog and Processor are pure Python. The LLM only wakes when there's actual work.

## Files

| File | What |
|------|------|
| `scripts/watchdog.py` | Watchdog script — edit Gmail query |
| `scripts/processor.py` | Processor script — edit voice + recipient |
| `references/processor-prompt.md` | Reference: the voice/format guide (used inline in processor.py) |
| `references/standing-rules.md` | Standing rules template |

## Changelog

**v2.0.0** — Processor changed from LLM agent (context_from) to no-agent script. Eliminates ~3,500 token burn per empty tick. ~97% token reduction on idle days.

**v1.0.0** — Initial release. Two-job architecture: no-agent watchdog + LLM agent processor.

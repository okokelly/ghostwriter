# Ghostwriter

Autonomous email management for Hermes Agent, running as **no-agent cron
scripts** so it costs **zero LLM tokens when idle**. It sorts your inbox into
two tiers:

1. **Tier 1 — auto-reply.** Unread mail from an address you manage (listed in
   `config.yaml`) gets a reply drafted in your voice and **sent automatically
   back to that same address** — never to an address chosen by the model. So
   it's safe to forward a third-party chain to the agent: the draft lands in
   *your* inbox for you to forward onward.
2. **Tier 2 — daily digest.** Everything else — newsletters, cold outreach,
   anyone not in your config — is rolled into one daily summary with priority
   scoring, delivered to your chat. Nothing to configure: if it isn't Tier 1,
   it's Tier 2, and your inbox stays quiet.

> Earlier versions (v1–v3) had a middle "draft → approve → send to a third
> party" tier. v4 dropped it (see *Design notes*), which is why the model is now
> just these two.

The LLM only wakes when there's real work. Empty inbox = every script exits
silently, no tokens spent.

```
Watchdog (every 5 min, no LLM)
  └─ searches Gmail for unread mail from your Tier 1 addresses
  └─ writes /tmp/ghostwriter_v4_trigger.json  (atomic)        ── nothing? exit silently

Processor (every 5 min, +1 offset, no LLM until work exists)
  └─ claims the trigger (rename-before-spawn → no double-send)
  └─ for each email:  LLM drafts the reply BODY only
                      Python appends the signature + SENDS to the config address
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
- **No double-send.** Three layers: a `flock` lock prevents overlapping ticks;
  the trigger is claimed (renamed) before the LLM runs, so a crash can't leave
  it to be reprocessed; and every successful reply records its message-id in
  `~/.ghostwriter/state/sent_ids.json`, so a message that gets re-listed while an
  earlier draft is still running is never replied to twice. A reply that
  genuinely fails to send is *not* recorded, so a later tick retries it.
- **No "approve and send to a third party" tier.** That middle tier was
  intentionally dropped — locked-to-self delivery gives the same
  human-in-the-loop for free: a reply to a forwarded chain lands in *your* inbox,
  and you forward it onward yourself. No approval machinery, no risk of the model
  emailing the wrong person.

> **Prerequisite: run the agent under a Gmail account that is _not_ one of your
> Tier 1 addresses.** The watchdog triggers on unread mail *from* a configured
> address and the processor replies *to* it. If the agent's mailbox is itself a
> Tier 1 address, each reply would re-trigger the watchdog — a reply loop. Keep
> them separate (you forward chains from your addresses into the agent's mailbox).

## Quick start

### 1. Prerequisites

Hermes Agent with Google Workspace configured. Verify the Gmail API works:

```bash
GAPI="$HOME/.hermes/hermes-agent/venv/bin/python3 $HOME/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
$GAPI gmail search "is:unread" --max 1
```

### 2. Configure your addresses

Copy the template and fill in **your own** address(es):

```bash
mkdir -p ~/.ghostwriter
cp config.example.yaml ~/.ghostwriter/config.yaml
$EDITOR ~/.ghostwriter/config.yaml      # or use the CLI — see below
```

Your real `config.yaml` holds your addresses and is gitignored — never commit
it. See `config.example.yaml` for every field. List one `tier: 1` entry per
mailbox you want auto-replied; anything not listed is Tier 2 (digest).

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
| `scripts/digest.py`     | Daily Tier 2 digest of unmanaged senders |
| `ghostwriter`           | CLI — `status` + contact management (see below) |
| `config.example.yaml`   | Config template — copy to `~/.ghostwriter/config.yaml` |
| `SKILL.md`              | Hermes skill definition |
| `references/`           | Voice / format reference notes |

## CLI

Manage contacts and check health. The cron pipeline reads `config.yaml`
directly and does **not** depend on this CLI — but the write commands rewrite
`config.yaml` via PyYAML, so manage that file with the CLI *or* by hand, not
both (comments aren't preserved on a CLI write).

```bash
chmod +x ghostwriter        # once; or symlink onto your PATH

./ghostwriter status                                   # tallies, dedup + trigger health
./ghostwriter add --name work --email me@work.com      # add a Tier 1 address you control
./ghostwriter edit --name work --signature "<p>Best,</p>"
./ghostwriter promote --email me@news.com --name news  # = add (e.g. from the digest)
./ghostwriter remove --name news
```

`status` output:

```
Contact  Email             Tier  Paused  Sent  Failed  Last sent
-------  ----------------  ----  ------  ----  ------  -------------------------
me       you@example.com   1     no      12    1       2026-06-30T09:01:22+00:00

Dedup: 12 message-id(s) tracked in sent_ids.json
Trigger: none pending
```

> **Only `add`/`promote` addresses you control.** A Tier 1 contact's reply is
> auto-sent to that contact's own address — handy for managing several of your
> own mailboxes, but adding someone else's address means auto-emailing a third
> party. `add`/`promote`/`remove` confirm first (`--yes` to skip). It's
> argparse-based, so more subcommands slot in easily.

## Cost

When the inbox is empty, every script is pure Python and exits without touching
an LLM — **$0/day idle**. The model is invoked only to draft a reply or build a
digest, i.e. only when there is real work.

## License

MIT

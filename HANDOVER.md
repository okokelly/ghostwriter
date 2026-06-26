# Ghostwriter CLI v3 — Handover Note

> Generated: 2026-06-26 | By: Amber (with Kelly) | Session: Telegram DM

> 🎯 **Scope of this version (v3):** Build Tier 1 (multi-contact auto-reply) and Tier 3 (daily digest) only. Tier 2 (the draft → approve → send mechanism) is deferred to v4, which is the next phase. Anything tagged `(deferred — v4)` below is design-only — do not build it now. The v3 design is settled except for the items flagged with "Kelly flagged this — verify" and "needs a design decision."

## What this is

Ghostwriter v3 is an opinionated CLI tool that manages your email relationships through a three-tier model. It replaces the v2 "one VIP = two scripts + two cron jobs" pattern with a single CLI that manages multiple contacts across three autonomy tiers. In v3, only Tier 1 (auto-reply) and Tier 3 (digest) ship; Tier 2 (approval) is deferred to v4.

## Where we left off

**v2 is running in production** for Kelly Jia (kellyjiashuyao@outlook.com) with minimal VIP coverage. It works. Don't break it.

**v3 design is settled**, except for the flagged open questions. We agreed on the three-tier model, CLI architecture, and phase plan. Still open: per-contact memory storage (Hard Problem #8) and the "Kelly flagged this — verify" items (#6 cron timing, #7 token budget). No code has been written for v3 yet. This folder contains a copy of v2 as reference/base.

## v3 Core Architecture

### Three-Tier Model

| Tier | Behavior | Use case |
|------|----------|----------|
| **Tier 1** | Fully autonomous: draft + send, zero friction | Your inner circle. Current v2 behavior. |
| **Tier 2** `(deferred — v4)` | Agent drafts → notify Kelly via Telegram → Kelly approves ("send" / "change X") → Agent sends | Important contacts: need quality control but not immediate |
| **Tier 3** | Never auto-reply. Daily digest: who emailed, one-line summary, AI priority score | Cold outreach, strangers, unknown |

### CLI Design (`ghostwriter`)

**Language:** Python (Hermes-native, zero extra deps). NOT Node/npm — we don't need agently-cli compatibility; we use Gmail API.

**Data model:** `~/.ghostwriter/config.yaml` (not SQLite — <50 contacts expected)

```yaml
contacts:
  - email: kelly@example.com
    name: kelly
    tier: 1
    voice: personal
    signature: "Cheers,\nKelly"
  - email: contact@example.com
    name: contact
    tier: 2
    voice: professional
    signature: "Best regards,\nKelly"
```

### Directory Structure

```
~/.ghostwriter/
├── config.yaml          # Source of truth — all contacts and tiers
├── state/               # Runtime state per contact (last_processed, stats)
│   ├── kelly.json
│   ├── contact.json
├── drafts/              # Tier 2 drafts awaiting approval
├── history/             # Conversation history (defer to v3.1)
└── cron/                # Generated cron configs (or just managed via hermes cron tool)
```

### CLI Commands

```bash
# Setup
ghostwriter init                          # Create ~/.ghostwriter/

# Contact management
ghostwriter add --email <email> --tier <1|2> --voice <name> [--signature "X"]
ghostwriter list                          # Table view: all contacts, tiers, status, stats
ghostwriter edit <name> --tier 2          # Change tier
ghostwriter pause <name>                  # Skip in cron ticks
ghostwriter resume <name>
ghostwriter remove <name>

# Tier 2 approval (deferred — v4)
ghostwriter pending                       # Show all pending drafts
ghostwriter approve <name> [--id <id>]    # Send
ghostwriter reject <name> [--id <id>]     # Discard

# Tier 3 digest
ghostwriter digest                        # Manual trigger (auto-scheduled at 9:00 daily)

# Stats
ghostwriter stats                         # Approval rate, emails processed, etc.
```

### Cron Architecture (runs via Hermes)

**One watchdog for all Tier 1+2 contacts:**

```
cron: watchdog.py (every 5min, no_agent=true)
  → Reads config.yaml
  → Searches Gmail for: (from:tier1_email1 OR from:tier1_email2 OR from:tier2_email1 ...) is:unread
  → Writes trigger file (JSON) with detected emails + their tiers

cron: processor.py (every 6min, no_agent=true, offset +1min)
  → Reads trigger file
  → For each email:
      Tier 1 → LLM draft + auto-send (current v2 behavior)
      Tier 2 → LLM draft → save to drafts/ → notify Kelly via Telegram (deferred — v4)

cron: digest.py (daily 9:00, no_agent=true)
  → Gmail search: is:unread -from:{all tier 1+2 emails}
  → LLM summary: per-sender summary + priority + recommendation
  → Push to Telegram
```

### Tier 2 Approval Flow (the hard part) — deferred to v4

```
processor cron tick → detect Tier 2 email
  → LLM drafts reply → writes drafts/<name>-<date>-<id>.txt
  → Amber (via Telegram): "New Tier 2 email from <name>. Draft ready. [show draft]"
  
Kelly: "send" / "change X"
  → If "send": ghostwriter approve → CLI sends via Gmail API directly
  → If "change": Amber revises draft → re-confirm → send
```

**CRITICAL DESIGN DECISION:** CLI must be able to send emails via Gmail API directly for Tier 2 approve. This means the send logic needs to be modularized — both processor.py (auto-send for Tier 1) and CLI (manual send for Tier 2) share the same send function. Otherwise format drift between auto and manual sends.

### Tier 3 Digest Flow

```
cron: digest.py (daily 9:00)
  → Gmail search: is:unread -from:{all tier1_emails} -from:{all tier2_emails}
  → LLM processes batch:
      For each sender: one-line summary, priority (🟢🟡🔴), category, recommendation
  → Push to Telegram as formatted message
  → Kelly responds: "reply to Mark Zhang" → Amber drafts → approve → send
                   "promote mzhang@vc.com --tier 2" → add to config.yaml
```

## Key Design Decisions (already made)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | CLI language | Python | Hermes-native, no extra deps. Don't need npm/agently-cli. |
| 2 | Data store | YAML config file | <50 contacts, SQLite overkill |
| 3 | Multi-round conversation state | DEFER to v3.1 | Kelly is the state engine (in the loop) |
| 4 | Tier 2 notification (v4) | Telegram only | Tier 2 is not urgent. No fallback needed. |
| 5 | Digest delivery | Push (daily 9am) + pull (manual `ghostwriter digest`) | Both, cost is identical |
| 6 | Tier promotion | Manual only | `ghostwriter promote <email> --tier 2`. No auto-suggestion until volume justifies it. |
| 7 | CLI approval sends directly (v4) | CLI calls Gmail API, not processor | Avoids 5-min cron delay on approval |

## Hard Problems (be ready for these)

### 1. Approval flow + cron model conflict (v4 — Tier 2 only)
Cron jobs run and exit. They can't "wait for approval." Solution: processor only drafts (never sends for Tier 2). CLI handles the actual send via `ghostwriter approve`. This means CLI needs direct Gmail API access.

### 2. Draft state machine (v4 — Tier 2 only)
A Tier 2 email goes through: `detected → drafted → notified → (edited? redrafted?) → approved → sent`. Each state must be on disk (state file) so crashes don't lose context. Edge cases:
- Same email detected twice by processor → must not create duplicate drafts
- Sending fails → state must roll back to "drafted", not get lost
- Kelly ignores notification for days → drafts pile up → need cleanup/presentation logic

### 3. Processor from singleton to multi-tenant
Current processor.py (77 lines) handles ONE contact. v3 must:
- Read config.yaml to know all contacts
- Match sender against config
- Dispatch to correct voice/tier behavior
- This is a near-complete rewrite of processor.py

### 4. CLI ↔ Cron sync
When user runs `ghostwriter add`, CLI must update Hermes cron jobs. `ghostwriter pause` must pause the right cron. We have the `cronjob` tool in Hermes, but need to ensure CLI operations never leave cron in an inconsistent state.

### 5. Testing feedback loop
Tier 2 requires real emails to test end-to-end. Designing a dry-run / test mode will save hours.

### 6. Cron timing with multi-tenant

**Kelly flagged this — verify before implementing.** Current v2 uses watchdog at minutes 0,5,10... and processor at 1,6,11... (1-minute offset). The offset works because watchdog writes to `/tmp/ghostwriter_output.txt` and processor reads it. For v3 multi-tenant: same pattern holds — one watchdog per tick, one trigger file, one processor tick. The 1-minute offset should still be sufficient. BUT: the watchdog now has a more complex Gmail query (multiple `from:` clauses). Verify the query doesn't slow down enough to miss the offset window.

### 7. Token budget: don't reintroduce the v2 mistake

**Kelly flagged this — critical.** v2's key innovation: both watchdog and processor are `no_agent=true` scripts → $0 on empty ticks. The v1 processor was an LLM cron job burning ~3,500 tokens per empty tick. v3 MUST preserve $0 idle:

| Component | Idle cost | Active cost | Notes |
|-----------|-----------|-------------|-------|
| watchdog.py | $0 | $0 | Pure Python, no LLM |
| processor.py | $0 | ~$0.002/email | LLM only when emails detected |
| digest.py | $0 | ~$0.01/day | LLM batch once daily (intentional) |

**Do not wrap processor.py or digest.py in an LLM agent cron job.** They stay `no_agent=true` scripts that spawn LLM only when work exists.

### 8. Where to store per-contact memories

**Kelly's question — needs a design decision.** Contacts accumulate context over time: preferred tone, past topics, specific details Kelly mentioned in approval feedback. Where does this live?

Options:
- **A: state/<name>.json** — Add a `memory` field. Simple, co-located with stats. But JSON is not great for free-form notes.
- **B: state/<name>.md** — Separate markdown file per contact. Agent reads/updates. More natural for prose.
- **C: config.yaml notes field** — Inline, visible when editing config. But clutters the config file.

**Recommendation: B.** `state/<name>.md` — one markdown file per contact. Agent reads before drafting, updates after Kelly's feedback. Lightweight, human-readable, Agent-editable.

## Phase Plan

### Phase 1: CLI + Tier 1 (est. 1 day)
- [ ] Design `~/.ghostwriter/` directory structure and config.yaml schema
- [ ] Implement `ghostwriter init/add/list/pause/resume/remove`
- [ ] Migrate existing v2 Tier 1 contacts into CLI
- [ ] Rewrite processor.py to read config.yaml (multi-tenant)
- [ ] **Tier 1 behavior = v2 behavior** (no approval flow yet)

### Phase 2: Tier 3 Digest (est. 1 day)
- [ ] `digest.py` cron job (daily 9am)
- [ ] LLM batch processing: Gmail search strangers → summary + priority
- [ ] Telegram push
- [ ] `ghostwriter digest` manual trigger
- [ ] `ghostwriter promote <email> --tier 1` (Tier 2 promotion lands in v4)

### v4 (next phase): Tier 2 Approval — deferred

**Not in scope for v3.** Captured here so the design isn't lost. Build only after v3 (Tier 1 + Tier 3) is stable in production.

- [ ] Processor detects Tier 2 emails → drafts → saves to `drafts/`
- [ ] Amber notifies Kelly via Telegram with draft content
- [ ] `ghostwriter pending/approve/reject` commands
- [ ] Modularize Gmail send logic (shared between processor + CLI)
- [ ] State machine for draft lifecycle
- [ ] **Resolve first:** how does Kelly's Telegram "send" / "change X" route back to `ghostwriter approve` without an always-on LLM listener? (See "Tier 2 Approval Flow" above — this is the load-bearing open question.)

## Files to extend/rewrite

| File | v2 role | v3 fate |
|------|---------|---------|
| `scripts/watchdog.py` | One VIP query | Rewrite: multi-contact from config.yaml |
| `scripts/processor.py` | One VIP auto-reply | Major rewrite: tier dispatch + draft mgmt |
| `scripts/digest.py` | — | NEW: Tier 3 daily digest |
| `SKILL.md` | Skill definition | Update for v3 |
| `README.md` | v2 docs | Replace with v3 docs |
| `references/` | Voice refs | Keep, add tier-specific voice templates |

## Context to load in new session

When starting a new session on this:
1. This HANDOVER.md (obviously)
2. `SKILL.md` — understand the v2 skill definition
3. `scripts/processor.py` — understand current auto-reply logic
4. `scripts/watchdog.py` — understand current Gmail polling pattern
5. The email we sent to Kelly (kellyjiashuyao@outlook.com, subject: "Ghostwriter v2 → v3 — jinqiu 对比 + 三层模型 + CLI Workflow + 行动计划") — contains full design rationale

## Key context: who's who

- **Kelly Jia = the human** (kellyjiashuyao@outlook.com).
- **Amber = the AI agent** — runs on Hermes, executes ghostwriter operations. Never use "Amber" in public-facing work (emails sent by ghostwriter come from Kelly).
- Gmail account for ghostwriter API operations: amber.jia.1024@gmail.com
- Gmail API path: `~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/skills/productivity/google-workspace/scripts/google_api.py`
- Communication: Kelly ↔ Amber via Telegram DM

## Voice & signature

- Voice: warm, direct, no AI-isms, contractions, natural American English
- **Tier 1 signature:** `"Cheers,\nKelly"` (warm, casual, inner circle)
- **Tier 2 signature:** `"Best regards,\nKelly"` (polished, professional)
- The signatures are intentionally different — do not unify them

## What NOT to do

- Don't introduce npm/Node.js dependency — we chose Python deliberately
- Don't add multi-round conversation state (conversation.md) — deferred to v3.1
- Don't break the existing v2 cron jobs — they're running in production
- Don't make Tier 2 auto-send — approval must be explicit
- Don't use file-based IPC for the approval flow (we tried that lesson from jinqiu) — use Telegram conversation instead
- Don't over-engineer — v3 MVP should be simple enough that Kelly can explain it in one sentence

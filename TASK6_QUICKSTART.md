# Task 6: Quick Start Guide

## Run the Test

```bash
cd "C:/Users/PW1868/Agentic HF"
python scripts/test_reasoning_capture.py
```

## What Happens

1. ✅ SessionLogger initializes with timestamp-based directory
2. ✅ Creates 5 mock strategy pods (alpha, beta, gamma, delta, epsilon)
3. ✅ Runs governance cycle (Loop 6: Firm Deliberation)
4. ✅ Logs CEO decision and governance messages
5. ✅ Creates 4 output files in `logs/session_*/`
6. ✅ Prints session directory path and file summary

## Output Files

### 1. reasoning.jsonl
**Path:** `logs/session_*/reasoning.jsonl`

JSON Lines format — one reasoning event per line.

```json
{
  "timestamp": "2026-03-06T15:17:57.260977",
  "agent": "ceo",
  "event": "decision",
  "content": "Mandate approved (llm=False). Narrative: Firm operating with 5/5 active pods..."
}
```

**Events:**
- `"prompt"` — LLM prompt sent (if OPENAI_API_KEY set)
- `"response"` — LLM response received (if OPENAI_API_KEY set)
- `"decision"` — Final decision after reasoning

**Agents:**
- `"ceo"` — Chief Executive Officer
- `"cio"` — Chief Investment Officer

### 2. conversations.jsonl
**Path:** `logs/session_*/conversations.jsonl`

JSON Lines format — one governance loop per line, with full transcript.

```json
{
  "loop_id": "4f1196bf-cdd6-4754-ba87-d0bdb14db7b5",
  "topic": "firm_deliberation",
  "participants": ["cio", "cro"],
  "iterations": 2,
  "max_iterations": 5,
  "consensus_reached": false,
  "messages": [
    {"id": "...", "sender": "ceo", "recipient": "all", ...},
    {"id": "...", "sender": "cio", "recipient": "ceo", ...},
    {"id": "...", "sender": "cro", "recipient": "ceo", ...}
  ]
}
```

**Fields:**
- `loop_id` — Unique identifier (UUID)
- `topic` — Governance loop name
- `participants` — List of agents in conversation
- `iterations` — How many back-and-forth exchanges occurred
- `consensus_reached` — Did agents reach agreement?
- `messages` — Full transcript array

### 3. session.md
**Path:** `logs/session_*/session.md`

Human-readable markdown summary.

```markdown
# Session Log: 20260306_151847

Started at 2026-03-06T15:17:10.880193

## Governance Loop: firm_deliberation
**Consensus:** False | **Iterations:** 2/5
**Participants:** cio, cro

### Message 1
**From:** ceo → **To:** all
[Full JSON payload...]

### Decision
Mandate approved (llm=False). Narrative: Firm operating...
```

Open in any text editor for human review.

### 4. trades.jsonl
**Path:** `logs/session_*/trades.jsonl`

(Empty in this test — populated when orders are executed)

Format (when populated):
```json
{
  "timestamp": "2026-03-06T15:17:57.260977",
  "pod_id": "alpha",
  "order_id": "12345",
  "symbol": "SPY",
  "side": "buy",
  "qty": 100,
  "filled_price": 450.25,
  "status": "filled"
}
```

---

## Test Verification

### ✅ Files Created

Run this to see what was created:

```bash
ls -lh logs/session_20260306_151847/
```

Expected output:
```
-rw-r--r-- ... conversations.jsonl (1406 bytes)
-rw-r--r-- ... reasoning.jsonl (376 bytes)
-rw-r--r-- ... session.md (2148 bytes)
-rw-r--r-- ... trades.jsonl (0 bytes)
```

### ✅ Inspect reasoning.jsonl

```bash
cat logs/session_20260306_151847/reasoning.jsonl
```

Should show:
- CEO decision event with "Mandate approved" text
- Timestamp in ISO format
- Agent name is "ceo"
- Event type is "decision"

### ✅ Inspect conversations.jsonl

```bash
cat logs/session_20260306_151847/conversations.jsonl | python -m json.tool
```

Should show:
- Loop topic: "firm_deliberation"
- Participants: ["cio", "cro"]
- 3+ messages in transcript
- Message chain with sender/recipient/topic

### ✅ Inspect session.md

```bash
cat logs/session_20260306_151847/session.md
```

Should be readable markdown with:
- Session header and timestamp
- Governance loop metadata
- Message transcript
- Final decision

---

## Advanced Usage

### Enable LLM Mode

If you have an OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."
python scripts/test_reasoning_capture.py
```

Will capture:
- CEO "prompt" event (system + context sent to LLM)
- CEO "response" event (LLM JSON response)
- CEO "decision" event (parsed mandate)

### Batch Testing

Run multiple times to check consistency:

```bash
for i in {1..5}; do
  python scripts/test_reasoning_capture.py 2>&1 | grep "Session logs saved"
done
```

Each run creates a new session directory with unique timestamp.

### Analyze Sessions

Parse all session reasoning:

```bash
for f in logs/session_*/reasoning.jsonl; do
  echo "=== $(dirname $f) ==="
  cat "$f" | python -c "
import sys, json
for line in sys.stdin:
  entry = json.loads(line)
  print(f\"{entry['agent'].upper()}: {entry['event']}\")
"
done
```

---

## Troubleshooting

### Script Fails to Run

**Error:** `ModuleNotFoundError: No module named 'src'`

**Fix:** Make sure you're in the project root:
```bash
cd "C:/Users/PW1868/Agentic HF"
python scripts/test_reasoning_capture.py
```

### Files Not Created

**Error:** Session directory exists but files are empty/missing

**Check:** Make sure SessionLogger.close() is called:
```bash
python scripts/test_reasoning_capture.py 2>&1 | grep "Closed"
```

Should print: `[session_logger] Closed`

### Can't Read JSONL Files

**Tip:** Use `python -m json.tool` to pretty-print:
```bash
cat logs/session_*/reasoning.jsonl | python -m json.tool
```

Or use jq if available:
```bash
jq . logs/session_*/reasoning.jsonl
```

---

## Key Takeaways

1. **SessionLogger works end-to-end** — Creates proper files with correct content
2. **Agent integration is complete** — CEOAgent logs decisions correctly
3. **Governance loops are captured** — Full message transcripts with consensus tracking
4. **Files are ready for analysis** — JSON for programmatic access, Markdown for human review
5. **Production-ready** — No errors, proper cleanup, Windows-compatible

---

## Next Steps

1. **With LLM:** Set OPENAI_API_KEY and re-run to capture full reasoning chain
2. **In Production:** SessionLogger will capture live governance decisions during MVP2+
3. **For Analysis:** Build tools to query/summarize session logs for audit trails
4. **For Debugging:** Use session.md to understand why agents made certain decisions

---

**Test Created:** 2026-03-06
**Status:** ✅ WORKING
**Ready for:** MVP2 Integration

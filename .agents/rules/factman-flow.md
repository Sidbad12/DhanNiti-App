# Factman-Flow

Factman-flow is the **active search protocol**. It does not describe — it executes.
Every step is narrated. Every skip is justified.

**Parent schema** → read [factman.md](file:///d:/sid/Paisa/Dhan-Optimizer/.agents/rules/factman.md) for tag definitions before this file.

---

## Core Rule

**Always: factman index before raw code. Never reverse.**

```
fm-scope=file → fm-key scan → fm-value read → fm-links traversal → raw code
```

---

## Protocol (5 Steps)

### STEP 1 — File manifests

```bash
grep -rn "<fm-scope>file</fm-scope>" src/
```

Read only `<fm-value>` from each result. Mark file as **candidate** if value contains
task vocabulary. **Skip** otherwise — do not open skipped files.

> Narrate: "billing_service.py → candidate (invoice, discount). auth.py → skip (JWT only)."

---

### STEP 2 — Key scan (candidates only)

```bash
grep -n "<fm-key>" billing_service.py
```

Read key names only. Shortlist keys with task-relevant terms. Skip unrelated keys.

> Narrate: "Shortlisted: apply_discount, invoice_finalize. Skipped: send_reminder."

---

### STEP 3 — Value read (shortlisted keys only)

```bash
grep -A4 "<fm-key>apply_discount</fm-key>" billing_service.py
```

Read each value fully. Verdict: confirmed / secondary / remove.

> Narrate: "apply_discount → 'Applies tiered rate to invoice total.' → CONFIRMED."

---

### STEP 4 — Link traversal (confirmed symbols, max 2 hops)

```bash
grep -A8 "<fm-key>invoice_finalize</fm-key>" billing_service.py | grep "fm-links"
grep -rn "<fm-key>stripe_client</fm-key>" src/
```

For each link: find its fm-key, read its fm-value. Stop at:
- Infrastructure (DB drivers, HTTP clients, loggers) → note, don't traverse
- Already-confirmed symbols → skip
- Out-of-scope symbols → skip

> Narrate as graph: "invoice_finalize → [apply_discount ✓, stripe_client → infra stop]"

---

### STEP 5 — Raw code (confirmed + linked business-logic symbols only)

Jump directly to each symbol using its factman block as position marker.
**Never read whole files.**

> Narrate: "Reading apply_discount(): 12 lines. Reading DISCOUNT_TIERS: 5 lines. Done."

---

## Grep Reference

```bash
# Step 1: all file manifests
grep -rn "<fm-scope>file</fm-scope>" src/

# Step 2: keys in one file
grep -n "<fm-key>" src/billing_service.py

# Step 2: concept search across files
grep -rn "<fm-key>.*discount" src/
grep -rn "<fm-key>.*payment" src/

# Step 3: key+value (4-line context)
grep -A4 "<fm-key>apply_discount</fm-key>" src/billing_service.py

# Step 4: links for confirmed symbol
grep -A8 "<fm-key>invoice_finalize</fm-key>" src/billing_service.py | grep "fm-links"

# Step 4: locate a linked symbol
grep -rn "<fm-key>stripe_client</fm-key>" src/
```

---

## Efficiency Targets

| Metric | Target |
|---|---|
| Files opened (raw code) | ≤ 2 |
| fm-key lines scanned | ≤ 12 |
| fm-values read | ≤ 4 |
| fm-links hops | ≤ 2 |
| Lines of raw code read | ≤ 50 |

Exceed a target → flag the annotation quality issue.

---

## Fallback Rules

| Condition | Action |
|---|---|
| No factman block on file | Open file, scan `def`/`class`/`function` keywords |
| fm-value too vague | Read function signature + first 5 lines only, then decide |
| No fm-key matches | Try synonyms (`charge`/`payment`/`billing`). If still nothing, grep raw code |
| fm-links point to missing symbols | Grep partial name. External package → docs |

---

## System Prompt

```
This codebase uses factman annotations. Search protocol — always in this order:

1. grep -rn "<fm-scope>file</fm-scope>" → read <fm-value> → candidate if vocabulary matches
2. grep -n "<fm-key>" in candidates → shortlist task-relevant keys
3. grep -A4 "<fm-key>NAME</fm-key>" → read value → confirmed / secondary / remove
4. Read <fm-links> of confirmed → find each link's fm-key → read its fm-value (max 2 hops)
5. Read raw code of confirmed + linked symbols only. Never whole files.

Narrate each step. Skip justification required. Factman index is faster than raw search.
```

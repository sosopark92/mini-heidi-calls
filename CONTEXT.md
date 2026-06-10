# CONTEXT.md — Mini Heidi Calls: Voicemail Briefing Tool for GP Receptionists

---

## 1. What We Are Building and Why

**Project:** Mini Heidi Calls — Intelligent Voicemail Triage
**Challenge:** Heidi Health Forward-Deployed Engineer — Project 2

Harbour to Sunset GP is a multi-location clinic with high inbound call volume and limited front desk capacity. Admin staff arrive each morning to dozens of unstructured voicemail recordings with no sense of urgency, no intent summary, and no clear next action.

**The brief is explicit:**

> "This is not an audio problem. It is a workflow and information problem."

The system we are building answers one question on behalf of every admin who arrives at 7:30 AM:

> "Of everything that came in overnight — what do I do first, what can wait, and what needs a human to look at before acting?"

It is a **morning briefing system** that turns unstructured recordings into a prioritised, grouped, actionable workflow — while keeping human judgement in the loop wherever confidence is low or clinical risk is present.

---

## 2. Core Design Decisions (and the reasoning behind each)

### 2.1 "Morning Handover" as the product frame

Most voicemail tools present a list. Admin staff then read each item one by one, mentally triaging as they go. This forces every person to do the same cognitive work the system could do once.

Reframe the product: instead of a list, the system produces a **briefing**. When an admin opens the dashboard, the highest-priority decisions are already surfaced. Routine items are already grouped. Items the AI cannot confidently handle are already flagged.

This is the design principle that everything else serves.

### 2.2 Batch by Intent, Not by Time

Standard voicemail UX is chronological. This causes constant context-switching: a prescription request, then a medication concern, then a reschedule, then another prescription. Every item requires a different mental mode and a different action.

The insight is that admin work is naturally batchable. Prescription requests all follow the same handling steps. Appointment reschedules all require the same system access. If these are grouped, staff can complete all items of one type before switching to the next, which is faster and less error-prone.

**This is the core workflow insight that separates this system from a summariser.** A summariser still leaves triage to the human. This system does the triage first.

```
❌ Standard approach:  voicemail_1 → voicemail_2 → voicemail_3 → ...
                       (context switch on every item)

✅ This system:       Urgent callbacks (2)       → attend first
                       Prescription requests (3)  → handle together
                       Appointment changes (4)    → handle together
                       Needs review (2)           → human decision required
```

### 2.3 LLM-First Safety Architecture

Keyword matching was the original Stage 1 approach, but it has a fundamental flaw: it requires constant manual updates and fails on indirect language.

"My chest was feeling tight last night" contains no emergency keyword — but it is a symptom that warrants attention. "I've been feeling really off" likewise. Keyword lists cannot cover the infinite ways patients describe symptoms.

The system uses a 2-stage LLM approach:

- **Stage 1 (LLM binary screen):** A single fast LLM call asks one question: does this transcript contain any clinical concern? Answer: YES or NO only. `temperature=0.0` for consistency across runs. Max 5 output tokens — effectively free. This is the gate.
- **Stage 2 (LLM context check):** Only runs when Stage 1 returns YES. Determines whether the concern is current or resolved, and returns one of three safety states: ACTIVE / WATCH / ROUTINE.

This is cheaper to maintain, more reliable on real-world language, and catches indirect expressions that keyword rules miss. For a 30-voicemail morning, Stage 1 costs approximately 0.1 cents in API calls.

### 2.4 Confidence is Computed, Not Asked For

Asking an LLM to rate its own confidence produces an unreliable number. The LLM does not know what it does not know — it will confidently return 0.9 on a transcript that is ambiguous.

Instead, confidence is calculated from observable signals in the extraction output:

```python
def calculate_confidence(task: VoicemailTask) -> float:
    score = 0.0

    if task.callback_number:                          score += 0.25  # Did CLI capture a number?
    if any(i != "unclear" for i in task.intents):     score += 0.25  # Do we know why they called?

    word_count = len(task.transcript.split())
    if word_count >= 20: score += 0.25  # Is there enough content to work with?
    if word_count >= 50: score += 0.25  # Is the message substantive?

    return round(score, 2)

# Decision threshold
if confidence < 0.6:
    needs_review = True
```

This means:

- A caller with a confirmed callback number, a clear intent, and a substantive transcript scores 1.0 — no review needed.
- A caller with no callback number and an ambiguous, short message scores 0.15 — flagged immediately.
- The system can explain exactly why it flagged something, because the score components are inspectable.

---

## 3. Architecture

```
Voicemail audio / transcript
            │
            ▼
    ┌───────────────────────┐
    │  1. ASR Layer         │  Groq Whisper API
    │                       │  Converts audio → transcript
    │                       │  Skip if transcript already exists
    └──────────┬────────────┘
               │
               ▼
    ┌───────────────────────┐
    │  2. Safety Layer      │  Stage 1: LLM binary screen (YES/NO)
    │                       │  Stage 2: LLM context check (nuanced)
    │                       │  Output: ACTIVE / WATCH / ROUTINE
    └──────────┬────────────┘
               │
               ▼
    ┌───────────────────────┐
    │  3. LLM Extraction    │  Groq LLaMA-3.3-70b
    │                       │  Structured JSON: intent, urgency,
    │                       │  summary, next_step, missing_info,
    │                       │  needs_review
    └──────────┬────────────┘
               │
               ▼
    ┌───────────────────────┐
    │  4. Confidence Scorer │  Computed from extraction signals
    │                       │  < 0.6 → needs_review = True
    └──────────┬────────────┘
               │
               ▼
    ┌───────────────────────┐
    │  5. Policy Router     │  clinic_policy.yaml
    │                       │  Maps intent + urgency → branch + role
    └──────────┬────────────┘
               │
               ▼
    ┌───────────────────────┐
    │  6. Task Grouper      │  Groups by intent for batch handling
    │                       │  Orders by urgency within groups
    └──────────┬────────────┘
               │
               ▼
    ┌───────────────────────┐
    │  7. Dashboard         │  Streamlit — morning briefing UI
    │                       │  Cards, detail view, status tracking,
    │                       │  simulation mode
    └───────────────────────┘
```

Each layer has a single responsibility. If the LLM changes or the policy YAML is updated, only that layer is affected. This also makes testing straightforward — each component can be tested in isolation.

---

## 4. Safety Layer (2-Stage)

### Why 2 Stages

A single LLM call that classifies everything at once has a specific failure mode: it tries to do too much in one step. By splitting into two focused calls, each stage has a single, clear responsibility.

- **Stage 1** answers: *is there any clinical concern at all?* (binary, cheap)
- **Stage 2** answers: *how serious is it and is it current?* (nuanced, only when needed)

This also controls cost — Stage 2 only runs when Stage 1 flags something. For a typical morning with 30 voicemails, Stage 2 might run for 3–5 of them.

### Stage 1 — LLM Binary Screen

A single fast LLM call asking one question: does this transcript contain any medical or emotional concern?

```
Input:  transcript
Output: YES | NO
Cost:   ~5 output tokens per call — effectively free
```

```python
prompt = """Does this caller describe ANY current or recent medical symptom,
concern, or emotional distress that would require prompt attention?
Answer YES or NO only.
- YES = any concern, even indirect or downplayed
- NO  = purely administrative (appointment, script, results, billing)"""
```

This replaces keyword matching. Keyword matching fails on indirect language:
- "tightness in my chest" → no keyword match, but LLM returns YES
- "I've been feeling really off" → no keyword match, but LLM returns YES
- "my chest was tight last night" → LLM returns YES, Stage 2 determines WATCH

`temperature=0.0` gives consistent results across runs.

### Stage 2 — LLM Context Check

Triggered only when Stage 1 returns YES. Determines the nature and urgency of the concern.

The LLM is asked three questions internally:

1. Is this symptom current or past/resolved?
2. Is the caller describing themselves or someone else?
3. Does the caller show signs of distress or urgency?

Output is one of three safety states:

| State     | Meaning                                                                            | Effect on urgency |
| --------- | ---------------------------------------------------------------------------------- | ----------------- |
| `ACTIVE`  | Concern is current — caller needs prompt attention                                 | Forces `critical` |
| `WATCH`   | Caller reports concern has passed — not clinically confirmed, GP should be informed | Minimum `high`   |
| `ROUTINE` | No genuine concern despite Stage 1 flag (false positive)                           | No effect         |

The safety state is stored on the task and shown in the detail view so admin staff can see exactly why something was flagged.

### Calibration for GP Clinical Context

In a typical GP clinic, **"Attend first" will be empty most mornings** — that is the expected and correct outcome, not a failure mode. The safety layer exists not because urgent cases are common, but because a single missed vulnerable patient among thirty routine calls is unacceptable.

The cost is asymmetric. A false positive — over-flagging a call — costs an admin thirty seconds. A false negative — a patient with a medication crisis buried in a list of appointment reschedules — costs far more. The architecture reflects this: Stage 1 is deliberately sensitive, Stage 2 resolves false positives before they reach the dashboard.

An empty "Attend first" group is a confirmed outcome, not a blank space. The system ran, checked every transcript, and found nothing requiring urgent attention. Staff should be able to trust that conclusion rather than re-triage manually to verify it.

---

## 5. LLM Structured Extraction

### What the LLM Does (and Does Not Do)

The LLM's job is extraction and interpretation — not decision-making. It reads the transcript and returns a structured object. All routing, confidence scoring, and grouping decisions happen in deterministic code outside the LLM.

This is deliberate. LLM output is probabilistic. Clinical routing decisions should not be. The LLM populates the data; the rules act on it.

### Prompt Contract

The LLM receives: `transcript + safety_state + intent taxonomy`

It returns:

```json
{
  "intents": ["primary intent", "additional intent if any"],
  "urgency": "critical | high | normal | low",
  "urgency_reason": "one sentence explaining the urgency classification",
  "summary": "1-2 sentences covering ALL reasons for the call — not a verbatim transcript",
  "needs_review": true,
  "review_reason": "why the AI cannot act confidently, or empty string"
}
```

`next_step` is not LLM-generated. After extraction, `next_step_router.py` maps (urgency, safety_state, intents) to a fixed set of clinic-approved receptionist actions — drawn from what receptionists actually do (call back immediately, book same-day, leave GP message, process script, etc.). This eliminates hallucination risk and ensures actions stay within the bounds of what a receptionist can actually carry out.

Note: `caller_type` is collected via IVR keypress before the voicemail is recorded. `callback_number` is captured automatically by CLI (Calling Line Identification) — the network transmits the caller's number without any keypad entry. Neither is extracted by the LLM.

Note: `confidence` is not in the LLM output. It is calculated separately in `confidence.py` from the values returned here.

---

## 6. Intent Taxonomy

### Why a Fixed Taxonomy

An open-ended intent field ("what does the caller want?") produces inconsistent labels. "Needs a prescription" and "script repeat request" and "medication refill" all mean the same thing but would never group correctly.

A fixed taxonomy with 9 categories covers the realistic scope of GP clinic voicemails. The LLM is instructed to list ALL that apply, most important first — callers often have more than one reason for calling. If intent cannot be determined, it returns `["unclear"]`.

```python
INTENT_TAXONOMY = {
    "prescription_repeat":    "Repeat script — no new clinical concern",
    "appointment_booking":    "New appointment request",
    "appointment_reschedule": "Change or cancel existing appointment",
    "test_results":           "Chasing pathology, imaging, or other results",
    "medication_concern":     "Side effect, dosing question, or supply issue",
    "referral_request":       "Patient requesting a specialist referral, OR a healthcare provider following up on a referral",
    "complaint":              "Complaint requiring manager or GP review",
    "general_enquiry":        "Opening hours, location, billing, other admin",
    "unclear":                "Insufficient information to classify",
}
```

Each intent maps to a routing target in `clinic_policy.yaml`.

### Dashboard Layout

The dashboard has two view modes:

**Full view** — a flat sorted table with all fields. Useful for searching across everything.

**Workflow view** — tasks grouped by what to do, not just by urgency level. This is the primary mode for the morning briefing.

```
🚨 Attend First          critical urgency → call immediately
📞 Call Back Today        high urgency    → GP review first, then call
⚠️ Needs GP Review        low confidence  → human decides before any action
💊 Repeat Scripts         prescription_repeat intent
📅 Appointments           appointment_booking / reschedule intent
📋 Admin & Other          normal urgency, everything else
⚪ Low Priority / Unclear  low urgency, catch-all
```

**Why this over a flat sorted list:**

A sorted list still forces context-switching. A critical item, then a prescription repeat, then an appointment change — each requires a different mental mode and different system access. Grouping by action type allows staff to complete all items of one type before moving to the next. Repeat scripts are all processed together. Appointments are all booked together. This is faster and less error-prone.

A staff member who arrives at 7:30 AM sees the number of items in each group before reading any individual task. Two items in "Attend First" and zero items in "Needs GP Review" is a completely different morning than two items in each.

Location tabs (Harbour / Sunset / All) allow a receptionist to work through their own branch first before handling the other location's calls.

---

## 7. Clinic Policy Routing

### Why YAML and Not Hardcode

Clinic policies change. A new branch opens. A doctor goes on leave. The on-call arrangement changes. If routing logic is hardcoded in Python, a non-technical clinic manager cannot update it. If it is in a YAML file, they can.

This also demonstrates product thinking: the system is designed to be maintained by the people who use it, not just the people who built it.

```yaml
clinic:
  name: Harbour to Sunset GP

roles:
  gp:             "GP — review before callback"
  practice_nurse: "Practice Nurse"
  clinic-manager: "Clinic Manager"
  admin:          "Admin"

routing_rules:
  - match: {urgency: critical}         → gp
  - match: {safety_state: [ACTIVE, WATCH]} → gp
  - match: {urgency: high}             → gp
  - match: {any_intent: medication_concern} → gp
  - match: {any_intent: referral_request}   → gp
  - match: {any_intent: test_results}       → gp
  - match: {any_intent: complaint}          → clinic-manager
  - match: {any_intent: appointment_booking} → practice_nurse
  - match: {any_intent: prescription_repeat} → practice_nurse
  - default                            → admin
```

Rules are evaluated in order. First match wins. This means a high-urgency appointment request goes to GP (urgency rule fires first), not Practice Nurse (intent rule would fire later).

**Practice Nurse routing:** In Australian GP clinics, practice nurses run nurse-led clinics for immunisations, chronic disease management reviews, wound care, and health assessments. These do not require GP involvement to book — the nurse coordinates directly. Prescription repeats flow through the practice nurse for processing, then to the GP for authorisation sign-off.

Routing is role-based, not branch-based — both clinic locations use the same staff types. `task.location` records which branch received the call; `task.assigned_to` records which role should handle it.

---

## 8. Failure Cases (Explicit Handling)

### Why Failure Cases Must Be Explicit

A system that silently misclassifies a voicemail is worse than one that admits uncertainty. If admin staff cannot trust that a "normal" item is genuinely normal, they will check everything manually — which defeats the purpose.

Every failure mode must be detected, labelled, and surfaced honestly. This is the basis of trust.

| Failure case              | Detection method                       | System behaviour                                                     |
| ------------------------- | -------------------------------------- | -------------------------------------------------------------------- |
| No speech / pocket dial   | `word_count < 5`                       | `urgency=low`, `needs_review=True`, "No audible message detected"    |
| No callback number        | `callback_number=null`                 | `needs_review=True`, review_reason set                               |
| Cutoff transcript         | No terminal punctuation + short length | `needs_review=True`, "Transcript may be incomplete"                  |
| Distressed / angry caller | Sentiment signal in transcript         | Urgency bumped to `high` minimum, note appended                      |
| Non-English voicemail     | Language detection                     | `needs_review=True`, "Non-English content detected"                  |
| LLM extraction fails      | Exception caught in pipeline           | `needs_review=True`, "Extraction error — review transcript manually" |

---

## 9. Mock Data

### Why Specific Coverage Matters

Mock data is not filler. It is the test suite for the triage logic. The 20 records cover every routing path, every role assignment, and the key edge cases the safety layer must handle correctly.

`data/mock_voicemails.csv` — 20 records:

| Category | Count | Assigned to | Example |
|---|---|---|---|
| Critical / ACTIVE | 2 | GP | Chest pain, unrelieved angina spray; severe low mood |
| High / WATCH | 3 | GP | Resolved chest tightness (cardiac history); child fever; Warfarin running out |
| Medication concern | 1 | GP | Metformin side effect query |
| Test results chasing | 1 | GP | Blood test results not received |
| Referral follow-up | 1 | GP | Specialist requesting clinical notes |
| Prescription repeat | 3 | Practice Nurse | Levlen, Perindopril, Rosuvastatin |
| Appointment booking | 3 | Practice Nurse | Flu vaccination; wound check; diabetes review |
| Appointment reschedule | 1 | Admin | Cannot make Thursday appointment |
| Complaint | 1 | Clinic Manager | Wait time complaint |
| General enquiry | 2 | Admin | Long weekend hours; bulk billing |
| Unclear / pocket dial | 2 | (needs_review) | No callback number; no speech |

**Key design decisions in the mock data:**

- Critical records use natural, indirect language ("I've been feeling really off", "just can't go on") — not "I am having a medical emergency". This tests that the safety layer catches real patient language.
- WATCH records involve resolved symptoms with relevant history — the system must distinguish "chest pain happening now" from "chest pain last night that went away".
- Practice Nurse cases use appointment types that genuinely belong to nurse-led clinics: vaccination, wound care, chronic disease management. These are direct bookings — no GP involvement required.
- Warfarin running out is routed to GP (not Practice Nurse) despite being medication-related — the WATCH safety state fires first in the routing rules, correctly prioritising clinical risk over intent category.

---

## 10. Dashboard Design

### Design Principle: Calm Under Load

The brief asks whether the system "feels calm under load." This means the UI must not make the situation feel worse than it is. Seven unread items should feel manageable, not alarming.

Design choices that serve this:

- Summary strip at the top gives the total picture before any individual items are read
- Items are grouped so similar actions are adjacent — no forced context switching
- "Needs Review" is a separate, clearly labelled group — not mixed into other items where it would create uncertainty
- Status tracking (Pending → In Progress → Done) lets the team see progress clearing during the morning
- The empty state for "Attend first" is explicitly confirmed, not blank — staff should not have to wonder whether an empty group means nothing was checked or nothing was found

### Morning Briefing View — Typical Morning (no urgent items)

On most mornings, the "Attend first" group will be empty. The system surfaces this as a confirmed outcome:

```
┌──────────────────────────────────────────────────────────────────┐
│ Heidi Calls — Morning Briefing   Friday 6 Jun   Last sync: 6:58  │
├──────────────────┬────────────────┬──────────────┬───────────────┤
│  Attend now: 0   │  Routine: 7    │  Review: 1   │  ~14 min      │
└──────────────────┴────────────────┴──────────────┴───────────────┘

⚠ Attend first (0)
  ──────────────────────────────────────────────────────────────────
  Nothing flagged overnight. All 8 items passed safety screening. ✓

📋 Prescription requests (2)
  ...

📅 Appointment changes (3)
  ...
```

This is the expected outcome. The system communicates it explicitly so staff can trust it rather than re-verify manually.

### Morning Briefing View — Exception Morning (urgent items present)

```
┌──────────────────────────────────────────────────────────────────┐
│ Heidi Calls — Morning Briefing   Friday 6 Jun   Last sync: 6:58  │
├──────────────────┬────────────────┬──────────────┬───────────────┤
│  Attend now: 2   │  Routine: 5    │  Review: 2   │  ~22 min      │
└──────────────────┴────────────────┴──────────────┴───────────────┘

⚠ Attend first (2)
  ──────────────────────────────────────────────────────────────────
  [CRITICAL]  0412 345 678 · 11:42 PM
              Ran out of BP medication, currently dizzy. Known cardiac history.
              Requests urgent callback before clinic opens.
              → Call before clinic opens. May need same-day script or ED referral.
              [Safety: ACTIVE] [Confidence: 0.75] [Review needed]    [Done]

  [HIGH]      0423 456 789 · 10:15 PM
              Chest tightness last night, resolved. Cardiac history.
              → Flag for GP review first thing. Confirm current status.
              [Safety: WATCH] [Confidence: 0.75]                     [Done]

📋 Prescription requests (1)
  ──────────────────────────────────────────────────────────────────
  [NORMAL]    0434 567 890 · 7:05 PM

📅 Appointment changes (1)
  ──────────────────────────────────────────────────────────────────
  [NORMAL]    0445 678 901 · 9:08 PM

👁 Needs human review (1)
  ──────────────────────────────────────────────────────────────────
  [LOW]       No callback number · 12:15 AM — unclear message, IVR incomplete
```

### Voicemail Card (compact)

```
┌─────────────────────────────────────────────────────────────────┐
│ ⚠ CRITICAL  │ Medication concern — urgent      │ 11:42 PM       │
├─────────────────────────────────────────────────────────────────┤
│ 0412 345 678                                                     │
│ BP medication ran out today. Feeling dizzy. Cardiac history.     │
│ Requesting urgent callback before clinic opens.                  │
│                                                                  │
│ → Call back before clinic opens. May need same-day script.      │
│                                                                  │
│ 👁 Review needed · Confidence: 0.75 · Safety: ACTIVE            │
│                                          [Done] [Expand] [Assign]│
└─────────────────────────────────────────────────────────────────┘
```

### Detail View (on expand)

Shown when admin needs full context before acting:

- Original transcript (read-only, scrollable)
- Safety state with explanation ("ACTIVE — 'feeling dizzy' identified as current symptom")
- Confidence score with breakdown (which factors contributed)
- Missing information list ("No callback number confirmed — caller-stated number may need verification")
- Urgency reason (from LLM output)
- Routing target (branch + role)
- Auto-generated handover note
- Status buttons: Pending → In Progress → Done
- Action buttons: Flag for GP / Flag for practice manager

### Simulation Mode (sidebar)

Admin pastes any transcript → full pipeline runs → structured output displayed live.

This is the primary demonstration tool for the challenge evaluation. It shows the system is real, not a mockup.

---

## 11. Tech Stack

| Component        | Tool                             | Reason                                                                    |
| ---------------- | -------------------------------- | ------------------------------------------------------------------------- |
| ASR              | Groq Whisper API                 | Fast, no local GPU required, consistent with existing project             |
| LLM extraction   | Groq LLaMA-3.3-70b-versatile     | Already in existing project, strong structured output                     |
| Safety screening | Groq LLaMA-3.3-70b-versatile     | LLM binary screen — catches indirect language that keyword rules miss     |
| Dashboard        | Streamlit                        | Rapid build, no frontend toolchain, easy to demo                          |
| Data model       | Python dataclass + Pydantic      | Type-safe, validates LLM output before use                                |
| Policy config    | YAML                             | Editable by clinic staff, not just developers                             |
| Storage          | CSV (mock) → SQLite (optional)   | No infra needed for prototype                                             |

### Why Groq over local Whisper

The original Mini Clinical Scribe used local `openai-whisper`. This requires a GPU or significant CPU time, and adds a complex setup step for anyone trying to run the project. For a challenge submission, this creates unnecessary friction.

Groq Whisper is an API call — one line of code, no hardware dependency, and fast. It also keeps the stack consistent (Groq for both ASR and LLM).

---

## 12. Repo Structure

```
mini-heidi-calls/
├── app/
│   └── streamlit_app.py           # dashboard — Workflow view, location tabs, detail panel, simulation mode
│
├── src/
│   ├── voicemail/
│   │   ├── load_voicemails.py     # loads and validates CSV → list[VoicemailTask]
│   │   ├── triage_pipeline.py     # orchestrates all pipeline steps (parallel, with retry)
│   │   └── extract_details.py     # LLM structured extraction (intents, urgency, summary)
│   │
│   ├── safety/
│   │   ├── safety_screen.py       # stage 1 LLM binary screen (YES/NO)
│   │   ├── context_check.py       # stage 2 LLM safety state (ACTIVE/WATCH/ROUTINE)
│   │   ├── confidence.py          # computed confidence score (4 signals × 0.25)
│   │   └── failure_cases.py       # detects pocket dials, missing numbers, cutoffs
│   │
│   ├── policy/
│   │   ├── clinic_policy.yaml     # role-based routing rules (editable without code changes)
│   │   ├── policy_router.py       # applies YAML rules → sets task.assigned_to
│   │   └── next_step_router.py    # maps (urgency, safety_state, intents) → fixed receptionist action
│   │
│   ├── utils/
│   │   └── llm_call.py            # chat_with_retry — exponential backoff on rate limit errors
│   │
│   └── workflow/
│       └── task_model.py          # VoicemailTask dataclass
│
├── data/
│   └── mock_voicemails.csv        # 20 records covering all routing paths and edge cases
│
├── README.md
├── CONTEXT.md
├── PATIENT_FLOW.md
└── requirements.txt
```

---

## 13. Data Model

```python
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class VoicemailTask:
    # --- Raw input ---
    id: str
    received_at: datetime
    location: str                        # branch that received the call
    duration_sec: int
    transcript: str
    audio_path: Optional[str] = None

    # --- Caller identity ---
    caller_type: str = "patient"          # patient | healthcare_provider (IVR keypress)
    callback_number: Optional[str] = None # captured automatically by CLI

    # --- Triage output ---
    intents: list[str] = field(default_factory=lambda: ["unclear"])
    urgency: str = "normal"               # critical | high | normal | low
    urgency_reason: str = ""
    safety_state: str = "ROUTINE"         # ACTIVE | WATCH | ROUTINE
    summary: str = ""
    next_step: str = ""

    # --- Confidence + review ---
    confidence: float = 0.0
    needs_review: bool = False
    review_reason: str = ""

    # --- Routing ---
    assigned_to: Optional[str] = None    # gp | practice_nurse | clinic-manager | admin

    # --- Status tracking ---
    status: str = "pending"               # pending | in_progress | done
    handled_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notes: str = ""
```

The model is deliberately flat. No nested objects. Each field maps directly to a dashboard display element or a routing decision. This makes it easy to serialise to CSV, render in Streamlit, and inspect in tests.

---

## 14. Implementation Phases

Each phase ends with something runnable. The goal is to always be in a state that could be shown to an evaluator if the build stopped today.

### Phase 1 — Skeleton (no AI)

Goal: a working dashboard that reads from CSV and displays voicemail cards.

Why first: validates the data model and UI structure before adding any complexity. Also produces an immediate demo.

- [x] `mock_voicemails.csv` — 10 records across all categories
- [x] `task_model.py` — VoicemailTask dataclass
- [x] `load_voicemails.py` — reads and validates CSV → list of VoicemailTask
- [x] `streamlit_app.py` — inbox view, basic cards, urgency colour coding

Deliverable: a clickable dashboard that displays 10 mock voicemails with their raw data.

---

### Phase 2 — Safety Layer

Goal: deterministic safety classification runs before any LLM call.

Why second: safety is the highest-stakes part of the system. Getting it right early means it can be tested and trusted before the rest is built.

- [x] `safety_screen.py` — stage 1 LLM binary screen (replaces keyword matching)
- [x] `context_check.py` — stage 2 LLM call for safety state (ACTIVE / WATCH / ROUTINE)
- [x] `failure_cases.py` — detects pocket dial, no callback number, cutoff transcript
- [x] `confidence.py` — 4-factor confidence scorer
- [x] Dashboard update: safety badge on each card, "Needs Review" group visible

Deliverable: dashboard shows safety state and confidence for each mock record. Failure cases are explicitly labelled.

---

### Phase 3 — LLM Extraction

Goal: the LLM extracts structured fields from each transcript.

Why third: extraction depends on a working data model (Phase 1) and should run after safety state is determined (Phase 2), since safety state is an input to the extraction prompt.

- [x] `extract_details.py` — structured JSON prompt to Groq LLaMA-3.3-70b, returns `intents` list
- [x] `triage_pipeline.py` — orchestrates: load → safety → extract → confidence → route
- [x] Dashboard update: extracted fields on cards, summary text, next step visible

Deliverable: full pipeline runs end-to-end on all 10 mock records. Each card shows intent, urgency, summary, and next step.

---

### Phase 4 — Routing and Grouping

Goal: tasks are routed to the correct branch/role and grouped by intent in the dashboard.

Why fourth: routing and grouping depend on a complete task object (intent, urgency, confidence) which is only available after Phase 3.

- [x] `clinic_policy.yaml` — role-based routing rules (on_call_gp / gp / practice_manager / admin)
- [x] `policy_router.py` — reads YAML, applies rules, sets `task.assigned_to`
- [x] Dashboard update: flat sorted list (urgency → time), assigned role shown on each card

Deliverable: dashboard shows grouped morning briefing with routing information. Looks and feels like the final product.

---

### Phase 5 — Polish and Standout Features

Goal: features that make the demo compelling and complete.

- [x] Simulation mode — paste any transcript in sidebar, see live output
- [x] Detail view — full transcript, confidence breakdown, urgency reason
- [x] Status tracking — Pending → In Progress → Done, persisted in session
- [x] README — setup instructions, routing table, mock data summary
- [x] CONTEXT.md — design decisions, architecture, data model
- [x] PATIENT_FLOW.md — end-to-end journey, automated vs human boundary

Deliverable: complete, polished prototype ready for submission.

---

## 15. What Good Output Looks Like

An evaluator finishing the demo should think:

> This person did not just attach an LLM to voicemail.
> They understood how a real admin team starts their morning,
> handled safety and uncertainty explicitly and honestly,
> and built a system that turns 25 overnight recordings into
> a calm, prioritised briefing that takes 18 minutes to clear.

The six moments that create that impression:

1. **Safety state is explained** — not just flagged. "ACTIVE — 'feeling dizzy' detected as current symptom."
2. **Confidence is computed** — from real signals, not guessed. The score breakdown is visible.
3. **Failure cases are named** — pocket dials, missing numbers, ambiguous transcripts all handled explicitly.
4. **Sorting is the UX** — urgency first, then call time. One card per voicemail, all intents shown. No context-switching forced by alphabetical or chronological order.
5. **The system is honest** — "Needs Review" exists and is respected. The AI does not pretend to know what it does not.
6. **The empty state is trusted** — "Attend first (0) — Nothing flagged overnight ✓" is not a blank space. It is a confirmed outcome. Staff know the system ran, checked every transcript, and found nothing requiring urgent attention. That is different from not knowing.
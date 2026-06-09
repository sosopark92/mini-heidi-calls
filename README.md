# Mini Heidi Calls — Intelligent Voicemail Triage

A morning briefing system for GP clinic admin staff. Processes overnight voicemails and surfaces a prioritised, actionable list — highest urgency first, with safety flags and role assignments — so staff know exactly what to attend to the moment they arrive.

Built for the Heidi Health Forward-Deployed Engineer challenge.

---

## The Problem

Admin staff arrive each morning to a queue of unstructured voicemails. No urgency order. No intent summary. No clear next action. They triage manually, one by one, and the most urgent call might be buried at the end.

## What This Does

- Runs a 2-stage LLM safety screen on every voicemail (catches indirect language like "feeling a bit off" that keyword rules miss)
- Extracts structured data: all caller intents, urgency, summary, next step
- Assigns each task to the right role: On-Call GP / GP / Practice Manager / Admin
- Surfaces a flat sorted list: critical → high → normal → low, then by call time
- Flags anything the system cannot act on confidently for human review

---

## Setup

**1. Clone and install**

```bash
cd mini-heidi-calls
pip install -r requirements.txt
```

**2. Add your Groq API key**

Create `.env` in `mini-heidi-calls/`:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com).

**3. Run the dashboard**

```bash
streamlit run app/streamlit_app.py
```

**4. Or run the pipeline in the terminal**

```bash
python src/voicemail/triage_pipeline.py
```

---

## Try the Simulation Mode

Open the dashboard and use the sidebar to paste any transcript. The full pipeline runs live — safety screen, extraction, confidence score, role assignment — and shows the result instantly.

---

## How It Works

```
Voicemail transcript
        │
        ▼
Stage 1 safety screen    LLM binary YES/NO — does this transcript contain any clinical concern?
        │
        ▼ (if YES)
Stage 2 context check    ACTIVE (current concern) / WATCH (reported as resolved) / ROUTINE
        │
        ▼
LLM extraction           intents (list), urgency, summary, next_step, needs_review
        │
        ▼
Confidence score         4 signals × 0.25 — callback number, intent clear, transcript length
        │
        ▼
Role assignment          clinic_policy.yaml → on_call_gp / gp / clinic-manager / admin
        │
        ▼
Dashboard                sorted by urgency, then call time
```

Safety state flows into extraction — ACTIVE forces `critical` urgency, WATCH sets a minimum of `high`.

---

## Mock Data

`data/mock_voicemails.csv` has 10 records covering all categories:

| ID     | Scenario                                      | Expected urgency |
|--------|-----------------------------------------------|------------------|
| VM-001 | BP medication ran out, currently dizzy        | critical         |
| VM-002 | Chest tightness last night (resolved)         | high             |
| VM-003 | Repeat contraceptive pill                     | normal           |
| VM-004 | Healthcare provider — referral follow-up      | normal           |
| VM-005 | Reschedule tomorrow's appointment             | normal           |
| VM-006 | New patient appointment booking               | normal           |
| VM-007 | Chasing blood test results                    | normal           |
| VM-008 | Complaint about billing                       | normal           |
| VM-009 | No callback number, unclear intent            | low              |
| VM-010 | Pocket dial, no speech                        | low              |

---

## Results

10 mock records processed end-to-end.

| Category                | Result                                      |
|-------------------------|---------------------------------------------|
| Safety classification   | 10 / 10                                     |
| Urgency accuracy        | 10 / 10                                     |
| Needs review flagged    | 3 / 10 — VM-001, VM-009, VM-010             |
| Stage 2 context check triggered | 2 / 10 — VM-001 (ACTIVE), VM-002 (WATCH) |
| Avg pipeline time       | 5.34s per record total:53.4s (10 records time)                           |

---


## Routing Rules

Defined in `src/policy/clinic_policy.yaml` — editable without touching code.

| Condition                        | Assigned to      |
|----------------------------------|------------------|
| `urgency = critical`             | On-Call GP       |
| `safety_state = ACTIVE or WATCH` | GP               |
| `urgency = high`                 | GP               |
| `intent includes medication_concern` | GP           |
| `intent includes complaint`      | Clinic Manager   |
| Everything else                  | Admin            |

---

## Stack

| Layer           | Tool                        |
|-----------------|-----------------------------|
| LLM             | Groq LLaMA-3.3-70b-versatile |
| Safety screen   | Groq LLaMA-3.3-70b-versatile |
| Dashboard       | Streamlit                   |
| Policy config   | YAML                        |
| Data model      | Python dataclass            |

---

## Design Notes

Full reasoning behind every design decision is in [CONTEXT.md](CONTEXT.md).

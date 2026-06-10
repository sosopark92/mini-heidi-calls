# Mini Heidi Calls — Voicemail Briefing Tool for GP Receptionists

A morning briefing tool for GP clinic receptionists. Processes overnight voicemails and surfaces a prioritised, grouped workflow — so staff know exactly what to do first the moment they arrive.

Built for the Heidi Health Forward-Deployed Engineer challenge.

**[Live demo → mini-heidi-calls.streamlit.app](https://mini-heidi-calls.streamlit.app/)**

---

## The Problem

A busy GP clinic receives 15–30 voicemails overnight. They arrive in the order they were left — not in the order they matter. The most urgent callback might be buried at the end.

Receptionists spend the first part of their morning doing triage that a system could do for them: listening to each message, mentally ranking importance, switching between contexts. This system does that work before they arrive.

---

## What This Does

- Runs a 2-stage LLM safety screen on every transcript — catches indirect language ("feeling really off", "bit of tightness last night") that keyword rules miss
- Extracts structured data: caller intents, urgency level, plain-language summary
- Groups tasks by what to do, not just by urgency — so repeat scripts are batched together, appointments are batched together
- Suggests a clinic-approved action for each call — no free-form LLM output, no hallucinated next steps
- Flags anything the system cannot act on confidently — humans decide, not the AI
- Receptionists can adjust urgency if the AI gets it wrong

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
LLM_MODEL=llama-3.3-70b-versatile
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

Open the dashboard and use the sidebar to paste any transcript. The full pipeline runs live — safety screen, extraction, confidence score, role assignment — and shows the result instantly. This is the quickest way to see what the system does with a real voicemail.

---

## How It Works

```
Voicemail transcript
        │
        ▼
Stage 1 safety screen    LLM binary YES/NO — any clinical concern?
        │
        ▼ (if YES)
Stage 2 context check    ACTIVE (current) / WATCH (resolved) / ROUTINE
        │
        ▼
LLM extraction           intents, urgency, summary, needs_review
        │
        ▼
Confidence score         4 signals × 0.25 — callback number, intent, length
        │
        ▼
Next step                next_step_router.py → fixed clinic-approved action
        │
        ▼
Role assignment          clinic_policy.yaml → GP / Practice Nurse / Clinic Manager / Admin
        │
        ▼
Dashboard                Workflow view: grouped by action type, not just urgency
```

Safety state feeds into extraction — ACTIVE forces `critical` urgency, WATCH sets a minimum of `high`.

---

## Routing Rules

Defined in `src/policy/clinic_policy.yaml` — editable without touching code.

| Condition                            | Assigned to      |
|--------------------------------------|------------------|
| `urgency = critical`                 | GP               |
| `safety_state = ACTIVE or WATCH`     | GP               |
| `urgency = high`                     | GP               |
| `intent includes medication_concern` | GP               |
| `intent includes referral_request`   | GP               |
| `intent includes test_results`       | GP               |
| `intent includes complaint`          | Clinic Manager   |
| `intent includes appointment_booking`| Practice Nurse   |
| `intent includes prescription_repeat`| Practice Nurse   |
| Everything else                      | Admin            |

---

## Mock Data

`data/mock_voicemails.csv` — 20 records across all categories.

| Scenarios                                                        | Count |
|------------------------------------------------------------------|-------|
| Critical / ACTIVE (unresolved medical concern)                   | 2     |
| High / WATCH (resolved concern, GP should be informed)           | 3     |
| Medication concern — GP review required                          | 1     |
| Test results chasing — GP review required                        | 1     |
| Referral follow-up — GP review required                          | 1     |
| Prescription repeat — Practice Nurse                             | 3     |
| Appointment booking (vaccination, wound check, diabetes review)  | 3     |
| Appointment reschedule — Admin                                   | 1     |
| Formal complaint — Clinic Manager                                | 1     |
| General enquiry — Admin                                          | 2     |
| Unclear / pocket dial — Needs review                             | 2     |

---

## Stack

| Layer           | Tool                          |
|-----------------|-------------------------------|
| LLM             | Groq LLaMA-3.3-70b-versatile  |
| Safety screen   | Groq LLaMA-3.3-70b-versatile  |
| Dashboard       | Streamlit                     |
| Policy config   | YAML                          |
| Data model      | Python dataclass              |

---

## Further Reading

- [CONTEXT.md](CONTEXT.md) — full design reasoning, architecture, and decision log
- [PATIENT_FLOW.md](PATIENT_FLOW.md) — end-to-end journey from voicemail to resolved action

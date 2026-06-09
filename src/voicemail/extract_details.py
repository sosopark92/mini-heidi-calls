import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_client = None

VALID_INTENTS = {
    "prescription_repeat",
    "appointment_booking",
    "appointment_reschedule",
    "test_results",
    "medication_concern",
    "referral_request",
    "complaint",
    "general_enquiry",
    "unclear",
}

_URGENCY_ORDER = ["low", "normal", "high", "critical"]

_URGENCY_FLOOR = {
    "ACTIVE": "critical",
    "WATCH":  "high",
    "ROUTINE": None,
}

_EXTRACT_PROMPT = """You are a triage assistant for a GP clinic voicemail system.

Extract structured information from the voicemail transcript below.
The safety layer has already been run and classified this transcript.

SAFETY STATE: {safety_state}
- ACTIVE  = caller has a current medical concern       → urgency MUST be "critical"
- WATCH   = concern was reported as resolved, but GP should still be informed → urgency minimum "high"
- ROUTINE = no clinical concern detected               → set urgency based on content only

TRANSCRIPT:
\"\"\"{transcript}\"\"\"

INTENT — list ALL that apply, most important first (callers often have more than one reason):
  prescription_repeat    = repeat script, no new clinical concern
  appointment_booking    = new appointment request
  appointment_reschedule = change or cancel existing appointment
  test_results           = chasing pathology, imaging, or other results
  medication_concern     = side effect, dosing question, or supply issue
  referral_request       = patient requesting a specialist referral, OR a healthcare provider following up on a referral
  complaint              = complaint requiring manager or GP review
  general_enquiry        = opening hours, location, billing, or other admin
  unclear                = insufficient information to determine intent

Return ONLY a valid JSON object — no markdown, no explanation:
{{
  "intents": ["<primary intent>", "<additional intent if any — omit if only one>"],
  "urgency": "<critical | high | normal | low>",
  "urgency_reason": "<one sentence explaining the urgency classification>",
  "summary": "<1-2 sentences covering ALL reasons for the call — not a verbatim transcript>",
  "next_step": "<one concrete action for clinic admin staff>",
  "needs_review": <true | false>,
  "review_reason": "<why this cannot be acted on confidently, or empty string>"
}}"""


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def _apply_urgency_floor(urgency: str, safety_state: str) -> str:
    floor = _URGENCY_FLOOR.get(safety_state)
    if floor is None:
        return urgency
    if _URGENCY_ORDER.index(urgency) < _URGENCY_ORDER.index(floor):
        return floor
    return urgency


def _append_review_reason(task: VoicemailTask, reason: str) -> None:
    if task.review_reason:
        task.review_reason += f" | {reason}"
    else:
        task.review_reason = reason


def extract_details(task: VoicemailTask) -> VoicemailTask:
    """Extract intent, urgency, summary, next_step from transcript via LLM.

    Mutates task in place and returns it. Safe defaults on any failure.
    """
    prompt = _EXTRACT_PROMPT.format(
        transcript=task.transcript,
        safety_state=task.safety_state,
    )

    try:
        response = _get_client().chat.completions.create(
            # model="llama-3.3-70b-versatile",
            model = "llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=600,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if the model wraps the output
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()

        data = json.loads(raw)

    except Exception as exc:
        task.needs_review = True
        _append_review_reason(task, f"Extraction error — review transcript manually ({exc})")
        return task

    # --- Intents (validate each against taxonomy, keep only known values) ---
    raw_intents = data.get("intents", ["unclear"])
    if isinstance(raw_intents, str):
        raw_intents = [raw_intents]  # LLM occasionally returns a string instead of list
    validated = [i for i in raw_intents if i in VALID_INTENTS]
    task.intents = validated if validated else ["unclear"]

    # --- Urgency (validate then apply safety floor) ---
    urgency = data.get("urgency", "normal")
    if urgency not in {"critical", "high", "normal", "low"}:
        urgency = "normal"
    task.urgency = _apply_urgency_floor(urgency, task.safety_state)

    # --- Remaining text fields ---
    task.urgency_reason = data.get("urgency_reason", "")
    task.summary        = data.get("summary", "")
    task.next_step      = data.get("next_step", "")

    # needs_review: OR logic — failure_cases or LLM can independently set it
    if data.get("needs_review", False):
        task.needs_review = True

    llm_review_reason = data.get("review_reason", "")
    if llm_review_reason:
        _append_review_reason(task, llm_review_reason)

    return task


if __name__ == "__main__":
    from src.voicemail.load_voicemails import load_voicemails

    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))

    for task in tasks:
        print(f"\n{'=' * 60}")
        print(f"{task.id} | safety={task.safety_state}")
        print(f"  transcript: \"{task.transcript[:75]}...\"")
        extract_details(task)
        print(f"  intents:    {task.intents}")
        print(f"  urgency:    {task.urgency}")
        print(f"  summary:    {task.summary}")
        print(f"  next_step:  {task.next_step}")
        if task.needs_review:
            print(f"  REVIEW:     {task.review_reason}")

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask
from src.utils.llm_call import chat_with_retry

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=0, timeout=30.0)
    return _client


SAFETY_STATES = {"ACTIVE", "WATCH", "ROUTINE"}

_CONTEXT_PROMPT = """You are a clinical triage assistant for a GP clinic voicemail system.

The transcript below has been flagged as potentially containing a medical concern.
Your job is to determine how urgent this concern is based on context.

Transcript:
\"\"\"{transcript}\"\"\"

Answer these questions internally, then give your final classification:
1. Is the symptom or concern CURRENT (happening now or very recently) — or PAST / already resolved?
2. Is the caller describing their own situation — or someone else's?
3. Does the caller show signs of distress or urgency?

Respond with ONLY one of these three words:

ACTIVE  → concern is current and the caller needs prompt attention
WATCH   → caller reports the concern has passed, but GP should still be informed
           (note: this is the CALLER's report — not clinically confirmed)
ROUTINE → no genuine medical concern despite being flagged

Your response (one word only):"""


def check_safety_context(task: VoicemailTask) -> str:
    """Stage 2 LLM context check. Returns ACTIVE, WATCH, or ROUTINE.

    Only called when Stage 1 (safety_screen) returns True.
    Updates task.safety_state and returns the state string.
    """
    prompt = _CONTEXT_PROMPT.format(transcript=task.transcript)

    response = chat_with_retry(_get_client(),
        model=os.environ.get("LLM_MODEL", "llama-3.1-8b-instant"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=10,
    )

    raw = response.choices[0].message.content.strip().upper()
    state = raw if raw in SAFETY_STATES else "ACTIVE"  # fail safe

    task.safety_state = state
    return state


if __name__ == "__main__":
    from src.voicemail.load_voicemails import load_voicemails
    from src.safety.safety_screen import screen_for_safety

    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))

    for task in tasks:
        flagged = screen_for_safety(task)
        if flagged:
            state = check_safety_context(task)
            print(f"{task.id} | safety_state={state}")
            print(f"  \"{task.transcript[:80]}...\"")
            print()

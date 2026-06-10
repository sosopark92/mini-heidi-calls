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
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


_SCREEN_PROMPT = """You are a clinical safety screener for a GP clinic voicemail system.

Read this voicemail transcript and answer ONE question:
Does this caller describe ANY current or recent medical symptom, concern, or emotional distress
that would require a GP or clinic staff to respond promptly?

Transcript:
\"\"\"{transcript}\"\"\"

Answer with YES or NO only.
- YES = any medical or emotional concern that needs attention, even if the caller downplays it
        (examples: pain, breathlessness, dizziness, chest tightness, feeling unwell, distress,
         medication side effect, mental health concern, any symptom — direct or indirect)
- NO  = purely administrative with no clinical concern
        (examples: appointment booking or change, repeat script request, test results query,
         billing question, general enquiry)"""


def screen_for_safety(task: VoicemailTask) -> bool:
    """Stage 1 LLM safety screen. Returns True if any clinical concern is detected.

    Cheap binary call (max 5 output tokens). Stage 2 only runs if this returns True.
    Uses temperature=0 for consistency.
    """
    if len(task.transcript.split()) < 5:
        return False  # pocket dial — handled by failure_cases.py

    prompt = _SCREEN_PROMPT.format(transcript=task.transcript)

    response = chat_with_retry(_get_client(),
        model=os.environ.get("LLM_MODEL", "llama-3.1-8b-instant"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=5,
    )

    answer = response.choices[0].message.content.strip().upper()
    return answer.startswith("YES")


if __name__ == "__main__":
    from src.voicemail.load_voicemails import load_voicemails

    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))

    for task in tasks:
        flagged = screen_for_safety(task)
        label = "FLAGGED  <-- goes to Stage 2" if flagged else "routine"
        print(f"{task.id} | {label}")
        print(f"  \"{task.transcript[:80]}...\"")
        print()

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask

REVIEW_THRESHOLD = 0.6


def calculate_confidence(task: VoicemailTask) -> tuple[float, dict]:
    """Compute confidence score from observable signals.

    Returns (score, breakdown) and updates task.confidence and task.needs_review.

    Signals:
      callback_number  → 0.25  (did the caller complete the IVR?)
      intent_clear     → 0.25  (do we know why they called?)
      transcript_20+   → 0.25  (enough content to work with?)
      transcript_50+   → 0.25  (is the message substantive?)
    Max score: 1.0 for all caller types.
    """
    breakdown = {}
    word_count = len(task.transcript.split())

    breakdown["callback_number"] = 0.25 if task.callback_number else 0.0
    breakdown["intent_clear"]    = 0.25 if any(i != "unclear" for i in task.intents) else 0.0
    breakdown["transcript_20+"]  = 0.25 if word_count >= 20 else 0.0
    breakdown["transcript_50+"]  = 0.25 if word_count >= 50 else 0.0

    score = round(sum(breakdown.values()), 2)

    task.confidence = score
    if score < REVIEW_THRESHOLD:
        task.needs_review = True

    return score, breakdown


if __name__ == "__main__":
    from src.voicemail.load_voicemails import load_voicemails

    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))

    for task in tasks:
        score, breakdown = calculate_confidence(task)
        print(f"{task.id} | confidence={score} | needs_review={task.needs_review}")
        for signal, value in breakdown.items():
            print(f"  {signal}: +{value}")
        print()

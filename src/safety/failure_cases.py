import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask

_CLOSING_WORDS = {"bye", "thanks", "thank you", "cheers", "goodbye"}


def detect_failure_cases(task: VoicemailTask) -> VoicemailTask:
    """Detect and label failure modes. Updates task in place and returns it."""
    reasons = []
    word_count = len(task.transcript.split())

    # 1. Pocket dial / no speech
    if word_count < 5:
        task.urgency = "low"
        task.needs_review = True
        task.review_reason = "No audible message detected"
        return task  # no point checking further

    # 2. No callback number (IVR did not complete)
    if task.callback_number is None:
        task.needs_review = True

    # 3. Cutoff transcript (short + no clean ending)
    last_word = task.transcript.strip().split()[-1].lower().rstrip(".,!?")
    ends_cleanly = task.transcript.strip()[-1] in ".!?…" or last_word in _CLOSING_WORDS
    if word_count < 15 and not ends_cleanly:
        task.needs_review = True
        reasons.append("Transcript may be incomplete")

    # 4. Non-English content
    non_ascii_ratio = sum(1 for c in task.transcript if ord(c) > 127) / max(len(task.transcript), 1)
    if non_ascii_ratio > 0.3:
        task.needs_review = True
        reasons.append("Non-English content detected")

    if reasons:
        existing = task.review_reason.strip(" |") if task.review_reason else ""
        combined = " | ".join([existing] + reasons) if existing else " | ".join(reasons)
        task.review_reason = combined

    return task


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.voicemail.load_voicemails import load_voicemails
    from pathlib import Path as P

    csv_path = P(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))

    for task in tasks:
        result = detect_failure_cases(task)
        if result.needs_review:
            print(f"{result.id} | needs_review={result.needs_review}")
            print(f"  review_reason: {result.review_reason}")
            print()

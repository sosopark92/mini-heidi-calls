import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask


def _optional(value: str) -> str | None:
    return value.strip() if value.strip() else None


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _float(value: str) -> float:
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return 0.0


def load_voicemails(csv_path: str) -> list[VoicemailTask]:
    tasks = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            task = VoicemailTask(
                # --- Raw input ---
                id=row["id"],
                received_at=datetime.strptime(row["received_at"], "%Y-%m-%d %H:%M:%S"),
                location=row["location"],
                duration_sec=int(row["duration_sec"]),
                transcript=row["transcript"],
                audio_path=_optional(row["audio_path"]),
                # --- IVR keypad data ---
                caller_type=row["caller_type"] or "patient",
                callback_number=_optional(row["callback_number"]),
                # --- Extracted fields ---
                intents=[row.get("intent", "unclear") or "unclear"],
                urgency=row.get("urgency", "normal") or "normal",
                safety_state=row.get("safety_state", "ROUTINE") or "ROUTINE",
                summary=row.get("summary", ""),
                next_step=row.get("next_step", ""),
                confidence=_float(row.get("confidence", "0.0")),
                needs_review=_bool(row.get("needs_review", "false")),
                review_reason=row.get("review_reason", ""),
            )
            tasks.append(task)
    return tasks


if __name__ == "__main__":
    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))
    for t in tasks:
        print(f"{t.id} | {t.urgency:8} | {t.intent:25} | confidence={t.confidence} | review={t.needs_review}")

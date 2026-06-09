import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.workflow.task_model import VoicemailTask
from src.safety.failure_cases import detect_failure_cases
from src.safety.safety_screen import screen_for_safety


def make_task(**kwargs) -> VoicemailTask:
    defaults = dict(
        id="T-001",
        received_at=datetime(2025, 1, 1, 8, 0),
        location="harbour",
        duration_sec=30,
        transcript="Hello I would like to book an appointment please thank you",
        caller_type="patient",
        callback_number="0400000000",
        intents=["appointment_booking"],
    )
    defaults.update(kwargs)
    return VoicemailTask(**defaults)


# ── failure_cases.py ──────────────────────────────────────────────────────────

def test_pocket_dial_sets_low_urgency_and_review():
    task = make_task(transcript="oh sorry")
    detect_failure_cases(task)
    assert task.urgency == "low"
    assert task.needs_review is True
    assert "No audible message detected" in task.review_reason


def test_pocket_dial_skips_further_checks():
    task = make_task(transcript="hi", callback_number=None)
    detect_failure_cases(task)
    # review_reason should only be the pocket dial message, not a missing number message
    assert task.review_reason == "No audible message detected"


def test_no_callback_number_triggers_review():
    task = make_task(callback_number=None)
    detect_failure_cases(task)
    assert task.needs_review is True


def test_cutoff_transcript_triggers_review():
    task = make_task(transcript="I wanted to ask about my medication")
    detect_failure_cases(task)
    assert task.needs_review is True
    assert "Transcript may be incomplete" in task.review_reason


def test_clean_ending_does_not_flag_cutoff():
    task = make_task(transcript="I wanted to ask about my prescription. Thanks.")
    detect_failure_cases(task)
    assert "Transcript may be incomplete" not in (task.review_reason or "")


def test_non_english_triggers_review():
    task = make_task(transcript="안녕하세요 저는 예약을 하고 싶습니다 감사합니다 좋은 하루 되세요")
    detect_failure_cases(task)
    assert task.needs_review is True
    assert "Non-English content detected" in task.review_reason


def test_distressed_tone_bumps_urgency():
    task = make_task(
        transcript="I cannot cope anymore this is absolutely ridiculous I need help now",
        urgency="normal",
    )
    detect_failure_cases(task)
    assert task.urgency == "high"
    assert "Distressed or angry tone detected" in task.review_reason


def test_distressed_tone_does_not_downgrade_critical():
    task = make_task(
        transcript="I cannot cope anymore this is absolutely ridiculous please help",
        urgency="critical",
    )
    detect_failure_cases(task)
    assert task.urgency == "critical"


# ── safety_screen.py (mocked) ─────────────────────────────────────────────────

def _mock_groq_response(answer: str):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = answer
    return mock_response


def test_screen_returns_true_on_yes():
    with patch("src.safety.safety_screen._get_client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = \
            _mock_groq_response("YES")
        task = make_task(transcript="I have been having chest pain since this morning")
        result = screen_for_safety(task)
        assert result is True


def test_screen_returns_false_on_no():
    with patch("src.safety.safety_screen._get_client") as mock_client:
        mock_client.return_value.chat.completions.create.return_value = \
            _mock_groq_response("NO")
        task = make_task(transcript="I would like to book an appointment for next week please")
        result = screen_for_safety(task)
        assert result is False


def test_screen_skips_pocket_dial():
    with patch("src.safety.safety_screen._get_client") as mock_client:
        task = make_task(transcript="oh hi")
        result = screen_for_safety(task)
        mock_client.assert_not_called()
        assert result is False

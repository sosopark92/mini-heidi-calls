import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.workflow.task_model import VoicemailTask
from src.safety.confidence import calculate_confidence


def make_task(**kwargs) -> VoicemailTask:
    defaults = dict(
        id="T-001",
        received_at=datetime(2025, 1, 1, 8, 0),
        location="harbour",
        duration_sec=30,
        transcript="",
        intents=["unclear"],
        callback_number=None,
    )
    defaults.update(kwargs)
    return VoicemailTask(**defaults)


def test_perfect_score():
    task = make_task(
        callback_number="0400000000",
        intents=["prescription_repeat"],
        transcript=" ".join(["word"] * 60),
    )
    score, breakdown = calculate_confidence(task)
    assert score == 1.0
    assert breakdown["callback_number"] == 0.25
    assert breakdown["intent_clear"] == 0.25
    assert breakdown["transcript_20+"] == 0.25
    assert breakdown["transcript_50+"] == 0.25
    assert task.needs_review is False


def test_zero_score():
    task = make_task(callback_number=None, intents=["unclear"], transcript="hi")
    score, _ = calculate_confidence(task)
    assert score == 0.0
    assert task.needs_review is True


def test_no_callback_number_reduces_score():
    task = make_task(
        callback_number=None,
        intents=["appointment_booking"],
        transcript=" ".join(["word"] * 60),
    )
    score, breakdown = calculate_confidence(task)
    assert breakdown["callback_number"] == 0.0
    assert score == 0.75  # 3 signals × 0.25, callback missing


def test_short_transcript_below_20_words():
    task = make_task(
        callback_number="0400000000",
        intents=["prescription_repeat"],
        transcript="just a few words",
    )
    score, breakdown = calculate_confidence(task)
    assert breakdown["transcript_20+"] == 0.0
    assert breakdown["transcript_50+"] == 0.0


def test_transcript_between_20_and_50_words():
    task = make_task(
        callback_number="0400000000",
        intents=["prescription_repeat"],
        transcript=" ".join(["word"] * 30),
    )
    score, breakdown = calculate_confidence(task)
    assert breakdown["transcript_20+"] == 0.25
    assert breakdown["transcript_50+"] == 0.0


def test_unclear_intent_does_not_count():
    task = make_task(
        callback_number="0400000000",
        intents=["unclear"],
        transcript=" ".join(["word"] * 60),
    )
    score, breakdown = calculate_confidence(task)
    assert breakdown["intent_clear"] == 0.0


def test_multi_intent_counts_if_any_clear():
    task = make_task(
        callback_number="0400000000",
        intents=["unclear", "prescription_repeat"],
        transcript=" ".join(["word"] * 60),
    )
    score, breakdown = calculate_confidence(task)
    assert breakdown["intent_clear"] == 0.25


def test_score_written_to_task():
    task = make_task(
        callback_number="0400000000",
        intents=["prescription_repeat"],
        transcript=" ".join(["word"] * 60),
    )
    calculate_confidence(task)
    assert task.confidence == 1.0

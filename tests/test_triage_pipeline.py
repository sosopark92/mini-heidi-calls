import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.workflow.task_model import VoicemailTask
from src.voicemail.triage_pipeline import run_pipeline


def make_task(id: str, urgency: str = "normal", received_at: datetime = None,
              transcript: str = "Hello I would like to book an appointment please thank you bye",
              **kwargs) -> VoicemailTask:
    return VoicemailTask(
        id=id,
        received_at=received_at or datetime(2025, 1, 1, 8, 0),
        location="harbour",
        duration_sec=30,
        transcript=transcript,
        callback_number="0400000000",
        urgency=urgency,
        **kwargs,
    )


def patched_pipeline(tasks):
    """Run pipeline with all LLM steps mocked out."""
    with patch("src.voicemail.triage_pipeline.screen_for_safety", return_value=False), \
         patch("src.voicemail.triage_pipeline.check_safety_context"), \
         patch("src.voicemail.triage_pipeline.extract_details"), \
         patch("src.voicemail.triage_pipeline.calculate_confidence"), \
         patch("src.voicemail.triage_pipeline.assign_role"):
        return run_pipeline(tasks, verbose=False)


# ── Sorting ───────────────────────────────────────────────────────────────────

def test_sorted_by_urgency():
    tasks = [
        make_task("A", urgency="low"),
        make_task("B", urgency="critical"),
        make_task("C", urgency="normal"),
        make_task("D", urgency="high"),
    ]
    result = patched_pipeline(tasks)
    assert [t.id for t in result] == ["B", "D", "C", "A"]


def test_same_urgency_sorted_by_time():
    tasks = [
        make_task("A", urgency="normal", received_at=datetime(2025, 1, 1, 10, 0)),
        make_task("B", urgency="normal", received_at=datetime(2025, 1, 1, 7, 0)),
        make_task("C", urgency="normal", received_at=datetime(2025, 1, 1, 9, 0)),
    ]
    result = patched_pipeline(tasks)
    assert [t.id for t in result] == ["B", "C", "A"]


# ── Pocket dial ───────────────────────────────────────────────────────────────

def test_pocket_dial_skips_llm_steps():
    task = make_task("POCKET", transcript="oh sorry")
    with patch("src.voicemail.triage_pipeline.screen_for_safety") as mock_screen, \
         patch("src.voicemail.triage_pipeline.extract_details") as mock_extract, \
         patch("src.voicemail.triage_pipeline.calculate_confidence") as mock_conf, \
         patch("src.voicemail.triage_pipeline.assign_role") as mock_role:
        run_pipeline([task], verbose=False)
        mock_screen.assert_not_called()
        mock_extract.assert_not_called()
        mock_conf.assert_not_called()
        mock_role.assert_not_called()


# ── Stage 2 only runs when Stage 1 flags ─────────────────────────────────────

def test_context_check_only_runs_when_flagged():
    tasks = [make_task("A"), make_task("B")]
    with patch("src.voicemail.triage_pipeline.screen_for_safety", side_effect=[True, False]), \
         patch("src.voicemail.triage_pipeline.check_safety_context") as mock_ctx, \
         patch("src.voicemail.triage_pipeline.extract_details"), \
         patch("src.voicemail.triage_pipeline.calculate_confidence"), \
         patch("src.voicemail.triage_pipeline.assign_role"):
        run_pipeline(tasks, verbose=False)
        assert mock_ctx.call_count == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_list_returns_empty():
    result = patched_pipeline([])
    assert result == []


def test_pipeline_returns_same_tasks():
    tasks = [make_task("A"), make_task("B")]
    result = patched_pipeline(tasks)
    assert len(result) == 2
    assert {t.id for t in result} == {"A", "B"}

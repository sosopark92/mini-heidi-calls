import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask
from src.safety.failure_cases import detect_failure_cases
from src.safety.safety_screen import screen_for_safety
from src.safety.context_check import check_safety_context
from src.voicemail.extract_details import extract_details
from src.safety.confidence import calculate_confidence
from src.policy.policy_router import assign_role

_URGENCY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def run_pipeline(tasks: list[VoicemailTask], verbose: bool = True) -> list[VoicemailTask]:
    """Run the full triage pipeline on a list of VoicemailTasks.

    Steps per task:
      1. detect_failure_cases  — structural issues (pocket dial, no callback, etc.)
      2. screen_for_safety     — Stage 1 LLM binary screen (YES/NO)
      3. check_safety_context  — Stage 2 LLM context check (only if Stage 1 flagged)
      4. extract_details       — LLM structured extraction (intents, urgency, summary, etc.)
      5. calculate_confidence  — computed score from observable signals

    Mutates tasks in place. Returns them sorted by urgency then received_at.
    """
    total = len(tasks)
    for i, task in enumerate(tasks, 1):
        if verbose:
            print(f"  [{i}/{total}] {task.id} ...", end=" ", flush=True)

        # Step 1 — structural failure detection (no LLM)
        detect_failure_cases(task)

        # Pocket dials have nothing to extract — skip LLM steps
        if len(task.transcript.split()) < 5:
            if verbose:
                print("pocket dial — skipped")
            continue

        # Step 2 — Stage 1 safety screen
        flagged = screen_for_safety(task)

        # Step 3 — Stage 2 context check (only when Stage 1 flagged)
        if flagged:
            check_safety_context(task)
            if verbose:
                print(f"safety={task.safety_state}", end=" ", flush=True)
        else:
            if verbose:
                print("safety=ROUTINE", end=" ", flush=True)

        # Step 4 — LLM structured extraction
        extract_details(task)

        # Step 5 — confidence score
        calculate_confidence(task)

        # Step 6 — role assignment
        assign_role(task)

        if verbose:
            print(f"| intents={task.intents} | urgency={task.urgency} | confidence={task.confidence}")

    # Sort: urgency (critical first), then received_at (earliest first within same urgency)
    tasks.sort(key=lambda t: (_URGENCY_ORDER.get(t.urgency, 99), t.received_at))
    return tasks


if __name__ == "__main__":
    from src.voicemail.load_voicemails import load_voicemails

    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))

    print(f"Running pipeline on {len(tasks)} voicemails...\n")
    processed = run_pipeline(tasks)

    print("\n" + "=" * 62)
    print("  HEIDI CALLS — MORNING BRIEFING")
    print("=" * 62)

    for task in processed:
        time_str = task.received_at.strftime("%H:%M")
        intents_str = " + ".join(task.intents)
        safety_flag = f"  [{task.safety_state}]" if task.safety_state != "ROUTINE" else ""
        review_flag = "  ** REVIEW **" if task.needs_review else ""

        print(f"\n[{task.urgency.upper():<8}]  {task.id}  {time_str}{safety_flag}{review_flag}")
        print(f"  intents : {intents_str}")
        print(f"  summary : {task.summary}")
        print(f"  next    : {task.next_step}")
        print(f"  conf    : {task.confidence}")

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _process_one(task: VoicemailTask, index: int, total: int, verbose: bool) -> tuple[VoicemailTask, float | None]:
    t_start = time.perf_counter()
    if verbose:
        print(f"  [{index}/{total}] {task.id} ...", end=" ", flush=True)

    detect_failure_cases(task)

    if len(task.transcript.split()) < 5:
        if verbose:
            print("pocket dial — skipped")
        return task, None

    flagged = screen_for_safety(task)

    if flagged:
        check_safety_context(task)
        if verbose:
            print(f"safety={task.safety_state}", end=" ", flush=True)
    else:
        if verbose:
            print("safety=ROUTINE", end=" ", flush=True)

    extract_details(task)
    calculate_confidence(task)
    assign_role(task)

    elapsed = time.perf_counter() - t_start
    if verbose:
        print(f"| intents={task.intents} | urgency={task.urgency} | confidence={task.confidence} | {elapsed:.2f}s")
    return task, elapsed


def run_pipeline(tasks: list[VoicemailTask], verbose: bool = True) -> list[VoicemailTask]:
    """Run the full triage pipeline on a list of VoicemailTasks.

    Steps per task:
      1. detect_failure_cases  — structural issues (pocket dial, no callback, etc.)
      2. screen_for_safety     — Stage 1 LLM binary screen (YES/NO)
      3. check_safety_context  — Stage 2 LLM context check (only if Stage 1 flagged)
      4. extract_details       — LLM structured extraction (intents, urgency, summary, etc.)
      5. calculate_confidence  — computed score from observable signals

    Tasks are processed in parallel. Returns them sorted by urgency then received_at.
    """
    total = len(tasks)
    timings: list[float] = []
    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=total) as executor:
        futures = {
            executor.submit(_process_one, task, i, total, verbose): task
            for i, task in enumerate(tasks, 1)
        }
        for future in as_completed(futures):
            _, elapsed = future.result()
            if elapsed is not None:
                timings.append(elapsed)

    wall_elapsed = time.perf_counter() - wall_start
    if verbose and timings:
        print(f"\n  avg: {sum(timings)/len(timings):.2f}s/record  total(sum): {sum(timings):.1f}s  wall: {wall_elapsed:.1f}s  ({len(timings)} records timed)")

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

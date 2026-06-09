import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask

_POLICY_PATH = Path(__file__).parent / "clinic_policy.yaml"
_policy = None


def _load_policy() -> dict:
    global _policy
    if _policy is None:
        with open(_POLICY_PATH, encoding="utf-8") as f:
            _policy = yaml.safe_load(f)
    return _policy


def _matches(rule: dict, task: VoicemailTask) -> bool:
    match = rule.get("match", {})

    if "urgency" in match:
        if task.urgency != match["urgency"]:
            return False

    if "safety_state" in match:
        if task.safety_state not in match["safety_state"]:
            return False

    if "any_intent" in match:
        if match["any_intent"] not in task.intents:
            return False

    return True


def assign_role(task: VoicemailTask) -> VoicemailTask:
    """Apply routing rules and set task.assigned_to. Mutates task in place."""
    policy = _load_policy()

    for rule in policy["routing_rules"]:
        if rule.get("default") or _matches(rule, task):
            task.assigned_to = rule["assign_to"]
            return task

    task.assigned_to = "admin"
    return task


if __name__ == "__main__":
    from src.voicemail.load_voicemails import load_voicemails
    from src.voicemail.triage_pipeline import run_pipeline

    csv_path = Path(__file__).parent.parent.parent / "data" / "mock_voicemails.csv"
    tasks = load_voicemails(str(csv_path))
    run_pipeline(tasks, verbose=False)

    print(f"\n{'ID':<10} {'URGENCY':<10} {'SAFETY':<8} {'INTENTS':<40} {'ASSIGNED TO'}")
    print("-" * 90)
    for task in tasks:
        assign_role(task)
        intents_str = " + ".join(task.intents)
        print(f"{task.id:<10} {task.urgency:<10} {task.safety_state:<8} {intents_str:<40} {task.assigned_to}")

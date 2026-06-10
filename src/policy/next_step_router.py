import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow.task_model import VoicemailTask

# Receptionist-executable actions only. Rules evaluated in order; first match wins.
_RULES: list[tuple[dict, str]] = [
    (
        {"safety_state": {"ACTIVE"}},
        "Call back immediately and connect to GP or nurse on duty — do not leave a message.",
    ),
    (
        {"urgency": {"critical"}},
        "Call back immediately and connect to GP or nurse on duty — do not leave a message.",
    ),
    (
        {"safety_state": {"WATCH"}},
        "Leave a message for GP to review before any callback is made.",
    ),
    (
        {"urgency": {"high"}},
        "Call back and offer a same-day appointment.",
    ),
    (
        {"any_intent": "complaint"},
        "Escalate to practice manager before making any callback.",
    ),
    (
        {"any_intent": "medication_concern"},
        "Leave a message for GP — do not advise on medication without clinical guidance.",
    ),
    (
        {"any_intent": "referral_request"},
        "Leave a message for GP to review the referral request.",
    ),
    (
        {"any_intent": "test_results"},
        "Leave a message for GP — patient is chasing results.",
    ),
    (
        {"any_intent": "prescription_repeat"},
        "Process repeat script request — confirm with GP if a new concern was raised.",
    ),
    (
        {"any_intent": "appointment_booking"},
        "Book appointment via standard booking system.",
    ),
    (
        {"any_intent": "appointment_reschedule"},
        "Reschedule or cancel appointment via standard booking system.",
    ),
    (
        {"any_intent": "general_enquiry"},
        "Handle directly — provide information or redirect to appropriate service.",
    ),
]

_DEFAULT = "Call back to clarify — leave a message for GP review if any clinical concern."


def _matches(rule: dict, task: VoicemailTask) -> bool:
    if "safety_state" in rule and task.safety_state not in rule["safety_state"]:
        return False
    if "urgency" in rule and task.urgency not in rule["urgency"]:
        return False
    if "any_intent" in rule and rule["any_intent"] not in task.intents:
        return False
    return True


def get_next_step(task: VoicemailTask) -> str:
    """Return the appropriate receptionist action for this task."""
    for rule, action in _RULES:
        if _matches(rule, task):
            return action
    return _DEFAULT

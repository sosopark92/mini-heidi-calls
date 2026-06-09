from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class VoicemailTask:
    # --- Raw input ---
    id: str
    received_at: datetime
    location: str
    duration_sec: int
    transcript: str
    audio_path: Optional[str] = None

    # --- Caller identity (IVR keypad — structured, confirmed) ---
    caller_type: str = "patient"          # patient | healthcare_provider
    callback_number: Optional[str] = None # always present if IVR completed

    # --- Triage output ---
    intents: list[str] = field(default_factory=lambda: ["unclear"])
    urgency: str = "normal"               # critical | high | normal | low
    urgency_reason: str = ""
    safety_state: str = "ROUTINE"         # ACTIVE | WATCH | ROUTINE
    summary: str = ""
    next_step: str = ""

    # --- Confidence + review ---
    confidence: float = 0.0
    needs_review: bool = False
    review_reason: str = ""

    # --- Routing ---
    assigned_to: Optional[str] = None   # on_call_gp | gp | practice_manager | admin

    # --- Status tracking ---
    status: str = "pending"               # pending | in_progress | done
    handled_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notes: str = ""

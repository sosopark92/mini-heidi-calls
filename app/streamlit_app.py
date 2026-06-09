import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.voicemail.load_voicemails import load_voicemails
from src.voicemail.triage_pipeline import run_pipeline
from src.workflow.task_model import VoicemailTask

st.set_page_config(page_title="Heidi Calls", layout="wide", page_icon="📋")

CSV_PATH = Path(__file__).parent.parent / "data" / "mock_voicemails.csv"

URGENCY_BADGE = {
    "critical": "🔴 CRITICAL",
    "high":     "🟠 HIGH",
    "normal":   "🔵 NORMAL",
    "low":      "⚫ LOW",
}
SAFETY_BADGE = {
    "ACTIVE":  "🚨 ACTIVE",
    "WATCH":   "👀 WATCH",
    "ROUTINE": "",
}
ROLE_LABEL = {
    "on_call_gp":       "→ On-Call GP",
    "gp":               "→ GP",
    "practice_manager": "→ Practice Manager",
    "admin":            "→ Admin",
}


def render_card(task: VoicemailTask):
    urgency_badge = URGENCY_BADGE.get(task.urgency, task.urgency.upper())
    safety_badge  = SAFETY_BADGE.get(task.safety_state, "")
    time_str      = task.received_at.strftime("%H:%M")
    callback      = task.callback_number or "*(no number)*"
    intents_str   = " + ".join(task.intents)

    with st.container(border=True):
        col_main, col_action = st.columns([5, 1])

        with col_main:
            badges = urgency_badge
            if safety_badge:
                badges += f"  {safety_badge}"
            if task.needs_review:
                badges += "  ⚠️ Review needed"
            st.markdown(f"**{badges}**  ·  {time_str}  ·  {task.location.title()} Branch")

            caller_icon = "🏥" if task.caller_type == "healthcare_provider" else "👤"
            role_str = ROLE_LABEL.get(task.assigned_to or "", "")
            st.caption(f"{caller_icon} {callback}  ·  `{intents_str}`  ·  {role_str}  ·  {task.duration_sec}s")

            if task.summary:
                st.markdown(task.summary)
            else:
                preview = task.transcript[:120] + "…" if len(task.transcript) > 120 else task.transcript
                st.markdown(f"*{preview}*")

            if task.next_step:
                st.markdown(f"**→** {task.next_step}")

        with col_action:
            st.selectbox(
                "Status",
                ["pending", "in_progress", "done"],
                key=f"status_{task.id}",
                label_visibility="collapsed",
            )

        with st.expander("Details"):
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Transcript**")
                st.text(task.transcript)
            with d2:
                st.markdown("**Triage detail**")
                st.markdown(f"- Intents: `{intents_str}`")
                st.markdown(f"- Assigned to: `{task.assigned_to}`")
                st.markdown(f"- Urgency: `{task.urgency}`")
                if task.urgency_reason:
                    st.caption(task.urgency_reason)
                st.markdown(f"- Safety: `{task.safety_state}`")
                st.markdown(f"- Confidence: `{task.confidence}`")
                if task.review_reason:
                    st.markdown("**Review reason**")
                    st.markdown(task.review_reason)


# ── Pipeline (runs once per session) ─────────────────────────────────────────

if "tasks" not in st.session_state:
    with st.spinner("Running triage pipeline on overnight voicemails…"):
        raw = load_voicemails(str(CSV_PATH))
        st.session_state.tasks = run_pipeline(raw, verbose=False)

tasks: list[VoicemailTask] = st.session_state.tasks

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## 📋 Heidi Calls — Morning Briefing")
st.markdown(
    f"**Harbour to Sunset GP** · "
    f"{datetime.now().strftime('%A %d %b %Y')} · "
    f"{len(tasks)} voicemails overnight"
)

col_refresh, _ = st.columns([1, 5])
if col_refresh.button("↺ Re-run pipeline"):
    del st.session_state["tasks"]
    st.rerun()

st.divider()

# ── Summary strip ─────────────────────────────────────────────────────────────

n_urgent  = sum(1 for t in tasks if t.urgency in ("critical", "high"))
n_routine = len(tasks) - n_urgent
n_review  = sum(1 for t in tasks if t.needs_review)

c1, c2, c3, c4 = st.columns(4)
c1.metric("🔴 Attend now", n_urgent)
c2.metric("🔵 Routine",    n_routine)
c3.metric("⚠️ Needs review", n_review)
c4.metric("📬 Total",      len(tasks))

st.divider()

# ── Attend first ──────────────────────────────────────────────────────────────

urgent_tasks  = [t for t in tasks if t.urgency in ("critical", "high")]
routine_tasks = [t for t in tasks if t.urgency not in ("critical", "high")]

if urgent_tasks:
    st.markdown(f"### Attend first ({len(urgent_tasks)})")
    for task in urgent_tasks:
        render_card(task)
    st.divider()
else:
    st.success(
        f"Nothing flagged overnight. "
        f"All {len(tasks)} voicemails passed safety screening. ✓"
    )
    st.divider()

# ── All remaining calls, sorted by time ───────────────────────────────────────

if routine_tasks:
    st.markdown(f"### All calls ({len(routine_tasks)})")
    for task in routine_tasks:
        render_card(task)

# ── Sidebar: Simulation mode ──────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🧪 Simulation mode")
    st.caption("Paste any transcript to preview how the system would triage it.")

    sim_transcript  = st.text_area(
        "Transcript", height=150,
        placeholder="Hi, I've been having chest pain since this morning…"
    )
    caller_type_sim = st.selectbox("Caller type", ["patient", "healthcare_provider"])
    has_number      = st.checkbox("Has callback number (IVR completed)", value=True)

    if st.button("Analyse", use_container_width=True) and sim_transcript.strip():
        from src.workflow.task_model import VoicemailTask
        from src.safety.failure_cases import detect_failure_cases
        from src.safety.safety_screen import screen_for_safety
        from src.safety.context_check import check_safety_context
        from src.voicemail.extract_details import extract_details
        from src.safety.confidence import calculate_confidence

        sim_task = VoicemailTask(
            id="SIM-001",
            received_at=datetime.now(),
            location="simulation",
            duration_sec=0,
            transcript=sim_transcript.strip(),
            caller_type=caller_type_sim,
            callback_number="0400000000" if has_number else None,
        )

        with st.spinner("Analysing…"):
            detect_failure_cases(sim_task)
            if len(sim_task.transcript.split()) >= 5:
                flagged = screen_for_safety(sim_task)
                if flagged:
                    check_safety_context(sim_task)
                extract_details(sim_task)
                calculate_confidence(sim_task)

        st.divider()
        st.markdown("**Result**")
        st.markdown(f"- Intents: `{'  +  '.join(sim_task.intents)}`")
        st.markdown(f"- Urgency: `{sim_task.urgency}`")
        st.markdown(f"- Safety: `{sim_task.safety_state}`")
        st.markdown(f"- Confidence: `{sim_task.confidence}`")
        st.markdown(f"- Needs review: `{sim_task.needs_review}`")
        if sim_task.summary:
            st.markdown("**Summary**")
            st.markdown(sim_task.summary)
        if sim_task.next_step:
            st.markdown(f"**→** {sim_task.next_step}")

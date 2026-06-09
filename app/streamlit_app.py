import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.voicemail.load_voicemails import load_voicemails
from src.voicemail.triage_pipeline import run_pipeline
from src.policy.policy_router import assign_role
from src.workflow.task_model import VoicemailTask

st.set_page_config(page_title="Heidi Calls", layout="wide", page_icon="📋")

CSV_PATH = Path(__file__).parent.parent / "data" / "mock_voicemails.csv"

URGENCY_BADGE = {
    "critical": "🔴 CRITICAL",
    "high":     "🟠 HIGH",
    "normal":   "🔵 NORMAL",
    "low":      "⚫ LOW",
}
ROLE_LABEL = {
    "on_call_gp":    "On-Call GP",
    "gp":            "GP",
    "clinic-manager": "Clinic Manager",
    "admin":         "Admin",
}
STATUS_OPTIONS = ["pending", "in_progress", "done"]


# ── Pipeline ──────────────────────────────────────────────────────────────────

if "tasks" not in st.session_state:
    with st.spinner("Running triage pipeline on overnight voicemails…"):
        raw = load_voicemails(str(CSV_PATH))
        st.session_state.tasks = run_pipeline(raw, verbose=False)

if "status_map" not in st.session_state:
    st.session_state.status_map = {t.id: t.status for t in st.session_state.tasks}

tasks: list[VoicemailTask] = st.session_state.tasks
status_map: dict = st.session_state.status_map


def build_df(task_list: list[VoicemailTask]) -> pd.DataFrame:
    rows = []
    for t in task_list:
        rows.append({
            "_id":           t.id,
            "Time":          t.received_at.strftime("%H:%M"),
            "Urgency":       URGENCY_BADGE.get(t.urgency, t.urgency.upper()),
            "Safety":        t.safety_state,
            "Needs Review":  "Yes" if t.needs_review else "No",
            "Caller Type":   "Provider" if t.caller_type == "healthcare_provider" else "Patient",
            "Callback":      t.callback_number or "—",
            "Intents":       " + ".join(t.intents),
            "Summary":       (t.summary[:80] + "…") if len(t.summary) > 80 else t.summary,
            "Assigned":      ROLE_LABEL.get(t.assigned_to or "", t.assigned_to or "—"),
            "Status":        status_map.get(t.id, t.status),
        })
    return pd.DataFrame(rows)


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## 📋 Heidi Calls — Morning Briefing")
st.markdown(
    f"**Harbour to Sunset GP**  ·  "
    f"{datetime.now().strftime('%A %d %b %Y')}  ·  "
    f"{len(tasks)} voicemails overnight"
)

st.divider()

# ── Metrics ───────────────────────────────────────────────────────────────────

n_urgent     = sum(1 for t in tasks if t.urgency in ("critical", "high"))
n_review     = sum(1 for t in tasks if t.needs_review)
n_done       = sum(1 for t in tasks if status_map.get(t.id) == "done")
n_in_progress = sum(1 for t in tasks if status_map.get(t.id) == "in_progress")
n_pending    = sum(1 for t in tasks if status_map.get(t.id) == "pending")

r1c1, r1c2, r1c3 = st.columns(3)
r1c1.metric("🔴 Attend now",   n_urgent)
r1c2.metric("⚠️ Needs review", n_review)
r1c3.metric("📬 Total",        len(tasks))

r2c1, r2c2, r2c3 = st.columns(3)
r2c1.metric("🕐 Pending",      n_pending)
r2c2.metric("🔄 In Progress",  n_in_progress)
r2c3.metric("✅ Done",         n_done)

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────

URGENCY_ALL = ["critical", "high", "normal", "low"]
ROLE_ALL    = ["on_call_gp", "gp", "clinic-manager", "admin"]

with st.expander("🔍 Filters"):
    f1, f2, f3 = st.columns(3)
    with f1:
        filter_urgency = st.multiselect(
            "Urgency", URGENCY_ALL, default=URGENCY_ALL,
        )
    with f2:
        filter_role = st.multiselect(
            "Assigned to", ROLE_ALL, default=ROLE_ALL,
            format_func=lambda x: ROLE_LABEL.get(x, x),
        )
    with f3:
        filter_status = st.multiselect(
            "Status", STATUS_OPTIONS, default=STATUS_OPTIONS,
        )

filtered = [
    t for t in tasks
    if t.urgency in filter_urgency
    and (t.assigned_to or "admin") in filter_role
    and status_map.get(t.id, t.status) in filter_status
]

# ── Table ─────────────────────────────────────────────────────────────────────

df = build_df(filtered)
display_df = df.drop(columns=["_id"])

event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── Detail panel ──────────────────────────────────────────────────────────────

selected_rows = event.selection.rows
if selected_rows:
    row_idx = selected_rows[0]
    task_id = df.iloc[row_idx]["_id"]
    task = next(t for t in tasks if t.id == task_id)

    st.divider()
    header = URGENCY_BADGE.get(task.urgency, task.urgency.upper())
    if task.safety_state != "ROUTINE":
        header += f"  · Safety: {task.safety_state}"
    st.markdown(f"### {header}  ·  {task.id}  ·  {task.location.title()} Branch")

    col_left, col_right = st.columns([3, 1])

    with col_left:
        if task.summary:
            st.markdown("**Summary**")
            st.markdown(task.summary)
        if task.next_step:
            st.info(f"**→ Next step:** {task.next_step}")
        if task.urgency_reason:
            override_note = f" _(safety override: {task.safety_state})_" if task.safety_state in ("ACTIVE", "WATCH") else ""
            st.caption(f"Urgency reason: {task.urgency_reason}{override_note}")
        with st.expander("Transcript"):
            st.text(task.transcript)

    with col_right:
        st.markdown("**Triage**")
        st.markdown(f"- Intents: `{'  +  '.join(task.intents)}`")
        st.markdown(f"- Assigned: **{ROLE_LABEL.get(task.assigned_to or '', '—')}**")
        st.markdown(f"- Safety: `{task.safety_state}`")
        st.markdown(f"- Confidence: `{task.confidence:.2f}`")
        if task.review_reason:
            st.warning(task.review_reason)

        st.markdown("**Status**")
        current = status_map.get(task.id, task.status)
        new_status = st.selectbox(
            "status",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(current),
            key=f"detail_status_{task.id}",
            label_visibility="collapsed",
        )
        if new_status != current:
            st.session_state.status_map[task.id] = new_status
            st.rerun()

# ── Sidebar: Simulation mode ──────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🧪 Simulation mode")
    st.caption("Paste any transcript to preview how the system would triage it.")

    sim_transcript  = st.text_area(
        "Transcript", height=150,
        placeholder="Hi, I've been having chest pain since this morning…",
    )
    caller_type_sim = st.selectbox("Caller type", ["patient", "healthcare_provider"])
    has_number      = st.checkbox("Has callback number (IVR completed)", value=True)

    if st.button("Analyse", use_container_width=True) and sim_transcript.strip():
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
            assign_role(sim_task)

        st.divider()
        st.markdown("**Result**")
        st.markdown(f"- Intents: `{'  +  '.join(sim_task.intents)}`")
        st.markdown(f"- Urgency: `{sim_task.urgency}`")
        st.markdown(f"- Safety: `{sim_task.safety_state}`")
        st.markdown(f"- Assigned to: **{ROLE_LABEL.get(sim_task.assigned_to or '', '—')}**")
        st.markdown(f"- Confidence: `{sim_task.confidence:.2f}`")
        st.markdown(f"- Needs review: `{sim_task.needs_review}`")
        if sim_task.summary:
            st.markdown("**Summary**")
            st.markdown(sim_task.summary)
        if sim_task.next_step:
            st.info(f"**→** {sim_task.next_step}")

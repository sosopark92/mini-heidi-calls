import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.voicemail.load_voicemails import load_voicemails
# from src.voicemail.triage_pipeline import run_pipeline
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
URGENCY_OPTIONS = ["critical", "high", "normal", "low"]
ROLE_LABEL = {
    "gp":             "GP",
    "practice_nurse": "Practice Nurse",
    "clinic-manager": "Clinic Manager",
    "admin":          "Admin",
}
STATUS_OPTIONS = ["pending", "in_progress", "done"]


# ── Pipeline ──────────────────────────────────────────────────────────────────

if "tasks" not in st.session_state:
    # Load preprocessed demonstration results.
    # The live LLM pipeline remains available through Simulation mode.
    raw = load_voicemails(str(CSV_PATH))

    for task in raw:
        assign_role(task)

    st.session_state.tasks = raw

if "status_map" not in st.session_state:
    st.session_state.status_map = {t.id: t.status for t in st.session_state.tasks}

if "urgency_override_map" not in st.session_state:
    st.session_state.urgency_override_map = {}

tasks: list[VoicemailTask] = st.session_state.tasks
status_map: dict = st.session_state.status_map
urgency_override_map: dict = st.session_state.urgency_override_map

_FULL_COLS     = ["Time", "Location", "Urgency", "Safety", "Needs Review", "Caller Type",
                  "Callback", "Intents", "Summary", "Next Step", "Assigned", "Status"]

def build_df(task_list: list[VoicemailTask]) -> pd.DataFrame:
    rows = []
    for t in task_list:
        rows.append({
            "_id":          t.id,
            "Time":         t.received_at.strftime("%H:%M"),
            "Location":     t.location.title(),
            "Urgency":      URGENCY_BADGE.get(urgency_override_map.get(t.id, t.urgency), t.urgency.upper()),
            "Safety":       t.safety_state,
            "Needs Review": "⚠ Yes" if t.needs_review else "No",
            "Caller Type":  "Provider" if t.caller_type == "healthcare_provider" else "Patient",
            "Callback":     t.callback_number or "—",
            "Intents":      " + ".join(t.intents),
            "Summary":      (t.summary[:80] + "…") if len(t.summary) > 80 else t.summary,
            "Next Step":    (t.next_step[:60] + "…") if len(t.next_step) > 60 else t.next_step,
            "Assigned":     ROLE_LABEL.get(t.assigned_to or "", t.assigned_to or "—"),
            "Status":       status_map.get(t.id, t.status),
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

# ── Filters ───────────────────────────────────────────────────────────────────

URGENCY_ALL = ["critical", "high", "normal", "low"]
ROLE_ALL    = ["gp", "practice_nurse", "clinic-manager", "admin"]
INTENT_ALL  = [
    "prescription_repeat", "appointment_booking", "appointment_reschedule",
    "test_results", "medication_concern", "referral_request",
    "complaint", "general_enquiry", "unclear",
]
INTENT_LABEL = {
    "prescription_repeat":    "Repeat Script",
    "appointment_booking":    "Appointment Booking",
    "appointment_reschedule": "Appointment Reschedule",
    "test_results":           "Test Results",
    "medication_concern":     "Medication Concern",
    "referral_request":       "Referral",
    "complaint":              "Complaint",
    "general_enquiry":        "General Enquiry",
    "unclear":                "Unclear",
}

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
    f4, _ = st.columns([1, 2])
    with f4:
        filter_intent = st.multiselect(
            "Intent", INTENT_ALL, default=INTENT_ALL,
            format_func=lambda x: INTENT_LABEL.get(x, x),
        )

filtered = [
    t for t in tasks
    if urgency_override_map.get(t.id, t.urgency) in filter_urgency
    and (t.assigned_to or "admin") in filter_role
    and status_map.get(t.id, t.status) in filter_status
    and any(i in filter_intent for i in t.intents)
]

# ── Table ─────────────────────────────────────────────────────────────────────

def render_metrics(task_list: list[VoicemailTask]):
    n_urgent      = sum(1 for t in task_list if urgency_override_map.get(t.id, t.urgency) in ("critical", "high"))
    n_review      = sum(1 for t in task_list if t.needs_review)
    n_done        = sum(1 for t in task_list if status_map.get(t.id, t.status) == "done")
    n_in_progress = sum(1 for t in task_list if status_map.get(t.id, t.status) == "in_progress")
    n_pending     = sum(1 for t in task_list if status_map.get(t.id, t.status) == "pending")

    r1c1, r1c2, r1c3 = st.columns(3)
    r1c1.metric("🔴 Attend now",   n_urgent)
    r1c2.metric("⚠️ Needs review", n_review)
    r1c3.metric("📬 Showing",      len(task_list))

    r2c1, r2c2, r2c3 = st.columns(3)
    r2c1.metric("🕐 Pending",      n_pending)
    r2c2.metric("🔄 In Progress",  n_in_progress)
    r2c3.metric("✅ Done",         n_done)

view_mode = st.radio(
    "View",
    ["Full", "Workflow"],
    horizontal=True,
    help="Full: all fields · Workflow: grouped by action type",
)

_COLS_MAP = {"Full": _FULL_COLS}

_WORKFLOW_GROUPS = [
    (
        "🚨 Attend First",
        "Call back immediately — connect to GP or nurse on duty",
        lambda t: t.urgency == "critical",
    ),
    (
        "📞 Call Back Today",
        "Review with GP first, then call back and offer same-day appointment",
        lambda t: t.urgency == "high",
    ),
    (
        "💊 Repeat Scripts",
        "Process together — forward to GP for authorisation",
        lambda t: "prescription_repeat" in t.intents,
    ),
    (
        "📅 Appointments",
        "Book or reschedule via standard booking system",
        lambda t: any(i in ("appointment_booking", "appointment_reschedule") for i in t.intents),
    ),
    (
        "📋 Admin & Other",
        "Handle directly or leave message for appropriate staff",
        lambda t: t.urgency == "normal" and "unclear" not in t.intents,
    ),
    (
        "⚪ Low Priority / Unclear",
        "Cannot be acted on without further information — set aside for GP review",
        lambda t: True,
    ),
]

_WF_COLS = ["Time", "Location", "Urgency", "Intents", "Callback", "Assigned", "Status"]

tab_all, tab_harbour, tab_sunset, tab_needs_review = st.tabs(["📋 All", "🏠 Harbour", "🌅 Sunset", "⚠️ Needs Review"])


def render_table(task_list):
    df = build_df(task_list)
    display_df = df[_COLS_MAP.get(view_mode, _FULL_COLS)]
    return df, st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )


def render_workflow(task_list: list[VoicemailTask], tab_key: str):
    """Render tasks grouped by action type. Returns (active_df, active_event) for detail panel."""
    assigned_ids: set[str] = set()
    result_df = None
    result_event = None

    for gi, (title, description, condition) in enumerate(_WORKFLOW_GROUPS):
        group_tasks = [t for t in task_list if condition(t) and t.id not in assigned_ids]
        for t in group_tasks:
            assigned_ids.add(t.id)

        count = len(group_tasks)
        st.markdown(f"#### {title} &nbsp;&nbsp; `{count} task{'s' if count != 1 else ''}`")
        st.caption(description)

        if not group_tasks:
            st.success("Nothing here ✓")
        else:
            gdf = build_df(group_tasks)
            display = gdf[[c for c in _WF_COLS if c in gdf.columns]]
            ev = st.dataframe(
                display,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"wf_{tab_key}_{gi}",
            )
            if ev.selection.rows and result_event is None:
                result_df = gdf
                result_event = ev

        if gi < len(_WORKFLOW_GROUPS) - 1:
            st.divider()

    return result_df, result_event


active_df = build_df(filtered)
active_event = None

with tab_harbour:
    harbour_tasks = [t for t in filtered if t.location == "harbour"]
    render_metrics(harbour_tasks)
    st.divider()
    if view_mode == "Workflow":
        wf_df, wf_event = render_workflow(harbour_tasks, "harbour")
        if wf_df is not None:
            active_df, active_event = wf_df, wf_event
    else:
        h_df, h_event = render_table(harbour_tasks)
        if h_event.selection.rows:
            active_df, active_event = h_df, h_event

with tab_sunset:
    sunset_tasks = [t for t in filtered if t.location == "sunset"]
    render_metrics(sunset_tasks)
    st.divider()
    if view_mode == "Workflow":
        wf_df, wf_event = render_workflow(sunset_tasks, "sunset")
        if wf_df is not None:
            active_df, active_event = wf_df, wf_event
    else:
        s_df, s_event = render_table(sunset_tasks)
        if s_event.selection.rows:
            active_df, active_event = s_df, s_event

with tab_all:
    render_metrics(filtered)
    st.divider()
    if view_mode == "Workflow":
        wf_df, wf_event = render_workflow(filtered, "all")
        if wf_df is not None:
            active_df, active_event = wf_df, wf_event
    else:
        a_df, a_event = render_table(filtered)
        if a_event.selection.rows:
            active_df, active_event = a_df, a_event

with tab_needs_review:
    review_tasks = [t for t in filtered if t.needs_review]
    render_metrics(review_tasks)
    st.divider()
    if view_mode == "Workflow":
        wf_df, wf_event = render_workflow(review_tasks, "review")
        if wf_df is not None:
            active_df, active_event = wf_df, wf_event
    else:
        r_df, r_event = render_table(review_tasks)
        if r_event.selection.rows:
            active_df, active_event = r_df, r_event

# ── Detail panel ──────────────────────────────────────────────────────────────

selected_rows = active_event.selection.rows if active_event else []
if selected_rows:
    row_idx = selected_rows[0]
    task_id = active_df.iloc[row_idx]["_id"]
    task = next(t for t in tasks if t.id == task_id)

    st.divider()
    current_urgency = urgency_override_map.get(task.id, task.urgency)
    header = URGENCY_BADGE.get(current_urgency, current_urgency.upper())
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

        st.markdown("**Urgency**")
        current_urgency = urgency_override_map.get(task.id, task.urgency)
        new_urgency = st.selectbox(
            "urgency",
            URGENCY_OPTIONS,
            index=URGENCY_OPTIONS.index(current_urgency),
            key=f"detail_urgency_{task.id}",
            label_visibility="collapsed",
        )
        if new_urgency != current_urgency:
            st.session_state.urgency_override_map[task.id] = new_urgency
            st.rerun()

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
            try:
                detect_failure_cases(sim_task)

                if len(sim_task.transcript.split()) >= 5:
                    flagged = screen_for_safety(sim_task)

                    if flagged:
                        check_safety_context(sim_task)

                    extract_details(sim_task)

                calculate_confidence(sim_task)
                assign_role(sim_task)

            except Exception as exc:
                st.error(
                    "The live AI service is temporarily unavailable. "
                    "Please wait briefly and try again."
                )
                st.caption(f"Technical error: {type(exc).__name__}")
                st.stop()

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

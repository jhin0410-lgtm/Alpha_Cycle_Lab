from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request

DEFAULT_ARTIFACT_ROOT = os.environ.get(
    "ALPHA_CYCLE_ARTIFACT_ROOT",
    str(Path.cwd() / ".alpha_cycle_artifacts"),
)


def _new_request_id(now: datetime) -> str:
    return f"request-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"


def main() -> None:
    st.set_page_config(page_title="Research Request — Alpha Cycle Lab", page_icon="📝")
    st.title("Research Request Intake")
    st.caption(
        "Records an immutable research request only. It does not run research, create a thesis, "
        "change a position, or execute a trade."
    )

    now = datetime.now().astimezone()
    if "alpha_cycle_request_id" not in st.session_state:
        st.session_state.alpha_cycle_request_id = _new_request_id(now)

    artifact_root = st.text_input("Artifact root", value=DEFAULT_ARTIFACT_ROOT)
    request_id = st.text_input("Request ID", value=st.session_state.alpha_cycle_request_id)
    securities_text = st.text_input("Securities", value="000660,005930")
    evaluation_date = st.date_input("Evaluation date", value=now.date())
    horizon = st.selectbox("Horizon (trading days)", options=(60, 120, 250), index=1)
    mode_value = st.selectbox(
        "Mode",
        options=tuple(item.value for item in ResearchRoundMode),
        index=0,
    )
    lane_value = st.selectbox(
        "Requested lane",
        options=tuple(item.value for item in UnderwritingLane),
        index=1,
    )
    request_text = st.text_area(
        "Research request",
        value="Compare the requested securities using the current PIT research framework.",
    )
    tags_text = st.text_input("Tags (comma separated)", value="")

    if not st.button("Record immutable request", type="primary"):
        return

    securities = tuple(
        item.strip() for item in securities_text.split(",") if item.strip()
    )
    tags = tuple(item.strip() for item in tags_text.split(",") if item.strip())
    if not securities:
        st.error("At least one security is required.")
        return

    try:
        receipt = record_analysis_request(
            request_id=request_id,
            requested_at=now,
            recorded_at=datetime.now().astimezone(),
            evaluation_date=evaluation_date,
            horizon_trading_days=horizon,
            security_ids=securities,
            mode=ResearchRoundMode(mode_value),
            requested_lane=UnderwritingLane(lane_value),
            request_text=request_text,
            artifact_root=artifact_root,
            tags=tags,
        )
    except (ValueError, FileExistsError) as exc:
        st.error("Research request was not recorded.")
        st.code(str(exc))
        return

    st.success("Request recorded. The Observatory will show it as request_pending.")
    st.json(receipt.payload())
    st.info(
        "No research result was fabricated. A later typed execution step must bind this request "
        "to a ResearchRoundSnapshot or record explicit pre-orchestration blockers."
    )
    st.session_state.alpha_cycle_request_id = _new_request_id(datetime.now().astimezone())


if __name__ == "__main__":
    main()

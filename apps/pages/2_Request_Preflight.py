from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.research_observatory_v2_1 import (
    ObservatoryDataError,
    load_latest_observatory_state,
)
from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses

DEFAULT_ARTIFACT_ROOT = os.environ.get(
    "ALPHA_CYCLE_ARTIFACT_ROOT",
    str(Path.cwd() / ".alpha_cycle_artifacts"),
)


def main() -> None:
    st.set_page_config(page_title="Request Preflight — Alpha Cycle Lab", page_icon="🔎")
    st.title("Typed Thesis Preflight")
    st.caption(
        "Checks recorded requests against validated persisted InvestmentThesisSnapshot artifacts. "
        "It does not create a thesis or execute the research-round orchestrator."
    )
    artifact_root = st.text_input("Artifact root", value=DEFAULT_ARTIFACT_ROOT)
    try:
        state = load_latest_observatory_state(artifact_root)
    except (ObservatoryDataError, ValueError) as exc:
        st.error("Cannot load the latest validated Research Run Ledger.")
        st.code(str(exc))
        return
    if state is None or not state.ledger.requests:
        st.info("Record a research request first.")
        return

    requests = tuple(reversed(state.ledger.requests))
    request_by_label = {
        (
            f"{item.request_id} | {','.join(item.security_ids)} | "
            f"{item.horizon_trading_days}D | {item.requested_at.isoformat()}"
        ): item
        for item in requests
    }
    selected_label = st.selectbox("Research request", tuple(request_by_label))
    selected = request_by_label[selected_label]
    st.write("**Request text**", selected.request_text)
    st.write("**Mode / lane**", f"{selected.mode.value} / {selected.requested_lane.value}")
    st.write("**Evaluation date**", selected.evaluation_date.isoformat())

    replay_cutoff_text = ""
    if selected.mode is ResearchRoundMode.REPLAY:
        replay_cutoff_text = st.text_input(
            "Replay research cutoff (ISO 8601 with timezone)",
            placeholder="2026-06-30T15:00:00+09:00",
            help=(
                "Required for replay. Only thesis artifacts captured at or before this PIT cutoff "
                "can satisfy preflight."
            ),
        )
    else:
        st.caption("Prospective research cutoff defaults to the preflight processing time.")

    if not st.button("Run typed thesis preflight", type="primary"):
        return

    now = datetime.now().astimezone()
    research_cutoff_at: datetime | None = None
    if selected.mode is ResearchRoundMode.REPLAY:
        if not replay_cutoff_text.strip():
            st.error("Replay preflight requires an explicit research cutoff.")
            return
        try:
            research_cutoff_at = datetime.fromisoformat(replay_cutoff_text.strip())
        except ValueError:
            st.error("Replay research cutoff must be a valid ISO 8601 datetime.")
            return
        if research_cutoff_at.tzinfo is None or research_cutoff_at.utcoffset() is None:
            st.error("Replay research cutoff must include a timezone offset.")
            return

    run_id = f"thesis-preflight-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"
    try:
        receipt = preflight_pending_request_theses(
            request_id=selected.request_id,
            run_id=run_id,
            processed_at=now,
            artifact_root=artifact_root,
            research_cutoff_at=research_cutoff_at,
        )
    except (ValueError, FileExistsError) as exc:
        st.error("Typed thesis preflight failed closed.")
        st.code(str(exc))
        return

    st.write("**Research cutoff**", receipt.research_cutoff_at.isoformat())
    if receipt.ready_for_package_assembly:
        st.success("Typed thesis preflight passed for every requested security.")
        st.info(
            "This does not mean the research round is ready. Underwriting, payoff, expectation, "
            "and other typed package inputs still require separate validation."
        )
    elif receipt.changed_history:
        st.warning("Missing typed thesis evidence was recorded as a pre-orchestration blocker.")
    else:
        st.info("The same thesis blockers were already recorded; history was not duplicated.")
    st.json(receipt.payload())


if __name__ == "__main__":
    main()

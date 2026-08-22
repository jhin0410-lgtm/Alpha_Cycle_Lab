"""Read-only Streamlit control room for Alpha Cycle Lab research observability."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from alpha_cycle.research_observatory_v2_1 import (
    ObservatoryDataError,
    ResearchObservatoryState,
    load_latest_observatory_state,
)

DEFAULT_ARTIFACT_ROOT = os.environ.get(
    "ALPHA_CYCLE_ARTIFACT_ROOT",
    str(Path.cwd() / ".alpha_cycle_artifacts"),
)


def main() -> None:
    st.set_page_config(
        page_title="Alpha Cycle Lab — Research Observatory",
        page_icon="🔬",
        layout="wide",
    )
    st.title("Alpha Cycle Lab — Research Observatory")
    st.caption(
        "Point-in-time research operations, blockers, history, and process learning. "
        "Read-only: no investment logic, sizing, or execution lives in this UI."
    )

    artifact_root = st.sidebar.text_input("Artifact root", value=DEFAULT_ARTIFACT_ROOT)
    st.sidebar.caption(
        "Runtime artifacts may contain private request text. Keep this directory local/private."
    )
    if st.sidebar.button("Reload", type="secondary"):
        st.rerun()

    try:
        state = load_latest_observatory_state(artifact_root)
    except ObservatoryDataError as exc:
        st.error("Research ledger integrity validation failed.")
        st.code(str(exc))
        st.stop()
    except ValueError as exc:
        st.error("Research ledger typed-contract validation failed.")
        st.code(str(exc))
        st.stop()

    if state is None:
        _render_empty_state(Path(artifact_root))
        return

    _render_header_metrics(state)
    inbox_tab, blockers_tab, history_tab, learning_tab, health_tab = st.tabs(
        [
            "Research Inbox",
            "Blocker Inspector",
            "Analysis History",
            "Learning Observatory",
            "System Health",
        ]
    )
    with inbox_tab:
        _render_inbox(state)
    with blockers_tab:
        _render_blockers(state)
    with history_tab:
        _render_history(state)
    with learning_tab:
        _render_learning(state)
    with health_tab:
        _render_health(state)


def _render_empty_state(artifact_root: Path) -> None:
    st.info("No persisted Research Run Ledger is available yet.")
    st.write(
        "The Observatory intentionally does not invent demo investment results. "
        "Record an AnalysisRequestSnapshot / ResearchRoundRunSnapshot and persist a ledger "
        "under the artifact root to populate this control room."
    )
    st.code(str(artifact_root / "research_run_ledger_v2_1"))
    st.warning(
        "Predictive and investment-performance learning is unavailable until genuine "
        "prospective outcomes exist."
    )


def _render_header_metrics(state: ResearchObservatoryState) -> None:
    summary = state.ledger.summary
    columns = st.columns(5)
    columns[0].metric("Research requests", summary.request_count)
    columns[1].metric("Runs", summary.run_count)
    columns[2].metric("Blocked runs", summary.blocked_run_count)
    columns[3].metric("Prospective registered", summary.prospective_registered_run_count)
    columns[4].metric("Securities observed", summary.unique_security_count)


def _render_inbox(state: ResearchObservatoryState) -> None:
    st.subheader("Research Inbox")
    st.caption(
        "Latest operating state by security. This is a research-priority view, not a buy list."
    )
    if not state.inbox:
        st.info("No research requests are recorded in this ledger.")
        return
    rows = [item.payload() for item in state.inbox]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    security_ids = [item.security_id for item in state.inbox]
    selected = st.selectbox("Inspect latest security state", security_ids)
    row = next(item for item in state.inbox if item.security_id == selected)
    left, right = st.columns(2)
    with left:
        st.write("**State**", row.state)
        st.write("**Requested lane**", row.requested_lane.value)
        st.write("**Mode**", row.mode.value)
        st.write("**Blockers**", row.blocker_count)
    with right:
        st.write("**Opportunity set**", _yes_no(row.opportunity_set_available))
        st.write("**Expectation overlay**", _yes_no(row.expectation_overlay_available))
        st.write("**Prospective registration**", _yes_no(row.prospective_registered))
        st.write("**Latest request**", row.latest_request_at.isoformat())

    matching = [
        blocker.payload()
        for blocker in state.blockers
        if blocker.security_id in {None, selected}
    ]
    if matching:
        st.markdown("#### Relevant blocker history")
        st.dataframe(pd.DataFrame(matching), use_container_width=True, hide_index=True)


def _render_blockers(state: ResearchObservatoryState) -> None:
    st.subheader("Blocker Inspector")
    st.caption(
        "Structured reasons why research could not progress. Missing evidence is never "
        "neutralized into a favorable decision."
    )
    if not state.blockers:
        st.success("No blockers are recorded in the current ledger history.")
        return
    rows = [item.payload() for item in state.blockers]
    frame = pd.DataFrame(rows)
    components = ["All", *sorted(frame["component"].dropna().unique().tolist())]
    selected_component = st.selectbox("Component", components)
    if selected_component != "All":
        frame = frame[frame["component"] == selected_component]
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_history(state: ResearchObservatoryState) -> None:
    st.subheader("Analysis History")
    st.caption("Newest completed run first. Historical requests/runs are append-only artifacts.")
    if not state.history:
        st.info("No completed runs are recorded yet.")
        return
    frame = pd.DataFrame([item.payload() for item in state.history])
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_learning(state: ResearchObservatoryState) -> None:
    st.subheader("Learning Observatory")
    summary = state.ledger.summary
    st.markdown("#### Research-process learning — available now")
    left, middle, right = st.columns(3)
    blocked_rate = (
        summary.blocked_run_count / summary.run_count if summary.run_count else None
    )
    left.metric(
        "Blocked-run share",
        _percent_or_na(blocked_rate),
        help="Operational completeness metric, not investment performance.",
    )
    middle.metric(
        "Mean blockers / run",
        _number_or_na(summary.mean_blockers_per_run),
    )
    right.metric(
        "Median run seconds",
        _number_or_na(summary.median_duration_seconds),
    )

    blocker_codes = pd.DataFrame(
        summary.blocker_code_counts,
        columns=["blocker_code", "count"],
    )
    if not blocker_codes.empty:
        st.markdown("#### Repeated research bottlenecks")
        st.bar_chart(blocker_codes.set_index("blocker_code"))

    st.markdown("#### Forecast / investment-decision learning")
    st.info(
        "Not inferred from the Research Run Ledger. Forecast accuracy, calibration, decision "
        "relevance, information gain, realized opportunity regret, and competence require "
        "separate genuine prospective outcome records. No composite performance score is "
        "manufactured here."
    )


def _render_health(state: ResearchObservatoryState) -> None:
    st.subheader("System Health")
    health = state.health_payload()
    st.json(health)
    st.markdown("#### Ledger summary")
    st.json(state.ledger.summary.payload())
    st.caption(
        "The loader revalidates filename identity, content hash, child snapshot identities, "
        "typed invariants, and recomputed summary before rendering."
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _percent_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def _number_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from test_research_model_runtime_v1 import pack

from alpha_cycle.intelligence.outcome_learning_v1 import (
    AuthenticatedOutcomeLink,
    DecisionAction,
    DecisionMemory,
    ErrorContribution,
    ErrorDomain,
    build_outcome_learning_record,
)

H = "a" * 64


def outcome() -> AuthenticatedOutcomeLink:
    return AuthenticatedOutcomeLink(
        H,
        "b" * 64,
        "c" * 64,
        "000660:op_profit:2026Q3",
        ("d" * 64,),
        True,
        datetime(2026, 11, 1, tzinfo=UTC),
    )


def errors() -> tuple[ErrorContribution, ...]:
    return (
        ErrorContribution(
            ErrorDomain.TRANSMISSION,
            "inconsistent",
            "ASP-to-margin transmission lagged the pack hypothesis",
            ("d" * 64,),
        ),
    )


def decision() -> DecisionMemory:
    return DecisionMemory(
        H,
        H,
        H,
        H,
        pack().content_id,
        DecisionAction.OBSERVE,
        "uncertain",
        ("Monitor evidence",),
        ("Inventory turns",),
        "3m",
        datetime(2026, 9, 2, tzinfo=UTC),
    )


def test_authenticated_outcome_creates_prospective_revision_without_mutation() -> None:
    parent = pack()
    record = build_outcome_learning_record(
        outcome=outcome(),
        errors=errors(),
        decision=decision(),
        revision_parent=parent,
        proposed_version="2026.09.2",
    )
    assert record.revision_proposal is not None
    assert record.revision_proposal.parent_content_id == parent.content_id
    assert record.revision_proposal.proposed_version == "2026.09.2"
    assert record.outcome.authenticated
    assert parent.content_id == pack().content_id
    assert record.payload()["record_id"] == record.record_id


def test_optional_decision_memory_can_be_absent() -> None:
    record = build_outcome_learning_record(outcome=outcome(), errors=errors())
    assert record.decision is None
    assert record.revision_proposal is None


@pytest.mark.parametrize(
    "mutation", ["not_authenticated", "bad_source", "bad_registration", "naive_time"]
)
def test_untrusted_outcome_is_rejected(mutation: str) -> None:
    with pytest.raises(ValueError):
        value = outcome()
        if mutation == "not_authenticated":
            value = replace(value, authenticated=False)
        elif mutation == "bad_source":
            value = replace(value, source_evidence_ids=("not-sha",))
        elif mutation == "bad_registration":
            value = replace(value, registration_snapshot_id="not-sha")
        else:
            value = replace(value, observed_at=datetime(2026, 11, 1))
        build_outcome_learning_record(outcome=value, errors=errors())


def test_decision_cannot_bind_different_forecast() -> None:
    with pytest.raises(ValueError, match="registration"):
        build_outcome_learning_record(
            outcome=outcome(),
            errors=errors(),
            decision=replace(decision(), research_package_id="e" * 64),
        )


def test_revision_needs_explicit_errors_and_version() -> None:
    with pytest.raises(ValueError, match="error decomposition"):
        build_outcome_learning_record(outcome=outcome(), errors=())
    with pytest.raises(ValueError, match="proposed version"):
        build_outcome_learning_record(outcome=outcome(), errors=errors(), revision_parent=pack())


def test_single_outcome_does_not_claim_causality() -> None:
    record = build_outcome_learning_record(
        outcome=outcome(), errors=errors(), revision_parent=pack(), proposed_version="2"
    )
    assert "causal" in record.revision_proposal.risks[0]

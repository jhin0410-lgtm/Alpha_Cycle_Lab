"""Market, research, valuation, and investment decision intelligence snapshots.

The final package decision wrapper preserves the calibrated chain through
``decision_industry_evidence_calibrated``, ``decision_forward_estimate_calibrated``,
``decision_historical_pb_calibrated``, ``decision_sector_vertical_calibrated``,
``decision_semiconductor_transmission_calibrated``,
``decision_semiconductor_structural_calibrated``,
``decision_macro_liquidity_calibrated``,
``decision_semiconductor_forward_input_calibrated``,
``decision_semiconductor_operating_assumption_calibrated``,
``decision_semiconductor_baseline_reconciliation_calibrated``,
``decision_semiconductor_accounting_identity_calibrated``,
``decision_expectation_gap_calibrated``, ``decision_catalyst_horizon_calibrated``,
and finally ``decision_scenario_expected_return_calibrated``. These
evidence/readiness layers remain non-scoring: missing evidence is surfaced as a
research gap rather than converted into a zero factor score. Valuation still
passes through ``valuation_resilient`` before the final latest-observable-equity
P/B correction.
"""

from alpha_cycle.intelligence.decision import (
    InvestmentDecisionSnapshot,
    write_investment_decision_snapshot,
)
from alpha_cycle.intelligence.decision_provenance import (
    DecisionEvidenceEnvelope,
    build_decision_evidence_envelope,
    write_decision_evidence_envelope,
)
from alpha_cycle.intelligence.decision_scenario_expected_return_calibrated import (
    build_investment_decision_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import (
    CompanyExposure,
    DecisionPolicy,
    load_company_exposures,
)
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroSnapshot,
    write_fundamental_macro_snapshot,
)
from alpha_cycle.intelligence.fundamental_macro_priority_documents import (
    FundamentalMacroCollector,
)
from alpha_cycle.intelligence.market import (
    MarketIntelligenceCollector,
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
    load_market_consistency_provenance,
)
from alpha_cycle.intelligence.outcomes import label_decision_outcomes, write_outcome_labels
from alpha_cycle.intelligence.technical import TechnicalFeatures, calculate_technical_features
from alpha_cycle.intelligence.valuation import (
    CompanySecurityMapping,
    ValuationEvidenceSnapshot,
    build_financial_history,
    load_security_mappings,
    write_valuation_evidence_snapshot,
)
from alpha_cycle.intelligence.valuation_latest_equity_resilient import (
    build_valuation_evidence_snapshot,
)

__all__ = [
    "CompanyExposure",
    "CompanySecurityMapping",
    "DecisionEvidenceEnvelope",
    "DecisionPolicy",
    "FundamentalMacroCollector",
    "FundamentalMacroSnapshot",
    "InvestmentDecisionSnapshot",
    "MarketConsistencyProvenance",
    "MarketIntelligenceCollector",
    "MarketIntelligenceSnapshot",
    "TechnicalFeatures",
    "ValuationEvidenceSnapshot",
    "build_decision_evidence_envelope",
    "build_financial_history",
    "build_investment_decision_snapshot",
    "build_valuation_evidence_snapshot",
    "calculate_technical_features",
    "label_decision_outcomes",
    "load_company_exposures",
    "load_market_consistency_provenance",
    "load_security_mappings",
    "write_decision_evidence_envelope",
    "write_fundamental_macro_snapshot",
    "write_investment_decision_snapshot",
    "write_market_intelligence_snapshot",
    "write_outcome_labels",
    "write_valuation_evidence_snapshot",
]

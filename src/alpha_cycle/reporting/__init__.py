"""Metrics, attribution, and output writers."""

from alpha_cycle.reporting.attribution import (
    AlignmentPolicy,
    AttributionResult,
    CsvBenchmarkReturnsAdapter,
    CsvFactorReturnsAdapter,
    analyze_attribution,
    calculate_benchmark_metrics,
    calculate_factor_attribution,
    validate_benchmark_returns,
    validate_factor_returns,
)
from alpha_cycle.reporting.metrics import calculate_metrics
from alpha_cycle.reporting.writer import write_outputs

__all__ = [
    "AlignmentPolicy",
    "AttributionResult",
    "CsvBenchmarkReturnsAdapter",
    "CsvFactorReturnsAdapter",
    "analyze_attribution",
    "calculate_benchmark_metrics",
    "calculate_factor_attribution",
    "calculate_metrics",
    "validate_benchmark_returns",
    "validate_factor_returns",
    "write_outputs",
]

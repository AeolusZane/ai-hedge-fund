"""Anomaly detection for workflow execution.

Monitors execution metrics and flags anomalies:
- Execution time exceeding thresholds
- Low confidence scores in analysis
- Token usage exceeding limits
- Error patterns
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# Default thresholds
DEFAULT_THRESHOLDS = {
    # Per-stage execution time (seconds)
    "stage_timeout_seconds": 300,  # 5 minutes
    # Total workflow execution time (seconds)
    "workflow_timeout_seconds": 1800,  # 30 minutes
    # Token usage limits per run
    "max_input_tokens": 500_000,
    "max_output_tokens": 100_000,
    # Cost limit per run (USD)
    "max_cost_usd": 5.0,
    # Confidence threshold (below this = anomaly)
    "min_confidence": 0.4,
}


@dataclass
class Anomaly:
    """A detected anomaly in workflow execution."""
    type: str  # "timeout" | "low_confidence" | "token_limit" | "cost_limit" | "error_pattern"
    severity: str  # "warning" | "critical"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class AnomalyDetector:
    """Detects anomalies in workflow execution metrics."""

    def __init__(self, thresholds: dict[str, Any] | None = None):
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.anomalies: list[Anomaly] = []
        self._stage_start_times: dict[str, float] = {}

    def mark_stage_start(self, node_id: str) -> None:
        """Record when a stage starts executing."""
        self._stage_start_times[node_id] = time.time()

    def check_stage_timeout(self, node_id: str, stage_name: str) -> Anomaly | None:
        """Check if a stage has exceeded its timeout."""
        start_time = self._stage_start_times.get(node_id)
        if start_time is None:
            return None

        elapsed = time.time() - start_time
        timeout = self.thresholds["stage_timeout_seconds"]

        if elapsed > timeout:
            anomaly = Anomaly(
                type="timeout",
                severity="warning",
                message=f"Stage '{stage_name}' exceeded {timeout}s timeout ({elapsed:.1f}s elapsed)",
                details={
                    "node_id": node_id,
                    "stage_name": stage_name,
                    "elapsed_seconds": round(elapsed, 1),
                    "threshold_seconds": timeout,
                },
            )
            self.anomalies.append(anomaly)
            return anomaly
        return None

    def check_confidence(self, node_id: str, stage_name: str, confidence: float) -> Anomaly | None:
        """Check if confidence score is below threshold."""
        min_confidence = self.thresholds["min_confidence"]

        if confidence < min_confidence:
            anomaly = Anomaly(
                type="low_confidence",
                severity="warning",
                message=f"Stage '{stage_name}' has low confidence ({confidence:.0%} < {min_confidence:.0%})",
                details={
                    "node_id": node_id,
                    "stage_name": stage_name,
                    "confidence": confidence,
                    "threshold": min_confidence,
                },
            )
            self.anomalies.append(anomaly)
            return anomaly
        return None

    def check_token_usage(self, token_usage: dict[str, Any]) -> list[Anomaly]:
        """Check if token usage exceeds limits."""
        anomalies = []

        total_input = token_usage.get("total_input_tokens", 0)
        total_output = token_usage.get("total_output_tokens", 0)
        total_cost = token_usage.get("total_cost_usd", 0.0)

        max_input = self.thresholds["max_input_tokens"]
        max_output = self.thresholds["max_output_tokens"]
        max_cost = self.thresholds["max_cost_usd"]

        if total_input > max_input:
            anomaly = Anomaly(
                type="token_limit",
                severity="warning",
                message=f"Input tokens ({total_input:,}) exceeded limit ({max_input:,})",
                details={
                    "total_input_tokens": total_input,
                    "threshold": max_input,
                },
            )
            anomalies.append(anomaly)
            self.anomalies.append(anomaly)

        if total_output > max_output:
            anomaly = Anomaly(
                type="token_limit",
                severity="warning",
                message=f"Output tokens ({total_output:,}) exceeded limit ({max_output:,})",
                details={
                    "total_output_tokens": total_output,
                    "threshold": max_output,
                },
            )
            anomalies.append(anomaly)
            self.anomalies.append(anomaly)

        if total_cost > max_cost:
            anomaly = Anomaly(
                type="cost_limit",
                severity="critical",
                message=f"Cost (${total_cost:.2f}) exceeded limit (${max_cost:.2f})",
                details={
                    "total_cost_usd": total_cost,
                    "threshold_usd": max_cost,
                },
            )
            anomalies.append(anomaly)
            self.anomalies.append(anomaly)

        return anomalies

    def check_error_pattern(self, result: dict[str, Any]) -> Anomaly | None:
        """Check for error patterns in the result."""
        error_keys = [k for k in result.keys() if k.endswith("_error") and result[k]]

        if len(error_keys) >= 2:
            anomaly = Anomaly(
                type="error_pattern",
                severity="critical",
                message=f"Multiple stages failed: {', '.join(error_keys)}",
                details={
                    "error_count": len(error_keys),
                    "error_keys": error_keys,
                },
            )
            self.anomalies.append(anomaly)
            return anomaly
        return None

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all detected anomalies."""
        if not self.anomalies:
            return {"anomaly_count": 0, "anomalies": []}

        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}

        for a in self.anomalies:
            by_type[a.type] = by_type.get(a.type, 0) + 1
            by_severity[a.severity] = by_severity.get(a.severity, 0) + 1

        return {
            "anomaly_count": len(self.anomalies),
            "by_type": by_type,
            "by_severity": by_severity,
            "anomalies": [
                {
                    "type": a.type,
                    "severity": a.severity,
                    "message": a.message,
                    "details": a.details,
                    "timestamp": a.timestamp,
                }
                for a in self.anomalies
            ],
        }

from datetime import datetime, timedelta, timezone
from typing import Optional

from models import PixAnalysis, PixAnalysisRuleHit


def isoformat_in_transaction_offset(moment: Optional[datetime], analysis: PixAnalysis) -> Optional[str]:
    if moment is None:
        return None

    return moment.astimezone(timezone(timedelta(minutes=analysis.transaction_utc_offset_minutes))).isoformat()


def rule_hit_response(rule_hit: PixAnalysisRuleHit) -> dict:
    return {
        "code": rule_hit.rule.name,
        "kind": rule_hit.rule.kind,
        "family": rule_hit.rule.family,
        "points": rule_hit.points,
        "reason": rule_hit.reason,
    }


def alerts_response(analysis: PixAnalysis) -> list:
    alert_threshold = analysis.risk_policy_version.destination_risk_alert_threshold

    if analysis.destination_risk_score is None or analysis.destination_risk_score < alert_threshold:
        return []

    return [{"code": "destination_alert", "destination_risk_score": analysis.destination_risk_score, "threshold": alert_threshold}]


def two_factor_status(analysis: PixAnalysis, server_now: datetime) -> str:
    if analysis.two_factor_confirmation is not None:
        return analysis.two_factor_confirmation.result

    return "pending" if server_now < analysis.two_factor_expires_at else "expired"


def two_factor_response(analysis: PixAnalysis, server_now: datetime) -> Optional[dict]:
    if analysis.decision.enumerator != "two_factor_required":
        return None

    two_factor_confirmation = analysis.two_factor_confirmation
    return {
        "status": two_factor_status(analysis, server_now),
        "expires_at": isoformat_in_transaction_offset(analysis.two_factor_expires_at, analysis),
        "answered_at": isoformat_in_transaction_offset(two_factor_confirmation.answered_at if two_factor_confirmation else None, analysis),
    }


def pix_analysis_response(analysis: PixAnalysis, server_now: datetime) -> dict:
    return {
        "key": str(analysis.analysis_key),
        "status": analysis.decision.enumerator,
        "metadata": {
            "risk_score": analysis.risk_score,
            "destination_risk_score": analysis.destination_risk_score,
            "policy": {"name": analysis.risk_policy_version.risk_policy.name, "version": analysis.risk_policy_version.version_number},
            "rules": [rule_hit_response(rule_hit) for rule_hit in analysis.rule_hits],
            "alerts": alerts_response(analysis),
            "two_factor": two_factor_response(analysis, server_now),
        },
    }


def source_nightly_limit_response(nightly_limit) -> dict:
    requested_at_utc_offset = nightly_limit.requested_at.utcoffset()
    return {
        "nightly_limit_cents": nightly_limit.nightly_limit_cents,
        "requested_at": nightly_limit.requested_at.isoformat(),
        "effective_at": nightly_limit.effective_at.astimezone(timezone(requested_at_utc_offset)).isoformat(),
    }

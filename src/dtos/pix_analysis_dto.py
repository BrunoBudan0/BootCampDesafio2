from datetime import datetime, timedelta, timezone
from typing import Optional

from models import PixAnalysis, PixAnalysisRuleHit


def in_transaction_offset(moment: Optional[datetime], analysis: PixAnalysis) -> Optional[str]:
    if moment is None:
        return None

    return moment.astimezone(timezone(timedelta(minutes=analysis.transaction_utc_offset_minutes))).isoformat()


def rule_hit_response(rule_hit: PixAnalysisRuleHit) -> dict:
    return {
        "code": rule_hit.rule.code,
        "kind": rule_hit.rule.kind,
        "family": rule_hit.rule.family,
        "points": rule_hit.points,
        "reason": rule_hit.reason,
    }


def alerts_response(analysis: PixAnalysis) -> list:
    threshold = analysis.risk_policy_version.destination_alert_threshold

    if analysis.destination_risk is None or analysis.destination_risk < threshold:
        return []

    return [{"code": "destination_alert", "destination_risk": analysis.destination_risk, "threshold": threshold}]


def two_factor_status(analysis: PixAnalysis, now: datetime) -> str:
    if analysis.two_factor_confirmation is not None:
        return analysis.two_factor_confirmation.result

    return "pending" if now < analysis.two_factor_expires_at else "expired"


def two_factor_response(analysis: PixAnalysis, now: datetime) -> Optional[dict]:
    if analysis.decision.enumerator != "two_factor_required":
        return None

    confirmation = analysis.two_factor_confirmation
    return {
        "status": two_factor_status(analysis, now),
        "expires_at": in_transaction_offset(analysis.two_factor_expires_at, analysis),
        "confirmed_at": in_transaction_offset(confirmation.confirmed_at if confirmation else None, analysis),
    }


def pix_analysis_response(analysis: PixAnalysis, now: datetime) -> dict:
    return {
        "key": str(analysis.analysis_key),
        "status": analysis.decision.enumerator,
        "metadata": {
            "risk_score": analysis.risk_score,
            "destination_risk": analysis.destination_risk,
            "policy": {"name": analysis.risk_policy_version.risk_policy.name, "version": analysis.risk_policy_version.version},
            "rules": [rule_hit_response(rule_hit) for rule_hit in analysis.rule_hits],
            "alerts": alerts_response(analysis),
            "two_factor": two_factor_response(analysis, now),
        },
    }


def source_nightly_limit_response(nightly_limit) -> dict:
    offset = nightly_limit.requested_at.utcoffset()
    return {
        "nightly_limit_cents": nightly_limit.nightly_limit_cents,
        "requested_at": nightly_limit.requested_at.isoformat(),
        "effective_at": nightly_limit.effective_at.astimezone(timezone(offset)).isoformat(),
    }

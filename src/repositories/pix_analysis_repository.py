from datetime import datetime
from typing import Optional

from sqlalchemy import and_, distinct, exists, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from models import (
    AcceptedPix,
    Decision,
    PixAnalysis,
    PixAnalysisRuleHit,
    RiskPolicyVersion,
    Rule,
    TwoFactorConfirmation,
)


FAR_ABOVE_CAP_RULE_CODE = "new_account_to_new_destination_far_above_cap"


class PixAnalysisRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def find_by_pix_id(self, pix_id: str) -> Optional[PixAnalysis]:
        return self.session.scalars(
            select(PixAnalysis)
            .where(PixAnalysis.pix_id == pix_id)
            .options(
                joinedload(PixAnalysis.decision),
                joinedload(PixAnalysis.two_factor_confirmation),
                joinedload(PixAnalysis.risk_policy_version).joinedload(RiskPolicyVersion.risk_policy),
                selectinload(PixAnalysis.rule_hits).joinedload(PixAnalysisRuleHit.rule),
            )
            .execution_options(populate_existing=True)
        ).unique().one_or_none()

    def find_decisions_by_enumerator(self) -> dict:
        return {decision.enumerator: decision for decision in self.session.scalars(select(Decision)).all()}

    def add(self, analysis: PixAnalysis) -> None:
        self.session.add(analysis)
        self.session.flush()

    def find_source_analyses_between(self, source_document: str, since: datetime, until: datetime) -> list:
        return self.session.scalars(
            select(PixAnalysis)
            .where(
                PixAnalysis.source_document == source_document,
                PixAnalysis.transaction_date > since,
                PixAnalysis.transaction_date <= until,
            )
            .options(joinedload(PixAnalysis.decision), joinedload(PixAnalysis.two_factor_confirmation))
            .order_by(PixAnalysis.transaction_date, PixAnalysis.id)
        ).unique().all()

    def source_has_any_accepted_pix(self, source_document: str) -> bool:
        return self.session.scalar(select(exists().where(AcceptedPix.source_document == source_document)))

    def population_accepted_amounts_summary(
        self, source_person_type: str, destination_person_type: str, since: datetime, until: datetime
    ) -> tuple:
        count, median = self.session.execute(
            select(func.count(AcceptedPix.id), func.percentile_cont(0.5).within_group(AcceptedPix.amount_cents)).where(
                AcceptedPix.source_person_type == source_person_type,
                AcceptedPix.destination_person_type == destination_person_type,
                AcceptedPix.transaction_date > since,
                AcceptedPix.transaction_date <= until,
            )
        ).one()
        return count, median

    def count_other_sources_on_device(self, device_id: str, source_document: str, since: datetime, until: datetime) -> int:
        return self.session.scalar(
            select(func.count(distinct(PixAnalysis.source_document))).where(
                PixAnalysis.device_id == device_id,
                PixAnalysis.source_document != source_document,
                PixAnalysis.transaction_date > since,
                PixAnalysis.transaction_date <= until,
            )
        )

    def count_other_sources_paying_destination_from(
        self, destination_document: str, source_document: str, minimum_amount_cents: int, since: datetime, until: datetime
    ) -> int:
        return self.session.scalar(
            select(func.count(distinct(PixAnalysis.source_document))).where(
                PixAnalysis.destination_document == destination_document,
                PixAnalysis.source_document != source_document,
                PixAnalysis.amount_cents >= minimum_amount_cents,
                PixAnalysis.transaction_date > since,
                PixAnalysis.transaction_date <= until,
            )
        )

    def find_destination_accounts_between(self, destination_document: str, since: datetime, until: datetime) -> set:
        rows = self.session.execute(
            select(
                PixAnalysis.destination_participant,
                PixAnalysis.destination_branch,
                PixAnalysis.destination_account_number,
            )
            .where(
                PixAnalysis.destination_document == destination_document,
                PixAnalysis.transaction_date > since,
                PixAnalysis.transaction_date <= until,
            )
            .distinct()
        ).all()
        return {tuple(row) for row in rows}

    def count_other_sources_with_destination_rejections(
        self, destination_document: str, source_document: str, own_rule_id: int, since: datetime, until: datetime
    ) -> int:
        hit_of_the_rule_itself = exists().where(
            PixAnalysisRuleHit.pix_analysis_id == PixAnalysis.id,
            PixAnalysisRuleHit.rule_id == own_rule_id,
        )
        hit_with_counterparty_signal = (
            select(PixAnalysisRuleHit.id)
            .join(Rule, Rule.id == PixAnalysisRuleHit.rule_id)
            .where(
                PixAnalysisRuleHit.pix_analysis_id == PixAnalysis.id,
                or_(Rule.family == "counterparty", Rule.code == FAR_ABOVE_CAP_RULE_CODE),
            )
            .exists()
        )
        return self.session.scalar(
            select(func.count(distinct(PixAnalysis.source_document)))
            .join(Decision, Decision.id == PixAnalysis.decision_id)
            .outerjoin(TwoFactorConfirmation, TwoFactorConfirmation.pix_analysis_id == PixAnalysis.id)
            .where(
                PixAnalysis.destination_document == destination_document,
                PixAnalysis.source_document != source_document,
                PixAnalysis.transaction_date > since,
                PixAnalysis.transaction_date <= until,
                ~hit_of_the_rule_itself,
                or_(
                    TwoFactorConfirmation.result == "denied",
                    and_(Decision.enumerator == "rejected", hit_with_counterparty_signal),
                ),
            )
        )

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from controllers.rules import AnalysisDecision, TransactionContext, pix_under_analysis_from, required_datetime
from dtos import pix_analysis_response
from errors import (
    PixAnalysisNotFound,
    PixIdUsedWithOtherContent,
    TwoFactorAlreadyAnswered,
    TwoFactorNotRequested,
    TwoFactorOutsideValidity,
)
from models import PixAnalysis, PixAnalysisRuleHit, RegisteredDevice, TwoFactorConfirmation
from repositories import (
    AdvisoryLockRepository,
    PixAnalysisRepository,
    RiskPolicyRepository,
    RuleRepository,
    SourceRepository,
)


BANK_POLICY_NAME = "bank"
CREATED = 201
REPLAYED = 200


def source_lock_name(source_document: str) -> str:
    return f"source:{source_document}"


class PixAnalysisController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.pix_analysis_repository = PixAnalysisRepository(self.context)
        self.source_repository = SourceRepository(self.context)
        self.risk_policy_repository = RiskPolicyRepository(self.context)
        self.rule_repository = RuleRepository(self.context)
        self.advisory_lock_repository = AdvisoryLockRepository(self.context)

    def analyze(self, payload: dict) -> tuple:
        pix = pix_under_analysis_from(payload)
        recorded = self.pix_analysis_repository.find_by_pix_id(pix.pix_id)

        if recorded is not None:
            return self.replayed_analysis(recorded, pix.payload_hash)

        self.advisory_lock_repository.lock_until_commit(
            [source_lock_name(pix.source_document), f"device:{pix.device_id}", f"destination:{pix.destination_document}"]
        )
        recorded = self.pix_analysis_repository.find_by_pix_id(pix.pix_id)

        if recorded is not None:
            return self.replayed_analysis(recorded, pix.payload_hash)

        rules_by_code = self.rule_repository.find_all_by_code()
        policy_version = self.risk_policy_repository.find_current_version(BANK_POLICY_NAME)
        context = TransactionContext(pix, policy_version, self.pix_analysis_repository, self.source_repository)
        outcome = AnalysisDecision(rules_by_code).decide(context)
        registers_first_seen_device = (
            outcome.decision == "approved" and not context.source_has_any_accepted_pix and context.registered_device is None
        )

        analysis = PixAnalysis(
            analysis_key=str(uuid4()),
            pix_id=pix.pix_id,
            payload_hash=pix.payload_hash,
            amount_cents=pix.amount_cents,
            transaction_date=pix.transaction_date,
            transaction_utc_offset_minutes=pix.transaction_utc_offset_minutes,
            source_document=pix.source_document,
            source_person_type=pix.source_person_type,
            source_branch=pix.source_branch,
            source_account_number=pix.source_account_number,
            source_account_opening_date=pix.source_account_opening_date,
            destination_participant=pix.destination_participant,
            destination_branch=pix.destination_branch,
            destination_account_number=pix.destination_account_number,
            destination_account_opening_date=pix.destination_account_opening_date,
            destination_document=pix.destination_document,
            destination_person_type=pix.destination_person_type,
            device_id=pix.device_id,
            channel=pix.channel,
            ip=pix.ip,
            latitude=pix.latitude,
            longitude=pix.longitude,
            decision=self.pix_analysis_repository.find_decisions_by_enumerator()[outcome.decision],
            risk_score=outcome.risk_score,
            destination_risk=outcome.destination_risk,
            risk_policy_version=policy_version,
            two_factor_expires_at=outcome.two_factor_expires_at,
            rule_hits=[
                PixAnalysisRuleHit(rule=rules_by_code[rule_hit.code], points=rule_hit.points, reason=rule_hit.reason)
                for rule_hit in outcome.rule_hits
            ],
        )

        try:
            self.pix_analysis_repository.add(analysis)

            if registers_first_seen_device:
                self.source_repository.add_registered_device(
                    RegisteredDevice(
                        source_document=pix.source_document,
                        device_id=pix.device_id,
                        registration_origin="first_seen",
                        registered_at=pix.transaction_date,
                        pix_analysis_id=analysis.id,
                    )
                )

            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recorded = self.pix_analysis_repository.find_by_pix_id(pix.pix_id)
            if recorded is None:
                raise
            return self.replayed_analysis(recorded, pix.payload_hash)

        return CREATED, self.recorded_analysis_response(pix.pix_id)

    def get_analysis(self, pix_id: str) -> dict:
        return self.recorded_analysis_response(pix_id)

    def confirm_two_factor(self, pix_id: str, payload: dict) -> tuple:
        analysis = self.required_analysis(pix_id)
        self.advisory_lock_repository.lock_until_commit([source_lock_name(analysis.source_document)])
        analysis = self.required_analysis(pix_id)

        if analysis.decision.enumerator != "two_factor_required":
            raise TwoFactorNotRequested(pix_id)

        confirmed_at = required_datetime(payload["confirmed_at"], "confirmed_at")
        recorded_confirmation = analysis.two_factor_confirmation

        if recorded_confirmation is not None:
            return self.replayed_confirmation(pix_id, recorded_confirmation.result, payload["result"])

        if not analysis.transaction_date <= confirmed_at <= analysis.two_factor_expires_at:
            raise TwoFactorOutsideValidity(pix_id)

        try:
            self.source_repository.add_two_factor_confirmation(
                TwoFactorConfirmation(pix_analysis_id=analysis.id, result=payload["result"], confirmed_at=confirmed_at)
            )

            device_is_unregistered = self.source_repository.find_registered_device(analysis.source_document, analysis.device_id) is None
            if payload["result"] == "confirmed" and device_is_unregistered:
                self.source_repository.add_registered_device(
                    RegisteredDevice(
                        source_document=analysis.source_document,
                        device_id=analysis.device_id,
                        registration_origin="two_factor",
                        registered_at=confirmed_at,
                        pix_analysis_id=analysis.id,
                    )
                )

            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recorded_confirmation = self.required_analysis(pix_id).two_factor_confirmation
            if recorded_confirmation is None:
                raise
            return self.replayed_confirmation(pix_id, recorded_confirmation.result, payload["result"])

        return CREATED, self.recorded_analysis_response(pix_id)

    def replayed_analysis(self, recorded: PixAnalysis, payload_hash: str) -> tuple:
        if recorded.payload_hash != payload_hash:
            raise PixIdUsedWithOtherContent(recorded.pix_id)

        return REPLAYED, pix_analysis_response(recorded, datetime.now(timezone.utc))

    def replayed_confirmation(self, pix_id: str, recorded_result: str, sent_result: str) -> tuple:
        if recorded_result != sent_result:
            raise TwoFactorAlreadyAnswered(pix_id, recorded_result)

        return REPLAYED, self.recorded_analysis_response(pix_id)

    def required_analysis(self, pix_id: str) -> PixAnalysis:
        analysis = self.pix_analysis_repository.find_by_pix_id(pix_id)

        if analysis is None:
            raise PixAnalysisNotFound(pix_id)

        return analysis

    def recorded_analysis_response(self, pix_id: str) -> dict:
        return pix_analysis_response(self.required_analysis(pix_id), datetime.now(timezone.utc))

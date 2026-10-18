import re
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
from models import PixAnalysis, PixAnalysisRuleHit, RegisteredDevice, RiskPolicy, TwoFactorConfirmation
from repositories import (
    AdvisoryLockRepository,
    PixAnalysisRepository,
    RiskPolicyRepository,
    RuleRepository,
    SourceRepository,
    source_lock_name,
)


CREATED_STATUS_CODE = 201
REPLAYED_STATUS_CODE = 200
PIX_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


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
        recorded_analysis = self.pix_analysis_repository.find_by_pix_id(pix.pix_id)

        if recorded_analysis is not None:
            return self.replayed_analysis(recorded_analysis, pix.payload_hash)

        self.advisory_lock_repository.lock_until_commit(
            [source_lock_name(pix.source_document_number), f"device:{pix.source_device_id}", f"destination:{pix.destination_document_number}"]
        )
        recorded_analysis = self.pix_analysis_repository.find_by_pix_id(pix.pix_id)

        if recorded_analysis is not None:
            return self.replayed_analysis(recorded_analysis, pix.payload_hash)

        rules_by_name = self.rule_repository.find_all_by_name()
        policy_version = self.risk_policy_repository.find_current_version(RiskPolicy.BANK_NAME)
        context = TransactionContext(pix, policy_version, self.pix_analysis_repository, self.source_repository)
        outcome = AnalysisDecision(rules_by_name).decide(context)
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
            source_document_number=pix.source_document_number,
            source_person_type=pix.source_person_type,
            source_branch=pix.source_branch,
            source_account_number=pix.source_account_number,
            source_account_opening_date=pix.source_account_opening_date,
            destination_participant_ispb=pix.destination_participant_ispb,
            destination_branch=pix.destination_branch,
            destination_account_number=pix.destination_account_number,
            destination_account_opening_date=pix.destination_account_opening_date,
            destination_document_number=pix.destination_document_number,
            destination_person_type=pix.destination_person_type,
            source_device_id=pix.source_device_id,
            source_channel=pix.source_channel,
            source_ip=pix.source_ip,
            source_latitude=pix.source_latitude,
            source_longitude=pix.source_longitude,
            decision=self.pix_analysis_repository.find_decisions_by_enumerator()[outcome.decision],
            risk_score=outcome.risk_score,
            destination_risk_score=outcome.destination_risk_score,
            risk_policy_version=policy_version,
            two_factor_expires_at=outcome.two_factor_expires_at,
            rule_hits=[
                PixAnalysisRuleHit(rule=rules_by_name[rule_hit.rule_name], points=rule_hit.points, reason=rule_hit.reason)
                for rule_hit in outcome.rule_hits
            ],
        )

        try:
            self.pix_analysis_repository.add_analysis(analysis)

            if registers_first_seen_device:
                self.source_repository.add_registered_device(
                    RegisteredDevice(
                        source_document_number=pix.source_document_number,
                        device_id=pix.source_device_id,
                        registration_origin="first_seen",
                        registered_at=pix.transaction_date,
                        registration_pix_analysis_id=analysis.id,
                    )
                )

            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recorded_analysis = self.pix_analysis_repository.find_by_pix_id(pix.pix_id)
            if recorded_analysis is None:
                raise
            return self.replayed_analysis(recorded_analysis, pix.payload_hash)

        return CREATED_STATUS_CODE, self.recorded_analysis_response(pix.pix_id)

    def get_analysis(self, pix_id: str) -> dict:
        return self.recorded_analysis_response(pix_id)

    def record_two_factor_result(self, pix_id: str, payload: dict) -> tuple:
        analysis = self.analysis_or_not_found(pix_id)
        self.advisory_lock_repository.lock_until_commit([source_lock_name(analysis.source_document_number)])
        analysis = self.analysis_or_not_found(pix_id)

        if analysis.decision.enumerator != "two_factor_required":
            raise TwoFactorNotRequested(pix_id)

        answered_at = required_datetime(payload["answered_at"], "answered_at")
        recorded_confirmation = analysis.two_factor_confirmation

        if recorded_confirmation is not None:
            return self.replayed_two_factor_result(pix_id, recorded_confirmation.result, payload["result"])

        if not analysis.transaction_date <= answered_at <= analysis.two_factor_expires_at:
            raise TwoFactorOutsideValidity(pix_id)

        try:
            self.source_repository.add_two_factor_confirmation(
                TwoFactorConfirmation(pix_analysis_id=analysis.id, result=payload["result"], answered_at=answered_at)
            )

            device_is_unregistered = self.source_repository.find_registered_device(analysis.source_document_number, analysis.source_device_id) is None
            if payload["result"] == "confirmed" and device_is_unregistered:
                self.source_repository.add_registered_device(
                    RegisteredDevice(
                        source_document_number=analysis.source_document_number,
                        device_id=analysis.source_device_id,
                        registration_origin="two_factor",
                        registered_at=answered_at,
                        registration_pix_analysis_id=analysis.id,
                    )
                )

            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            recorded_confirmation = self.analysis_or_not_found(pix_id).two_factor_confirmation
            if recorded_confirmation is None:
                raise
            return self.replayed_two_factor_result(pix_id, recorded_confirmation.result, payload["result"])

        return CREATED_STATUS_CODE, self.recorded_analysis_response(pix_id)

    def replayed_analysis(self, recorded_analysis: PixAnalysis, payload_hash: str) -> tuple:
        if recorded_analysis.payload_hash != payload_hash:
            raise PixIdUsedWithOtherContent(recorded_analysis.pix_id)

        return REPLAYED_STATUS_CODE, pix_analysis_response(recorded_analysis, datetime.now(timezone.utc))

    def replayed_two_factor_result(self, pix_id: str, recorded_result: str, sent_result: str) -> tuple:
        if recorded_result != sent_result:
            raise TwoFactorAlreadyAnswered(pix_id, recorded_result)

        return REPLAYED_STATUS_CODE, self.recorded_analysis_response(pix_id)

    def analysis_or_not_found(self, pix_id: str) -> PixAnalysis:
        if PIX_ID_PATTERN.fullmatch(pix_id) is None:
            raise PixAnalysisNotFound(pix_id)

        analysis = self.pix_analysis_repository.find_by_pix_id(pix_id)

        if analysis is None:
            raise PixAnalysisNotFound(pix_id)

        return analysis

    def recorded_analysis_response(self, pix_id: str) -> dict:
        return pix_analysis_response(self.analysis_or_not_found(pix_id), datetime.now(timezone.utc))

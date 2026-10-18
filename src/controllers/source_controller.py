from controllers.base_controller import BaseController
from controllers.rules import nightly_limit_effective_at, required_datetime
from dtos import source_nightly_limit_response
from errors import InvalidDocumentNumber, NightlyLimitOnlyForIndividuals
from models import SourceNightlyLimit
from repositories import AdvisoryLockRepository, SourceRepository, source_lock_name
from utils.document_number import is_valid_document_number, normalized_document_number, person_type_of


class SourceController(BaseController):
    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)
        self.source_repository = SourceRepository(self.context)
        self.advisory_lock_repository = AdvisoryLockRepository(self.context)

    def create_nightly_limit(self, document_number: str, payload: dict) -> dict:
        if not is_valid_document_number(document_number):
            raise InvalidDocumentNumber("document")

        source_document_number = normalized_document_number(document_number)

        if person_type_of(source_document_number) != "individual":
            raise NightlyLimitOnlyForIndividuals()

        requested_at = required_datetime(payload["requested_at"], "requested_at")
        self.advisory_lock_repository.lock_until_commit([source_lock_name(source_document_number)])
        nightly_limits = self.source_repository.find_nightly_limits(source_document_number)

        nightly_limit = SourceNightlyLimit(
            source_document_number=source_document_number,
            nightly_limit_cents=payload["nightly_limit_cents"],
            requested_at=requested_at,
            effective_at=nightly_limit_effective_at(nightly_limits, payload["nightly_limit_cents"], requested_at),
        )
        self.source_repository.add_nightly_limit(nightly_limit)
        response = source_nightly_limit_response(nightly_limit)
        self.session.commit()

        return response

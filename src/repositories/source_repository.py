from typing import Optional

from sqlalchemy import select

from models import RegisteredDevice, SourceNightlyLimit, TwoFactorConfirmation


class SourceRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def find_registered_device(self, source_document_number: str, device_id: str) -> Optional[RegisteredDevice]:
        return self.session.scalars(
            select(RegisteredDevice).where(
                RegisteredDevice.source_document_number == source_document_number,
                RegisteredDevice.device_id == device_id,
            )
        ).one_or_none()

    def add_registered_device(self, registered_device: RegisteredDevice) -> None:
        self.session.add(registered_device)
        self.session.flush()

    def find_nightly_limits(self, source_document_number: str) -> list:
        return self.session.scalars(
            select(SourceNightlyLimit)
            .where(SourceNightlyLimit.source_document_number == source_document_number)
            .order_by(SourceNightlyLimit.requested_at, SourceNightlyLimit.id)
        ).all()

    def add_nightly_limit(self, nightly_limit: SourceNightlyLimit) -> None:
        self.session.add(nightly_limit)
        self.session.flush()

    def add_two_factor_confirmation(self, confirmation: TwoFactorConfirmation) -> None:
        self.session.add(confirmation)
        self.session.flush()

from sqlalchemy import BigInteger, Column, DateTime, String, func

from models.base import Base


class SourceNightlyLimit(Base):
    __tablename__ = "source_nightly_limit"

    id = Column(BigInteger, primary_key=True)
    source_document_number = Column(String(14), nullable=False)
    nightly_limit_cents = Column(BigInteger, nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

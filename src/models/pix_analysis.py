from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import relationship

from models.base import Base


class PixAnalysis(Base):
    __tablename__ = "pix_analysis"

    id = Column(BigInteger, primary_key=True)
    analysis_key = Column(UUID(as_uuid=False), nullable=False, unique=True)
    pix_id = Column(String(64), nullable=False, unique=True)
    payload_hash = Column(String(64), nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    transaction_utc_offset_minutes = Column(SmallInteger, nullable=False)
    source_document = Column(String(14), nullable=False)
    source_person_type = Column(String(10), nullable=False)
    source_branch = Column(String(10), nullable=False)
    source_account_number = Column(String(20), nullable=False)
    source_account_opening_date = Column(DateTime(timezone=True), nullable=False)
    destination_participant = Column(String(8), nullable=False)
    destination_branch = Column(String(10), nullable=False)
    destination_account_number = Column(String(20), nullable=False)
    destination_account_opening_date = Column(DateTime(timezone=True), nullable=False)
    destination_document = Column(String(14), nullable=False)
    destination_person_type = Column(String(10), nullable=False)
    device_id = Column(String(100), nullable=False)
    channel = Column(String(30), nullable=False)
    ip = Column(INET, nullable=False)
    latitude = Column(Numeric(8, 6))
    longitude = Column(Numeric(9, 6))
    decision_id = Column(Integer, ForeignKey("decision.id"), nullable=False)
    risk_score = Column(Integer)
    destination_risk = Column(Integer)
    risk_policy_version_id = Column(Integer, ForeignKey("risk_policy_version.id"), nullable=False)
    two_factor_expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    decision = relationship("Decision")
    risk_policy_version = relationship("RiskPolicyVersion")
    rule_hits = relationship("PixAnalysisRuleHit", order_by="PixAnalysisRuleHit.rule_id")
    two_factor_confirmation = relationship("TwoFactorConfirmation", uselist=False)

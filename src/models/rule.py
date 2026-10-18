from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from models.base import Base

class Rule(Base):
    __tablename__ = "rule"

    id = Column(Integer, primary_key=True)
    code = Column(String(80), nullable=False, unique=True)
    kind = Column(String(20), nullable=False)
    family = Column(String(20))
    counterparty_signal = Column(String(15))
    forced_decision_id = Column(Integer, ForeignKey("decision.id"))
    threshold_unit = Column(String(30))
    uses_window = Column(Boolean, nullable=False)
    uses_company_threshold = Column(Boolean, nullable=False)
    description = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

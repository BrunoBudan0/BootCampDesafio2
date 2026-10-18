from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import relationship

from models.base import Base

class RiskPolicyRuleSetting(Base):
    __tablename__ = "risk_policy_rule_setting"

    EDITABLE_FIELDS = ("enabled", "points", "threshold", "window_minutes", "company_threshold")

    id = Column(Integer, primary_key=True)
    risk_policy_version_id = Column(Integer, ForeignKey("risk_policy_version.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("rule.id"), nullable=False)
    enabled = Column(Boolean, nullable=False)
    points = Column(Integer)
    threshold = Column(Numeric(12, 2))
    window_minutes = Column(Integer)
    company_threshold = Column(Numeric(12, 2))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rule = relationship("Rule")

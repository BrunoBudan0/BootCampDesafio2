from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from models.base import Base


class PixAnalysisRuleHit(Base):
    __tablename__ = "pix_analysis_rule_hit"

    id = Column(BigInteger, primary_key=True)
    pix_analysis_id = Column(BigInteger, ForeignKey("pix_analysis.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("rule.id"), nullable=False)
    points = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rule = relationship("Rule")

from sqlalchemy import Column, DateTime, Integer, String, func

from models.base import Base


class RiskPolicy(Base):
    __tablename__ = "risk_policy"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    kind = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

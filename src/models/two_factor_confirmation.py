from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, func

from models.base import Base


class TwoFactorConfirmation(Base):
    __tablename__ = "two_factor_confirmation"

    id = Column(BigInteger, primary_key=True)
    pix_analysis_id = Column(BigInteger, ForeignKey("pix_analysis.id"), nullable=False, unique=True)
    result = Column(String(10), nullable=False)
    answered_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

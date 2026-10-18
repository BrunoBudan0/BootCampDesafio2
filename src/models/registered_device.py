from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, func

from models.base import Base


class RegisteredDevice(Base):
    __tablename__ = "registered_device"

    id = Column(BigInteger, primary_key=True)
    source_document = Column(String(14), nullable=False)
    device_id = Column(String(100), nullable=False)
    registration_origin = Column(String(15), nullable=False)
    registered_at = Column(DateTime(timezone=True), nullable=False)
    pix_analysis_id = Column(BigInteger, ForeignKey("pix_analysis.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

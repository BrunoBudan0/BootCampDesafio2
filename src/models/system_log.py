from sqlalchemy import BigInteger, Column, DateTime, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from models.base import Base


class SystemLog(Base):
    __tablename__ = "system_log"

    id = Column(BigInteger, primary_key=True)
    request_id = Column(String(64), nullable=False)
    level = Column(String(10), nullable=False)
    event = Column(String(50), nullable=False)
    logger_name = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    http_method = Column(String(10))
    path = Column(String(500))
    http_status = Column(SmallInteger)
    error_code = Column(String(20))
    details = Column(JSONB)
    stack_trace = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())

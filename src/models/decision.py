from sqlalchemy import Column, DateTime, Integer, String, func

from models.base import Base


class Decision(Base):
    __tablename__ = "decision"

    id = Column(Integer, primary_key=True)
    enumerator = Column(String(30), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

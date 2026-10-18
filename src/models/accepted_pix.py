from sqlalchemy import BigInteger, Column, DateTime, String

from models.base import Base


class AcceptedPix(Base):
    __tablename__ = "accepted_pix"

    id = Column(BigInteger, primary_key=True)
    amount_cents = Column(BigInteger, nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    source_document = Column(String(14), nullable=False)
    source_person_type = Column(String(10), nullable=False)
    destination_person_type = Column(String(10), nullable=False)
    acceptance = Column(String(10), nullable=False)

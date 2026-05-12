from sqlalchemy import Column, Date, Integer, Numeric, String, Text

from app.database import Base


class PettyCash(Base):
    __tablename__ = "petty_cash"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    category = Column(String(30), nullable=False)  # cleaning, supplies, electricity, water, other
    description = Column(String(200), nullable=True)
    receipt_note = Column(Text, nullable=True)
    balance_after = Column(Numeric(10, 2), nullable=False)

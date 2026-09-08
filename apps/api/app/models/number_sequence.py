from sqlalchemy import Column, Integer, String

from app.database import Base


class NumberSequence(Base):
    """配號用的計數器。一列一個 scope，見 app/services/numbering.py。

    刻意不是 Postgres 原生 SEQUENCE：原生序列不受交易 rollback 影響（會留空號），
    而收據號要求連號可稽核；而且原生序列沒辦法「每天、每位心理師各一條」這種
    動態 scope。用一張表 + 單語句 UPDATE ... RETURNING 兩個需求都滿足。
    """

    __tablename__ = "number_sequences"

    scope = Column(String(120), primary_key=True)
    last_seq = Column(Integer, nullable=False, default=0)

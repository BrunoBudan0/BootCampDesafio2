from datetime import datetime
from typing import Optional

from sqlalchemy import select

from database import SessionLocal
from models import SystemLog


class SystemLogRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def find_latest(self, filters: dict, since: Optional[datetime], limit: int) -> list:
        query = select(SystemLog)

        for field_name, value in filters.items():
            query = query.where(getattr(SystemLog, field_name) == value)

        if since is not None:
            query = query.where(SystemLog.created_at >= since)

        return self.session.scalars(query.order_by(SystemLog.created_at.desc(), SystemLog.id.desc()).limit(limit)).all()


def add_system_log_in_its_own_transaction(system_log: SystemLog) -> None:
    with SessionLocal() as session:
        session.add(system_log)
        session.commit()

import hashlib

from sqlalchemy import text


def advisory_lock_number(lock_name: str) -> int:
    digest = hashlib.sha256(lock_name.encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class AdvisoryLockRepository:
    def __init__(self, context) -> None:
        self.session = context.db_session

    def lock_until_commit(self, lock_names: list) -> None:
        for lock_number in sorted({advisory_lock_number(lock_name) for lock_name in lock_names}):
            self.session.execute(text("SELECT pg_advisory_xact_lock(:lock_number)"), {"lock_number": lock_number})

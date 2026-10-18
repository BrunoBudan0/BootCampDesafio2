from datetime import datetime, timedelta, timezone


SAO_PAULO = timezone(timedelta(hours=-3))


def now_in_sao_paulo() -> datetime:
    return datetime.now(SAO_PAULO).replace(microsecond=0)


def today_at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return now_in_sao_paulo().replace(hour=hour, minute=minute, second=second)


def business_hours_today() -> datetime:
    return today_at(14)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)

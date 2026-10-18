from datetime import datetime, time, timedelta, timezone


SAO_PAULO = timezone(timedelta(hours=-3))
TODAY_IN_SAO_PAULO = datetime.now(SAO_PAULO).date()


def now_in_sao_paulo() -> datetime:
    return datetime.now(SAO_PAULO).replace(microsecond=0)


def today_at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime.combine(TODAY_IN_SAO_PAULO, time(hour, minute, second), tzinfo=SAO_PAULO)


def business_hours_today() -> datetime:
    return today_at(14)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)

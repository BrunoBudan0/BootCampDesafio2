from datetime import datetime, timedelta


SMALLEST_UTC_OFFSET = timedelta(hours=-12)
LARGEST_UTC_OFFSET = timedelta(hours=14)
SMALLEST_YEAR = 1900
LARGEST_YEAR = 2999


def parsed_datetime_with_offset(text: str):
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None

    if moment.utcoffset() is None or not SMALLEST_UTC_OFFSET <= moment.utcoffset() <= LARGEST_UTC_OFFSET:
        return None

    if not SMALLEST_YEAR <= moment.year <= LARGEST_YEAR:
        return None

    return moment


def utc_offset_minutes(moment: datetime) -> int:
    return int(moment.utcoffset().total_seconds() // 60)

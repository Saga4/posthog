from datetime import datetime, timedelta


def start_of_minute(dt: datetime) -> datetime:
    return datetime(year=dt.year, month=dt.month, day=dt.day, hour=dt.hour, minute=dt.minute, tzinfo=dt.tzinfo)


def start_of_hour(dt: datetime) -> datetime:
    return datetime(year=dt.year, month=dt.month, day=dt.day, hour=dt.hour, tzinfo=dt.tzinfo)


def start_of_day(dt: datetime):
    return datetime(year=dt.year, month=dt.month, day=dt.day, tzinfo=dt.tzinfo)


def end_of_day(dt: datetime):
    # Directly construct end-of-day datetime for maximum efficiency
    return datetime(dt.year, dt.month, dt.day, 23, 59, 59, 999999, dt.tzinfo)


def start_of_week(dt: datetime) -> datetime:
    # weeks start on sunday
    return datetime(year=dt.year, month=dt.month, day=dt.day, tzinfo=dt.tzinfo) - timedelta(days=(dt.weekday() + 1) % 7)


def start_of_month(dt: datetime) -> datetime:
    return datetime(year=dt.year, month=dt.month, day=1, tzinfo=dt.tzinfo)

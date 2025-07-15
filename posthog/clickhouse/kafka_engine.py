# Note for the vary: these engine definitions (and many table definitions) are not in sync with cloud!
from __future__ import annotations
from typing import Literal

from django.conf import settings

# Caches for expensive or often-repeated computations
_ON_CLUSTER_CLAUSE_CACHE: dict[bool, str] = {}
_KAFKA_HOSTS_JOINED: str | None = None
_KAFKA_ENGINE_CACHE: dict[tuple[str, str, str, str], str] = {}
_KAFKA_LOG_ENTRIES_ENGINE: str | None = None
_KAFKA_LOG_ENTRIES_TABLE_SQL: dict[bool, str] = {}

STORAGE_POLICY = lambda: "SETTINGS storage_policy = 'hot_to_cold'" if settings.CLICKHOUSE_ENABLE_STORAGE_POLICY else ""

KAFKA_ENGINE = "Kafka('{kafka_host}', '{topic}', '{group}', '{serialization}')"

KAFKA_PROTO_ENGINE = """
    Kafka () SETTINGS
    kafka_broker_list = '{kafka_host}',
    kafka_topic_list = '{topic}',
    kafka_group_name = '{group}',
    kafka_format = 'Protobuf',
    kafka_schema = '{proto_schema}',
    kafka_skip_broken_messages = {skip_broken_messages}
    """

GENERATE_UUID_SQL = """
SELECT generateUUIDv4()
"""

# The kafka_engine automatically adds these columns to the kafka tables. We use
# this string to add them to the other tables as well.
KAFKA_COLUMNS = """
, _timestamp DateTime
, _offset UInt64
"""

# Use this with new tables, old one didn't include partition
KAFKA_COLUMNS_WITH_PARTITION = """
, _timestamp DateTime
, _offset UInt64
, _partition UInt64
"""

KAFKA_TIMESTAMP_MS_COLUMN = "_timestamp_ms DateTime64"


def kafka_engine(topic: str, kafka_host: str | None = None, group="group1", serialization="JSONEachRow") -> str:
    # Memoize engine string for input params
    if kafka_host is None:
        kafka_host = _get_kafka_hosts_joined()
    key = (topic, kafka_host, group, serialization)
    if key not in _KAFKA_ENGINE_CACHE:
        _KAFKA_ENGINE_CACHE[key] = KAFKA_ENGINE.format(
            topic=topic, kafka_host=kafka_host, group=group, serialization=serialization
        )
    return _KAFKA_ENGINE_CACHE[key]


def ttl_period(field: str = "created_at", amount: int = 3, unit: Literal["DAY", "WEEK"] = "WEEK") -> str:
    return "" if settings.TEST else f"TTL toDate({field}) + INTERVAL {amount} {unit}"


def trim_quotes_expr(expr: str) -> str:
    return f"replaceRegexpAll({expr}, '^\"|\"$', '')"


def _get_kafka_hosts_joined() -> str:
    global _KAFKA_HOSTS_JOINED
    if _KAFKA_HOSTS_JOINED is None:
        # Join only once since KAFKA_HOSTS_FOR_CLICKHOUSE is immutable during process lifetime
        _KAFKA_HOSTS_JOINED = ",".join(settings.KAFKA_HOSTS_FOR_CLICKHOUSE)
    return _KAFKA_HOSTS_JOINED

import json
from dataclasses import dataclass

from posthog.clickhouse.client import sync_execute
from posthog.hogql.context import HogQLContext
from posthog.schema import QueryIndexUsage


def find_all_reads(explain: dict) -> list[dict]:
    """
    Looks for a Plan/Subplan with "Indexes" element. ClickHouse' MergeTree engine uses "ReadFromMergeTree"
    plan Node Type to describe reading from a table and if defined with index it will contain "Indexes" field.
    """
    # Use iterative DFS to avoid call stack overhead and faster list extension
    reads = []
    stack = [explain.get("Plan", explain)]
    while stack:
        node = stack.pop()
        if "Indexes" in node:
            reads.append(node)
        plans = node.get("Plans")
        if plans:
            stack.extend(plans)
    return reads


def selected_less_granules(index: dict, tiny_data_granules: int = 100) -> bool:
    """
    Each "Indexes" field contains a description of how the index impact selection of partitions and granules.
    Index is effective if the number of granules selected is smaller than before using an index. If the data is
    small enough, the index won't limit what we read.
    """
    initial_granules = index.get("Initial Granules", 0)
    return index.get("Selected Granules", 0) < initial_granules or initial_granules < tiny_data_granules


@dataclass
class ReadIndexUsage:
    table: str
    use: QueryIndexUsage


def guestimate_index_use(plan_with_indexes: dict) -> ReadIndexUsage:
    """
    For a given table read we try to indentify if an index was used. This is limited as the plan is being processed
    without a context (a table schema / index). Some tables have simple index and no real partitioning.
    :param plan_with_indexes:
    :return:
    """
    db_table = plan_with_indexes.get("Description", "")
    result = ReadIndexUsage(table=db_table, use=QueryIndexUsage.NO)
    indexes = plan_with_indexes.get("Indexes")
    if not indexes:
        return result

    # Fast path for ".person_distinct_id_overrides"
    if db_table.endswith(".person_distinct_id_overrides"):
        if len(indexes) == 1:
            index = indexes[0]
            keys = index.get("Keys", [])
            if index.get("Condition", "") != "true" and "team_id" in keys and selected_less_granules(index):
                result.use = QueryIndexUsage.YES
        return result

    # Fast path for ".sharded_events"
    if db_table.endswith(".sharded_events"):
        min_max = partition = primary_key = False
        for index in indexes:
            if index.get("Condition", "") == "true":
                continue
            index_type = index.get("Type", "")
            if index_type == "MinMax":
                min_max = min_max or selected_less_granules(index)
            elif index_type == "Partition":
                partition = partition or selected_less_granules(index)
            elif index_type == "PrimaryKey":
                keys = index.get("Keys", [])
                primary_key = primary_key or (keys and selected_less_granules(index))
        if (min_max or partition) and primary_key:
            result.use = QueryIndexUsage.YES
        return result

    # Generic fallback
    result.use = QueryIndexUsage.UNDECISIVE
    has_min_max = has_partition = False
    min_max = partition = primary_key = False
    for index in indexes:
        cond = index.get("Condition", "")
        override_not_using = cond == "true"
        index_type = index.get("Type", "")
        if index_type == "MinMax":
            has_min_max = True
            if not override_not_using and selected_less_granules(index):
                min_max = True
        elif index_type == "Partition":
            has_partition = True
            if not override_not_using and selected_less_granules(index):
                partition = True
        elif index_type == "PrimaryKey":
            keys = index.get("Keys", [])
            if not override_not_using and keys and selected_less_granules(index):
                primary_key = True
    if primary_key:
        if (not has_min_max and not has_partition) or min_max or partition:
            result.use = QueryIndexUsage.YES
        else:
            result.use = QueryIndexUsage.PARTIAL

    return result


def extract_index_usage_from_plan(plan: str) -> QueryIndexUsage:
    try:
        explain = json.loads(plan)
        reads = find_all_reads(explain[0])
        if not reads:
            return QueryIndexUsage.UNDECISIVE
        all_indices_use = [guestimate_index_use(r) for r in reads]
        uses = {x.use for x in all_indices_use}
        if uses == {QueryIndexUsage.YES}:
            return QueryIndexUsage.YES
        elif uses == {QueryIndexUsage.NO}:
            return QueryIndexUsage.NO
        elif QueryIndexUsage.YES in uses or QueryIndexUsage.PARTIAL in uses:
            return QueryIndexUsage.PARTIAL
    except json.decoder.JSONDecodeError:
        pass
    return QueryIndexUsage.UNDECISIVE


def execute_explain_get_index_use(clickhouse_sql: str, context: HogQLContext) -> QueryIndexUsage:
    # try:
    explain_results = sync_execute(
        f"EXPLAIN PLAN indexes=1,json=1 {clickhouse_sql}",
        context.values,
        with_column_types=True,
        team_id=context.team_id,
        readonly=True,
        settings={"allow_experimental_join_condition": 1},
    )
    return extract_index_usage_from_plan(explain_results[0][0][0])


# except:
#     return QueryIndexUsage.UNDECISIVE

from datetime import datetime, timedelta

from posthog.hogql import ast
from posthog.hogql.ast import CompareOperation
from posthog.hogql.parser import parse_select
from posthog.models import Team
from posthog.schema import RecordingsQuery
from posthog.session_recordings.queries.utils import poe_is_active
from posthog.session_recordings.queries.sub_queries.base_query import SessionRecordingsListingBaseQuery


class PersonsIdCompareOperation(SessionRecordingsListingBaseQuery):
    def __init__(self, team: Team, query: RecordingsQuery):
        super().__init__(team, query)

    def get_operation(self) -> CompareOperation | None:
        team = self._team
        query_result = self.get_query()

        if not query_result:
            return None

        if poe_is_active(team):
            # this hits the distributed events table from the distributed session_replay_events table
            # so we should use GlobalIn
            # see https://clickhouse.com/docs/en/sql-reference/operators/in#distributed-subqueries
            return ast.CompareOperation(
                op=ast.CompareOperationOp.GlobalIn,
                left=ast.Field(chain=["session_id"]),
                right=query_result,
            )
        else:
            return ast.CompareOperation(
                op=ast.CompareOperationOp.In,
                left=ast.Field(chain=["distinct_id"]),
                right=query_result,
            )

    def get_query(self) -> ast.SelectQuery | ast.SelectSetQuery | None:
        query = self._query
        # Quick check to avoid further computation.
        person_id = query.person_uuid
        if not person_id:
            return None

        team = self._team
        poe_mode = poe_is_active(team)

        # Anchor to python now so that tests can freeze time
        now = datetime.utcnow()
        if poe_mode:
            ttl_days = self.ttl_days
            query_date_range = self.query_date_range
            date_from = query_date_range.date_from()
            date_to = query_date_range.date_to()
            ttl_date = now - timedelta(days=ttl_days)
            # Reuse dictionary allocation in-place for parse_select
            placeholders = {
                "person_id": ast.Constant(value=person_id),
                "ttl_days": ast.Constant(value=ttl_days),
                "date_from": ast.Constant(value=date_from),
                "date_to": ast.Constant(value=date_to),
                "now": ast.Constant(value=now),
                "ttl_date": ast.Constant(value=ttl_date),
            }
            return parse_select(
                (
                    "select\n"
                    "    distinct `$session_id`\n"
                    "from\n"
                    "    events\n"
                    "where\n"
                    "    person_id = {person_id}\n"
                    "    and timestamp <= {now}\n"
                    "    and timestamp >= {ttl_date}\n"
                    "    and timestamp >= {date_from}\n"
                    "    and timestamp <= {date_to}\n"
                    "    and notEmpty(`$session_id`)\n"
                ),
                placeholders,
            )
        else:
            return parse_select(
                "SELECT distinct_id FROM person_distinct_ids WHERE person_id = {person_id}",
                {"person_id": ast.Constant(value=person_id)},
            )

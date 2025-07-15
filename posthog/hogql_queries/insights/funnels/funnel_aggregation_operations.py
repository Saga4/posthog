from typing import cast

from posthog.hogql import ast
from posthog.hogql_queries.insights.funnels.funnel_query_context import FunnelQueryContext
from posthog.hogql_queries.insights.utils.aggregations import FirstTimeForUserEventsQueryAlternator
from posthog.hogql_queries.utils.query_date_range import QueryDateRange


class FirstTimeForUserAggregationQuery:
    _context: FunnelQueryContext
    _filters: ast.Expr | None
    _event_or_action_filter: ast.Expr | None

    def __init__(
        self,
        context: FunnelQueryContext,
        filters: ast.Expr | None = None,
        event_or_action_filter: ast.Expr | None = None,
    ):
        self._context = context
        self._filters = filters
        self._event_or_action_filter = event_or_action_filter
        self._cached_ratio_expr = None
        self._cached_sampling_factor = getattr(self._context.query, "samplingFactor", None)

        # If samplingFactor is not None, prebuild the RatioExpr for reuse
        if self._cached_sampling_factor is not None:
            self._cached_ratio_expr = ast.RatioExpr(left=ast.Constant(value=self._cached_sampling_factor))

    def to_query(self) -> ast.SelectQuery:
        query = ast.SelectQuery(
            select=[ast.Field(chain=["uuid"])],
            select_from=ast.JoinExpr(table=self._inner_query()),
        )
        return query

    def _inner_query(self) -> ast.SelectQuery | None:
        inner_query = ast.SelectQuery(select=[])
        builder = FirstTimeForUserEventsQueryAlternator(
            inner_query,
            self._date_from_expr(),
            self._date_to_expr(),
            self._filters,
            self._event_or_action_filter,
            self._ratio_expr(),
        )
        builder.append_select(self._select_expr(), aggregate=True)
        return cast(ast.SelectQuery, builder.build())

    def _select_expr(self):
        return ast.Alias(
            alias="uuid",
            expr=ast.Field(chain=["uuid"]),
        )

    def _date_range(self) -> QueryDateRange:
        team, query, now = self._context.team, self._context.query, self._context.now
        date_range = QueryDateRange(
            date_range=query.dateRange,
            team=team,
            interval=query.interval,
            now=now,
        )
        return date_range

    def _date_to_expr(self) -> ast.Expr:
        return ast.CompareOperation(
            op=ast.CompareOperationOp.LtEq,
            left=ast.Field(chain=["timestamp"]),
            right=ast.Constant(value=self._date_range().date_to()),
        )

    def _date_from_expr(self) -> ast.Expr:
        return ast.CompareOperation(
            op=ast.CompareOperationOp.GtEq,
            left=ast.Field(chain=["timestamp"]),
            right=ast.Constant(value=self._date_range().date_from()),
        )

    def _ratio_expr(self) -> ast.RatioExpr | None:
        # Access the attribute only once and return cached result if possible
        if self._cached_sampling_factor is None:
            return None
        return self._cached_ratio_expr

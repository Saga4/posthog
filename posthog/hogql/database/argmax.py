from typing import Optional


from posthog.hogql.ast import (
    Alias,
    And,
    Call,
    CompareOperation,
    CompareOperationOp,
    Constant,
    Field,
    JoinExpr,
    SelectQuery,
)
from posthog.hogql.parser import parse_expr


def argmax_select(
    table_name: str,
    select_fields: dict[str, list[str | int]],
    group_fields: list[str],
    argmax_field: str,
    deleted_field: Optional[str] = None,
    timestamp_field_to_clamp: Optional[str] = None,
) -> "SelectQuery":
    # --- Optimization: move type lookups out of loops & alias classes ---
    _Field = Field
    _Call = Call
    _Alias = Alias
    _JoinExpr = JoinExpr
    _CompareOperation = CompareOperation
    _CompareOperationOp = CompareOperationOp
    _And = And
    _Constant = Constant

    # Pre-build set for O(1) membership test for group_fields
    group_fields_set = set(group_fields)

    # Preallocate these lists
    fields_to_group = []
    fields_to_select = []

    table_field_cache = {}  # Avoid redundant Field construction

    # Helper to get Field for [table_name, k] with memoization
    def _table_field(key):
        if key not in table_field_cache:
            table_field_cache[key] = _Field(chain=[table_name, key])
        return table_field_cache[key]

    # Helper for argmax
    def argmax_version(field):
        return _Call(name="argMax", args=[field, _table_field(argmax_field)])

    # Build select/agg/alias fields in one loop
    for name, chain in select_fields.items():
        if name not in group_fields_set:  # O(1) due to set
            f = _Field(chain=[table_name, *chain])
            # Compose call + alias, reduce attribute lookup
            fields_to_select.append(
                _Alias(
                    alias=name,
                    expr=argmax_version(f),
                )
            )

    # Group fields and passthrough selects
    for key in group_fields:
        f = _table_field(key)
        fields_to_group.append(f)
        fields_to_select.append(_Alias(alias=key, expr=f))

    select_query = _Field(chain=[table_name])
    join_expr = _JoinExpr(table=select_query)
    select_query_obj = SelectQuery(
        select=fields_to_select,
        select_from=join_expr,
        group_by=fields_to_group,
    )

    # Having/filters
    if deleted_field:
        select_query_obj.having = _CompareOperation(
            op=_CompareOperationOp.Eq,
            left=argmax_version(_table_field(deleted_field)),
            right=_Constant(value=0),
        )
    if timestamp_field_to_clamp:
        clause = _CompareOperation(
            op=_CompareOperationOp.Lt,
            left=argmax_version(_table_field(timestamp_field_to_clamp)),
            right=parse_expr("now() + interval 1 day"),
        )
        if select_query_obj.having is None:
            select_query_obj.having = clause
        else:
            select_query_obj.having = _And(exprs=[select_query_obj.having, clause])

    return select_query_obj

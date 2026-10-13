"""Every query SiebDiff runs against the Siebel repository lives in this file.

Rows are read with `select *` and fields are picked by column name afterwards, so a
column that is missing in a given Siebel release is reported by name instead of
failing as a bare Oracle error.
"""
from .db import DbError


def _dicts(columns, rows):
    return [dict(zip(columns, row)) for row in rows]


def _require(table, columns, needed):
    missing = [name for name in needed if name not in columns]
    if missing:
        raise DbError(f"{table} does not have the expected column(s) {', '.join(missing)}. "
                      f"Columns found: {', '.join(columns)}.")


def _columns(db, table):
    columns, _ = db.query(f"select * from {db.info['owner']}.{table} where rownum < 1")
    return columns


def workspaces(db):
    owner = db.info["owner"]
    columns, rows = db.query(f"select * from {owner}.S_WORKSPACE")
    _require("S_WORKSPACE", columns, ("ROW_ID", "NAME"))
    items = [
        {
            "id": row["ROW_ID"],
            "name": row["NAME"],
            "parent_id": row.get("PAR_WS_ID"),
            "status": row.get("STATUS_CD"),
            "created": row.get("CREATED"),
        }
        for row in _dicts(columns, rows)
    ]
    names = {item["id"]: item["name"] for item in items}
    for item in items:
        item["parent"] = names.get(item["parent_id"])
    items.sort(key=lambda item: (item["name"] or "").upper())
    return items


def versions(db, workspace_id):
    owner = db.info["owner"]
    columns = _columns(db, "S_WS_VERSION")
    _require("S_WS_VERSION", columns, ("WS_ID", "VERSION_NUM"))
    columns, rows = db.query(f"select * from {owner}.S_WS_VERSION where WS_ID = :ws", {"ws": workspace_id})
    items = [
        {
            "id": row.get("ROW_ID"),
            "number": row["VERSION_NUM"],
            "created": row.get("CREATED"),
            "status": row.get("STATUS_CD"),
            "comments": row.get("COMMENTS") or row.get("DESC_TEXT"),
            "rebase_ver_id": row.get("REBASE_VER_ID"),
        }
        for row in _dicts(columns, rows)
    ]
    items.sort(key=lambda item: item["number"], reverse=True)
    return items


def parent_base(db, workspace_id):
    """The parent version a workspace is based on: the one it was created from, or last rebased from.

    Each version row carries REBASE_VER_ID, the ROW_ID of that parent version.
    """
    owner = db.info["owner"]
    items = versions(db, workspace_id)
    if not items:
        return {"latest": None, "base": None}
    latest = items[0]
    base = None
    if latest["rebase_ver_id"]:
        columns, rows = db.query(f"select * from {owner}.S_WS_VERSION where ROW_ID = :id",
                                 {"id": latest["rebase_ver_id"]})
        for row in _dicts(columns, rows):
            base = {
                "id": row["ROW_ID"],
                "workspace_id": row["WS_ID"],
                "number": row["VERSION_NUM"],
                "created": row.get("CREATED"),
                "comments": row.get("COMMENTS") or row.get("DESC_TEXT"),
            }
    return {"latest": latest, "base": base}


# --- Repository structure and changed rows ---------------------------------------

_IDS_PER_QUERY = 400


def repository_tables(db):
    """Names of the workspace-enabled repository tables, and the columns of each one's U1 index."""
    owner = db.info["owner"]
    _, names = db.query(
        "select table_name from all_tab_columns "
        "where owner = :owner and column_name = 'WS_OBJ_VER' order by table_name",
        {"owner": owner})
    _, index_rows = db.query(
        "select c.table_name, i.column_position, i.column_name "
        "from all_tab_columns c, all_ind_columns i "
        "where c.owner = :owner and c.column_name = 'WS_OBJ_VER' "
        "and i.table_owner = c.owner and i.table_name = c.table_name "
        "and i.index_name = c.table_name || '_U1' "
        "order by c.table_name, i.column_position",
        {"owner": owner})
    return [row[0] for row in names], index_rows


def _row_columns(table):
    columns = ["ROW_ID", "WS_SRC_ID", "WS_OBJ_VER", "WS_DELETE_FLG"]
    if table.has_name:
        columns.append("NAME")
    if table.parent_column:
        columns.append(table.parent_column)
    return ", ".join(columns)


def changed_rows(db, table, workspace_id, after=None, upto=None):
    """Rows of one table that belong to a workspace, optionally limited to versions after..upto.

    WS_OBJ_VER is the workspace's depth * 100000 + the version the row was changed in,
    so the version is the remainder.
    """
    owner = db.info["owner"]
    params = {"ws": workspace_id}
    if table.known:
        sql = f"select {_row_columns(table)} from {owner}.{table.name} where WS_ID = :ws"
    else:
        sql = f"select * from {owner}.{table.name} where WS_ID = :ws"
    if after is not None:
        sql += " and MOD(WS_OBJ_VER, 100000) > :after and MOD(WS_OBJ_VER, 100000) <= :upto"
        params.update(after=after, upto=upto)
    columns, rows = db.query(sql, params)
    return _dicts(columns, rows)


def rows_by_id(db, table, ids, column="ROW_ID"):
    """Look up rows of one table by ROW_ID (or by WS_SRC_ID), to find the names of parent objects."""
    owner = db.info["owner"]
    found = []
    ids = list(ids)
    for start in range(0, len(ids), _IDS_PER_QUERY):
        chunk = ids[start:start + _IDS_PER_QUERY]
        params = {f"b{n}": value for n, value in enumerate(chunk)}
        binds = ", ".join(f":b{n}" for n in range(len(chunk)))
        columns, rows = db.query(
            f"select {_row_columns(table)} from {owner}.{table.name} where {column} in ({binds})", params)
        found.extend(_dicts(columns, rows))
    return found

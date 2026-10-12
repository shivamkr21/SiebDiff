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
        }
        for row in _dicts(columns, rows)
    ]
    items.sort(key=lambda item: item["number"], reverse=True)
    return items

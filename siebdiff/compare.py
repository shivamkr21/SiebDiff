"""Reads the selected objects, with all their children, as they stood on each side of the comparison.

How a row is read "as of" a workspace version:
  1. the workspace's own newest copy at or before that version, if it has one;
  2. otherwise the parent workspace at the version this one was based on (REBASE_VER_ID),
     and so on up to MAIN.
A copy with WS_DELETE_FLG = 'Y' means the row does not exist on that side.
Copies of the same row in different workspaces share WS_SRC_ID, and children point
at their parent's WS_SRC_ID, so WS_SRC_ID is the identity used everywhere here.
"""
import datetime
import threading

from . import model, repo
from .db import DbError

# Columns that differ between copies of a row even when nothing was changed.
SYSTEM_COLUMNS = {
    "ROW_ID", "CREATED", "CREATED_BY", "LAST_UPD", "LAST_UPD_BY", "MODIFICATION_NUM", "CONFLICT_ID",
    "DB_LAST_UPD", "DB_LAST_UPD_SRC", "REPOSITORY_ID", "WS_ID", "WS_OBJ_VER", "WS_SRC_ID", "WS_DELETE_FLG",
    "PAR_ROW_ID",
}
_VERSION_SPAN = 100000
_MAX_CHAIN = 30


def _value(value):
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat(sep=" ")
    return value


def _key(row):
    return row.get("WS_SRC_ID") or row["ROW_ID"]


def side_chain(db, workspace_id, version):
    """[(workspace id, version), ...] from the workspace up through the parents it was based on."""
    chain = []
    seen = set()
    while workspace_id and workspace_id not in seen and len(chain) < _MAX_CHAIN:
        seen.add(workspace_id)
        chain.append((workspace_id, int(version)))
        row = next((v for v in repo.versions(db, workspace_id) if int(v["number"]) == int(version)), None)
        if row is None:
            raise DbError(f"Version {version} was not found for one of the workspaces being compared.")
        if not row["rebase_ver_id"]:
            break
        base = repo.version_by_id(db, row["rebase_ver_id"])
        if base is None:
            break
        workspace_id, version = base["workspace_id"], base["number"]
    return chain


def resolve(copies, chain):
    """The copy of one row that is visible at the end of `chain`, or None if it does not exist there."""
    for workspace_id, version in chain:
        best = None
        for row in copies:
            if row.get("WS_ID") != workspace_id:
                continue
            number = int(row.get("WS_OBJ_VER") or 0) % _VERSION_SPAN
            if number <= version and (best is None or number > int(best.get("WS_OBJ_VER") or 0) % _VERSION_SPAN):
                best = row
        if best is not None:
            return None if best.get("WS_DELETE_FLG") == "Y" else best
    return None


class Compare:
    def __init__(self, db, keys, chain_a, chain_b):
        self.db = db
        self.keys = keys            # ["S_APPLET:1-ABC", ...] from the changed-object search
        self.chains = (chain_a, chain_b)
        self.status = "running"
        self.done = 0
        self.total = 0
        self.current = ""
        self.error = None
        self.result = None
        self._cancel = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._cancel.set()

    def progress(self):
        data = {"status": self.status, "done": self.done, "total": self.total, "current": self.current}
        if self.status == "done":
            data["result"] = self.result
        if self.status == "error":
            data["error"] = self.error
        return data

    def _run(self):
        try:
            self.result = self._compare()
            self.status = "cancelled" if self.result is None else "done"
        except DbError as exc:
            self.error = str(exc)
            self.status = "error"
        except Exception as exc:  # never leave the UI polling a dead job
            self.error = f"Unexpected error: {exc}"
            self.status = "error"

    def _compare(self):
        names, index_rows = repo.repository_tables(self.db)
        tables = model.describe(names, index_rows)
        children_of = {}
        for table in tables.values():
            if table.known and table.parent in tables and table.parent_column:
                children_of.setdefault(table.parent, []).append(table)

        wanted = {}
        for key in self.keys:
            table, _, row_key = str(key).partition(":")
            if table in tables and tables[table].top_level and row_key:
                wanted.setdefault(table, set()).add(row_key)

        # Every table that can hold part of the selected objects, parents before children.
        order, queue = [], list(wanted)
        while queue:
            name = queue.pop(0)
            if name not in order:
                order.append(name)
                queue.extend(t.name for t in children_of.get(name, []))
        self.total = len(order)

        workspace_ids = sorted({ws for chain in self.chains for ws, _ in chain})
        copies = {}       # table -> logical key -> [row copies]
        parent_of = {}    # table -> logical key -> parent logical key
        ids_for = {name: set(keys) for name, keys in wanted.items()}

        for name in order:
            if self._cancel.is_set():
                return None
            self.current = name
            table = tables[name]
            ids = ids_for.get(name)
            if ids:
                column = table.parent_column if name not in wanted else "WS_SRC_ID"
                bucket = copies.setdefault(name, {})
                for row in repo.rows_for(self.db, name, column, ids, workspace_ids):
                    key = _key(row)
                    bucket.setdefault(key, []).append(row)
                    if table.parent_column:
                        parent_of.setdefault(name, {})[key] = row.get(table.parent_column)
                # Children are looked up by the keys of every row found here, on either side.
                for child in children_of.get(name, []):
                    ids_for.setdefault(child.name, set()).update(bucket)
            self.done += 1

        self.current = "Building objects"
        kids = {}  # (child table, parent key) -> [child keys]
        for name, parents in parent_of.items():
            for key, parent_key in parents.items():
                kids.setdefault((name, parent_key), []).append(key)
        sides = []
        for chain in self.chains:
            visible = {name: {key: resolve(rows, chain) for key, rows in bucket.items()}
                       for name, bucket in copies.items()}
            sides.append([obj for obj in (self._node(tables, children_of, visible, kids, name, key)
                                          for name in wanted for key in sorted(wanted[name]))
                          if obj is not None])
        return {"before": sides[0], "after": sides[1], "tables": len(order)}

    def _node(self, tables, children_of, visible, kids, name, key):
        row = visible.get(name, {}).get(key)
        if row is None:
            return None
        table = tables[name]
        hidden = SYSTEM_COLUMNS | ({table.parent_column} if table.parent_column else set())
        node = {
            "type": table.label,
            "name": row.get("NAME") or table.label,
            "id": key,
            "props": {col: _value(val) for col, val in row.items() if col not in hidden},
            "system": {col: _value(val) for col, val in row.items() if col in hidden},
            "children": [],
        }
        for child in children_of.get(name, []):
            for child_key in kids.get((child.name, key), []):
                sub = self._node(tables, children_of, visible, kids, child.name, child_key)
                if sub is not None:
                    node["children"].append(sub)
        node["children"].sort(key=lambda c: (c["type"], str(c["name"]).upper()))
        return node

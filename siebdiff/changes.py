"""Finds the objects a workspace changed, and groups every changed row under its top-level object.

Runs in a background thread because it visits every repository table; the UI polls for progress.
"""
import threading

from . import model, repo
from .db import DbError

_MAX_DEPTH = 10
_MAX_OTHER_NAMES = 25


class Scan:
    def __init__(self, db, workspace_id, depth, after=None, upto=None):
        self.db = db
        self.workspace_id = workspace_id
        self.depth = depth
        self.after = after
        self.upto = upto
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
            self.result = self._scan()
            self.status = "cancelled" if self.result is None else "done"
        except DbError as exc:
            self.error = str(exc)
            self.status = "error"
        except Exception as exc:  # never leave the UI polling a dead scan
            self.error = f"Unexpected error: {exc}"
            self.status = "error"

    def _scan(self):
        names, index_rows = repo.repository_tables(self.db)
        tables = model.describe(names, index_rows)
        self.total = len(tables)
        warnings = []

        # 1. Changed rows per table, one entry per object (its newest row in the range).
        changed = {}
        prefixes = set()
        for table in tables.values():
            if self._cancel.is_set():
                return None
            self.current = table.name
            try:
                rows = repo.changed_rows(self.db, table, self.workspace_id, self.after, self.upto)
            except DbError as exc:
                warnings.append(f"{table.name} could not be read: {exc}")
                rows = []
            latest = {}
            for row in rows:
                version = row.get("WS_OBJ_VER") or 0
                prefixes.add(int(version) // 100000)
                key = row.get("WS_SRC_ID") or row["ROW_ID"]
                if key not in latest or version > (latest[key].get("WS_OBJ_VER") or 0):
                    latest[key] = row
            if latest:
                changed[table.name] = latest
            self.done += 1

        unexpected = sorted(p for p in prefixes if p != self.depth)
        if unexpected:
            warnings.append(
                f"WS_OBJ_VER has prefix {', '.join(map(str, unexpected))} but this workspace is at depth "
                f"{self.depth}. The version filter may be wrong for this workspace.")

        # 2. Names of parent objects, walking up until every chain reaches a top-level object.
        self.current = "Resolving parent objects"
        known = {name: dict(rows) for name, rows in changed.items()}
        for _ in range(_MAX_DEPTH):
            if self._cancel.is_set():
                return None
            wanted = {}
            for name, rows in known.items():
                table = tables[name]
                if not table.parent_column or table.parent not in tables:
                    continue
                for row in rows.values():
                    if row is None:
                        continue
                    parent_id = row.get(table.parent_column)
                    if parent_id and parent_id not in known.get(table.parent, {}):
                        wanted.setdefault(table.parent, set()).add(parent_id)
            if not wanted:
                break
            for parent_name, ids in wanted.items():
                parent = tables[parent_name]
                bucket = known.setdefault(parent_name, {})
                try:
                    for row in repo.rows_by_id(self.db, parent, ids):
                        bucket.setdefault(row["ROW_ID"], row)
                    missing = [i for i in ids if i not in bucket]
                    if missing:
                        for row in repo.rows_by_id(self.db, parent, missing, "WS_SRC_ID"):
                            bucket.setdefault(row["WS_SRC_ID"], row)
                except DbError as exc:
                    warnings.append(f"{parent_name} could not be read: {exc}")
                for i in ids:
                    bucket.setdefault(i, None)  # not found: stop asking for it

        # 3. Group every changed row under its top-level object.
        objects = {}
        other = {}
        total_rows = 0
        for name, rows in changed.items():
            table = tables[name]
            for key, row in rows.items():
                total_rows += 1
                chain = self._chain(tables, known, table, key, row)
                if chain is None:
                    entry = other.setdefault(name, {"table": name, "type": table.label, "count": 0, "names": []})
                    entry["count"] += 1
                    if len(entry["names"]) < _MAX_OTHER_NAMES and row.get("NAME"):
                        entry["names"].append(row["NAME"])
                    continue
                top_table, top_key, top_row = chain[0]
                obj = objects.setdefault((top_table.name, top_key), {
                    "key": f"{top_table.name}:{top_key}", "table": top_table.name, "id": top_key,
                    "type": top_table.label, "name": (top_row or {}).get("NAME") or top_key,
                    "self_changed": False, "deleted": False, "changes": [],
                })
                deleted = row.get("WS_DELETE_FLG") == "Y"
                if len(chain) == 1:
                    obj["self_changed"] = True
                    obj["deleted"] = deleted
                else:
                    path = [f"{t.label} '{(r or {}).get('NAME') or k}'" for t, k, r in chain[1:-1]]
                    obj["changes"].append({
                        "table": name, "type": table.label, "name": row.get("NAME") or "",
                        "deleted": deleted, "path": " > ".join(path),
                    })
        result = sorted(objects.values(), key=lambda o: (o["type"], str(o["name"]).upper()))
        for obj in result:
            obj["changes"].sort(key=lambda c: (c["type"], c["path"], c["name"]))
        return {
            "objects": result,
            "other": sorted(other.values(), key=lambda o: o["table"]),
            "warnings": warnings,
            "tables": len(tables),
            "rows": total_rows,
        }

    @staticmethod
    def _chain(tables, known, table, key, row):
        """[(table, key, row), ...] from the top-level object down to this row, or None if it cannot be placed."""
        chain = [(table, key, row)]
        for _ in range(_MAX_DEPTH):
            if table.top_level:
                return list(reversed(chain))
            if not table.known or table.parent not in tables or row is None:
                return None
            parent_id = row.get(table.parent_column)
            parent_row = known.get(table.parent, {}).get(parent_id)
            if not parent_id or parent_row is None:
                return None
            table, key, row = tables[table.parent], parent_row.get("WS_SRC_ID") or parent_id, parent_row
            chain.append((table, key, row))
        return None

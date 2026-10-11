"""Oracle access. Thin mode only, so no Oracle client is needed. Read-only by design."""
import os
import re
import threading

try:
    import oracledb
    _IMPORT_ERROR = None
except ImportError as exc:  # e.g. the driver was blocked by an application control policy
    oracledb = None
    _IMPORT_ERROR = str(exc)

_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")

_HINTS = [
    (("ORA-01017",), "The user ID or password is not correct."),
    (("ORA-28000",), "This database account is locked."),
    (("ORA-28001",), "The password for this account has expired. Change it in SQL Developer first."),
    (("ORA-12154", "DPY-4000", "DPY-4026", "DPY-4027"), "The database name was not found in tnsnames.ora."),
    (("ORA-12514", "DPY-6001"), "The database server does not know this service name."),
    (("ORA-12505", "DPY-6003"), "The database server does not know this SID."),
    (("DPY-6005", "DPY-6000", "DPY-4011", "ORA-12541", "ORA-12170", "ORA-12545"),
     "Could not reach the database server. Check the host and port, and that you are on the right network or VPN."),
    (("DPY-3001",), "This database requires Native Network Encryption, which the built-in driver does not support."),
    (("DPY-3015",), "This account uses an old password format the built-in driver does not support."),
]


class DbError(Exception):
    def __init__(self, message, **extra):
        super().__init__(message)
        self.extra = extra


def _friendly(exc):
    detail = str(exc).strip()
    for codes, hint in _HINTS:
        if any(code in detail for code in codes):
            return f"{hint} ({detail})"
    return detail


_FOR_UPDATE = re.compile(r"\bfor\s+update\b", re.IGNORECASE)


def _select(cur, sql, params=None):
    """The only place a statement is sent to Oracle. Anything that is not a plain SELECT is refused."""
    text = sql.strip()
    if not text.lower().startswith("select") or ";" in text or _FOR_UPDATE.search(text):
        raise DbError("Only SELECT statements are allowed.")
    cur.execute(text, params or {})


class Database:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = None
        self.info = None

    @property
    def connected(self):
        return self._conn is not None

    def connect(self, *, mode, user, password, owner, alias="", tns_path="", host="", port=1521, service=""):
        if oracledb is None:
            raise DbError(f"The Oracle driver could not be loaded on this computer. ({_IMPORT_ERROR})")
        owner = (owner or "").strip().upper()
        if not _IDENT.match(owner):
            raise DbError("Table owner is not a valid schema name.")
        kwargs = {"user": user, "password": password, "tcp_connect_timeout": 15}
        if mode == "tns":
            kwargs["dsn"] = alias
            kwargs["config_dir"] = os.path.dirname(tns_path)
            target = alias
        else:
            kwargs["dsn"] = f"{host}:{int(port)}/{service}"
            target = kwargs["dsn"]

        try:
            conn = oracledb.connect(**kwargs)
        except oracledb.Error as exc:
            raise DbError(_friendly(exc)) from exc

        try:
            with conn.cursor() as cur:
                _select(cur, "select sys_context('USERENV','DB_NAME'), user from dual")
                db_name, db_user = cur.fetchone()
                _select(cur, "select owner from all_tables where table_name = 'S_WORKSPACE' order by owner")
                owners = [row[0] for row in cur]
                if owner not in owners:
                    if owners:
                        message = (f"Connected, but no Siebel repository tables were found under table owner "
                                   f"{owner}. They exist under: {', '.join(owners)}.")
                    else:
                        message = ("Connected, but this user cannot see any Siebel repository tables "
                                   "(S_WORKSPACE was not found in any schema).")
                    raise DbError(message, owners=owners)
                # owner is safe to place in the statement: it matched _IDENT and came back from all_tables.
                _select(cur, f"select count(*) from {owner}.S_WORKSPACE")
                workspaces = cur.fetchone()[0]
        except oracledb.Error as exc:
            conn.close()
            raise DbError(_friendly(exc)) from exc
        except DbError:
            conn.close()
            raise

        self.disconnect()
        with self._lock:
            self._conn = conn
            self.info = {
                "target": target,
                "database": db_name,
                "user": db_user,
                "owner": owner,
                "version": conn.version,
                "workspaces": workspaces,
            }
        return self.info

    def disconnect(self):
        with self._lock:
            conn, self._conn, self.info = self._conn, None, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def query(self, sql, params=None):
        """Run one SELECT and return (column names, rows)."""
        with self._lock:
            if self._conn is None:
                raise DbError("Not connected.")
            try:
                with self._conn.cursor() as cur:
                    _select(cur, sql, params)
                    columns = [d[0] for d in cur.description]
                    return columns, cur.fetchall()
            except oracledb.Error as exc:
                raise DbError(_friendly(exc)) from exc

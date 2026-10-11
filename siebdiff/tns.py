"""Locate tnsnames.ora and list the aliases defined in it."""
import os
import re
from pathlib import Path

FILE_NAME = "tnsnames.ora"
_ALIAS = re.compile(r"^[\w.\-]+$")


def _registry_dirs():
    try:
        import winreg
    except ImportError:
        return
    for root in (r"SOFTWARE\ORACLE", r"SOFTWARE\WOW6432Node\ORACLE"):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as key:
                count = winreg.QueryInfoKey(key)[0]
                names = [winreg.EnumKey(key, i) for i in range(count)]
                for name in [""] + names:
                    try:
                        with winreg.OpenKey(key, name) as sub:
                            for value in ("TNS_ADMIN", "ORACLE_HOME"):
                                try:
                                    yield value, winreg.QueryValueEx(sub, value)[0]
                                except OSError:
                                    pass
                    except OSError:
                        pass
        except OSError:
            pass


def _sqldeveloper_dirs():
    """SQL Developer stores a custom tnsnames folder in its preferences."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    base = Path(appdata) / "SQL Developer"
    try:
        prefs = sorted(base.glob("system*/o.sqldeveloper*/product-preferences.xml"), reverse=True)
    except OSError:
        return
    for pref in prefs:
        try:
            text = pref.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = re.search(r'n="TNSNAMES_DIR"\s+v="([^"]+)"', text)
        if match:
            yield match.group(1)


def candidate_dirs():
    seen = []

    def add(folder):
        if folder and folder not in seen:
            seen.append(folder)

    add(os.environ.get("TNS_ADMIN"))
    if os.environ.get("ORACLE_HOME"):
        add(os.path.join(os.environ["ORACLE_HOME"], "network", "admin"))
    for folder in _sqldeveloper_dirs():
        add(folder)
    for kind, value in _registry_dirs():
        add(value if kind == "TNS_ADMIN" else os.path.join(value, "network", "admin"))
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        # An Oracle client on PATH keeps its network files next to (or one level above) its binaries.
        if folder and os.path.isfile(os.path.join(folder, "oci.dll")):
            add(os.path.join(folder, "network", "admin"))
            add(os.path.join(os.path.dirname(folder.rstrip("\\/")), "network", "admin"))
    return seen


def find():
    for folder in candidate_dirs():
        path = os.path.join(folder, FILE_NAME)
        if os.path.isfile(path):
            return path
    return ""


def resolve(path):
    """Accept either the file itself or the folder holding it."""
    path = (path or "").strip().strip('"')
    if not path:
        return ""
    if os.path.isdir(path):
        path = os.path.join(path, FILE_NAME)
    return path if os.path.isfile(path) else ""


def parse_aliases(text):
    text = re.sub(r"#.*", "", text)
    aliases, buf, depth = [], [], 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            if ch == "=":
                lines = [ln.strip() for ln in "".join(buf).splitlines() if ln.strip()]
                buf = []
                if not lines or lines[-1].upper() == "IFILE":
                    continue
                for name in lines[-1].split(","):
                    name = name.strip()
                    if _ALIAS.match(name) and name not in aliases:
                        aliases.append(name)
            else:
                buf.append(ch)
    return sorted(aliases, key=str.upper)


def read_aliases(path):
    try:
        return parse_aliases(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return []

from __future__ import annotations

import argparse
import importlib
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.sql_helper import SqlF


DEPENDENCIES = {
    "PySide2": "GUI",
    "cv2": "OpenCV video and face recognition",
    "pymysql": "MySQL connector",
    "PIL": "image loading",
    "numpy": "array processing",
}


def check_environment() -> int:
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"OS: {platform.platform()}")

    ok = True
    major, minor = sys.version_info[:2]
    if not (major == 3 and 8 <= minor <= 10):
        ok = False
        print("WARN Python 3.8-3.10 is recommended; old PySide2 does not support newer Python well.")

    for module, purpose in DEPENDENCIES.items():
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, "__version__", "")
            print(f"OK   {module:<8} {version} - {purpose}")
        except Exception as exc:
            ok = False
            print(f"MISS {module:<8} - {purpose}: {exc}")

    try:
        sql = SqlF()
        print(f"DB: {sql.backend}")
        print(f"Accounts: {[row[0] for row in sql.getAllaccount()]}")
        print(f"admin/admin: {sql.verify_login('admin', 'admin')}")
        sql.dbclose()
    except Exception as exc:
        ok = False
        print(f"DB ERROR: {exc}")

    return 0 if ok else 1


def reset_admin(password: str) -> int:
    sql = SqlF()
    existing = [row[0] for row in sql.getAllaccount()]
    if "admin" in existing:
        sql.cursor.execute(f"DELETE FROM accounts WHERE username = {sql.param}", ("admin",))
        sql.db.commit()
    sql.register("admin", password)
    print("Admin account reset.")
    print(f"DB: {sql.backend}")
    print(f"admin/{password}: {sql.verify_login('admin', password)}")
    sql.dbclose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Facial recognition system setup helper")
    parser.add_argument("--reset-admin", metavar="PASSWORD", help="reset the admin password")
    args = parser.parse_args()

    if args.reset_admin:
        return reset_admin(args.reset_admin)
    return check_environment()


if __name__ == "__main__":
    raise SystemExit(main())

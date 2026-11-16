"""SQLite connection and single-worker atomic publication facility."""
import sqlite3
from contextlib import contextmanager

def connect(path):
    db = sqlite3.connect(str(path), isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    return db

@contextmanager
def atomic(db, before_commit=None):
    """No nesting. Any exception, including a pre-commit hook, rolls back DDL/DML."""
    if db.in_transaction:
        raise RuntimeError("nested transaction")
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        if before_commit is not None:
            before_commit()
        db.commit()
    except BaseException:
        db.rollback()
        raise

def create_legacy(db):
    """Create the complete old schema. Existing databases are never reset."""
    with atomic(db):
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO metadata VALUES ('storage_version','1')")
        db.execute("""CREATE TABLE regions1 (
            region_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision>0),
            rings_json TEXT NOT NULL)""")
        db.execute("""CREATE TABLE windows1 (
            name TEXT PRIMARY KEY, window_json TEXT NOT NULL, ids_json TEXT NOT NULL)""")

def version(db):
    row = db.execute("SELECT value FROM metadata WHERE key='storage_version'").fetchone()
    if row is None:
        raise ValueError("missing storage version")
    return int(row[0])

"""Apply versioned additive migrations: python -m server.database.migrate."""

import os

import psycopg

from server.config import ROOT_DIR


def migrate():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    migration_dir = ROOT_DIR / "migrations"
    applied = []
    # Do not register pgvector before its extension is installed on a fresh DB.
    with psycopg.connect(database_url, connect_timeout=10) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(731940384);")
        cursor.execute((migration_dir / "init.sql").read_text(encoding="utf-8"))
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version VARCHAR(255) PRIMARY KEY,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
               );"""
        )
        for path in sorted(migration_dir.glob("[0-9]*.sql")):
            cursor.execute("SELECT 1 FROM schema_migrations WHERE version = %s;", (path.name,))
            if cursor.fetchone():
                continue
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s);", (path.name,))
            applied.append(path.name)
    return applied


def main():
    try:
        applied = migrate()
    except Exception as error:
        if "Refusing to change populated document_chunks" in str(error):
            print("Migration refused: populated embeddings are incompatible with vector(384). Data is preserved; plan explicit re-embedding.")
        else:
            print(f"Migration failed ({type(error).__name__}); all changes rolled back. Check the database connection and permissions.")
        return 1
    print("Applied migrations: " + (", ".join(applied) if applied else "none (schema is current)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

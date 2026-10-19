
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql, params=()):
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def inspect_database():
    with connect() as conn:
        tables = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
        """).fetchall()

        print("Database:", DB_PATH)
        print("Existing tables:")
        for table in tables:
            print("-", table["name"])

        for table_name in (
            "students", "teachers", "attendance", "password_resets"
        ):
            exists = conn.execute("""
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
            """, (table_name,)).fetchone()

            if exists:
                columns = conn.execute(
                    f'PRAGMA table_info("{table_name}")'
                ).fetchall()
                print(f"\n{table_name} columns:")
                print(", ".join(column["name"] for column in columns))


def migrate_attendance_for_teachers():
    """Add teacher-wise attendance support without deleting old records."""
    with connect() as conn:
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(attendance)"
            ).fetchall()
        }

        if not columns:
            raise RuntimeError(
                "Attendance table not found. No migration was performed."
            )

        if "teacher_id" not in columns:
            conn.execute(
                "ALTER TABLE attendance ADD COLUMN teacher_id INTEGER"
            )

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attendance_teacher_date
            ON attendance (teacher_id, date)
        """)

    print("Attendance migration complete.")
    print("Existing attendance records preserved.")
    print("Old records remain unassigned to a teacher.")


if __name__ == "__main__":
    migrate_attendance_for_teachers()
    inspect_database()
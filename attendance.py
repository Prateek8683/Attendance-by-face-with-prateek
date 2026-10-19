
import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"


def create_attendance_table():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_no TEXT NOT NULL,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                UNIQUE(roll_no, date)
            )
        """)


def mark_attendance(roll_no, name):
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO attendance
            (roll_no, name, date, time)
            VALUES (?, ?, ?, ?)
        """, (roll_no, name, date, time))

        if cursor.rowcount == 1:
            print(f"Attendance marked: {name} ({roll_no}) at {time}")
        else:
            print(f"Already marked today: {name} ({roll_no})")


def view_attendance():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT roll_no, name, date, time
            FROM attendance
            ORDER BY date DESC, time DESC
        """).fetchall()

    if not rows:
        print("No attendance records found.")
        return

    print("\n--- ATTENDANCE RECORDS ---")
    print(f"{'Roll No':<15}{'Name':<20}{'Date':<15}{'Time'}")
    print("-" * 65)

    for roll, name, date, time in rows:
        print(f"{roll:<15}{name:<20}{date:<15}{time}")


if __name__ == "__main__":
    create_attendance_table()

    while True:
        print("\n1. Mark attendance (manual test)")
        print("2. View attendance")
        print("3. Exit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            roll_no = input("Enter registered roll number: ").strip()

            with sqlite3.connect(DB_PATH) as conn:
                student = conn.execute(
                    "SELECT roll_no, name FROM students WHERE roll_no = ?",
                    (roll_no,)
                ).fetchone()

            if student:
                confirm = input(
                    f"Mark attendance for {student[1]}? (yes/no): "
                ).strip().lower()

                if confirm == "yes":
                    mark_attendance(student[0], student[1])
            else:
                print("Student not registered.")

        elif choice == "2":
            view_attendance()

        elif choice == "3":
            break

        else:
            print("Invalid choice. Try again.")
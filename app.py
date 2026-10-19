from flask import Flask, render_template, request, Response, jsonify
from pathlib import Path
from datetime import date
import sqlite3
import csv
import io
import threading
import webbrowser
import subprocess
import sys
import atexit
import re
from auth import init_auth

app = Flask(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "students.db"
REGISTER_SCRIPT = PROJECT_DIR / "register.py"
RECOGNIZE_SCRIPT = PROJECT_DIR / "recognize.py"
REGISTER_LOG = PROJECT_DIR / "registration.log"

recognition_process = None
registration_process = None
process_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Create tables and safely add contact columns to older databases."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                roll_no TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                contact TEXT DEFAULT ''
            )
        """)
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(students)")
        }
        if "email" not in columns:
            conn.execute("ALTER TABLE students ADD COLUMN email TEXT DEFAULT ''")
        if "contact" not in columns:
            conn.execute("ALTER TABLE students ADD COLUMN contact TEXT DEFAULT ''")
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


init_database()
init_auth(app)


def process_status(process):
    if process is None:
        return "stopped"
    return "running" if process.poll() is None else "stopped"


def read_registration_log():
    try:
        lines = REGISTER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-8:])
    except OSError:
        return ""


def stop_process(process_name):
    global recognition_process, registration_process
    with process_lock:
        process = recognition_process if process_name == "recognition" else registration_process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process_name == "recognition":
            recognition_process = None
        else:
            registration_process = None


def cleanup_processes():
    stop_process("recognition")
    stop_process("registration")


atexit.register(cleanup_processes)


@app.route("/")
def dashboard():
    selected_date = request.args.get("date", date.today().isoformat())
    search = request.args.get("q", "").strip()
    try:
        selected_date = date.fromisoformat(selected_date).isoformat()
    except (ValueError, TypeError):
        selected_date = date.today().isoformat()

    try:
        with get_db() as conn:
            students = conn.execute("""
                SELECT roll_no, name, email, contact
                FROM students ORDER BY roll_no
            """).fetchall()

            records = conn.execute("""
                SELECT a.roll_no, a.name, a.date, a.time
                FROM attendance a
                WHERE a.date = ?
                  AND (a.roll_no LIKE ? OR a.name LIKE ?)
                ORDER BY a.time DESC
            """, (selected_date, f"%{search}%", f"%{search}%")).fetchall()

            total = len(students)
            present = conn.execute("""
                SELECT COUNT(DISTINCT roll_no) FROM attendance WHERE date = ?
            """, (selected_date,)).fetchone()[0]

        absent = max(0, total - present)
        rate = round(present * 100 / total) if total else 0
        error = None
    except sqlite3.Error as exc:
        students, records = [], []
        total = present = absent = rate = 0
        error = str(exc)

    return render_template(
        "home.html", page="home", students=students, records=records,
        selected_date=selected_date, search=search, total=total,
        present=present, absent=absent, rate=rate, error=error
    )


@app.get("/api/recognition/status")
def recognition_status():
    return jsonify({"status": process_status(recognition_process)})


@app.post("/api/recognition/start")
def start_recognition():
    global recognition_process
    if not RECOGNIZE_SCRIPT.is_file():
        return jsonify(ok=False, message="recognize.py file nahi mili."), 404

    with process_lock:
        if process_status(recognition_process) == "running":
            return jsonify(ok=True, status="running", message="Recognition pehle se chal rahi hai.")
        try:
            recognition_process = subprocess.Popen(
                [sys.executable, str(RECOGNIZE_SCRIPT)],
                cwd=str(PROJECT_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False
            )
        except OSError as exc:
            return jsonify(ok=False, message=f"Recognition start nahi hui: {exc}"), 500

    return jsonify(ok=True, status="running", message="Recognition launch ki gayi. Webcam window check karo.")


@app.post("/api/recognition/stop")
def stop_recognition():
    try:
        stop_process("recognition")
        return jsonify(ok=True, status="stopped", message="Recognition process stop kar diya.")
    except (OSError, subprocess.SubprocessError) as exc:
        return jsonify(ok=False, message=f"Stop karne mein problem: {exc}"), 500


@app.post("/api/register/start")
def start_registration():
    global registration_process

    data = request.get_json(silent=True) or request.form
    roll_no = str(data.get("roll_no", "")).strip()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    contact = str(data.get("contact", "")).strip()

    if not roll_no or not name or not email or not contact:
        return jsonify(ok=False, message="Roll number, name, email aur contact sab bharna zaroori hai."), 400
    if len(roll_no) > 40 or len(name) > 100:
        return jsonify(ok=False, message="Roll number ya name bahut lamba hai."), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(ok=False, message="Valid email address enter karo."), 400
    if not re.fullmatch(r"[0-9+()\-\s]{7,20}", contact):
        return jsonify(ok=False, message="Valid contact number enter karo."), 400
    if not REGISTER_SCRIPT.is_file():
        return jsonify(ok=False, message="register.py file nahi mili."), 404

    with process_lock:
        if process_status(registration_process) == "running":
            return jsonify(ok=False, message="Ek registration pehle se chal rahi hai."), 409
        try:
            with get_db() as conn:
                exists = conn.execute("SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
            if exists:
                return jsonify(ok=False, message="Ye roll number pehle se registered hai."), 409

            REGISTER_LOG.write_text("Registration starting...\n", encoding="utf-8")
            log_file = open(REGISTER_LOG, "a", encoding="utf-8")
            registration_process = subprocess.Popen(
                [sys.executable, str(REGISTER_SCRIPT),
                 "--roll-no", roll_no, "--name", name,
                 "--email", email, "--contact", contact],
                cwd=str(PROJECT_DIR),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                shell=False
            )
            # The child inherits its own handle; close the parent's handle.
            log_file.close()
        except OSError as exc:
            return jsonify(ok=False, message=f"Registration start nahi hui: {exc}"), 500

    return jsonify(ok=True, status="running", message="Webcam registration start ho gayi. Camera window mein ek face rakho; Q se cancel kar sakte ho.")


@app.get("/api/register/status")
def registration_status():
    global registration_process
    status = process_status(registration_process)
    log = read_registration_log()
    success = "REGISTRATION_SUCCESS" in log
    if status == "stopped" and registration_process is not None:
        code = registration_process.returncode
        if success:
            message = "Registration complete! Student aur face samples save ho gaye."
        elif code not in (None, 0):
            message = "Registration fail hui. Log check karo."
        else:
            message = "Registration process band ho gaya."
        return jsonify(status="stopped", success=success, message=message, log=log)
    return jsonify(status=status, success=success, message="Webcam capture chal rahi hai." if status == "running" else "Registration start nahi hui.", log=log)


@app.post("/api/register/stop")
def stop_registration():
    try:
        stop_process("registration")
        return jsonify(ok=True, status="stopped", message="Registration process stop kar diya.")
    except (OSError, subprocess.SubprocessError) as exc:
        return jsonify(ok=False, message=f"Registration stop nahi hui: {exc}"), 500



@app.route("/register")
def register_page():
    return render_template("register.html", page="register")


@app.route("/recognition")
def recognition_page():
    return render_template("recognition.html", page="recognition")


@app.route("/students")
def students_page():
    with get_db() as conn:
        students = conn.execute(
            "SELECT roll_no, name, email, contact FROM students ORDER BY roll_no"
        ).fetchall()
    return render_template("students.html", page="students", students=students)


@app.route("/attendance")
def attendance_page():
    selected_date = request.args.get("date", date.today().isoformat())
    search = request.args.get("q", "").strip()
    try:
        selected_date = date.fromisoformat(selected_date).isoformat()
    except (ValueError, TypeError):
        selected_date = date.today().isoformat()
    with get_db() as conn:
        records = conn.execute("""
            SELECT roll_no, name, date, time FROM attendance
            WHERE date = ? AND (roll_no LIKE ? OR name LIKE ?)
            ORDER BY time DESC
        """, (selected_date, f"%{search}%", f"%{search}%")).fetchall()
    return render_template(
        "attendance.html", page="attendance", records=records,
        selected_date=selected_date, search=search
    )


@app.route("/system")
def system_page():
    with get_db() as conn:
        student_count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        attendance_count = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    return render_template(
        "system.html", page="system", student_count=student_count,
        attendance_count=attendance_count,
        recognition_status=process_status(recognition_process),
        registration_status=process_status(registration_process)
    )


@app.get("/export")
def export_csv():
    selected_date = request.args.get("date", date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_date).isoformat()
    except (ValueError, TypeError):
        selected_date = date.today().isoformat()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Roll Number", "Name", "Date", "Time", "Status"])

    with get_db() as conn:
        rows = conn.execute("""
            SELECT roll_no, name, date, time
            FROM attendance WHERE date = ? ORDER BY time DESC
        """, (selected_date,)).fetchall()
        for row in rows:
            writer.writerow([row["roll_no"], row["name"], row["date"], row["time"], "Present"])

    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=attendance_{selected_date}.csv"}
    )


if __name__ == "__main__":
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
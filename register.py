import argparse
import cv2
import sqlite3
import re
import shutil
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"
FACES_DIR = BASE_DIR / "data" / "faces"
FACES_DIR.mkdir(parents=True, exist_ok=True)


def create_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                roll_no TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                contact TEXT DEFAULT ''
            )
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(students)")}
        if "email" not in columns:
            conn.execute("ALTER TABLE students ADD COLUMN email TEXT DEFAULT ''")
        if "contact" not in columns:
            conn.execute("ALTER TABLE students ADD COLUMN contact TEXT DEFAULT ''")


def capture_and_register(roll_no, name, email, contact):
    if not all(value.strip() for value in (roll_no, name, email, contact)):
        print("All student fields are required.")
        return False

    safe_roll = re.sub(r"[^A-Za-z0-9_-]", "_", roll_no)
    student_dir = FACES_DIR / safe_roll
    temp_dir = FACES_DIR / (safe_roll + "_capture_temp")

    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM students WHERE roll_no = ?", (roll_no,)).fetchone():
            print("This roll number is already registered.")
            return False

    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if detector.empty():
        print("ERROR: Face detector could not load.")
        return False

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("ERROR: Camera could not open. Close apps using the webcam and try again.")
        return False

    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    max_samples = 10
    frame_counter = 0
    print("Keep only one face in the camera. Move your head slightly between samples. Press Q to cancel.", flush=True)

    try:
        while count < max_samples:
            ok, frame = camera.read()
            if not ok:
                print("ERROR: Cannot read from camera.", flush=True)
                break

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
            )

            if len(faces) == 1:
                x, y, w, h = faces[0]
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                frame_counter += 1
                if frame_counter % 8 == 0:
                    face = gray[y:y+h, x:x+w]
                    face = cv2.resize(face, (200, 200))
                    if cv2.imwrite(str(temp_dir / f"{count + 1}.jpg"), face):
                        count += 1
            elif len(faces) > 1:
                cv2.putText(frame, "Only one person in frame", (20, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.putText(frame, f"Student: {name}", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            cv2.putText(frame, f"Samples: {count}/{max_samples}", (20, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            cv2.imshow("FaceTrack - Student Registration (Q to cancel)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("Registration cancelled by user.", flush=True)
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()

    if count != max_samples:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"Registration incomplete: captured {count}/{max_samples} samples.", flush=True)
        return False

    # Save student details only after face capture succeeds.
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO students (roll_no, name, email, contact)
                VALUES (?, ?, ?, ?)
            """, (roll_no, name, email, contact))
        if student_dir.exists():
            shutil.rmtree(student_dir)
        temp_dir.rename(student_dir)
    except (sqlite3.Error, OSError) as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"ERROR: Could not save student: {exc}", flush=True)
        return False

    print(f"Saved 10 face samples to {student_dir}", flush=True)
    print("REGISTRATION_SUCCESS", flush=True)
    print(f"Registration successful: {name} ({roll_no})", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roll-no")
    parser.add_argument("--name")
    parser.add_argument("--email", default="")
    parser.add_argument("--contact", default="")
    args = parser.parse_args()

    create_database()
    if args.roll_no and args.name:
        return 0 if capture_and_register(args.roll_no.strip(), args.name.strip(),
                                         args.email.strip(), args.contact.strip()) else 1

    # Backward-compatible terminal mode
    roll_no = input("Enter Roll Number: ").strip()
    name = input("Enter Student Name: ").strip()
    email = input("Enter Student Email: ").strip()
    contact = input("Enter Contact Number: ").strip()
    return 0 if capture_and_register(roll_no, name, email, contact) else 1


if __name__ == "__main__":
    sys.exit(main())

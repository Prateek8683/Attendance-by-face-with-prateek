
import cv2
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"
FACES_DIR = BASE_DIR / "data" / "faces"
MODEL_PATH = BASE_DIR / "face_model.yml"
LABELS_PATH = BASE_DIR / "face_labels.npz"


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
        return True

    return False


def train_model():
    if not hasattr(cv2, "face"):
        print("OpenCV face module missing.")
        print("Install opencv-contrib-python.")
        return False

    if not DB_PATH.exists():
        print("Student database not found. Register students first.")
        return False

    images = []
    labels = []
    label_map = {}
    current_label = 0

    with sqlite3.connect(DB_PATH) as conn:
        students = conn.execute(
            "SELECT roll_no, name FROM students"
        ).fetchall()

    for roll_no, name in students:
        safe_roll = "".join(
            c if c.isalnum() or c in "_-" else "_"
            for c in roll_no
        )
        folder = FACES_DIR / safe_roll
        student_has_images = False

        if not folder.exists():
            continue

        for image_path in folder.glob("*.jpg"):
            image = cv2.imread(
                str(image_path), cv2.IMREAD_GRAYSCALE
            )

            if image is None:
                continue

            image = cv2.resize(image, (200, 200))
            images.append(image)
            labels.append(current_label)
            student_has_images = True

        if student_has_images:
            label_map[current_label] = (roll_no, name)
            current_label += 1

    if not images:
        print("No face samples found. Register a student first.")
        return False

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(images, np.array(labels, dtype=np.int32))
    recognizer.save(str(MODEL_PATH))

    np.savez(
        str(LABELS_PATH),
        labels=np.array([
            [label, roll, name]
            for label, (roll, name) in label_map.items()
        ], dtype=str)
    )

    print("Model trained successfully.")
    print("Registered identities with samples:", len(label_map))
    return True


def run_recognition():
    if not MODEL_PATH.exists() or not LABELS_PATH.exists():
        print("Recognition model not found.")
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(MODEL_PATH))

    saved = np.load(LABELS_PATH, allow_pickle=False)
    label_map = {
        int(row[0]): (row[1], row[2])
        for row in saved["labels"]
    }

    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades
        + "haarcascade_frontalface_default.xml"
    )

    if detector.empty():
        print("Face detector could not load.")
        return

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Camera could not open.")
        return

    # Avoid repeated database writes for the same person in this run.
    marked_this_session = set()
    print("Recognition started. Press Q to exit.")

    try:
        while True:
            success, frame = camera.read()

            if not success:
                break

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(80, 80)
            )

            for (x, y, w, h) in faces:
                face = gray[y:y+h, x:x+w]
                face = cv2.resize(face, (200, 200))

                label, confidence = recognizer.predict(face)

                # Starting threshold only; calibrate with test data.
                if confidence < 65 and label in label_map:
                    roll_no, name = label_map[label]
                    color = (0, 255, 0)

                    if roll_no not in marked_this_session:
                        inserted = mark_attendance(roll_no, name)
                        marked_this_session.add(roll_no)

                    display_text = f"{name} ({roll_no})"
                else:
                    color = (0, 0, 255)
                    display_text = "Unknown"

                cv2.rectangle(
                    frame, (x, y), (x+w, y+h), color, 2
                )
                cv2.putText(
                    frame, display_text, (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, color, 2
                )

            cv2.imshow("Automatic Face Attendance", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    create_attendance_table()

    if train_model():
        run_recognition()
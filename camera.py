
import cv2

def main():
    # Load the pre-trained face detector
    detector_path = (
        cv2.data.haarcascades
        + "haarcascade_frontalface_default.xml"
    )

    face_detector = cv2.CascadeClassifier(detector_path)

    if face_detector.empty():
        print("Error: Face detector not found!")
        return

    # Open webcam
    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Error: Camera not found!")
        return

    print("Face Detection Started!")
    print("Press Q to exit.")

    while True:
        success, frame = camera.read()

        if not success:
            print("Cannot read camera.")
            break

        # Flip camera horizontally (mirror view)
        frame = cv2.flip(frame, 1)

        # Convert frame to grayscale
        gray = cv2.cvtColor(
            frame, cv2.COLOR_BGR2GRAY
        )

        # Detect faces
        faces = face_detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(50, 50)
        )

        # Draw a green box around every detected face
        for (x, y, w, h) in faces:
            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                "Face Detected",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

        # Display face count
        cv2.putText(
            frame,
            f"Faces: {len(faces)}",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2
        )

        # Show camera window
        cv2.imshow("Face Attendance System", frame)

        # Press Q to quit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
import cv2
import mediapipe as mp
import pyautogui
import time
from collections import deque

# ---------------- SETTINGS ----------------

CAMERA_INDEX = 0

# Hold your gaze this long before a slide changes.
HOLD_SECONDS = 0.8

# Require the eyes to return near the center before
# another slide change can happen.
CENTER_MIN = 0.40
CENTER_MAX = 0.60

# Adjust these if the controller is too sensitive.
LEFT_THRESHOLD = 0.32
RIGHT_THRESHOLD = 0.68

# Smooth small, noisy changes in iris position.
SMOOTHING_FRAMES = 5

# ------------------------------------------

pyautogui.FAILSAFE = True

mp_face_mesh = mp.solutions.face_mesh

camera = cv2.VideoCapture(CAMERA_INDEX)

if not camera.isOpened():
    raise RuntimeError(
        "Could not open webcam. Check CAMERA_INDEX "
        "and make sure another app is not using it."
    )

gaze_history = deque(maxlen=SMOOTHING_FRAMES)

# Face Mesh iris landmark groups
LEFT_IRIS = [468, 469, 470, 471, 472]
RIGHT_IRIS = [473, 474, 475, 476, 477]

# Eye corner landmarks
LEFT_EYE_CORNERS = [33, 133]
RIGHT_EYE_CORNERS = [362, 263]

gaze_started = None
current_direction = "CENTER"
armed = True


def average_x(landmarks, indices):
    """Average horizontal position of selected landmarks."""
    return sum(landmarks[i].x for i in indices) / len(indices)


def eye_ratio(landmarks, iris_indices, corner_indices):
    """
    Estimate horizontal iris position relative to the eye.
    Returns roughly 0 at one edge and 1 at the other.
    """
    iris_x = average_x(landmarks, iris_indices)

    corner_a = landmarks[corner_indices[0]].x
    corner_b = landmarks[corner_indices[1]].x

    eye_left = min(corner_a, corner_b)
    eye_right = max(corner_a, corner_b)
    eye_width = eye_right - eye_left

    if eye_width < 0.001:
        return None

    return (iris_x - eye_left) / eye_width


def classify_gaze(ratio):
    if ratio < LEFT_THRESHOLD:
        return "LEFT"
    elif ratio > RIGHT_THRESHOLD:
        return "RIGHT"
    elif CENTER_MIN <= ratio <= CENTER_MAX:
        return "CENTER"
    else:
        return "HOLD"


def change_slide(direction):
    """Send a navigation key to the active application."""
    if direction == "RIGHT":
        pyautogui.press("right")
        print("Next slide")
    elif direction == "LEFT":
        pyautogui.press("left")
        print("Previous slide")


print("Eye PowerPoint Controller started.")
print("Look left or right and hold your gaze.")
print("Click PowerPoint's slideshow to give it focus.")
print("Close the camera preview or press Ctrl+C to stop.")

try:
    with mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    ) as face_mesh:

        while True:
            success, frame = camera.read()

            if not success:
                print("Could not read webcam frame.")
                break

            # Mirror the preview like a normal selfie camera.
            frame = cv2.flip(frame, 1)

            rgb_frame = cv2.cvtColor(
                frame, cv2.COLOR_BGR2RGB
            )

            results = face_mesh.process(rgb_frame)

            status = "Face not detected"
            ratio = None

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark

                left_ratio = eye_ratio(
                    landmarks, LEFT_IRIS, LEFT_EYE_CORNERS
                )
                right_ratio = eye_ratio(
                    landmarks, RIGHT_IRIS, RIGHT_EYE_CORNERS
                )

                if left_ratio is not None and right_ratio is not None:
                    # Average both eyes for a more stable estimate.
                    ratio = (left_ratio + right_ratio) / 2
                    gaze_history.append(ratio)

                    smooth_ratio = sum(gaze_history) / len(gaze_history)
                    direction = classify_gaze(smooth_ratio)

                    now = time.monotonic()

                    # Centering rearms the next command.
                    if direction == "CENTER":
                        armed = True
                        gaze_started = None
                        current_direction = "CENTER"

                    elif direction in ("LEFT", "RIGHT"):
                        if direction != current_direction:
                            current_direction = direction
                            gaze_started = now

                        elif gaze_started is None:
                            gaze_started = now

                        elif armed and now - gaze_started >= HOLD_SECONDS:
                            change_slide(direction)
                            armed = False
                            gaze_started = None

                    else:
                        # Uncertain gaze: do not trigger a command.
                        gaze_started = None
                        current_direction = "HOLD"

                    status = (
                        f"Gaze: {direction} | "
                        f"Ratio: {smooth_ratio:.2f}"
                    )

                    if not armed:
                        status += " | Return to CENTER to rearm"

            cv2.putText(
                frame,
                status,
                (15, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2
            )

            cv2.imshow("Eye PowerPoint Controller", frame)

            # Closing the preview window stops the controller.
            try:
                if cv2.getWindowProperty(
                    "Eye PowerPoint Controller",
                    cv2.WND_PROP_VISIBLE
                ) < 1:
                    break
            except cv2.error:
                break

            # Q works when the camera preview has keyboard focus.
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

finally:
    camera.release()
    cv2.destroyAllWindows()
    print("Eye controller stopped.")



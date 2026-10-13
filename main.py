import cv2
import time
import pyautogui
import mediapipe as mp
from collections import deque


mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1,
                       min_detection_confidence=0.7,
                       min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

COOLDOWN = 1.0
LOCK_HOLD = 1.5

# --- Swipe settings ---
SWIPE_THRESHOLD = 0.18   # min horizontal travel (fraction of frame width)
SWIPE_WINDOW = 0.5       # seconds of motion history considered
SWIPE_MIN_SAMPLES = 4    # min frames needed in the window
SWIPE_COOLDOWN = 0.7     # seconds between swipes / after any action
SWIPE_MAX_DRIFT = 0.6    # max vertical/horizontal ratio (keeps it a horizontal swipe)

# gesture: (key, command, seconds to hold)
ACTIONS = {
    "index": ("right", "Next slide", 0.4),
    "two": ("left", "Previous slide", 0.4),
    "three": ("b", "Black screen on/off", 0.6),
    "pinky": ("esc", "End slideshow", 0.8),
    "thumb": ("home", "First slide", 0.6),
    "palm": ("volumemute", "Mute / unmute", 1.0),
    "swipeleft": ("right", "Next slide", 0.4),
    "swiperight": ("left", "Previous slide", 0.4),
}

def fingers_up(lm):
    return tuple(1 if lm[t].y < lm[t - 2].y else 0
                 for t in (8, 12, 16, 20))

def thumb_up(lm):
    top = min(lm[6].y, lm[10].y, lm[14].y, lm[18].y)
    return lm[4].y < top - 0.05

def detect_swipe(history):
    if len(history) < SWIPE_MIN_SAMPLES:
        return None
    dx = history[-1][1] - history[0][1]
    dy = history[-1][2] - history[0][2]
    if abs(dx) < SWIPE_THRESHOLD:
        return None
    if abs(dy) > abs(dx) * SWIPE_MAX_DRIFT:
        return None
    return "right" if dx > 0 else "left"

def classify(lm):
    f = fingers_up(lm)
    if f == (0, 0, 0, 0):
        return "thumb" if thumb_up(lm) else "fist"
    if f == (1, 0, 0, 0): return "index"
    if f == (1, 1, 0, 0): return "two"
    if f == (1, 1, 1, 0): return "three"
    if f == (0, 0, 0, 1): return "pinky"
    if f == (1, 1, 1, 1): return "palm"
    if f == (1, 0, 0, 0): return "swipeleft"
    if f == (1, 1, 0, 0): return "swiperight"
    return None


cap = cv2.VideoCapture(0)
armed = False
last_gesture = None
hold_start = time.time()
last_action = 0
done = False
message = ""
swipe_history = deque()

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame = cv2.flip(frame, 1)
    result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    now = time.time()

    gesture = None
    if result.multi_hand_landmarks:
        hand = result.multi_hand_landmarks[0]
        gesture = classify(hand.landmark)
        mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)

        # Track wrist for swipe detection (time-limited window)
        wrist = hand.landmark[0]
        swipe_history.append((now, wrist.x, wrist.y))
        while swipe_history and now - swipe_history[0][0] > SWIPE_WINDOW:
            swipe_history.popleft()
    else:
        swipe_history.clear()

    if gesture != last_gesture:
        last_gesture = gesture
        hold_start = now
        done = False
    held = now - hold_start

    # Swipe -> change slide (only when armed)
    if armed and now - last_action > SWIPE_COOLDOWN:
        swipe = detect_swipe(swipe_history)
        if swipe == "right":
            pyautogui.press("right")
            message = "Swipe: Next slide"
        elif swipe == "left":
            pyautogui.press("left")
            message = "Swipe: Previous slide"
        if swipe:
            last_action = now        # blocks pose actions right after a swipe
            done = True              # don't fire the currently held pose
            hold_start = now
            swipe_history.clear()

    if gesture and not done:
        if gesture == "fist" and held > LOCK_HOLD:
            armed = not armed
            done = True
            swipe_history.clear()
            message = "UNLOCKED" if armed else "LOCKED"
        elif armed and gesture in ACTIONS:
            key, label, need = ACTIONS[gesture]
            if held >= need and now - last_action > COOLDOWN:
                pyautogui.press(key)
                last_action = now
                done = True
                message = label

    status = "ARMED" if armed else "LOCKED - hold fist 1.5s"
    color = (0, 255, 0) if armed else (0, 0, 255)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, status, (10, 30), font, 0.8, color, 2)
    cv2.putText(frame, "Seeing: " + str(gesture), (10, 65),
                font, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, message, (10, 100), font, 0.8, (255, 255, 0), 2)
    cv2.imshow("Gesture Control", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
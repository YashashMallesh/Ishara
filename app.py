import cv2
import time
import math
import queue
import json
import os
import uuid
import threading
from collections import deque
from werkzeug.utils import secure_filename
from flask import Flask, render_template, Response, request, jsonify, send_from_directory
from flask_cors import CORS
import pyautogui
import mediapipe as mp
import pptx
import pypdf

# Configure PyAutoGUI safely
pyautogui.FAILSAFE = False

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

# ============================================================
# Global Configuration & State
# ============================================================
class ControllerConfig:
    def __init__(self):
        # Hand settings
        self.hand_cooldown = 1.2         # Cooldown after static gesture (prevents spamming)
        self.lock_hold = 1.5
        self.swipe_threshold = 0.24      # Minimum horizontal travel (requires deliberate swipe)
        self.swipe_window = 0.6          # Window of motion history
        self.swipe_min_samples = 5       # Minimum frames required
        self.swipe_cooldown = 1.3        # Minimum seconds between swipes (stops rapid 1->2->3 skipping)
        self.swipe_max_drift = 0.5       # Keeps swipe strictly horizontal
        
        # Eye settings
        self.eye_hold_seconds = 1.0
        self.eye_center_min = 0.40
        self.eye_center_max = 0.60
        self.eye_left_threshold = 0.30
        self.eye_right_threshold = 0.70
        self.eye_smoothing_frames = 6
        
        # Camera
        self.camera_index = 0

config = ControllerConfig()

# Hand actions mapping: gesture -> (key, description, required hold time)
HAND_ACTIONS = {
    "index": ("right", "Next slide", 0.7),     # Hold index for 0.7s (prevents accidental trigger during swipe)
    "two": ("left", "Previous slide", 0.7),    # Hold two fingers for 0.7s
    "three": ("b", "Black screen on/off", 0.8),
    "pinky": ("esc", "End slideshow", 1.0),
    "thumb": ("home", "First slide", 0.8),
    "palm": ("volumemute", "Mute / unmute", 1.2),
}

# Initial Default Minimalist Deck
DEFAULT_SLIDES = [
    {
        "id": 1,
        "type": "custom",
        "tag": "Swipe AI",
        "title": "Minimalist Vision Controller",
        "subtitle": "Touchless, gesture-controlled presentations powered by MediaPipe AI.",
        "content": [
            "Wave your hand or glance left/right to navigate.",
            "Insert your own PowerPoint (.pptx), PDF, or custom slides anytime.",
            "Supports real OS keystrokes for PowerPoint, Keynote & Google Slides."
        ],
        "theme": "dark"
    },
    {
        "id": 2,
        "type": "custom",
        "tag": "Controls",
        "title": "Natural Hand Gestures",
        "subtitle": "Hold steady in front of your camera to trigger navigation actions.",
        "content": [
            "👉 Index Finger (0.4s) — Next Slide",
            "✌️ Two Fingers (0.4s) — Previous Slide",
            "💨 Horizontal Swipe — Quick Slide Advance",
            "✊ Closed Fist (1.5s) — Lock / Unlock Controller",
            "🤟 Three Fingers (0.6s) — Blackout Screen ('B')"
        ],
        "theme": "slate"
    },
    {
        "id": 3,
        "type": "custom",
        "tag": "Eye Tracking",
        "title": "Subtle Eye Gaze Navigation",
        "subtitle": "Switch to Eye Gaze mode in the top navigation bar.",
        "content": [
            "👉 Glance Right (0.8s) — Advance to next slide",
            "👈 Glance Left (0.8s) — Return to previous slide",
            "👀 Center Gaze — Automatically rearms the trigger for safety"
        ],
        "theme": "indigo"
    },
    {
        "id": 4,
        "type": "custom",
        "tag": "Custom Slides",
        "title": "Insert Your Own Presentation",
        "subtitle": "Drag and drop any file using the '+ Insert Slides' button above.",
        "content": [
            "Upload Microsoft PowerPoint (.pptx) — parsed automatically into clean slides",
            "Upload Adobe PDF (.pdf) — rendered in high-definition canvas",
            "Upload Slide Images (.png, .jpg, .webp) — full-bleed photo slides",
            "Create Custom Markdown & Typography slides directly in the browser"
        ],
        "theme": "emerald"
    }
]

class SystemState:
    def __init__(self):
        self.lock = threading.Lock()
        self.mode = "hand"          # "hand" or "eye"
        self.camera_active = True
        self.armed = True
        self.enable_pyautogui = True
        
        # Detection telemetry
        self.current_gesture = "None"
        self.held_time = 0.0
        self.needed_time = 0.0
        self.progress = 0.0
        self.message = "Ready"
        self.fps = 0.0
        
        # Eye telemetry
        self.eye_ratio = 0.50
        self.eye_direction = "CENTER"
        self.eye_armed = True
        
        # Slides Deck
        self.slides = list(DEFAULT_SLIDES)
        self.deck_title = "Minimalist Vision Controller"
        
        # Action history & SSE event subscribers
        self.action_history = []
        self.subscribers = []
        self.stats = {
            "total_actions": 0,
            "next_slide": 0,
            "prev_slide": 0,
            "swipes": 0
        }

    def broadcast_event(self, event_type, data):
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        with self.lock:
            dead_subs = []
            for q in self.subscribers:
                try:
                    q.put_nowait(payload)
                except Exception:
                    dead_subs.append(q)
            for q in dead_subs:
                self.subscribers.remove(q)

    def log_action(self, action_name, key, trigger_type):
        timestamp_str = time.strftime("%H:%M:%S")
        entry = {
            "id": len(self.action_history) + 1,
            "action": action_name,
            "key": key,
            "type": trigger_type,
            "time": timestamp_str
        }
        with self.lock:
            self.action_history.insert(0, entry)
            if len(self.action_history) > 30:
                self.action_history.pop()
            
            self.stats["total_actions"] += 1
            if "Next" in action_name:
                self.stats["next_slide"] += 1
            elif "Prev" in action_name:
                self.stats["prev_slide"] += 1
            elif "Swipe" in trigger_type:
                self.stats["swipes"] += 1

        self.broadcast_event("action", entry)

state = SystemState()

# ============================================================
# Computer Vision Engine
# ============================================================
class VisionEngine:
    def __init__(self):
        self.cap = None
        self.running = False
        self.thread = None
        self.current_frame = None
        self.frame_lock = threading.Lock()
        
        # MediaPipe Solutions
        self.mp_hands = mp.solutions.hands
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_draw = mp.solutions.drawing_utils
        
        # State trackers for Hand Gesture
        self.last_gesture = None
        self.hold_start = time.time()
        self.last_action_time = 0
        self.action_done = False
        self.swipe_history = deque()
        
        # State trackers for Eye Gaze
        self.gaze_history = deque(maxlen=config.eye_smoothing_frames)
        self.gaze_started = None
        self.current_eye_direction = "CENTER"
        
        # Face Mesh iris landmark groups
        self.LEFT_IRIS = [468, 469, 470, 471, 472]
        self.RIGHT_IRIS = [473, 474, 475, 476, 477]
        self.LEFT_EYE_CORNERS = [33, 133]
        self.RIGHT_EYE_CORNERS = [362, 263]

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def execute_key(self, key, label, trigger_type):
        if state.enable_pyautogui:
            try:
                pyautogui.press(key)
            except Exception as e:
                print(f"[PyAutoGUI Error]: {e}")
        state.log_action(label, key, trigger_type)

    @staticmethod
    def fingers_up(lm):
        return tuple(1 if lm[t].y < lm[t - 2].y else 0 for t in (8, 12, 16, 20))

    @staticmethod
    def thumb_up(lm):
        top = min(lm[6].y, lm[10].y, lm[14].y, lm[18].y)
        return lm[4].y < top - 0.05

    def detect_swipe(self, history):
        if len(history) < config.swipe_min_samples:
            return None
        dx = history[-1][1] - history[0][1]
        dy = history[-1][2] - history[0][2]
        if abs(dx) < config.swipe_threshold:
            return None
        if abs(dy) > abs(dx) * config.swipe_max_drift:
            return None
        return "right" if dx > 0 else "left"

    def classify_hand(self, lm):
        f = self.fingers_up(lm)
        if f == (0, 0, 0, 0):
            return "thumb" if self.thumb_up(lm) else "fist"
        if f == (1, 0, 0, 0): return "index"
        if f == (1, 1, 0, 0): return "two"
        if f == (1, 1, 1, 0): return "three"
        if f == (0, 0, 0, 1): return "pinky"
        if f == (1, 1, 1, 1): return "palm"
        return None

    @staticmethod
    def average_x(landmarks, indices):
        return sum(landmarks[i].x for i in indices) / len(indices)

    def eye_ratio(self, landmarks, iris_indices, corner_indices):
        iris_x = self.average_x(landmarks, iris_indices)
        corner_a = landmarks[corner_indices[0]].x
        corner_b = landmarks[corner_indices[1]].x
        eye_left = min(corner_a, corner_b)
        eye_right = max(corner_a, corner_b)
        eye_width = eye_right - eye_left
        if eye_width < 0.001:
            return None
        return (iris_x - eye_left) / eye_width

    def classify_gaze(self, ratio):
        if ratio < config.eye_left_threshold:
            return "LEFT"
        elif ratio > config.eye_right_threshold:
            return "RIGHT"
        elif config.eye_center_min <= ratio <= config.eye_center_max:
            return "CENTER"
        else:
            return "HOLD"

    def _process_loop(self):
        self.cap = cv2.VideoCapture(config.camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        hands_detector = self.mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )

        face_mesh_detector = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )

        fps_timer = time.time()
        fps_counter = 0

        while self.running:
            if not state.camera_active:
                time.sleep(0.1)
                continue

            if not self.cap or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(config.camera_index)
                if not self.cap.isOpened():
                    time.sleep(0.5)
                    continue

            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            now = time.time()

            fps_counter += 1
            if now - fps_timer >= 1.0:
                with state.lock:
                    state.fps = round(fps_counter / (now - fps_timer), 1)
                fps_counter = 0
                fps_timer = now

            mode = state.mode

            if mode == "hand":
                results = hands_detector.process(rgb_frame)
                gesture = None

                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]
                    gesture = self.classify_hand(hand_landmarks.landmark)
                    
                    # Minimalist, clean landmarks drawing
                    self.mp_draw.draw_landmarks(
                        frame,
                        hand_landmarks,
                        self.mp_hands.HAND_CONNECTIONS,
                        self.mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=2),
                        self.mp_draw.DrawingSpec(color=(160, 160, 160), thickness=1, circle_radius=1)
                    )

                    wrist = hand_landmarks.landmark[0]
                    self.swipe_history.append((now, wrist.x, wrist.y))
                    while self.swipe_history and now - self.swipe_history[0][0] > config.swipe_window:
                        self.swipe_history.popleft()

                    # Sleek motion trail
                    if len(self.swipe_history) > 1:
                        pts = []
                        for _, px, py in self.swipe_history:
                            pts.append((int(px * w), int(py * h)))
                        for i in range(1, len(pts)):
                            cv2.line(frame, pts[i-1], pts[i], (255, 255, 255), 2)
                else:
                    self.swipe_history.clear()

                if gesture != self.last_gesture:
                    self.last_gesture = gesture
                    self.hold_start = now
                    self.action_done = False

                held = now - self.hold_start

                # Swipe action
                if state.armed and (now - self.last_action_time > config.swipe_cooldown):
                    swipe = self.detect_swipe(self.swipe_history)
                    if swipe == "right":
                        self.execute_key("right", "Next slide", "Swipe Right")
                        state.message = "Next Slide"
                        self.last_action_time = now
                        self.action_done = True
                        self.hold_start = now
                        self.swipe_history.clear()
                    elif swipe == "left":
                        self.execute_key("left", "Previous slide", "Swipe Left")
                        state.message = "Prev Slide"
                        self.last_action_time = now
                        self.action_done = True
                        self.hold_start = now
                        self.swipe_history.clear()

                # Hold action
                hold_progress = 0.0
                needed_time = 0.0

                if gesture and not self.action_done:
                    if gesture == "fist":
                        needed_time = config.lock_hold
                        hold_progress = min(1.0, held / needed_time)
                        if held >= needed_time:
                            state.armed = not state.armed
                            self.action_done = True
                            self.swipe_history.clear()
                            state.message = "Armed" if state.armed else "Locked"
                            state.broadcast_event("status_change", {"armed": state.armed, "message": state.message})
                    elif state.armed and gesture in HAND_ACTIONS:
                        key, label, need = HAND_ACTIONS[gesture]
                        needed_time = need
                        hold_progress = min(1.0, held / needed_time)
                        if held >= need and (now - self.last_action_time > config.hand_cooldown):
                            self.execute_key(key, label, f"Gesture: {gesture.capitalize()}")
                            self.last_action_time = now
                            self.action_done = True
                            state.message = label

                with state.lock:
                    state.current_gesture = gesture if gesture else "None"
                    state.held_time = round(held, 2) if gesture else 0.0
                    state.needed_time = needed_time
                    state.progress = round(hold_progress, 2)

                # Minimalist HUD Overlay on video
                # Top-left clean badge
                badge_color = (120, 220, 140) if state.armed else (100, 100, 240)
                cv2.circle(frame, (20, 24), 5, badge_color, -1)
                status_txt = f"{'ARMED' if state.armed else 'LOCKED'} • {gesture or 'Scanning'}"
                cv2.putText(frame, status_txt, (34, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1, cv2.LINE_AA)

                # Bottom minimalist progress line
                if hold_progress > 0:
                    prog_w = int(w * hold_progress)
                    cv2.rectangle(frame, (0, h - 4), (prog_w, h), (255, 255, 255), -1)

            else:
                # Eye Gaze Mode
                results = face_mesh_detector.process(rgb_frame)
                ratio = None
                direction = "CENTER"

                if results.multi_face_landmarks:
                    landmarks = results.multi_face_landmarks[0].landmark

                    left_ratio = self.eye_ratio(landmarks, self.LEFT_IRIS, self.LEFT_EYE_CORNERS)
                    right_ratio = self.eye_ratio(landmarks, self.RIGHT_IRIS, self.RIGHT_EYE_CORNERS)

                    # Draw subtle iris points
                    for idx in self.LEFT_IRIS + self.RIGHT_IRIS:
                        pt = landmarks[idx]
                        cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 2, (255, 255, 255), -1)

                    if left_ratio is not None and right_ratio is not None:
                        ratio = (left_ratio + right_ratio) / 2
                        self.gaze_history.append(ratio)
                        smooth_ratio = sum(self.gaze_history) / len(self.gaze_history)
                        direction = self.classify_gaze(smooth_ratio)

                        now_mono = time.monotonic()

                        if direction == "CENTER":
                            state.eye_armed = True
                            self.gaze_started = None
                            self.current_eye_direction = "CENTER"
                        elif direction in ("LEFT", "RIGHT"):
                            if direction != self.current_eye_direction:
                                self.current_eye_direction = direction
                                self.gaze_started = now_mono
                            elif self.gaze_started is None:
                                self.gaze_started = now_mono
                            elif state.eye_armed and (now_mono - self.gaze_started >= config.eye_hold_seconds):
                                if direction == "RIGHT":
                                    self.execute_key("right", "Next slide", "Gaze Right")
                                    state.message = "Next Slide"
                                elif direction == "LEFT":
                                    self.execute_key("left", "Previous slide", "Gaze Left")
                                    state.message = "Prev Slide"
                                state.eye_armed = False
                                self.gaze_started = None
                        else:
                            self.gaze_started = None
                            self.current_eye_direction = "HOLD"

                        held_gaze = (now_mono - self.gaze_started) if self.gaze_started else 0.0
                        gaze_progress = min(1.0, held_gaze / config.eye_hold_seconds) if self.gaze_started else 0.0

                        with state.lock:
                            state.eye_ratio = round(smooth_ratio, 2)
                            state.eye_direction = direction
                            state.current_gesture = f"Gaze {direction}"
                            state.held_time = round(held_gaze, 2)
                            state.needed_time = config.eye_hold_seconds
                            state.progress = round(gaze_progress, 2)

                # Minimalist Eye HUD
                cv2.circle(frame, (20, 24), 5, (255, 255, 255), -1)
                cv2.putText(frame, f"GAZE • {direction}", (34, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1, cv2.LINE_AA)

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                with self.frame_lock:
                    self.current_frame = buffer.tobytes()

        hands_detector.close()
        face_mesh_detector.close()
        if self.cap:
            self.cap.release()
            self.cap = None

engine = VisionEngine()
engine.start()

# ============================================================
# Slide Parsing Helpers (PPTX, PDF, Images)
# ============================================================
def extract_pptx_slides(filepath, original_filename):
    prs = pptx.Presentation(filepath)
    slides = []
    
    for idx, slide in enumerate(prs.slides):
        title = f"Slide {idx + 1}"
        subtitle = ""
        content_items = []
        
        # Check shapes
        for shape in slide.shapes:
            if shape.has_text_frame:
                paragraphs = [p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip()]
                if not paragraphs:
                    continue
                if shape == slide.shapes.title or (not content_items and not title.startswith("Slide")):
                    title = paragraphs[0]
                    if len(paragraphs) > 1:
                        content_items.extend(paragraphs[1:])
                else:
                    content_items.extend(paragraphs)

        # Assign subtle theme
        themes = ["dark", "slate", "indigo", "emerald"]
        theme = themes[idx % len(themes)]

        slides.append({
            "id": idx + 1,
            "type": "custom",
            "tag": f"{original_filename} • {idx + 1}",
            "title": title,
            "subtitle": subtitle,
            "content": content_items[:6],
            "theme": theme
        })
    return slides

# ============================================================
# Flask Endpoints
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

def generate_frames():
    while True:
        with engine.frame_lock:
            frame = engine.current_frame
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            time.sleep(0.04)
        time.sleep(0.03)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status')
def get_status():
    with state.lock:
        return jsonify({
            "mode": state.mode,
            "camera_active": state.camera_active,
            "armed": state.armed,
            "enable_pyautogui": state.enable_pyautogui,
            "gesture": state.current_gesture,
            "held_time": state.held_time,
            "needed_time": state.needed_time,
            "progress": state.progress,
            "message": state.message,
            "fps": state.fps,
            "eye_ratio": state.eye_ratio,
            "eye_direction": state.eye_direction,
            "eye_armed": state.eye_armed,
            "deck_title": state.deck_title,
            "slide_count": len(state.slides),
            "stats": state.stats,
            "history": state.action_history[:10]
        })

@app.route('/api/slides', methods=['GET', 'POST', 'DELETE'])
def handle_slides():
    if request.method == 'GET':
        with state.lock:
            return jsonify({
                "title": state.deck_title,
                "slides": state.slides
            })

    elif request.method == 'POST':
        data = request.get_json() or {}
        new_slides = data.get('slides')
        deck_title = data.get('title')
        with state.lock:
            if new_slides is not None:
                state.slides = new_slides
            if deck_title:
                state.deck_title = deck_title
        state.broadcast_event("deck_update", {"slides": state.slides, "title": state.deck_title})
        return jsonify({"success": True, "count": len(state.slides)})

    elif request.method == 'DELETE':
        with state.lock:
            state.slides = list(DEFAULT_SLIDES)
            state.deck_title = "Minimalist Vision Controller"
        state.broadcast_event("deck_update", {"slides": state.slides, "title": state.deck_title})
        return jsonify({"success": True, "slides": state.slides})

@app.route('/api/upload', methods=['POST'])
def upload_presentation():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(save_path)

    ext = os.path.splitext(filename)[1].lower()

    new_slides = []

    # 1. PPTX Parsing
    if ext in ('.pptx', '.ppt'):
        try:
            new_slides = extract_pptx_slides(save_path, filename)
            if not new_slides:
                raise ValueError("No slides could be extracted.")
            with state.lock:
                state.slides = new_slides
                state.deck_title = filename
            state.broadcast_event("deck_update", {"slides": new_slides, "title": filename})
            return jsonify({
                "success": True,
                "type": "pptx",
                "count": len(new_slides),
                "slides": new_slides,
                "title": filename
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Error parsing PowerPoint: {str(e)}"}), 500

    # 2. PDF Presentation
    elif ext == '.pdf':
        try:
            reader = pypdf.PdfReader(save_path)
            total_pages = len(reader.pages)
            pdf_url = f"/static/uploads/{unique_name}"
            # Create slide entries pointing to PDF pages
            new_slides = [{
                "id": i + 1,
                "type": "pdf",
                "page": i + 1,
                "total_pages": total_pages,
                "pdf_url": pdf_url,
                "title": f"Page {i + 1}",
                "tag": filename
            } for i in range(total_pages)]

            with state.lock:
                state.slides = new_slides
                state.deck_title = filename
            state.broadcast_event("deck_update", {"slides": new_slides, "title": filename})
            return jsonify({
                "success": True,
                "type": "pdf",
                "pdf_url": pdf_url,
                "count": total_pages,
                "slides": new_slides,
                "title": filename
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Error reading PDF: {str(e)}"}), 500

    # 3. Slide Images (.png, .jpg, etc.)
    elif ext in ('.png', '.jpg', '.jpeg', '.webp', '.svg'):
        img_url = f"/static/uploads/{unique_name}"
        with state.lock:
            new_slide = {
                "id": len(state.slides) + 1,
                "type": "image",
                "src": img_url,
                "tag": "Image Slide",
                "title": filename,
                "content": []
            }
            state.slides.append(new_slide)
        state.broadcast_event("deck_update", {"slides": state.slides, "title": state.deck_title})
        return jsonify({
            "success": True,
            "type": "image",
            "slide": new_slide,
            "count": len(state.slides)
        })

    else:
        return jsonify({"success": False, "error": f"Unsupported format '{ext}'. Upload .pptx, .pdf, or image."}), 400

@app.route('/api/events')
def events():
    def event_stream():
        q = queue.Queue(maxsize=20)
        with state.lock:
            state.subscribers.append(q)
        try:
            initial_data = json.dumps({"mode": state.mode, "armed": state.armed, "msg": "connected"})
            yield f"event: connect\ndata: {initial_data}\n\n"
            while True:
                msg = q.get()
                yield msg
        except GeneratorExit:
            with state.lock:
                if q in state.subscribers:
                    state.subscribers.remove(q)

    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })

@app.route('/api/toggle_mode', methods=['POST'])
def toggle_mode():
    data = request.get_json() or {}
    new_mode = data.get('mode')
    with state.lock:
        if new_mode in ("hand", "eye"):
            state.mode = new_mode
        else:
            state.mode = "eye" if state.mode == "hand" else "hand"
        mode_val = state.mode
    state.broadcast_event("mode_change", {"mode": mode_val})
    return jsonify({"success": True, "mode": mode_val})

@app.route('/api/toggle_armed', methods=['POST'])
def toggle_armed():
    with state.lock:
        state.armed = not state.armed
        armed_val = state.armed
    state.broadcast_event("status_change", {"armed": armed_val})
    return jsonify({"success": True, "armed": armed_val})

@app.route('/api/toggle_pyautogui', methods=['POST'])
def toggle_pyautogui():
    with state.lock:
        state.enable_pyautogui = not state.enable_pyautogui
        val = state.enable_pyautogui
    return jsonify({"success": True, "enable_pyautogui": val})

@app.route('/api/toggle_camera', methods=['POST'])
def toggle_camera():
    with state.lock:
        state.camera_active = not state.camera_active
        val = state.camera_active
    return jsonify({"success": True, "camera_active": val})

@app.route('/api/trigger', methods=['POST'])
def trigger_action():
    data = request.get_json() or {}
    key = data.get("key", "right")
    label = data.get("label", "Manual action")
    engine.execute_key(key, label, "Web Click")
    return jsonify({"success": True, "action": label})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        data = request.get_json() or {}
        if "hand_cooldown" in data: config.hand_cooldown = float(data["hand_cooldown"])
        if "lock_hold" in data: config.lock_hold = float(data["lock_hold"])
        if "swipe_threshold" in data: config.swipe_threshold = float(data["swipe_threshold"])
        if "swipe_cooldown" in data: config.swipe_cooldown = float(data["swipe_cooldown"])
        if "eye_hold_seconds" in data: config.eye_hold_seconds = float(data["eye_hold_seconds"])
        return jsonify({"success": True, "message": "Settings updated"})
    
    return jsonify({
        "hand_cooldown": config.hand_cooldown,
        "lock_hold": config.lock_hold,
        "swipe_threshold": config.swipe_threshold,
        "swipe_cooldown": config.swipe_cooldown,
        "eye_hold_seconds": config.eye_hold_seconds
    })

if __name__ == '__main__':
    print("==================================================")
    print("   VisionSwipe AI Minimalist WebApp Starting...   ")
    print("   Access URL: http://localhost:5000              ")
    print("==================================================")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

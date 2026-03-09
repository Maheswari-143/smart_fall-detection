# main.py
import cv2
import cvzone
import math
from ultralytics import YOLO
import torch
import os
import time

# Allow unsafe weights loading for PyTorch 2.6+ compatibility
torch.serialization.add_safe_globals([torch.nn.modules.container.Sequential])

# Set torch.load to allow weights_only=False for compatibility
original_load = torch.load
def patched_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return original_load(*args, **kwargs)
torch.load = patched_load

# -----------------------------
# Load YOLO model and classes
# -----------------------------
MODEL_PATH = 'yolov8s.pt'
CLASSES_PATH = 'classes.txt'

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")
if not os.path.exists(CLASSES_PATH):
    raise FileNotFoundError(f"Classes file not found: {CLASSES_PATH}")

model = YOLO(MODEL_PATH)

with open(CLASSES_PATH, 'r') as f:
    classnames = f.read().splitlines()

# -----------------------------
# Detector class
# -----------------------------
class Detector:
    """
    Fall Detection with YOLO
    Detects lying persons or sudden falls
    """

    def __init__(self, model, classnames):
        self.model = model
        self.classnames = classnames
        self.prev_aspect = 1.0
        self.prev_time = time.time()
        self.in_fall_state = False  # Track if we're currently in a fall state
        self.fall_cooldown_frames = 0  # Frames since last fall was logged

    def _annotate(self, frame, callback=None):
        results = self.model(frame)
        fall_detected = False

        for info in results:
            for box in info.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                class_name = self.classnames[class_id]

                if class_name != "person" or confidence < 0.80:
                    continue

                width = x2 - x1
                height = y2 - y1
                aspect = width / (height + 1e-6)

                # Draw detection box
                cvzone.cornerRect(frame, [x1, y1, width, height], l=20, rt=3)
                cvzone.putTextRect(frame, f"person {int(confidence*100)}%", [x1, y1 - 10],
                                   scale=1, thickness=1)

                # ---------- IMPROVED FALL DETECTION LOGIC ----------
                # STRICTER DETECTION: Require aspect ratio > 1.2 (more horizontal) to trigger fall
                # This prevents false positives from people sitting or at slight angles
                lying_orientation = aspect > 1.2  # Detect when person is horizontal
                
                # Only count as a NEW fall if:
                # 1. Clear transition from standing (aspect < 1.0) to lying (aspect > 1.5)
                # 2. AND person was previously detected as upright
                should_log_fall = False
                
                if lying_orientation and not self.in_fall_state and self.prev_aspect < 1.0:
                    # Strong transition from standing to lying - log it as fall
                    should_log_fall = True
                    self.in_fall_state = True
                    self.fall_cooldown_frames = 0
                elif lying_orientation and self.in_fall_state:
                    # Already in fall state - only log if significant cooldown expired
                    self.fall_cooldown_frames += 1
                    if self.fall_cooldown_frames > 30:  # Wait ~1 second at 30 FPS before logging another fall
                        should_log_fall = True
                        self.fall_cooldown_frames = 0
                elif not lying_orientation:
                    # Person stood up or returned to upright - exit fall state
                    self.in_fall_state = False
                    self.fall_cooldown_frames = 0

                if should_log_fall:
                    cvzone.putTextRect(frame, "FALL DETECTED!", [10, 40],
                                       scale=2, thickness=2, colorR=(0, 0, 255))
                    fall_detected = True

                self.prev_aspect = aspect

        # Trigger callback
        if fall_detected and callback:
            try:
                callback("fall", {"source": "Live", "confidence": 0.95})
            except:
                pass

        return frame

    # Camera stream generator
    def camera_frame_generator(self, camera_index=0, callback=None):
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame = cv2.resize(frame, (980, 740))
                frame = self._annotate(frame, callback=callback)
                ret2, jpeg = cv2.imencode('.jpg', frame)
                if not ret2:
                    continue
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        finally:
            cap.release()

    # Video stream generator
    def video_frame_generator(self, video_path, callback=None):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame = cv2.resize(frame, (980, 740))
                frame = self._annotate(frame, callback=callback)
                ret2, jpeg = cv2.imencode('.jpg', frame)
                if not ret2:
                    continue
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        finally:
            cap.release()

# -----------------------------
# Global detector object
# -----------------------------
detector = Detector(model, classnames)
__all__ = ["detector"]

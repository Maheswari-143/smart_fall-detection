# app.py
from flask import Flask, render_template, Response, request, redirect, url_for, jsonify, send_from_directory, session, flash
import os
from werkzeug.utils import secure_filename
from threading import Lock, Thread
from collections import Counter
from datetime import datetime, timedelta
from pymongo import MongoClient
import cv2
import time
import subprocess
import base64
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
try:
    import imageio
    IMAGEIO_AVAILABLE = True
except ImportError:
    IMAGEIO_AVAILABLE = False

# Global state for progress tracking
processing_state = {
    'active': False,
    'current_frame': 0,
    'total_frames': 0,
    'current_image_base64': None,
    'falls_detected': 0,
    'message': ''
}
processing_lock = Lock()
# Snapshot of the most recent processing result
processing_result = {}
# Cached analytics summary for the last processed video (simple, not per-user)
analytics_cache = {
    'total_videos': 0
}


# YOLO detector from main.py
from main import detector

# -----------------------------
# Windows Beep Support
# -----------------------------
try:
    import winsound
    def play_beep():
        try:
            winsound.Beep(1000, 500)
        except:
            pass
except:
    def play_beep():
        pass  # For Linux/Mac, no beep

# -----------------------------
# Flask + Upload Folder
# -----------------------------
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXT = {'mp4', 'avi', 'mov', 'mkv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = "your_secret_key"
app.permanent_session_lifetime = timedelta(hours=1)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# -----------------------------
# MongoDB Setup (Contacts + Users)
# -----------------------------
client = MongoClient("mongodb://localhost:27017/")
db = client.fall
contacts_collection = db.contacts
users_collection = db.users  # New collection for signup/login
fall_events_collection = db.fall_events  # New collection for fall events per user

# -----------------------------
# Gmail Setup for Email Alerts
# -----------------------------
GMAIL_SENDER = os.getenv('GMAIL_SENDER', 'your_email@gmail.com')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')  # Set via environment variable

def send_fall_alert_email(recipient_name, recipient_email, user_email=None):
    """Send fall detection alert via Gmail SMTP"""
    try:
        if not GMAIL_APP_PASSWORD:
            print("❌ Gmail App Password not configured. Please set GMAIL_APP_PASSWORD environment variable.")
            return False
        
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = GMAIL_SENDER
        msg['To'] = recipient_email
        msg['Subject'] = '🚨 FALL ALERT - SmartFall Detection System'
        
        # Email body
        body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .header {{ color: #d32f2f; font-size: 24px; font-weight: bold; margin-bottom: 20px; }}
        .alert-box {{ background-color: #ffebee; border-left: 4px solid #d32f2f; padding: 15px; margin-bottom: 20px; }}
        .info {{ color: #666; margin: 10px 0; }}
        .timestamp {{ color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">⚠️ FALL DETECTED!</div>
        <div class="alert-box">
            <p><strong>A fall has been detected by the SmartFall Detection System</strong></p>
            <p class="info"><strong>Contact Person:</strong> {recipient_name}</p>
            <p class="info"><strong>Time:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p class="info"><strong>Monitored By:</strong> {user_email or 'System'}</p>
        </div>
        <p style="color: #333;">Please check on the person immediately.</p>
        <p style="color: #999; font-size: 12px; margin-top: 30px;">This is an automated alert from SmartFall Detection System.</p>
    </div>
</body>
</html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Send email via Gmail SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email sent to {recipient_name} ({recipient_email})")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print(f"❌ Gmail authentication failed. Check GMAIL_SENDER and GMAIL_APP_PASSWORD.")
        return False
    except Exception as e:
        print(f"❌ Failed to send email to {recipient_name}: {e}")
        return False



# -----------------------------
# Fall Events Memory Store
# (Temporary for real-time display, persistent in MongoDB)
# -----------------------------
fall_events = []  # Current fall event for display (cleared quickly)
fall_events_persistent = []  # All fall events for analytics (persistent)
events_lock = Lock()

# -----------------------------
# Fall Callback
# -----------------------------
def fall_callback(event_type, info, user_email=None):
    """
    Callback for fall detection events
    Stores fall events in MongoDB with user email for persistence
    Sends email alerts to all contacts
    
    Args:
        event_type: Type of event (e.g., 'fall')
        info: Event information dict
        user_email: Email of user who is monitoring (optional)
    """
    if event_type == 'fall':
        event = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'source': info.get('source', 'Live'),
            'confidence': info.get('confidence', 0),
            'user_email': user_email  # Store which user detected the fall
        }
        with events_lock:
            fall_events.append(event)  # For immediate display
            fall_events_persistent.append(event)  # For analytics
        
        # Store in MongoDB for persistent user-specific storage
        if user_email:
            try:
                fall_events_collection.insert_one(event)
                print(f"📊 Fall event stored for user: {user_email}")
            except Exception as e:
                print(f"⚠️ Failed to store fall event in MongoDB: {e}")
        
        play_beep()
        print(f"⚠️ FALL DETECTED - Event stored in database for user: {user_email}")
        
        # Send email alerts to all contacts
        if user_email:
            contacts = list(contacts_collection.find({'user_email': user_email}, {"_id": 0}))
        else:
            contacts = list(contacts_collection.find({}, {"_id": 0}))
        
        # Send email to each contact
        for contact in contacts:
            send_fall_alert_email(contact['name'], contact['email'], user_email=user_email)

# -----------------------------
# ROUTES
# -----------------------------

# --- Home Redirect ---
@app.route('/')
def index():
    return redirect(url_for('home'))

# --- HOME ---
@app.route('/home')
def home():
    return render_template('home.html')

# --- ABOUT ---
@app.route('/about')
def about():
    return render_template('about.html')

# --- SIGNUP ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not fullname or not email or not password or not confirm_password:
            flash("Please fill all fields.", "error")
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for('signup'))

        if users_collection.find_one({"email": email}):
            flash("Email already registered.", "error")
            return redirect(url_for('signup'))

        users_collection.insert_one({
            "fullname": fullname,
            "email": email,
            "password": password
        })
        flash("Signup successful! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = users_collection.find_one({"email": email})
        if user and user['password'] == password:
            session.permanent = True
            session['user'] = user['email']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')

# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.pop('user', None)
    return render_template('logout_success.html')

@app.route('/logout_redirect')
def logout_redirect():
    return redirect(url_for('home'))

# --- PROTECTED ROUTES ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Function: Convert AVI to MP4 using FFmpeg or imageio ---
def convert_avi_to_mp4(avi_path, mp4_path):
    """Convert AVI video to MP4 using FFmpeg or imageio"""
    try:
        if not os.path.exists(avi_path):
            print(f"❌ AVI file not found: {avi_path}")
            return None
        
        print(f"🔄 Converting AVI to MP4...")
        print(f"   Input: {avi_path}")
        print(f"   Output: {mp4_path}")
        
        # Try FFmpeg first
        try:
            cmd = [
                'ffmpeg',
                '-i', avi_path,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-q:a', '5',
                '-y',
                mp4_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and os.path.exists(mp4_path):
                mp4_size = os.path.getsize(mp4_path) / (1024 * 1024)
                print(f"✅ Conversion successful (FFmpeg)!")
                print(f"   MP4 Size: {mp4_size:.2f} MB")
                return mp4_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"⚠️ FFmpeg not available, trying imageio...")
        
        # Fallback: Use imageio if FFmpeg fails
        if IMAGEIO_AVAILABLE:
            import imageio_ffmpeg
            
            # Read AVI and write as MP4
            reader = imageio.get_reader(avi_path, 'ffmpeg')
            writer = imageio.get_writer(mp4_path, 'ffmpeg', fps=30)
            
            frame_count = 0
            for frame in reader:
                writer.append_data(frame)
                frame_count += 1
                if frame_count % 50 == 0:
                    print(f"   Processed {frame_count} frames...")
            
            writer.close()
            reader.close()
            
            if os.path.exists(mp4_path):
                mp4_size = os.path.getsize(mp4_path) / (1024 * 1024)
                print(f"✅ Conversion successful (imageio)!")
                print(f"   MP4 Size: {mp4_size:.2f} MB")
                return mp4_path
        else:
            print(f"⚠️ Installing imageio-ffmpeg (one-time setup)...")
            try:
                subprocess.run(['pip', 'install', 'imageio-ffmpeg', '-q'], timeout=60)
                import imageio
                import imageio_ffmpeg
                
                reader = imageio.get_reader(avi_path, 'ffmpeg')
                writer = imageio.get_writer(mp4_path, 'ffmpeg', fps=30)
                
                frame_count = 0
                for frame in reader:
                    writer.append_data(frame)
                    frame_count += 1
                
                writer.close()
                reader.close()
                
                if os.path.exists(mp4_path):
                    mp4_size = os.path.getsize(mp4_path) / (1024 * 1024)
                    print(f"✅ Conversion successful (imageio-ffmpeg)!")
                    print(f"   MP4 Size: {mp4_size:.2f} MB")
                    return mp4_path
            except Exception as e2:
                print(f"❌ imageio-ffmpeg installation/conversion failed: {e2}")
        
        return None
        
    except Exception as e:
        print(f"❌ Conversion error: {e}")
        return None

# --- Progress Streaming Endpoint ---
@app.route('/processing-progress')
def processing_progress():
    """Server-Sent Events endpoint for real-time processing progress"""
    def generate():
        while True:
            with processing_lock:
                if processing_state['active']:
                    data = {
                        'active': True,
                        'current_frame': processing_state['current_frame'],
                        'total_frames': processing_state['total_frames'],
                        'falls_detected': processing_state['falls_detected'],
                        'message': processing_state['message'],
                        'image': processing_state['current_image_base64']
                    }
                    # Calculate progress percentage
                    progress = 0
                    if processing_state['total_frames'] > 0:
                        progress = int((processing_state['current_frame'] / processing_state['total_frames']) * 100)
                    data['progress'] = progress
                    
                    yield f"data: {json.dumps(data)}\n\n"
                else:
                    yield f"data: {json.dumps({'active': False})}\n\n"
            time.sleep(0.05)  # Faster updates for smoother video
    
    return Response(generate(), mimetype='text/event-stream')

# --- Processing Result Snapshot ---
@app.route('/processing-result')
def processing_result_snapshot():
    """Return the latest processing progress and final results (if ready)."""
    with processing_lock:
        data = {
            'active': processing_state['active'],
            'message': processing_state['message'],
            'falls_detected': processing_state['falls_detected'],
            'current_frame': processing_state['current_frame'],
            'total_frames': processing_state['total_frames'],
        }
        progress = 0
        if processing_state['total_frames'] > 0:
            progress = int((processing_state['current_frame'] / processing_state['total_frames']) * 100)
        data['progress'] = progress

        if not processing_state['active'] and processing_result:
            if processing_result.get('error'):
                data['status'] = 'error'
                data['error'] = processing_result.get('error')
            else:
                data['status'] = 'done'
                data['results'] = processing_result
        elif processing_state['active']:
            data['status'] = 'processing'
        else:
            # Idle but check if message carries error
            if processing_state['message'].lower().startswith('error'):
                data['status'] = 'error'
                data['error'] = processing_state['message']
            else:
                data['status'] = 'idle'

    return jsonify(data)
@app.route('/api/live-analytics')
@login_required
def api_live_analytics():
    """API endpoint for live detection analytics"""
    try:
        user_email = session.get('user')
        fall_events = list(fall_events_collection.find({'user_email': user_email, 'source': 'Live'}, {"_id": 0}).sort('timestamp', -1).limit(1000))
        weekly = [0] * 7
        monthly_live = [0] * 12
        monthly_upload = [0] * 12
        total_confidence = 0
        for event in fall_events:
            try:
                timestamp = datetime.strptime(event['timestamp'], "%Y-%m-%d %H:%M:%S")
                weekly[timestamp.weekday()] += 1
                monthly_live[timestamp.month - 1] += 1
                total_confidence += event.get('confidence', 0)
            except:
                pass
        avg_confidence = total_confidence / len(fall_events) if fall_events else 0
        upload_events = list(fall_events_collection.find({'user_email': user_email, 'source': 'Upload'}, {"_id": 0}).sort('timestamp', -1).limit(1000))
        for event in upload_events:
            try:
                timestamp = datetime.strptime(event['timestamp'], "%Y-%m-%d %H:%M:%S")
                monthly_upload[timestamp.month - 1] += 1
            except:
                pass
        return jsonify({'weekly': weekly, 'monthly_live': monthly_live, 'monthly_upload': monthly_upload, 'avg_confidence': avg_confidence, 'total_live_detections': len(fall_events), 'total_upload_detections': len(upload_events)})
    except Exception as e:
        print(f"❌ Live analytics error: {e}")
        return jsonify({'weekly': [0]*7, 'monthly_live': [0]*12, 'monthly_upload': [0]*12, 'avg_confidence': 0, 'total_live_detections': 0, 'total_upload_detections': 0})


# --- Video Upload ---
@app.route('/upload', methods=['GET', 'POST'])
def upload_page():
    if request.method == 'POST':
        user_email = session.get('user')
        quick_mode = request.form.get('quick', '0') == '1'
        
        if 'video' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        
        # Start video processing in background thread to avoid blocking
        thread = Thread(target=_process_video_background, args=(save_path, filename, user_email, quick_mode))
        thread.daemon = True
        thread.start()
        
        # Return immediately
        return jsonify({
            "status": "processing",
            "message": "Video uploaded! Processing started...",
            "filename": filename
        })

    return render_template('upload.html')


def _process_video_background(save_path, filename, user_email, quick_mode):
    """Process video in background thread"""
    global processing_state, processing_result, analytics_cache
    
    annotated_filename = f"annotated_{filename.rsplit('.', 1)[0]}.mp4"
    annotated_path = os.path.join(app.config['UPLOAD_FOLDER'], annotated_filename)
    
    total_falls = 0
    max_confidence = 0.0
    events_list = []
    person_count_data = []
    fall_risk_data = []
    activity_counts = {"Fall": [], "Near-Fall": [], "Walking": [], "Standing": [], "Sitting": []}
    time_labels = []
    
    try:
        cap = cv2.VideoCapture(save_path)
        if not cap.isOpened():
            with processing_lock:
                processing_state['active'] = False
                processing_state['message'] = 'Error: Could not open video'
                processing_result = {'error': 'Could not open video'}
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Mark as processing
        with processing_lock:
            processing_state['active'] = True
            processing_state['current_frame'] = 0
            processing_state['total_frames'] = total_frames
            processing_state['falls_detected'] = 0
            processing_state['message'] = f'Analyzing video ({total_frames} frames)...'
            processing_result = {}
            analytics_cache = {'total_videos': 0}
        
        print(f"📹 Processing: {filename} ({total_frames} frames @ {fps} FPS)")
        
        # Set up video writer if not in quick mode
        out = None
        use_original_video = False
        annotated_path_used = None
        
        if not quick_mode:
            fourcc_options = [
                ('mp4v', '.mp4'),
                ('H264', '.mp4'),
                ('MJPG', '.avi'),
                (-1, '.avi'),
            ]
            for codec_name, ext in fourcc_options:
                try:
                    test_path = annotated_path if ext == '.mp4' else annotated_path.replace('.mp4', ext)
                    fourcc = cv2.VideoWriter_fourcc(*codec_name) if codec_name != -1 else -1
                    out = cv2.VideoWriter(test_path, fourcc, fps, (width, height))
                    
                    if out and out.isOpened():
                        annotated_path_used = test_path
                        print(f"✅ Video writer ready: {codec_name if codec_name != -1 else 'DEFAULT'}")
                        break
                except:
                    out = None
            
            if out is None:
                use_original_video = True
                print("⚠️ Could not initialize video writer, will use original video")
        
        # Process frames
        frame_idx = 0
        fall_frames = set()
        in_fall_state = False
        fall_cooldown_frames = 0
        frame_base64 = None
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            
            timestamp = str(datetime.utcfromtimestamp(frame_idx / fps).strftime("%H:%M:%S"))
            results = detector.model(frame)
            
            person_detected = False
            fall_detected = False
            frame_person_count = 0
            detected_confidences = []
            
            for info in results:
                for box in info.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    confidence = float(box.conf[0])
                    class_id = int(box.cls[0])
                    class_name = detector.classnames[class_id]
                    
                    if class_name != "person" or confidence < 0.80:
                        continue
                    
                    frame_person_count += 1
                    person_detected = True
                    detected_confidences.append(confidence)
                    
                    # Calculate aspect ratio for fall detection
                    width_box = x2 - x1
                    height_box = y2 - y1
                    aspect = width_box / (height_box + 1e-6)
                    
                    # Fall detection logic
                    lying_orientation = aspect > 1.20
                    
                    if lying_orientation and not in_fall_state:
                        fall_detected = True
                        in_fall_state = True
                        fall_cooldown_frames = 0
                    elif lying_orientation and in_fall_state:
                        fall_cooldown_frames += 1
                        if fall_cooldown_frames > 25:
                            fall_detected = True
                            fall_cooldown_frames = 0
                    elif not lying_orientation:
                        in_fall_state = False
                        fall_cooldown_frames = 0
                    
                    if fall_detected:
                        fall_frames.add(frame_idx)
                        max_confidence = max(max_confidence, confidence)
                        total_falls += 1
                        events_list.append({
                            "time": timestamp,
                            "event": "Fall",
                            "confidence": round(confidence, 2)
                        })
                        event = {
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'source': 'Upload',
                            'confidence': confidence,
                            'user_email': user_email
                        }
                        try:
                            fall_events_collection.insert_one(event)
                        except:
                            pass
                        print(f"   🚨 FALL at {timestamp} (Confidence: {confidence:.2f})")
            
            # Annotate frame if not in quick mode
            if not quick_mode and out and out.isOpened():
                annotated_frame = frame.copy()
                for info in results:
                    for box in info.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        confidence = float(box.conf[0])
                        class_id = int(box.cls[0])
                        class_name = detector.classnames[class_id]
                        
                        if class_name != "person" or confidence < 0.80:
                            continue
                        
                        color = (0, 0, 255) if frame_idx in fall_frames else (0, 255, 0)
                        label = f"FALL! {confidence:.2f}" if frame_idx in fall_frames else f"person {confidence:.2f}"
                        
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3 if color == (0, 0, 255) else 2)
                        cv2.putText(annotated_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                cv2.putText(annotated_frame, f"Time: {timestamp}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(annotated_frame, f"People: {frame_person_count}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                out.write(annotated_frame)
                
                # Encode frame for streaming
                _, buffer = cv2.imencode('.jpg', cv2.resize(annotated_frame, (640, 480)))
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
            else:
                # Quick mode: encode original frame with detection boxes
                display_frame = frame.copy()
                for info in results:
                    for box in info.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        confidence = float(box.conf[0])
                        class_id = int(box.cls[0])
                        class_name = detector.classnames[class_id]
                        
                        if class_name != "person" or confidence < 0.80:
                            continue
                        
                        color = (0, 0, 255) if frame_idx in fall_frames else (0, 255, 0)
                        label = f"FALL! {confidence:.2f}" if frame_idx in fall_frames else f"person {confidence:.2f}"
                        
                        cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 3 if color == (0, 0, 255) else 2)
                        cv2.putText(display_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                cv2.putText(display_frame, f"Time: {timestamp}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(display_frame, f"People: {frame_person_count}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Always encode frame for streaming
                try:
                    _, buffer = cv2.imencode('.jpg', cv2.resize(display_frame, (640, 480)))
                    frame_base64 = base64.b64encode(buffer).decode('utf-8')
                except Exception as e:
                    print(f"Error encoding frame {frame_idx}: {e}")
                    frame_base64 = None
            
            # Update progress with frame image
            with processing_lock:
                processing_state['current_frame'] = frame_idx
                processing_state['falls_detected'] = total_falls
                processing_state['message'] = f"Frame {frame_idx}/{total_frames} - {timestamp}"
                if frame_base64:
                    processing_state['current_image_base64'] = frame_base64
            
            # Analytics for every frame
            time_labels.append(timestamp)
            person_count_data.append(frame_person_count)
            
            if person_detected:
                avg_conf = sum(detected_confidences) / len(detected_confidences)
                fall_risk = min(100, int(avg_conf * 50 + (20 if fall_detected else 10)))
            else:
                fall_risk = 0
            
            fall_risk_data.append(fall_risk)
            
            if fall_detected:
                activity_counts["Fall"].append(1)
                activity_counts["Walking"].append(0)
                activity_counts["Standing"].append(0)
            elif person_detected:
                activity_counts["Fall"].append(0)
                activity_counts["Walking"].append(1)
                activity_counts["Standing"].append(1)
            else:
                activity_counts["Fall"].append(0)
                activity_counts["Walking"].append(0)
                activity_counts["Standing"].append(0)
            
            activity_counts["Near-Fall"].append(0)
            activity_counts["Sitting"].append(0)
        
        cap.release()
        if out:
            out.release()
        
        # Mark complete
        with processing_lock:
            processing_state['active'] = False
            processing_state['message'] = f"✅ Analysis complete! {total_falls} falls detected"
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            processing_result = {
                "total_falls": total_falls,
                "video_duration": f"{minutes:02d}:{seconds:02d}",
                "events": events_list,
                "filename": filename,
                "annotated_video": annotated_path_used if annotated_path_used else (save_path if use_original_video else None)
            }

            # Update analytics cache (simple single-video cache)
            avg_conf = 0.0
            if events_list:
                avg_conf = sum(e.get('confidence', 0) for e in events_list) / len(events_list)

            analytics_cache = {
                'total_videos': 1,
                'fall_count': total_falls,
                'near_fall_count': 0,
                'safe_count': max(len(time_labels) - total_falls, 0),
                'avg_confidence': avg_conf,
                'time_labels': time_labels,
                'person_count': person_count_data,
                'fall_risk': fall_risk_data,
                'activity_counts': activity_counts,
                'events': events_list,
            }
        
        print(f"✅ Done: {total_falls} falls, {duration:.1f}s video")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        with processing_lock:
            processing_state['active'] = False
            processing_state['message'] = f'Error: {str(e)}'
            processing_result = {'error': str(e)}




@app.route('/play/<filename>')
@login_required
def play_video(filename):
    return render_template('play_video.html', filename=filename)

@app.route('/stream_video/<path:filename>')
@login_required
def stream_video(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(path):
        return 'Not found', 404

    user_email = session.get('user')
    return Response(
        detector.video_frame_generator(path, callback=lambda event_type, info: fall_callback(event_type, info, user_email=user_email)),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# --- Live Stream ---
@app.route('/live')
def live():
    if 'user' not in session:
        flash("Please login to access Live Monitor.", "info")
        return redirect(url_for('login'))
    return render_template('live.html')

@app.route('/stream_live')
@login_required
def stream_live():
    user_email = session.get('user')
    return Response(
        detector.camera_frame_generator(0, callback=lambda event_type, info: fall_callback(event_type, info, user_email=user_email)),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# --- Analytics ---
@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/analytics')
def api_analytics():
    # Serve the cached analytics from the last processed video
    with processing_lock:
        data = analytics_cache.copy()

    # Ensure required keys exist with defaults
    data.setdefault('total_videos', 0)
    data.setdefault('fall_count', 0)
    data.setdefault('near_fall_count', 0)
    data.setdefault('safe_count', 0)
    data.setdefault('avg_confidence', 0)
    data.setdefault('time_labels', [])
    data.setdefault('person_count', [])
    data.setdefault('fall_risk', [])
    data.setdefault('activity_counts', {
        "Fall": [], "Near-Fall": [], "Walking": [], "Standing": [], "Sitting": []
    })
    data.setdefault('events', [])

    return jsonify(data)

# --- Fall Alert API ---
@app.route('/fall_status')
@login_required
def fall_status():
    global fall_events
    with events_lock:
        fall_detected = len(fall_events) > 0
        if fall_detected:
            # Clear events after confirming detection
            fall_events.clear()
    return jsonify({"fall": fall_detected})

# --- Contact Management ---
# --- Contact Management ---

@app.route('/contact')
@login_required
def contact_page():
    return render_template('contact.html')


@app.route('/get_contacts')
@login_required
def get_contacts():
    user_email = session.get('user')
    contacts = list(contacts_collection.find({'user_email': user_email}, {"_id": 0}))
    return jsonify({"contacts": contacts})


@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    data = request.json
    user_email = session.get('user')

    # Validate required fields
    name = data.get('name')
    number = data.get('number')
    email = data.get('email')

    if not name or not number or not email:
        return jsonify({"message": "Name, number, and email are required."}), 400

    if contacts_collection.find_one({
        "name": name,
        "number": number,
        "email": email,
        "user_email": user_email
    }):
        return jsonify({"message": "This contact already exists!"}), 409

    contact_data = {
        "name": name,
        "number": number,
        "email": email,
        "user_email": user_email
    }

    contacts_collection.insert_one(contact_data)
    return jsonify({"message": "Contact added successfully!"})


@app.route('/update_contact', methods=['POST'])
@login_required
def update_contact():
    data = request.json
    user_email = session.get('user')

    # Validate required fields
    old_name = data.get('old_name')
    old_number = data.get('old_number')
    old_email = data.get('old_email')

    new_name = data.get('name')
    new_number = data.get('number')
    new_email = data.get('email')

    if not old_name or not old_number or not old_email or not new_name or not new_number or not new_email:
        return jsonify({"message": "All old and new contact fields are required."}), 400

    query = {
        "name": old_name,
        "number": old_number,
        "email": old_email,
        "user_email": user_email
    }

    update = {
        "$set": {
            "name": new_name,
            "number": new_number,
            "email": new_email
        }
    }

    result = contacts_collection.update_one(query, update)
    if result.matched_count == 0:
        return jsonify({"message": "No matching contact found to update."}), 404

    return jsonify({"message": "Contact updated successfully!"})


@app.route('/delete_contact', methods=['POST'])
@login_required
def delete_contact():
    data = request.json
    user_email = session.get('user')

    # Validate required fields
    name = data.get('name')
    number = data.get('number')
    email = data.get('email')

    if not name or not number or not email:
        return jsonify({"message": "Name, number, and email are required."}), 400

    query = {
        "name": name,
        "number": number,
        "email": email,
        "user_email": user_email
    }

    result = contacts_collection.delete_one(query)
    if result.deleted_count == 0:
        return jsonify({"message": "No matching contact found."}), 404

    return jsonify({"message": "Contact deleted successfully!"})

# --- Test Email ---
@app.route('/send_test_email', methods=['POST'])
@login_required
def send_test_email():
    try:
        user_email = session.get('user')
        contacts = list(contacts_collection.find({'user_email': user_email}, {"_id": 0}))
        if not contacts:
            return jsonify({"message": "No contacts to send email."})

        success_count = 0
        for contact in contacts:
            if send_fall_alert_email(contact['name'], contact['email'], user_email=user_email):
                success_count += 1
        
        return jsonify({"message": f"Test email sent successfully to {success_count}/{len(contacts)} contacts!"})
    except Exception as e:
        print("Failed to send test email:", e)
        return jsonify({"message": "Failed to send test email.", "error": str(e)})

# --- Serve Upload Files ---
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # Debug logging
    print(f"📁 Serving: {filename}")
    print(f"   Path: {file_path}")
    print(f"   Exists: {os.path.exists(file_path)}")
    if os.path.exists(file_path):
        print(f"   Size: {os.path.getsize(file_path)} bytes")
    
    # Determine MIME type
    if filename.endswith('.avi'):
        mimetype = 'video/avi'
    elif filename.endswith('.mp4'):
        mimetype = 'video/mp4'
    else:
        mimetype = 'application/octet-stream'
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, mimetype=mimetype)

# -----------------------------
# Run App
# -----------------------------
if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0')

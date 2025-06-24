from flask import Flask, render_template, request, jsonify, Response, send_file, session
from flask_session import Session
import cv2
import mediapipe as mp
import numpy as np
import json
import threading
import time
import uuid
import redis
from datetime import datetime
from counters import get_counter, list_counters
from visualizer import Visualizer
import base64
import os
from werkzeug.utils import secure_filename

# Allowed video file extensions
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'm4v'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_counter_type(counter):
    """Determine counter type based on its attributes"""
    if hasattr(counter, 'detection_type'):
        if counter.detection_type == 'yolo':
            return 'yolo'
        elif counter.detection_type == 'mediapipe':
            return 'mediapipe'
    
    # Fallback: check if it has YOLO-specific attributes
    if hasattr(counter, 'object_class') and hasattr(counter, 'tracker'):
        return 'yolo'
    
    # Default to mediapipe for human action counters
    return 'mediapipe'

# Global storage for user sessions (thread-safe)
user_sessions = {}
session_lock = threading.Lock()

class UserSession:
    """Thread-safe user session for video processing"""
    def __init__(self, session_id):
        self.session_id = session_id
        self.counter = None
        self.visualizer = None
        self.video_capture = None
        self.mp_pose = None
        self.pose = None
        self.mp_drawing = None
        self.processing_thread = None
        self.is_processing = False
        self.current_frame = None
        self.frame_lock = threading.Lock()
        
        # Video recording variables
        self.video_writer = None
        self.is_recording = False
        self.recording_filename = None
        self.recording_start_time = None
        self.recorded_frames = 0
        
        # Session data
        self.session_data = {
            'counts': [],
            'start_time': None,
            'current_count': 0,
            'counter_name': '',
            'counter_type': '',
            'video_source': '',
            'parameters': {}
        }
        
        self.initialize_mediapipe()
    
    def initialize_mediapipe(self):
        """Initialize MediaPipe pose detection for this session"""
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils

def get_user_session(session_id=None):
    """Get or create user session (thread-safe)"""
    if session_id is None:
        session_id = session.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
    
    with session_lock:
        if session_id not in user_sessions:
            user_sessions[session_id] = UserSession(session_id)
        return user_sessions[session_id]

def create_app():
    """Application factory for Flask app"""
    app = Flask(__name__)
    
    # Configuration
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
    app.config['UPLOAD_FOLDER'] = 'uploads'
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'multi-counter-secret-key-change-in-production')
    
    # Session configuration (Redis-backed for production)
    if os.environ.get('REDIS_URL'):
        app.config['SESSION_TYPE'] = 'redis'
        app.config['SESSION_REDIS'] = redis.from_url(os.environ.get('REDIS_URL'))
    else:
        # Fallback to filesystem sessions for development
        app.config['SESSION_TYPE'] = 'filesystem'
        app.config['SESSION_FILE_DIR'] = './sessions'
    
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    
    # Initialize session
    Session(app)

    def process_video_stream(user_session):
        """Process video stream in background thread - supports both MediaPipe and YOLO"""
        counter_type = user_session.session_data.get('counter_type', 'mediapipe')
        
        # Get video FPS for proper timing
        video_fps = 30  # Default FPS
        if user_session.video_capture:
            video_fps = user_session.video_capture.get(cv2.CAP_PROP_FPS)
            if video_fps <= 0 or video_fps > 60:
                video_fps = 30  # Fallback to 30 FPS
        
        # Calculate proper frame delay
        frame_delay = 1.0 / video_fps  # Seconds per frame
        
        while user_session.is_processing and user_session.video_capture and user_session.video_capture.isOpened():
            frame_start_time = time.time()
            
            ret, frame = user_session.video_capture.read()
            if not ret:
                if user_session.session_data.get('video_source', '0').isdigit():
                    # Camera disconnected
                    break
                else:
                    # Video ended, restart
                    user_session.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                
            # Keep original frame for recording (full resolution)
            recording_frame = frame.copy()
            
            # Resize frame for web display only
            if frame.shape[1] > 640:
                scale = 640 / frame.shape[1]
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
            
            if counter_type == 'mediapipe':
                # Process with MediaPipe for human action counters
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = user_session.pose.process(frame_rgb)
                
                if results.pose_landmarks and user_session.counter:
                    # Draw pose landmarks on web display frame
                    user_session.mp_drawing.draw_landmarks(frame, results.pose_landmarks, user_session.mp_pose.POSE_CONNECTIONS)
                    
                    # Update counter
                    old_count = user_session.counter.count
                    count = user_session.counter.update(results.pose_landmarks)
                    
                    # Record count changes
                    if count > old_count:
                        user_session.session_data['counts'].append({
                            'count': count,
                            'timestamp': datetime.now().isoformat(),
                            'validation_score': getattr(user_session.counter, 'validation_score', 1.0)
                        })
                    
                    user_session.session_data['current_count'] = count
                    
                    # Display counter info on web frame
                    cv2.putText(frame, f'{user_session.session_data["counter_name"]}: {count}', 
                               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    # Add timestamp for web display
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
                    # Draw debug info on web frame
                    if user_session.visualizer:
                        user_session.visualizer.draw_debug_info(frame, user_session.counter, results.pose_landmarks)
                    
                    # For recording: draw overlays on original resolution frame
                    if user_session.is_recording and user_session.video_writer is not None:
                        # Scale the landmarks to original frame size
                        scale_x = recording_frame.shape[1] / frame.shape[1]
                        scale_y = recording_frame.shape[0] / frame.shape[0]
                        
                        # Draw pose landmarks on recording frame
                        user_session.mp_drawing.draw_landmarks(recording_frame, results.pose_landmarks, user_session.mp_pose.POSE_CONNECTIONS)
                        
                        # Add counter info to recording frame (scaled)
                        cv2.putText(recording_frame, f'{user_session.session_data["counter_name"]}: {count}', 
                                   (int(10 * scale_x), int(30 * scale_y)), cv2.FONT_HERSHEY_SIMPLEX, 
                                   1 * min(scale_x, scale_y), (0, 255, 0), 2)
                        
                        # Add timestamp to recording frame
                        cv2.putText(recording_frame, timestamp, 
                                   (int(10 * scale_x), recording_frame.shape[0] - int(10 * scale_y)), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5 * min(scale_x, scale_y), (255, 255, 255), 1)
            
            elif counter_type == 'yolo':
                # Process with YOLO for animal/object counters
                if user_session.counter:
                    # Update counter with web display frame
                    old_count = user_session.counter.count
                    count = user_session.counter.update(frame)
                    
                    # Record count changes
                    if count > old_count:
                        user_session.session_data['counts'].append({
                            'count': count,
                            'timestamp': datetime.now().isoformat(),
                            'confidence': getattr(user_session.counter.debug_info, 'confidence', 0.0)
                        })
                    
                    user_session.session_data['current_count'] = count
                    
                    # Get detection for display
                    detections = user_session.counter.tracker.detect_objects(frame)
                    best_detection = user_session.counter.tracker.get_best_detection(detections)
                    
                    # Draw debug info with YOLO detection on web frame
                    frame = user_session.counter.draw_debug_info(frame, best_detection)
                    
                    # Add timestamp for web display
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
                    # For recording: draw overlays on original resolution frame
                    if user_session.is_recording and user_session.video_writer is not None:
                        # Process recording frame with YOLO
                        recording_detections = user_session.counter.tracker.detect_objects(recording_frame)
                        recording_best = user_session.counter.tracker.get_best_detection(recording_detections)
                        recording_frame = user_session.counter.draw_debug_info(recording_frame, recording_best)
                        
                        # Add timestamp to recording frame
                        cv2.putText(recording_frame, timestamp, 
                                   (10, recording_frame.shape[0] - 10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Store current frame for streaming
            with user_session.frame_lock:
                user_session.current_frame = frame.copy()
            
            # Write to video file if recording
            if user_session.is_recording and user_session.video_writer is not None:
                user_session.video_writer.write(recording_frame)
                user_session.recorded_frames += 1
            
            # Maintain proper frame timing
            frame_process_time = time.time() - frame_start_time
            sleep_time = max(0, frame_delay - frame_process_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def generate_frames():
        """Generate video frames for streaming"""
        user_session = get_user_session()
        
        while user_session.is_processing:
            with user_session.frame_lock:
                if user_session.current_frame is not None:
                    frame = user_session.current_frame.copy()
                else:
                    # Generate a black frame with message
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, 'No video feed', (250, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(0.033)  # ~30 FPS

    def list_counters_by_category():
        """Get all counters organized by category"""
        all_counters = list_counters()
        
        categories = {
            'human_actions': {
                'name': 'Human Actions',
                'icon': '🏃',
                'counters': []
            },
            'animals': {
                'name': 'Animals',
                'icon': '🐾',
                'counters': []
            },
            'objects': {
                'name': 'Objects',
                'icon': '📦',
                'counters': []
            },
            'custom': {
                'name': 'Custom',
                'icon': '⚙️',
                'counters': []
            }
        }
        
        for counter_name in all_counters:
            try:
                counter = get_counter(counter_name)
                counter_type = get_counter_type(counter)
                
                counter_info = {
                    'name': counter_name,
                    'type': counter_type,
                    'description': getattr(counter, 'description', f'{counter_name} counter')
                }
                
                # Categorize based on counter type and name
                if counter_type == 'mediapipe' or any(action in counter_name.lower() for action in ['push', 'pull', 'squat', 'jump', 'run']):
                    categories['human_actions']['counters'].append(counter_info)
                elif any(animal in counter_name.lower() for animal in ['dog', 'cat', 'bird', 'fish', 'animal']):
                    categories['animals']['counters'].append(counter_info)
                elif counter_type == 'yolo':
                    categories['objects']['counters'].append(counter_info)
                else:
                    categories['custom']['counters'].append(counter_info)
                    
            except Exception as e:
                print(f"Error loading counter {counter_name}: {e}")
                continue
        
        return categories

    # Routes
    @app.route('/')
    def index():
        categories = list_counters_by_category()
        return render_template('index.html', categories=categories)

    @app.route('/video_feed')
    def video_feed():
        return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/start_counter', methods=['POST'])
    def start_counter():
        user_session = get_user_session()
        
        try:
            data = request.get_json()
            counter_name = data.get('counter_name')
            video_source = data.get('video_source', '0')
            
            if not counter_name:
                return jsonify({'success': False, 'error': 'Counter name is required'})
            
            # Stop any existing processing
            if user_session.is_processing:
                user_session.is_processing = False
                if user_session.processing_thread:
                    user_session.processing_thread.join(timeout=2)
                if user_session.video_capture:
                    user_session.video_capture.release()
            
            # Load the counter
            user_session.counter = get_counter(counter_name)
            if not user_session.counter:
                return jsonify({'success': False, 'error': f'Counter "{counter_name}" not found'})
            
            # Initialize visualizer
            user_session.visualizer = Visualizer()
            
            # Determine counter type
            counter_type = get_counter_type(user_session.counter)
            
            # Setup video capture
            if video_source.isdigit():
                # Camera
                video_source = int(video_source)
                user_session.video_capture = cv2.VideoCapture(video_source)
                if not user_session.video_capture.isOpened():
                    return jsonify({'success': False, 'error': f'Could not open camera {video_source}'})
                
                # Set camera properties for better performance
                user_session.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                user_session.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                user_session.video_capture.set(cv2.CAP_PROP_FPS, 30)
                user_session.video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
            else:
                # Video file
                video_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(video_source))
                if not os.path.exists(video_path):
                    return jsonify({'success': False, 'error': f'Video file "{video_source}" not found'})
                
                user_session.video_capture = cv2.VideoCapture(video_path)
                if not user_session.video_capture.isOpened():
                    return jsonify({'success': False, 'error': f'Could not open video file "{video_source}"'})
            
            # Reset session data
            user_session.session_data = {
                'counts': [],
                'start_time': datetime.now().isoformat(),
                'current_count': 0,
                'counter_name': counter_name,
                'counter_type': counter_type,
                'video_source': str(video_source),
                'parameters': {}
            }
            
            # Reset counter
            user_session.counter.reset()
            
            # Start processing
            user_session.is_processing = True
            user_session.processing_thread = threading.Thread(target=process_video_stream, args=(user_session,))
            user_session.processing_thread.daemon = True
            user_session.processing_thread.start()
            
            return jsonify({
                'success': True, 
                'counter_name': counter_name,
                'counter_type': counter_type,
                'video_source': str(video_source)
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/stop_counter', methods=['POST'])
    def stop_counter():
        user_session = get_user_session()
        
        try:
            # Stop processing
            user_session.is_processing = False
            
            # Wait for thread to finish
            if user_session.processing_thread:
                user_session.processing_thread.join(timeout=2)
            
            # Release video capture
            if user_session.video_capture:
                user_session.video_capture.release()
                user_session.video_capture = None
            
            # Stop recording if active
            if user_session.is_recording:
                user_session.is_recording = False
                if user_session.video_writer:
                    user_session.video_writer.release()
                    user_session.video_writer = None
            
            return jsonify({'success': True})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/get_counter_info/<counter_name>')
    def get_counter_info(counter_name):
        try:
            counter = get_counter(counter_name)
            if not counter:
                return jsonify({'success': False, 'error': 'Counter not found'})
            
            counter_type = get_counter_type(counter)
            
            info = {
                'name': counter_name,
                'type': counter_type,
                'description': getattr(counter, 'description', f'{counter_name} counter'),
                'parameters': {}
            }
            
            # Add type-specific parameters
            if counter_type == 'mediapipe':
                info['parameters'] = {
                    'sensitivity': getattr(counter, 'sensitivity', 0.5),
                    'center_line': getattr(counter, 'center_line', 0.5),
                    'min_detection_confidence': getattr(counter, 'min_detection_confidence', 0.5),
                    'min_tracking_confidence': getattr(counter, 'min_tracking_confidence', 0.5)
                }
            elif counter_type == 'yolo':
                info['parameters'] = {
                    'confidence_threshold': getattr(counter, 'confidence_threshold', 0.5),
                    'object_class': getattr(counter, 'object_class', 'person'),
                    'tracking_method': getattr(counter, 'tracking_method', 'centroid')
                }
            
            return jsonify({'success': True, 'info': info})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/get_session_data')
    def get_session_data():
        user_session = get_user_session()
        return jsonify(user_session.session_data)

    @app.route('/save_session', methods=['POST'])
    def save_session():
        user_session = get_user_session()
        
        try:
            # Create sessions directory if it doesn't exist
            session_dir = os.path.join('sessions', user_session.session_id)
            os.makedirs(session_dir, exist_ok=True)
            
            # Save session data
            filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(session_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(user_session.session_data, f, indent=2)
            
            return jsonify({'success': True, 'filename': filename})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/upload_video', methods=['POST'])
    def upload_video():
        try:
            if 'video' not in request.files:
                return jsonify({'success': False, 'error': 'No video file provided'})
            
            file = request.files['video']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No file selected'})
            
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'error': 'File type not allowed'})
            
            # Create upload directory
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Save file with secure filename
            filename = secure_filename(file.filename)
            # Add timestamp to avoid conflicts
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            return jsonify({'success': True, 'filename': filename})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/list_uploaded_videos')
    def list_uploaded_videos():
        try:
            upload_folder = app.config['UPLOAD_FOLDER']
            if not os.path.exists(upload_folder):
                return jsonify({'success': True, 'videos': []})
            
            videos = []
            for filename in os.listdir(upload_folder):
                if allowed_file(filename):
                    filepath = os.path.join(upload_folder, filename)
                    stat = os.stat(filepath)
                    videos.append({
                        'filename': filename,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
            
            # Sort by modification time (newest first)
            videos.sort(key=lambda x: x['modified'], reverse=True)
            
            return jsonify({'success': True, 'videos': videos})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    # Parameter adjustment routes (existing routes adapted for multi-user)
    @app.route('/adjust_center_line', methods=['POST'])
    def adjust_center_line():
        user_session = get_user_session()
        
        try:
            data = request.get_json()
            adjustment = data.get('adjustment', 0)
            
            if not user_session.counter:
                return jsonify({'success': False, 'error': 'No active counter'})
            
            # Adjust center line
            if hasattr(user_session.counter, 'center_line'):
                user_session.counter.center_line = max(0.0, min(1.0, user_session.counter.center_line + adjustment))
                user_session.session_data['parameters']['center_line'] = user_session.counter.center_line
                
                return jsonify({
                    'success': True, 
                    'center_line': user_session.counter.center_line
                })
            else:
                return jsonify({'success': False, 'error': 'Counter does not support center line adjustment'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/reset_calibration', methods=['POST'])
    def reset_calibration():
        user_session = get_user_session()
        
        try:
            if not user_session.counter:
                return jsonify({'success': False, 'error': 'No active counter'})
            
            # Reset counter calibration
            if hasattr(user_session.counter, 'reset_calibration'):
                user_session.counter.reset_calibration()
            else:
                # Generic reset
                if hasattr(user_session.counter, 'center_line'):
                    user_session.counter.center_line = 0.5
                if hasattr(user_session.counter, 'sensitivity'):
                    user_session.counter.sensitivity = 0.5
                if hasattr(user_session.counter, 'confidence_threshold'):
                    user_session.counter.confidence_threshold = 0.5
            
            # Update session parameters
            user_session.session_data['parameters'] = {
                'center_line': getattr(user_session.counter, 'center_line', 0.5),
                'sensitivity': getattr(user_session.counter, 'sensitivity', 0.5),
                'confidence_threshold': getattr(user_session.counter, 'confidence_threshold', 0.5)
            }
            
            return jsonify({'success': True, 'parameters': user_session.session_data['parameters']})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/adjust_sensitivity', methods=['POST'])
    def adjust_sensitivity():
        user_session = get_user_session()
        
        try:
            data = request.get_json()
            adjustment = data.get('adjustment', 0)
            
            if not user_session.counter:
                return jsonify({'success': False, 'error': 'No active counter'})
            
            # Adjust sensitivity
            if hasattr(user_session.counter, 'sensitivity'):
                user_session.counter.sensitivity = max(0.0, min(1.0, user_session.counter.sensitivity + adjustment))
                user_session.session_data['parameters']['sensitivity'] = user_session.counter.sensitivity
                
                return jsonify({
                    'success': True, 
                    'sensitivity': user_session.counter.sensitivity
                })
            else:
                return jsonify({'success': False, 'error': 'Counter does not support sensitivity adjustment'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/adjust_sensitivity_absolute', methods=['POST'])
    def adjust_sensitivity_absolute():
        user_session = get_user_session()
        
        try:
            data = request.get_json()
            sensitivity = data.get('sensitivity', 0.5)
            
            if not user_session.counter:
                return jsonify({'success': False, 'error': 'No active counter'})
            
            # Set absolute sensitivity
            if hasattr(user_session.counter, 'sensitivity'):
                user_session.counter.sensitivity = max(0.0, min(1.0, float(sensitivity)))
                user_session.session_data['parameters']['sensitivity'] = user_session.counter.sensitivity
                
                return jsonify({
                    'success': True, 
                    'sensitivity': user_session.counter.sensitivity
                })
            else:
                return jsonify({'success': False, 'error': 'Counter does not support sensitivity adjustment'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/adjust_center_line_absolute', methods=['POST'])
    def adjust_center_line_absolute():
        user_session = get_user_session()
        
        try:
            data = request.get_json()
            center_line = data.get('center_line', 0.5)
            
            if not user_session.counter:
                return jsonify({'success': False, 'error': 'No active counter'})
            
            # Set absolute center line
            if hasattr(user_session.counter, 'center_line'):
                user_session.counter.center_line = max(0.0, min(1.0, float(center_line)))
                user_session.session_data['parameters']['center_line'] = user_session.counter.center_line
                
                return jsonify({
                    'success': True, 
                    'center_line': user_session.counter.center_line
                })
            else:
                return jsonify({'success': False, 'error': 'Counter does not support center line adjustment'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/adjust_parameter', methods=['POST'])
    def adjust_parameter():
        user_session = get_user_session()
        
        try:
            data = request.get_json()
            parameter_name = data.get('parameter_name')
            parameter_value = data.get('parameter_value')
            
            if not user_session.counter:
                return jsonify({'success': False, 'error': 'No active counter'})
            
            if not parameter_name:
                return jsonify({'success': False, 'error': 'Parameter name is required'})
            
            # Set parameter value
            if hasattr(user_session.counter, parameter_name):
                # Convert to appropriate type
                current_value = getattr(user_session.counter, parameter_name)
                if isinstance(current_value, bool):
                    parameter_value = bool(parameter_value)
                elif isinstance(current_value, int):
                    parameter_value = int(parameter_value)
                elif isinstance(current_value, float):
                    parameter_value = float(parameter_value)
                
                setattr(user_session.counter, parameter_name, parameter_value)
                user_session.session_data['parameters'][parameter_name] = parameter_value
                
                return jsonify({
                    'success': True, 
                    'parameter_name': parameter_name,
                    'parameter_value': parameter_value
                })
            else:
                return jsonify({'success': False, 'error': f'Parameter "{parameter_name}" not found'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    # Recording routes
    @app.route('/start_recording', methods=['POST'])
    def start_recording():
        user_session = get_user_session()
        
        try:
            if not user_session.is_processing:
                return jsonify({'success': False, 'error': 'No active video processing'})
            
            if user_session.is_recording:
                return jsonify({'success': False, 'error': 'Recording already in progress'})
            
            # Create recordings directory
            recordings_dir = os.path.join('recordings', user_session.session_id)
            os.makedirs(recordings_dir, exist_ok=True)
            
            # Generate recording filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            counter_name = user_session.session_data.get('counter_name', 'unknown')
            user_session.recording_filename = f"{counter_name}_{timestamp}.mp4"
            recording_path = os.path.join(recordings_dir, user_session.recording_filename)
            
            # Get frame dimensions from video capture
            if user_session.video_capture:
                width = int(user_session.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(user_session.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = user_session.video_capture.get(cv2.CAP_PROP_FPS)
                if fps <= 0 or fps > 60:
                    fps = 30
            else:
                width, height, fps = 1280, 720, 30
            
            # Initialize video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            user_session.video_writer = cv2.VideoWriter(recording_path, fourcc, fps, (width, height))
            
            if not user_session.video_writer.isOpened():
                return jsonify({'success': False, 'error': 'Failed to initialize video writer'})
            
            user_session.is_recording = True
            user_session.recording_start_time = datetime.now()
            user_session.recorded_frames = 0
            
            return jsonify({
                'success': True, 
                'filename': user_session.recording_filename,
                'start_time': user_session.recording_start_time.isoformat()
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/stop_recording', methods=['POST'])
    def stop_recording():
        user_session = get_user_session()
        
        try:
            if not user_session.is_recording:
                return jsonify({'success': False, 'error': 'No active recording'})
            
            # Stop recording
            user_session.is_recording = False
            
            if user_session.video_writer:
                user_session.video_writer.release()
                user_session.video_writer = None
            
            # Calculate recording info
            end_time = datetime.now()
            duration = (end_time - user_session.recording_start_time).total_seconds()
            
            recording_info = {
                'filename': user_session.recording_filename,
                'duration': duration,
                'frames': user_session.recorded_frames,
                'start_time': user_session.recording_start_time.isoformat(),
                'end_time': end_time.isoformat()
            }
            
            return jsonify({'success': True, 'recording_info': recording_info})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    @app.route('/download_latest_recording')
    def download_latest_recording():
        user_session = get_user_session()
        
        try:
            recordings_dir = os.path.join('recordings', user_session.session_id)
            
            if not os.path.exists(recordings_dir):
                return jsonify({'success': False, 'error': 'No recordings found'})
            
            # Find latest recording
            recordings = []
            for filename in os.listdir(recordings_dir):
                if filename.endswith('.mp4'):
                    filepath = os.path.join(recordings_dir, filename)
                    recordings.append((filepath, os.path.getmtime(filepath)))
            
            if not recordings:
                return jsonify({'success': False, 'error': 'No recordings found'})
            
            # Get latest recording
            latest_recording = max(recordings, key=lambda x: x[1])[0]
            
            return send_file(latest_recording, as_attachment=True)
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    # Create necessary directories
    @app.before_first_request
    def create_directories():
        directories = ['sessions', 'uploads', 'recordings']
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    return app

# For backwards compatibility during development
if __name__ == "__main__":
    app = create_app()
    print("🏋️ Multi Counter Web Interface Starting...")
    print("📱 Access at: http://localhost:5000")
    
    try:
        # Set Flask to handle errors gracefully
        app.config['PROPAGATE_EXCEPTIONS'] = False
        app.run(debug=False, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n⏹️ Web interface stopped by user.")
    except Exception as e:
        print(f"❌ Error starting web interface: {e}")
        input("Press Enter to exit...") 
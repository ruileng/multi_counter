from flask import Flask, render_template, request, jsonify, Response, send_file
import cv2
import mediapipe as mp
import numpy as np
import json
import threading
import time
from datetime import datetime
from counters import get_counter, list_counters
from visualizer import Visualizer
import base64
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'

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

# Global variables for video processing
current_counter = None
current_visualizer = None
video_capture = None
mp_pose = None
pose = None
mp_drawing = None
processing_thread = None
is_processing = False
current_frame = None
frame_lock = threading.Lock()

# Video recording variables
video_writer = None
is_recording = False
recording_filename = None
recording_start_time = None
recorded_frames = 0

# Session data
session_data = {
    'counts': [],
    'start_time': None,
    'current_count': 0,
    'counter_name': '',
    'counter_type': '',
    'video_source': '',
    'parameters': {}
}

def initialize_mediapipe():
    """Initialize MediaPipe pose detection"""
    global mp_pose, pose, mp_drawing
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    mp_drawing = mp.solutions.drawing_utils

def process_video_stream():
    """Process video stream in background thread - supports both MediaPipe and YOLO"""
    global current_frame, is_processing, current_counter, current_visualizer
    global video_capture, session_data, video_writer, is_recording, recorded_frames
    
    counter_type = session_data.get('counter_type', 'mediapipe')
    
    # Get video FPS for proper timing
    video_fps = 30  # Default FPS
    if video_capture:
        video_fps = video_capture.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0 or video_fps > 60:
            video_fps = 30  # Fallback to 30 FPS
    
    # Calculate proper frame delay
    frame_delay = 1.0 / video_fps  # Seconds per frame
    
    while is_processing and video_capture and video_capture.isOpened():
        frame_start_time = time.time()
        
        ret, frame = video_capture.read()
        if not ret:
            if session_data.get('video_source', '0').isdigit():
                # Camera disconnected
                break
            else:
                # Video ended, restart
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
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
            results = pose.process(frame_rgb)
            
            if results.pose_landmarks and current_counter:
                # Draw pose landmarks on web display frame
                mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                
                # Update counter
                old_count = current_counter.count
                count = current_counter.update(results.pose_landmarks)
                
                # Record count changes
                if count > old_count:
                    session_data['counts'].append({
                        'count': count,
                        'timestamp': datetime.now().isoformat(),
                        'validation_score': getattr(current_counter, 'validation_score', 1.0)
                    })
                
                session_data['current_count'] = count
                
                # Display counter info on web frame
                cv2.putText(frame, f'{session_data["counter_name"]}: {count}', 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # Add timestamp for web display
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Draw debug info on web frame
                if current_visualizer:
                    current_visualizer.draw_debug_info(frame, current_counter, results.pose_landmarks)
                
                # For recording: draw overlays on original resolution frame
                if is_recording and video_writer is not None:
                    # Scale the landmarks to original frame size
                    scale_x = recording_frame.shape[1] / frame.shape[1]
                    scale_y = recording_frame.shape[0] / frame.shape[0]
                    
                    # Draw pose landmarks on recording frame
                    mp_drawing.draw_landmarks(recording_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                    
                    # Add counter info to recording frame (scaled)
                    cv2.putText(recording_frame, f'{session_data["counter_name"]}: {count}', 
                               (int(10 * scale_x), int(30 * scale_y)), cv2.FONT_HERSHEY_SIMPLEX, 
                               1 * min(scale_x, scale_y), (0, 255, 0), 2)
                    
                    # Add timestamp to recording frame
                    cv2.putText(recording_frame, timestamp, 
                               (int(10 * scale_x), recording_frame.shape[0] - int(10 * scale_y)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5 * min(scale_x, scale_y), (255, 255, 255), 1)
        
        elif counter_type == 'yolo':
            # Process with YOLO for animal/object counters
            if current_counter:
                # Update counter with web display frame
                old_count = current_counter.count
                count = current_counter.update(frame)
                
                # Record count changes
                if count > old_count:
                    session_data['counts'].append({
                        'count': count,
                        'timestamp': datetime.now().isoformat(),
                        'confidence': getattr(current_counter.debug_info, 'confidence', 0.0)
                    })
                
                session_data['current_count'] = count
                
                # Get detection for display
                detections = current_counter.tracker.detect_objects(frame)
                best_detection = current_counter.tracker.get_best_detection(detections)
                
                # Draw debug info with YOLO detection on web frame
                frame = current_counter.draw_debug_info(frame, best_detection)
                
                # Add timestamp for web display
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # For recording: process and draw on original resolution frame
                if is_recording and video_writer is not None:
                    # Update counter with original frame to get proper detections
                    recording_detections = current_counter.tracker.detect_objects(recording_frame)
                    recording_detection = current_counter.tracker.get_best_detection(recording_detections)
                    
                    # Draw debug info on recording frame (full resolution)
                    recording_frame = current_counter.draw_debug_info(recording_frame, recording_detection)
                    
                    # Add timestamp to recording frame
                    cv2.putText(recording_frame, timestamp, (10, recording_frame.shape[0] - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Record video if recording is active (use original frame with overlays)
        if is_recording and video_writer is not None:
            try:
                video_writer.write(recording_frame)
                recorded_frames += 1
            except Exception:
                # Silently handle recording errors
                pass
        
        # Store web display frame for streaming
        with frame_lock:
            current_frame = frame.copy()
        
        # Maintain proper frame rate timing
        frame_process_time = time.time() - frame_start_time
        sleep_time = max(0, frame_delay - frame_process_time)
        time.sleep(sleep_time)

def generate_frames():
    """Generate frames for video streaming"""
    global current_frame
    
    # Target frame rate for web streaming
    target_fps = 25  # Slightly lower than source for stable web streaming
    frame_delay = 1.0 / target_fps
    
    while True:
        frame_start_time = time.time()
        
        with frame_lock:
            if current_frame is not None:
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', current_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Maintain consistent frame rate for web streaming
        frame_process_time = time.time() - frame_start_time
        sleep_time = max(0, frame_delay - frame_process_time)
        time.sleep(sleep_time)

def list_counters_by_category():
    """Returns counters organized by category."""
    from counters import list_counters, get_counter
    
    categorized = {
        'Human': [],
        'Animal': [],
        'Object': []
    }
    
    all_counters = list_counters()
    for counter_name in all_counters:
        try:
            CounterClass = get_counter(counter_name)
            if CounterClass:
                temp_counter = CounterClass()
                counter_type = get_counter_type(temp_counter)
                
                counter_info = {
                    'name': counter_name,
                    'type': counter_type,
                    'object_class': getattr(temp_counter, 'object_class', 'human'),
                    'logic_type': getattr(temp_counter, 'logic_type', 'exercise'),
                    'confidence_threshold': getattr(temp_counter, 'confidence_threshold', 0.5),
                    'description': getattr(temp_counter, 'description', ''),
                    'has_center_line': hasattr(temp_counter, 'adjust_center_line') or hasattr(temp_counter, 'start_position') or hasattr(temp_counter, 'center_reference')
                }
                
                if counter_type == 'yolo':
                    if counter_info['object_class'] in ['cat', 'dog', 'bird', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe']:
                        categorized['Animal'].append(counter_info)
                    else:
                        categorized['Object'].append(counter_info)
                else:
                    categorized['Human'].append(counter_info)
        except Exception:
            # Silently skip problematic counters
            pass
    
    return categorized

@app.route('/')
def index():
    """Main page"""
    categorized_counters = list_counters_by_category()
    return render_template('index.html', counters=categorized_counters)

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_counter', methods=['POST'])
def start_counter():
    """Start counter with selected parameters - supports all counter types"""
    global current_counter, current_visualizer, video_capture, is_processing
    global processing_thread, session_data
    
    try:
        data = request.get_json()
        counter_name = data['counter']
        video_source = data.get('video_source', '0')
        parameters = data.get('parameters', {})
        
        # Stop existing processing
        stop_counter()
        
        # Get counter class and create instance
        CounterClass = get_counter(counter_name)
        if not CounterClass:
            return jsonify({'error': f'Counter {counter_name} not found'}), 400
        
        current_counter = CounterClass()
        counter_type = get_counter_type(current_counter)
        
        # Initialize appropriate detection system
        if counter_type == 'mediapipe':
            # Initialize MediaPipe for human action counters
            if mp_pose is None:
                initialize_mediapipe()
            current_visualizer = Visualizer(counter_name)
        elif counter_type == 'yolo':
            # YOLO counters have their own visualization
            current_visualizer = None
        
        # Apply custom parameters
        for param, value in parameters.items():
            if hasattr(current_counter, param):
                # Convert string values to appropriate types
                if param in ['threshold', 'validation_threshold', 'min_visibility', 'confidence_threshold']:
                    value = float(value)
                elif param in ['stable_frames', 'calibration_frames']:
                    value = int(value)
                elif param in ['enable_anti_cheat']:
                    value = bool(value)
                
                setattr(current_counter, param, value)
        
        # Initialize video capture
        if video_source.isdigit():
            video_capture = cv2.VideoCapture(int(video_source))
        else:
            video_capture = cv2.VideoCapture(video_source)
        
        if not video_capture.isOpened():
            return jsonify({'error': f'Could not open video source: {video_source}'}), 400
        
        # Reset session data
        session_data = {
            'counts': [],
            'start_time': datetime.now().isoformat(),
            'current_count': 0,
            'counter_name': counter_name,
            'counter_type': counter_type,
            'video_source': video_source,
            'parameters': parameters
        }
        
        # Start processing thread
        is_processing = True
        processing_thread = threading.Thread(target=process_video_stream)
        processing_thread.daemon = True
        processing_thread.start()
        
        return jsonify({
            'success': True, 
            'message': f'Started {counter_name} ({counter_type})',
            'counter_type': counter_type
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_counter', methods=['POST'])
def stop_counter():
    """Stop counter processing"""
    global is_processing, video_capture, processing_thread, current_frame
    global video_writer, is_recording, recording_filename
    
    is_processing = False
    
    # Stop recording if active
    if is_recording and video_writer is not None:
        is_recording = False
        video_writer.release()
        video_writer = None
    
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=2)
    
    if video_capture:
        video_capture.release()
        video_capture = None
    
    with frame_lock:
        current_frame = None
    
    return jsonify({'success': True})

@app.route('/get_counter_info/<counter_name>')
def get_counter_info(counter_name):
    """Get detailed information about a specific counter"""
    try:
        CounterClass = get_counter(counter_name)
        if not CounterClass:
            return jsonify({'error': 'Counter not found'}), 404
        
        counter = CounterClass()
        counter_type = get_counter_type(counter)
        
        info = {
            'name': counter_name,
            'type': counter_type,
            'parameters': {}
        }
        
        # Common parameters
        if hasattr(counter, 'threshold'):
            info['parameters']['threshold'] = {'type': 'float', 'default': counter.threshold, 'description': 'Movement detection threshold'}
        if hasattr(counter, 'stable_frames'):
            info['parameters']['stable_frames'] = {'type': 'int', 'default': counter.stable_frames, 'description': 'Frames to stabilize detection'}
        
        # MediaPipe specific parameters
        if counter_type == 'mediapipe':
            if hasattr(counter, 'min_visibility'):
                info['parameters']['min_visibility'] = {'type': 'float', 'default': counter.min_visibility, 'description': 'Minimum pose visibility'}
            if hasattr(counter, 'validation_threshold'):
                info['parameters']['validation_threshold'] = {'type': 'float', 'default': counter.validation_threshold, 'description': 'Anti-cheat validation threshold'}
            if hasattr(counter, 'enable_anti_cheat'):
                info['parameters']['enable_anti_cheat'] = {'type': 'bool', 'default': counter.enable_anti_cheat, 'description': 'Enable anti-cheat validation'}
            
            # Add description for MediaPipe counters
            info['description'] = f"Human {getattr(counter, 'logic_type', 'action')} detection using MediaPipe"
        
        # YOLO specific parameters
        elif counter_type == 'yolo':
            if hasattr(counter, 'confidence_threshold'):
                info['parameters']['confidence_threshold'] = {'type': 'float', 'default': counter.confidence_threshold, 'description': 'YOLO detection confidence threshold'}
            if hasattr(counter, 'calibration_frames'):
                info['parameters']['calibration_frames'] = {'type': 'int', 'default': counter.calibration_frames, 'description': 'Frames needed for auto-calibration'}
            
            info['object_class'] = getattr(counter, 'object_class', 'unknown')
            info['logic_type'] = getattr(counter, 'logic_type', 'unknown')
            info['description'] = f"{counter.object_class} {counter.logic_type} detection using YOLO"
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_session_data')
def get_session_data():
    """Get current session data"""
    return jsonify(session_data)

@app.route('/save_session', methods=['POST'])
def save_session():
    """Save session data to file"""
    try:
        filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(f"sessions/{filename}", 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return jsonify({'success': True, 'filename': filename})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload_video', methods=['POST'])
def upload_video():
    """Handle video file upload"""
    try:
        if 'video_file' not in request.files:
            return jsonify({'error': 'No file selected'}), 400
        
        file = request.files['video_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            # Secure the filename and save
            filename = secure_filename(file.filename)
            # Add timestamp to avoid conflicts
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            return jsonify({
                'success': True, 
                'filename': filename,
                'filepath': filepath,
                'message': f'Video uploaded successfully: {filename}'
            })
        else:
            return jsonify({'error': 'Invalid file type. Allowed: ' + ', '.join(ALLOWED_EXTENSIONS)}), 400
            
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/list_uploaded_videos')
def list_uploaded_videos():
    """List all uploaded video files"""
    try:
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            return jsonify({'videos': []})
        
        videos = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file_size = os.path.getsize(filepath)
                videos.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2)
                })
        
        # Sort by modification time (newest first)
        videos.sort(key=lambda x: os.path.getmtime(x['filepath']), reverse=True)
        return jsonify({'videos': videos})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_center_line', methods=['POST'])
def adjust_center_line():
    """Adjust center line for object counters"""
    global current_counter
    
    try:
        data = request.get_json()
        adjustment = data.get('adjustment', 0)
        
        if current_counter and hasattr(current_counter, 'adjust_center_line'):
            # Determine direction and amount based on adjustment value
            if adjustment > 0:
                direction = 'down'
                amount = abs(adjustment * 20)  # Convert to pixel amount
            else:
                direction = 'up'
                amount = abs(adjustment * 20)
            
            # Check if it's SportsBallCounter (uses different method signature)
            if hasattr(current_counter, 'object_class') and current_counter.object_class == 'sports ball':
                current_counter.adjust_center_line(direction, amount)
                current_line = getattr(current_counter, 'start_position', 0)
            else:
                # Animal counters (dog/cat) use different signature
                current_counter.adjust_center_line(direction, amount)
                current_line = getattr(current_counter, 'center_reference', getattr(current_counter, 'start_position', 0))
            
            return jsonify({
                'success': True, 
                'new_center_line': current_line,
                'message': f'Center line adjusted {direction} to {current_line:.1f}'
            })
        else:
            return jsonify({'error': 'Counter does not support center line adjustment'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reset_calibration', methods=['POST'])
def reset_calibration():
    """Reset calibration for YOLO counters"""
    global current_counter
    
    try:
        if current_counter:
            # Check if counter has reset method
            if hasattr(current_counter, 'reset_to_auto_calibration'):
                current_counter.reset_to_auto_calibration()
                return jsonify({
                    'success': True, 
                    'message': 'Calibration reset successfully'
                })
            elif hasattr(current_counter, 'calibrated'):
                # Reset calibration flag to trigger re-calibration
                current_counter.calibrated = False
                current_counter.position_history = []
                if hasattr(current_counter, 'start_position'):
                    current_counter.start_position = None
                if hasattr(current_counter, 'center_reference'):
                    current_counter.center_reference = None
                current_counter.state = "start"
                current_counter.count = 0  # Reset count as well
                return jsonify({
                    'success': True, 
                    'message': 'Calibration reset - will recalibrate automatically'
                })
            else:
                return jsonify({'error': 'Counter does not support calibration reset'}), 400
        else:
            return jsonify({'error': 'No active counter'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_sensitivity', methods=['POST'])
def adjust_sensitivity():
    """Adjust sensitivity for YOLO counters"""
    global current_counter
    
    try:
        data = request.get_json()
        direction = data.get('direction', 'increase')
        
        if current_counter and hasattr(current_counter, 'adjust_sensitivity'):
            # Call the counter's sensitivity adjustment method
            if hasattr(current_counter, 'object_class') and current_counter.object_class == 'sports ball':
                # SportsBallCounter uses different method signature
                current_counter.adjust_sensitivity(direction, 0.1)
                return jsonify({
                    'success': True, 
                    'message': f'Sensitivity {direction}d for sports ball detection'
                })
            else:
                # Animal counters
                current_counter.adjust_sensitivity(direction, 0.1)
                return jsonify({
                    'success': True, 
                    'message': f'Sensitivity {direction}d for {current_counter.object_class} detection'
                })
        else:
            return jsonify({'error': 'Counter does not support sensitivity adjustment'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_sensitivity_absolute', methods=['POST'])
def adjust_sensitivity_absolute():
    """Set absolute sensitivity value for YOLO counters"""
    global current_counter
    
    try:
        data = request.get_json()
        value = data.get('value', 1.0)
        
        if current_counter and hasattr(current_counter, 'sensitivity_multiplier'):
            # Set the sensitivity multiplier directly
            current_counter.sensitivity_multiplier = float(value)
            
            # Recalculate thresholds with new sensitivity
            if hasattr(current_counter, '_recalculate_thresholds'):
                current_counter._recalculate_thresholds()
            
            return jsonify({
                'success': True, 
                'message': f'Sensitivity set to {value:.1f} for {getattr(current_counter, "object_class", "counter")} detection'
            })
        elif current_counter:
            # If counter doesn't have sensitivity_multiplier yet, add it
            current_counter.sensitivity_multiplier = float(value)
            return jsonify({
                'success': True, 
                'message': f'Sensitivity initialized to {value:.1f}'
            })
        else:
            return jsonify({'error': 'No active counter'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_center_line_absolute', methods=['POST'])
def adjust_center_line_absolute():
    """Set absolute center line position for YOLO counters"""
    global current_counter
    
    try:
        data = request.get_json()
        position = data.get('position', 500)
        
        if current_counter:
            # Set absolute position based on counter type
            if hasattr(current_counter, 'object_class') and current_counter.object_class == 'sports ball':
                # SportsBallCounter uses start_position
                current_counter.start_position = float(position)
                if hasattr(current_counter, '_recalculate_thresholds'):
                    current_counter._recalculate_thresholds()
                return jsonify({
                    'success': True, 
                    'new_center_line': position,
                    'message': f'Ground line set to {position:.1f}px'
                })
            elif hasattr(current_counter, 'center_reference'):
                # Animal counters use center_reference
                current_counter.center_reference = float(position)
                if hasattr(current_counter, '_recalculate_thresholds'):
                    current_counter._recalculate_thresholds()
                return jsonify({
                    'success': True, 
                    'new_center_line': position,
                    'message': f'Jump target set to {position:.1f}px'
                })
            elif hasattr(current_counter, 'start_position'):
                # Fallback to start_position
                current_counter.start_position = float(position)
                return jsonify({
                    'success': True, 
                    'new_center_line': position,
                    'message': f'Center line set to {position:.1f}px'
                })
            else:
                return jsonify({'error': 'Counter does not support absolute positioning'}), 400
        else:
            return jsonify({'error': 'No active counter'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_parameter', methods=['POST'])
def adjust_parameter():
    """Adjust any counter parameter in real-time"""
    global current_counter
    
    try:
        data = request.get_json()
        param_name = data.get('parameter')
        param_value = data.get('value')
        
        if not current_counter:
            return jsonify({'error': 'No active counter'}), 400
        
        if not param_name or param_value is None:
            return jsonify({'error': 'Parameter name and value required'}), 400
        
        # Convert value to appropriate type
        if param_name in ['stable_frames', 'calibration_frames']:
            param_value = int(param_value)
        else:
            param_value = float(param_value)
        
        # Check if parameter exists on counter
        if not hasattr(current_counter, param_name):
            return jsonify({'error': f'Parameter {param_name} not supported by this counter'}), 400
        
        # Set the parameter
        old_value = getattr(current_counter, param_name)
        setattr(current_counter, param_name, param_value)
        
        # Special handling for specific parameters
        if param_name == 'confidence_threshold' and hasattr(current_counter, 'tracker'):
            # Update YOLO tracker confidence threshold
            current_counter.tracker.confidence_threshold = param_value
        
        # Recalculate thresholds if needed
        if hasattr(current_counter, '_recalculate_thresholds'):
            current_counter._recalculate_thresholds()
        
        return jsonify({
            'success': True, 
            'message': f'{param_name.replace("_", " ").title()} adjusted from {old_value} to {param_value}',
            'old_value': old_value,
            'new_value': param_value
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_recording', methods=['POST'])
def start_recording():
    """Start recording video with overlays"""
    global video_writer, is_recording, recording_filename, recording_start_time, recorded_frames
    
    try:
        if not is_processing:
            return jsonify({'error': 'No active counter session to record'}), 400
        
        if is_recording:
            return jsonify({'error': 'Recording already in progress'}), 400
        
        # Create recordings directory
        os.makedirs('recordings', exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        counter_name = session_data.get('counter_name', 'unknown').replace(' ', '_')
        recording_filename = f"recordings/recording_{counter_name}_{timestamp}.mp4"
        
        # Get original frame dimensions from video source (not resized web display)
        original_width = 640
        original_height = 480
        
        if video_capture:
            # Get actual video dimensions
            original_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Fallback if dimensions are invalid
            if original_width <= 0 or original_height <= 0:
                original_width, original_height = 640, 480
        
        # Get proper FPS from video source
        video_fps = 30.0  # Default FPS
        if video_capture:
            source_fps = video_capture.get(cv2.CAP_PROP_FPS)
            if source_fps > 0 and source_fps <= 60:
                video_fps = source_fps
            else:
                video_fps = 30.0  # Fallback
        
        # Initialize video writer with original video dimensions and correct FPS
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(recording_filename, fourcc, video_fps, (original_width, original_height))
        
        if not video_writer.isOpened():
            return jsonify({'error': 'Failed to initialize video writer'}), 500
        
        # Start recording
        is_recording = True
        recording_start_time = time.time()
        recorded_frames = 0
        
        return jsonify({
            'success': True, 
            'message': f'Recording started at {video_fps:.1f} FPS ({original_width}x{original_height})',
            'filename': recording_filename,
            'fps': video_fps,
            'width': original_width,
            'height': original_height
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    """Stop recording video"""
    global video_writer, is_recording, recording_filename, recording_start_time, recorded_frames
    
    try:
        if not is_recording:
            return jsonify({'error': 'No recording in progress'}), 400
        
        # Stop recording
        is_recording = False
        
        if video_writer is not None:
            video_writer.release()
            video_writer = None
        
        # Calculate duration
        duration = None
        if recording_start_time:
            duration = round(time.time() - recording_start_time, 2)
        
        # Get file info
        file_info = {
            'filename': os.path.basename(recording_filename) if recording_filename else 'unknown',
            'duration': duration,
            'frames': recorded_frames
        }
        
        return jsonify({
            'success': True, 
            'message': 'Recording stopped',
            **file_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_latest_recording')
def download_latest_recording():
    """Download the latest recording"""
    try:
        if not recording_filename or not os.path.exists(recording_filename):
            return jsonify({'error': 'No recording available for download'}), 404
        
        filename = os.path.basename(recording_filename)
        return send_file(recording_filename, as_attachment=True, download_name=filename)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('sessions', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('recordings', exist_ok=True)
    
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
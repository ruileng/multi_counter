from flask import Flask, render_template, request, jsonify, Response, send_file
import cv2
import mediapipe as mp
import json
import threading
import time
from datetime import datetime
from counters import get_counter, list_counters
from visualizer import Visualizer
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['UPLOAD_FOLDER'] = 'uploads'

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'm4v'}

def allowed_file(filename):
    """检查文件扩展名是否被允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_counter_type(counter):
    """根据计数器属性确定计数器类型"""
    return getattr(counter, 'detection_type', 'yolo' if hasattr(counter, 'tracker') else 'mediapipe')

# 全局变量
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

# 录制变量
video_writer = None
is_recording = False
recording_filename = None
recording_start_time = None
recording_dimensions = None  # Store recording dimensions globally

# 会话数据
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
    """初始化MediaPipe"""
    global mp_pose, pose, mp_drawing
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(static_image_mode=False, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    mp_drawing = mp.solutions.drawing_utils

def add_overlay_to_frame(frame, count, counter_name, timestamp):
    """添加覆盖层到帧"""
    cv2.putText(frame, f'{counter_name}: {count}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame

def process_video_stream():
    """处理视频流"""
    global current_frame, is_processing, current_counter, current_visualizer
    global video_capture, session_data, video_writer, is_recording
    
    counter_type = session_data.get('counter_type', 'mediapipe')
    video_source = session_data.get('video_source', '0')
    
    # Get original video properties
    source_fps = video_capture.get(cv2.CAP_PROP_FPS) if video_capture else 30.0
    
    # Adaptive frame rate based on source type
    if video_source.isdigit():
        # Camera: Use stable 25 FPS for real-time processing
        target_fps = 25.0
    else:
        # Uploaded video: Use original FPS but clamp to reasonable range
        target_fps = max(15.0, min(60.0, source_fps))  # Clamp between 15-60 FPS
    
    frame_delay = 1.0 / target_fps
    
    print(f"🎥 Video processing: Source FPS={source_fps:.1f}, Target FPS={target_fps:.1f}")
    
    # Frame timing and stabilization
    last_frame_time = time.time()
    frame_skip_count = 0  # Track skipped frames for uploaded videos
    
    while is_processing and video_capture and video_capture.isOpened():
        frame_start_time = time.time()
        
        ret, frame = video_capture.read()
        if not ret:
            if not session_data.get('video_source', '0').isdigit():
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break
        
        # Store original frame for processing
        original_frame = frame.copy()
        
        # For uploaded videos with high FPS, occasionally skip processing but still advance
        current_time = time.time()
        elapsed_since_last = current_time - last_frame_time
        
        # Skip frame processing if we're running behind (but always process every 3rd frame minimum)
        should_process = True
        if not video_source.isdigit() and elapsed_since_last < frame_delay * 0.8:
            frame_skip_count += 1
            if frame_skip_count < 3:  # Skip max 2 frames, then force process
                should_process = False
            else:
                frame_skip_count = 0  # Reset counter
        else:
            frame_skip_count = 0
        
        if should_process:
            # Create consistent display frame (640px max width)
            display_frame = frame.copy()
            target_width = 640
            if frame.shape[1] > target_width:
                scale = target_width / frame.shape[1]
                new_width = target_width
                new_height = int(frame.shape[0] * scale)
                display_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if counter_type == 'mediapipe' and current_counter:
                frame_rgb = cv2.cvtColor(original_frame, cv2.COLOR_BGR2RGB)
                results = pose.process(frame_rgb)
                
                if results.pose_landmarks:
                    # Scale landmarks for display frame
                    scale_x = display_frame.shape[1] / original_frame.shape[1]
                    scale_y = display_frame.shape[0] / original_frame.shape[0]
                    
                    # Create scaled landmarks for display
                    scaled_landmarks = results.pose_landmarks
                    mp_drawing.draw_landmarks(display_frame, scaled_landmarks, mp_pose.POSE_CONNECTIONS)
                    
                    old_count = current_counter.count
                    count = current_counter.update(results.pose_landmarks)
                    
                    if count > old_count:
                        session_data['counts'].append({
                            'count': count,
                            'timestamp': datetime.now().isoformat(),
                            'validation_score': getattr(current_counter, 'validation_score', 1.0)
                        })
                    
                    session_data['current_count'] = count
                    display_frame = add_overlay_to_frame(display_frame, count, session_data["counter_name"], timestamp)
                    
                    if current_visualizer:
                        current_visualizer.draw_debug_info(display_frame, current_counter, results.pose_landmarks)
            
            elif counter_type == 'yolo' and current_counter:
                old_count = current_counter.count
                count = current_counter.update(original_frame)  # Process on original frame
                
                if count > old_count:
                    session_data['counts'].append({
                        'count': count,
                        'timestamp': datetime.now().isoformat(),
                        'confidence': getattr(current_counter.debug_info, 'confidence', 0.0)
                    })
                
                session_data['current_count'] = count
                
                # Always draw debug info - even when no objects detected
                # This is essential for setup, calibration, and debugging
                
                # Calculate scale factors for display frame
                scale_x = display_frame.shape[1] / original_frame.shape[1]
                scale_y = display_frame.shape[0] / original_frame.shape[0]
                
                # Create a temporary counter for display with scaled coordinates
                display_counter = current_counter.__class__()
                display_counter.calibrated = current_counter.calibrated
                display_counter.count = current_counter.count
                display_counter.state = current_counter.state
                display_counter.debug_info = current_counter.debug_info.copy() if hasattr(current_counter, 'debug_info') else {}
                
                # Copy essential attributes for proper display
                display_counter.object_class = getattr(current_counter, 'object_class', 'unknown')
                display_counter.logic_type = getattr(current_counter, 'logic_type', 'unknown')
                display_counter.stable_frames = getattr(current_counter, 'stable_frames', 10)
                display_counter.stable_count = getattr(current_counter, 'stable_count', 0)
                
                # Copy calibration-related attributes  
                if hasattr(current_counter, 'body_height'):
                    display_counter.body_height = current_counter.body_height
                if hasattr(current_counter, 'jump_threshold_px'):
                    display_counter.jump_threshold_px = current_counter.jump_threshold_px
                if hasattr(current_counter, 'sensitivity_multiplier'):
                    display_counter.sensitivity_multiplier = current_counter.sensitivity_multiplier
                if hasattr(current_counter, 'position_history'):
                    display_counter.position_history = current_counter.position_history.copy()
                
                # Copy methods that might be called by draw_debug_info
                if hasattr(current_counter, 'get_current_dead_zone'):
                    display_counter.get_current_dead_zone = current_counter.get_current_dead_zone
                
                # Scale all threshold positions for display
                if hasattr(current_counter, 'start_position') and current_counter.start_position:
                    display_counter.start_position = current_counter.start_position * scale_y
                if hasattr(current_counter, 'center_reference') and current_counter.center_reference:
                    display_counter.center_reference = current_counter.center_reference * scale_y
                if hasattr(current_counter, 'up_threshold') and current_counter.up_threshold:
                    display_counter.up_threshold = current_counter.up_threshold * scale_y
                if hasattr(current_counter, 'down_threshold') and current_counter.down_threshold:
                    display_counter.down_threshold = current_counter.down_threshold * scale_y
                
                # Get detection for current frame
                detections = current_counter.tracker.detect_objects(original_frame)
                best_detection = current_counter.tracker.get_best_detection(detections)
                
                # Scale detection coordinates if object is detected
                scaled_detection = None
                if best_detection:
                    scaled_detection = {
                        'bbox': [
                            best_detection['bbox'][0] * scale_x,
                            best_detection['bbox'][1] * scale_y,
                            best_detection['bbox'][2] * scale_x,
                            best_detection['bbox'][3] * scale_y
                        ],
                        'confidence': best_detection['confidence'],
                        'class': best_detection['class']
                    }
                
                # Always draw debug info (lines, thresholds, status) regardless of detection
                display_frame = display_counter.draw_debug_info(display_frame, scaled_detection)
                
                display_frame = add_overlay_to_frame(display_frame, count, session_data["counter_name"], timestamp)
            
            # Store display frame for streaming and recording
            with frame_lock:
                current_frame = display_frame.copy()
            
            # Record at stable frame rate (always 25fps for recording consistency)
            if is_recording and video_writer and recording_dimensions:
                try:
                    target_width, target_height = recording_dimensions
                    
                    # Ensure frame dimensions match recording dimensions
                    if display_frame.shape[:2] != (target_height, target_width):
                        # Resize if needed (height, width for OpenCV)
                        recording_frame = cv2.resize(display_frame, (target_width, target_height))
                    else:
                        recording_frame = display_frame.copy()
                    
                    # Write frame and track success
                    success = video_writer.write(recording_frame)
                    
                    # Track frame count
                    if not hasattr(video_writer, 'frame_count'):
                        video_writer.frame_count = 0
                    video_writer.frame_count += 1
                    
                    # Debug: Print every 25 frames (1 second at 25fps) 
                    if video_writer.frame_count % 25 == 0:
                        print(f"🎬 Recorded {video_writer.frame_count} frames (success: {success})")
                        print(f"   Frame shape: {recording_frame.shape}, Target: {target_width}x{target_height}")
                        
                except Exception as e:
                    print(f"❌ Recording frame error: {e}")
                    print(f"   Display frame shape: {display_frame.shape}")
                    print(f"   Target dimensions: {recording_dimensions}")
                    print(f"   Video writer valid: {video_writer and video_writer.isOpened()}")
            
            last_frame_time = current_time
        
        # Adaptive frame timing control
        elapsed = time.time() - frame_start_time
        
        # For uploaded videos, respect original timing more closely
        if video_source.isdigit():
            # Camera: Use consistent timing
            sleep_time = max(0, frame_delay - elapsed)
        else:
            # Uploaded video: More flexible timing, avoid falling behind
            target_sleep = frame_delay - elapsed
            sleep_time = max(0, min(target_sleep, frame_delay * 0.5))  # Cap sleep to prevent slowdown
        
        if sleep_time > 0:
            time.sleep(sleep_time)

def generate_frames():
    """生成视频帧"""
    global current_frame
    
    # Get adaptive frame rate based on current video source
    video_source = session_data.get('video_source', '0')
    if video_source.isdigit():
        # Camera: Use stable frame rate
        target_fps = 25.0
    else:
        # Uploaded video: Try to match processing speed
        source_fps = video_capture.get(cv2.CAP_PROP_FPS) if video_capture else 30.0
        target_fps = max(15.0, min(60.0, source_fps))
    
    frame_delay = 1.0 / target_fps
    
    while True:
        frame_start_time = time.time()
        
        with frame_lock:
            if current_frame is not None:
                # Use higher quality encoding for web streaming
                ret, buffer = cv2.imencode('.jpg', current_frame, [
                    cv2.IMWRITE_JPEG_QUALITY, 90,  # Higher quality
                    cv2.IMWRITE_JPEG_OPTIMIZE, 1   # Optimize for web
                ])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        elapsed = time.time() - frame_start_time
        sleep_time = max(0, frame_delay - elapsed)
        time.sleep(sleep_time)

def list_counters_by_category():
    """按类别列出计数器"""
    categorized = {'Human': [], 'Animal': [], 'Object': []}
    
    for counter_name in list_counters():
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
                    'has_center_line': hasattr(temp_counter, 'adjust_center_line') or hasattr(temp_counter, 'start_position')
                }
                
                if counter_type == 'yolo':
                    category = 'Animal' if counter_info['object_class'] in ['cat', 'dog', 'bird', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe'] else 'Object'
                else:
                    category = 'Human'
                
                categorized[category].append(counter_info)
        except:
            pass
    
    return categorized

@app.route('/')
def index():
    return render_template('index.html', counters=list_counters_by_category())

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_counter', methods=['POST'])
def start_counter():
    global current_counter, current_visualizer, video_capture, is_processing, processing_thread, session_data
    
    try:
        data = request.get_json()
        counter_name = data['counter']
        video_source = data.get('video_source', '0')
        parameters = data.get('parameters', {})
        
        stop_counter()
        
        CounterClass = get_counter(counter_name)
        if not CounterClass:
            return jsonify({'error': f'计数器 {counter_name} 未找到'}), 400
        
        current_counter = CounterClass()
        counter_type = get_counter_type(current_counter)
        
        # 初始化检测系统
        if counter_type == 'mediapipe':
            if mp_pose is None:
                initialize_mediapipe()
            current_visualizer = Visualizer(counter_name)
        else:
            current_visualizer = None
        
        # 应用参数
        for param, value in parameters.items():
            if hasattr(current_counter, param):
                if param in ['threshold', 'validation_threshold', 'min_visibility', 'confidence_threshold']:
                    value = float(value)
                elif param in ['stable_frames', 'calibration_frames']:
                    value = int(value)
                elif param == 'enable_anti_cheat':
                    value = bool(value)
                setattr(current_counter, param, value)
        
        # 初始化视频
        if video_source.isdigit():
            # 摄像头
            video_capture = cv2.VideoCapture(int(video_source))
        else:
            # 视频文件 - 确保使用绝对路径
            if not os.path.isabs(video_source):
                # 如果是相对路径，检查是否在uploads文件夹中
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(video_source))
                if os.path.exists(upload_path):
                    video_source = os.path.abspath(upload_path)
                else:
                    video_source = os.path.abspath(video_source)
            video_capture = cv2.VideoCapture(video_source)
            
        if not video_capture.isOpened():
            return jsonify({'error': f'无法打开视频源: {video_source}'}), 400
        
        # 重置会话数据
        session_data = {
            'counts': [],
            'start_time': datetime.now().isoformat(),
            'current_count': 0,
            'counter_name': counter_name,
            'counter_type': counter_type,
            'video_source': video_source,
            'parameters': parameters
        }
        
        # 启动处理线程
        is_processing = True
        processing_thread = threading.Thread(target=process_video_stream)
        processing_thread.daemon = True
        processing_thread.start()
        
        return jsonify({'success': True, 'message': f'Started {counter_name} ({counter_type})', 'counter_type': counter_type})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_counter', methods=['POST'])
def stop_counter():
    global is_processing, video_capture, processing_thread, current_frame, video_writer, is_recording
    
    is_processing = False
    
    if is_recording and video_writer:
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
    try:
        CounterClass = get_counter(counter_name)
        if not CounterClass:
            return jsonify({'error': '计数器未找到'}), 404
        
        counter = CounterClass()
        counter_type = get_counter_type(counter)
        
        info = {
            'name': counter_name,
            'type': counter_type,
            'parameters': {}
        }
        
        # 通用参数
        for param in ['threshold', 'stable_frames', 'min_visibility', 'validation_threshold', 'enable_anti_cheat', 'confidence_threshold', 'calibration_frames']:
            if hasattr(counter, param):
                value = getattr(counter, param)
                param_type = 'bool' if isinstance(value, bool) else ('int' if isinstance(value, int) else 'float')
                info['parameters'][param] = {'type': param_type, 'default': value, 'description': f'{param.replace("_", " ").title()}'}
        
        if counter_type == 'yolo':
            info['object_class'] = getattr(counter, 'object_class', 'unknown')
            info['logic_type'] = getattr(counter, 'logic_type', 'unknown')
            info['description'] = f"{counter.object_class} {counter.logic_type} detection using YOLO"
        else:
            info['description'] = f"Human {getattr(counter, 'logic_type', 'action')} detection using MediaPipe"
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_session_data')
def get_session_data():
    return jsonify(session_data)

@app.route('/save_session', methods=['POST'])
def save_session():
    try:
        filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(f"sessions/{filename}", 'w') as f:
            json.dump(session_data, f, indent=2)
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload_video', methods=['POST'])
def upload_video():
    try:
        if 'video_file' not in request.files:
            return jsonify({'error': '未选择文件'}), 400
        
        file = request.files['video_file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'error': '文件类型无效'}), 400
        
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        return jsonify({'success': True, 'filename': filename, 'filepath': filepath, 'message': f'视频上传成功: {filename}'})
        
    except Exception as e:
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

@app.route('/list_uploaded_videos')
def list_uploaded_videos():
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
        
        videos.sort(key=lambda x: os.path.getmtime(x['filepath']), reverse=True)
        return jsonify({'videos': videos})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def adjust_counter_property(property_name, value_func):
    """通用属性调整函数"""
    global current_counter
    try:
        if not current_counter:
            return jsonify({'error': 'No active counter'}), 400
        
        result = value_func(current_counter)
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify({'error': result.get('error', 'Adjustment failed')}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_center_line', methods=['POST'])
def adjust_center_line():
    data = request.get_json()
    adjustment = data.get('adjustment', 0)
    
    def adjust_func(counter):
        if hasattr(counter, 'adjust_center_line'):
            direction = 'down' if adjustment > 0 else 'up'
            amount = abs(adjustment * 200)  # Increased from 20 to 200 for more visible changes (10px per 0.05 adjustment)
            
            # Log before adjustment - handle both center_reference and start_position
            before_center_ref = getattr(counter, 'center_reference', None)
            before_start_pos = getattr(counter, 'start_position', None)
            print(f"🔧 Before adjustment: center_reference={before_center_ref}, start_position={before_start_pos}")
            
            counter.adjust_center_line(direction, amount)
            
            # Log after adjustment and get the updated center line value
            # SportsBallCounter uses start_position, Animal counters use center_reference
            if hasattr(counter, 'center_reference') and counter.center_reference is not None:
                current_line = counter.center_reference
                print(f"🔧 After adjustment: center_reference={current_line}")
            elif hasattr(counter, 'start_position') and counter.start_position is not None:
                current_line = counter.start_position
                print(f"🔧 After adjustment: start_position={current_line}")
            else:
                current_line = 0
                print(f"🔧 After adjustment: no valid center line found, using 0")
            
            # Force frame refresh by clearing current frame cache
            global current_frame
            with frame_lock:
                if current_frame is not None:
                    current_frame = None  # This will force the next frame to be processed fresh
                
            return {'success': True, 'new_center_line': current_line, 'message': f'Center line adjusted {direction} to {current_line:.1f}'}
        return {'error': 'Counter does not support center line adjustment'}
    
    return adjust_counter_property('center_line', adjust_func)

@app.route('/reset_calibration', methods=['POST'])
def reset_calibration():
    def reset_func(counter):
        if hasattr(counter, 'reset_to_auto_calibration'):
            counter.reset_to_auto_calibration()
            return {'success': True, 'message': 'Calibration reset successfully'}
        elif hasattr(counter, 'calibrated'):
            # Full reset for counters that don't have reset_to_auto_calibration
            counter.calibrated = False
            counter.position_history = []
            counter.state = "start"
            counter.stable_count = 0
            counter.count = 0  # Also reset count
            
            # Reset position references
            if hasattr(counter, 'start_position'):
                counter.start_position = None
            if hasattr(counter, 'center_reference'):
                counter.center_reference = None
            if hasattr(counter, 'up_threshold'):
                counter.up_threshold = None
            if hasattr(counter, 'down_threshold'):
                counter.down_threshold = None
            
            # Reset sensitivity multiplier if it exists
            if hasattr(counter, 'sensitivity_multiplier'):
                counter.sensitivity_multiplier = 1.0
            
            # Force frame refresh
            global current_frame
            with frame_lock:
                if current_frame is not None:
                    current_frame = None
            
            return {'success': True, 'message': 'Counter reset - will recalibrate automatically'}
        return {'error': 'Counter does not support calibration reset'}
    
    return adjust_counter_property('calibration', reset_func)

@app.route('/adjust_sensitivity', methods=['POST'])
def adjust_sensitivity():
    data = request.get_json()
    direction = data.get('direction', 'increase')
    
    def adjust_func(counter):
        if hasattr(counter, 'adjust_sensitivity'):
            counter.adjust_sensitivity(direction, 0.1)
            return {'success': True, 'message': f'Sensitivity {direction}d for {getattr(counter, "object_class", "counter")} detection'}
        return {'error': 'Counter does not support sensitivity adjustment'}
    
    return adjust_counter_property('sensitivity', adjust_func)

@app.route('/adjust_sensitivity_absolute', methods=['POST'])
def adjust_sensitivity_absolute():
    data = request.get_json()
    value = data.get('value', 1.0)
    
    def adjust_func(counter):
        counter.sensitivity_multiplier = float(value)
        if hasattr(counter, '_recalculate_thresholds'):
            counter._recalculate_thresholds()
        return {'success': True, 'message': f'Sensitivity set to {value:.1f} for {getattr(counter, "object_class", "counter")} detection'}
    
    return adjust_counter_property('sensitivity_absolute', adjust_func)

@app.route('/adjust_center_line_absolute', methods=['POST'])
def adjust_center_line_absolute():
    data = request.get_json()
    position = data.get('position', 500)
    
    def adjust_func(counter):
        # Log before adjustment for debugging
        before_center_ref = getattr(counter, 'center_reference', None)
        before_start_pos = getattr(counter, 'start_position', None)
        print(f"🎚️ Slider adjustment: setting position to {position}")
        print(f"   Before: center_reference={before_center_ref}, start_position={before_start_pos}")
        
        # Handle different counter types
        if hasattr(counter, 'center_reference'):
            # Animal counters (CatCounter, DogCounter) use center_reference
            counter.center_reference = float(position)
            
            # Recalculate thresholds for Animal counters
            if hasattr(counter, 'jump_threshold_px') and counter.jump_threshold_px:
                margin = 50
                if hasattr(counter, 'original_frame_size') and counter.original_frame_size:
                    video_height = counter.original_frame_size[1]
                else:
                    video_height = 1080
                
                detection_range = counter.jump_threshold_px
                counter.up_threshold = max(counter.center_reference - detection_range * 0.5, margin)
                counter.down_threshold = min(counter.center_reference + detection_range * 2.0, video_height - margin)
                
                print(f"   Recalculated thresholds: up={counter.up_threshold:.1f}, down={counter.down_threshold:.1f}")
            
            current_line = counter.center_reference
            
        elif hasattr(counter, 'start_position'):
            # Object counters (SportsBallCounter) use start_position as ground reference
            counter.start_position = float(position)
            current_line = counter.start_position
            
            # Recalculate thresholds for Object counters
            if hasattr(counter, '_recalculate_thresholds'):
                counter._recalculate_thresholds()
            
        else:
            return {'error': 'Counter does not support absolute positioning'}
        
        # Generic threshold recalculation if available
        if hasattr(counter, '_recalculate_thresholds'):
            counter._recalculate_thresholds()
        
        # Force frame refresh
        global current_frame
        with frame_lock:
            if current_frame is not None:
                current_frame = None
        
        print(f"   After: center_reference={getattr(counter, 'center_reference', None)}, start_position={getattr(counter, 'start_position', None)}")
        return {'success': True, 'new_center_line': current_line, 'message': f'Position set to {current_line:.1f}px'}
    
    return adjust_counter_property('center_line_absolute', adjust_func)

@app.route('/adjust_parameter', methods=['POST'])
def adjust_parameter():
    data = request.get_json()
    param_name = data.get('parameter')
    param_value = data.get('value')
    
    def adjust_func(counter):
        if not param_name or param_value is None:
            return {'error': 'Parameter name and value required'}
        
        if not hasattr(counter, param_name):
            return {'error': f'Parameter {param_name} not supported by this counter'}
        
        # 类型转换
        if param_name in ['stable_frames', 'calibration_frames']:
            param_value_converted = int(param_value)
        elif param_name == 'enable_anti_cheat':
            param_value_converted = bool(param_value)
        else:
            param_value_converted = float(param_value)
        
        old_value = getattr(counter, param_name)
        setattr(counter, param_name, param_value_converted)
        
        # 特殊处理
        if param_name == 'confidence_threshold' and hasattr(counter, 'tracker'):
            counter.tracker.confidence_threshold = param_value_converted
        
        if hasattr(counter, '_recalculate_thresholds'):
            counter._recalculate_thresholds()
        
        return {'success': True, 'message': f'{param_name.replace("_", " ").title()} adjusted from {old_value} to {param_value_converted}', 'old_value': old_value, 'new_value': param_value_converted}
    
    return adjust_counter_property('parameter', adjust_func)

@app.route('/update_parameter', methods=['POST'])
def update_parameter():
    """实时更新计数器参数"""
    global current_counter
    
    try:
        if not current_counter:
            return jsonify({'error': '没有活动的计数器'}), 400
        
        data = request.get_json()
        param_name = data.get('parameter')
        param_value = data.get('value')
        
        if not param_name or param_value is None:
            return jsonify({'error': '需要参数名称和值'}), 400
        
        if not hasattr(current_counter, param_name):
            return jsonify({'error': f'参数 {param_name} 不被此计数器支持'}), 400
        
        # 类型转换
        if param_name in ['stable_frames', 'calibration_frames']:
            param_value_converted = int(param_value)
        elif param_name == 'enable_anti_cheat':
            param_value_converted = bool(param_value)
        else:
            param_value_converted = float(param_value)
        
        old_value = getattr(current_counter, param_name)
        setattr(current_counter, param_name, param_value_converted)
        
        # 特殊处理
        if param_name == 'confidence_threshold' and hasattr(current_counter, 'tracker'):
            current_counter.tracker.confidence_threshold = param_value_converted
        
        if hasattr(current_counter, '_recalculate_thresholds'):
            current_counter._recalculate_thresholds()
        
        return jsonify({
            'success': True, 
            'message': f'{param_name.replace("_", " ").title()} 已从 {old_value} 调整为 {param_value_converted}',
            'old_value': old_value,
            'new_value': param_value_converted
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_recording', methods=['POST'])
def start_recording():
    global video_writer, is_recording, recording_filename, recording_start_time, recording_dimensions
    
    try:
        if not is_processing:
            return jsonify({'error': 'No active counter session to record'}), 400
        
        if is_recording:
            return jsonify({'error': 'Recording already in progress'}), 400
        
        os.makedirs('recordings', exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        counter_name = session_data.get('counter_name', 'unknown').replace(' ', '_')
        recording_filename = f"recordings/recording_{counter_name}_{timestamp}.mp4"
        
        # Get display frame dimensions (what user sees on website)
        original_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)) if video_capture else 640
        original_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) if video_capture else 480
        
        # Calculate display dimensions (same logic as in process_video_stream)
        target_width = 640
        if original_width > target_width:
            scale = target_width / original_width
            display_width = target_width
            display_height = int(original_height * scale)
        else:
            display_width = original_width
            display_height = original_height
        
        # Use standardized frame rate for smooth playback
        recording_fps = 25.0  # Fixed frame rate for consistent playback
        
        # Ensure dimensions are valid
        if display_width <= 0 or display_height <= 0:
            display_width, display_height = 640, 480
        
        # Ensure dimensions are even numbers (required for most codecs)
        display_width = display_width + (display_width % 2)
        display_height = display_height + (display_height % 2)
        
        # Store dimensions globally for frame writing
        recording_dimensions = (display_width, display_height)
        
        # Try multiple codecs for better compatibility
        codecs_to_try = [
            ('mp4v', 'MP4V'),  # Most compatible
            ('XVID', 'XVID'),  # Widely supported
            ('MJPG', 'MJPG'),  # Motion JPEG - always works
        ]
        
        video_writer = None
        used_codec = None
        
        for fourcc_str, codec_name in codecs_to_try:
            try:
                fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                temp_writer = cv2.VideoWriter(recording_filename, fourcc, recording_fps, recording_dimensions)
                
                if temp_writer.isOpened():
                    video_writer = temp_writer
                    used_codec = codec_name
                    print(f"✅ Video writer initialized with {codec_name} codec")
                    break
                else:
                    temp_writer.release()
                    print(f"❌ Failed to initialize with {codec_name} codec")
            except Exception as e:
                print(f"❌ Error with {codec_name} codec: {e}")
        
        if not video_writer or not video_writer.isOpened():
            return jsonify({'error': 'Failed to initialize video writer with any codec. Check OpenCV installation.'}), 500
        
        is_recording = True
        recording_start_time = time.time()
        
        print(f"🎬 Recording started:")
        print(f"   File: {recording_filename}")
        print(f"   Dimensions: {display_width}x{display_height}")
        print(f"   FPS: {recording_fps}")
        print(f"   Codec: {used_codec}")
        
        return jsonify({
            'success': True, 
            'message': f'Recording started at {recording_fps:.1f} FPS ({display_width}x{display_height}) - {used_codec} codec',
            'filename': recording_filename,
            'fps': recording_fps,
            'width': display_width,
            'height': display_height,
            'codec': used_codec,
            'note': 'Recording with compatible codec for smooth playback'
        })
        
    except Exception as e:
        print(f"❌ Recording start error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    global video_writer, is_recording, recording_filename, recording_start_time, recording_dimensions
    
    try:
        if not is_recording:
            return jsonify({'error': 'No recording in progress'}), 400
        
        is_recording = False
        final_frame_count = 0
        
        # Ensure video writer is properly closed
        if video_writer:
            try:
                final_frame_count = getattr(video_writer, 'frame_count', 0)
                video_writer.release()
                print(f"🎬 Video writer released. Total frames written: {final_frame_count}")
            except Exception as e:
                print(f"❌ Error releasing video writer: {e}")
            finally:
                video_writer = None
        
        # Reset recording dimensions
        recording_dimensions = None
        
        # Check if file was actually created and has content
        file_size = 0
        if recording_filename and os.path.exists(recording_filename):
            file_size = os.path.getsize(recording_filename)
            print(f"📹 Recording file size: {file_size} bytes ({final_frame_count} frames)")
            
            if file_size == 0:
                print("⚠️  Warning: Recording file is empty (0 bytes)")
            elif final_frame_count == 0:
                print("⚠️  Warning: No frames were written to the recording file")
        else:
            print(f"❌ Recording file not found: {recording_filename}")
        
        duration = round(time.time() - recording_start_time, 2) if recording_start_time else None
        
        return jsonify({
            'success': True, 
            'message': 'Recording stopped',
            'filename': os.path.basename(recording_filename) if recording_filename else 'unknown',
            'duration': duration,
            'file_size': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2) if file_size > 0 else 0,
            'frame_count': final_frame_count
        })
        
    except Exception as e:
        print(f"❌ Recording stop error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download_latest_recording')
def download_latest_recording():
    try:
        if not recording_filename or not os.path.exists(recording_filename):
            return jsonify({'error': 'No recording available for download'}), 404
        
        filename = os.path.basename(recording_filename)
        return send_file(recording_filename, as_attachment=True, download_name=filename)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_center_line_position')
def get_center_line_position():
    """Get current center line position for slider updates"""
    global current_counter
    try:
        if not current_counter:
            return jsonify({'error': 'No active counter'}), 400
        
        # Get the current center line position - handle both counter types
        if hasattr(current_counter, 'center_reference') and current_counter.center_reference is not None:
            position = current_counter.center_reference
        elif hasattr(current_counter, 'start_position') and current_counter.start_position is not None:
            position = current_counter.start_position
        else:
            return jsonify({'error': 'Counter does not have center line position'}), 400
        
        return jsonify({
            'success': True,
            'position': position,
            'calibrated': getattr(current_counter, 'calibrated', False)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # 创建必要目录
    for folder in ['sessions', 'uploads', 'recordings']:
        os.makedirs(folder, exist_ok=True)
    
    print("🏋️ 多计数器网页界面启动中...")
    print("📱 访问地址: http://localhost:5000")
    
    try:
        app.config['PROPAGATE_EXCEPTIONS'] = False
        app.run(debug=False, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n⏹️ 网页界面被用户停止。")
    except Exception as e:
        print(f"❌ 启动网页界面时出错: {e}")
        input("按回车键退出...") 
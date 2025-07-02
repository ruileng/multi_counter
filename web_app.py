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
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB最大文件大小
app.config['UPLOAD_FOLDER'] = 'uploads'

# 允许的视频文件扩展名
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'm4v'}

def allowed_file(filename):
    """检查文件扩展名是否被允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_counter_type(counter):
    """根据计数器属性确定计数器类型"""
    if hasattr(counter, 'detection_type'):
        if counter.detection_type == 'yolo':
            return 'yolo'
        elif counter.detection_type == 'mediapipe':
            return 'mediapipe'
    
    # 后备：检查是否有YOLO特定属性
    if hasattr(counter, 'object_class') and hasattr(counter, 'tracker'):
        return 'yolo'
    
    # 默认为人体动作计数器使用mediapipe
    return 'mediapipe'

# 视频处理的全局变量
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

# 视频录制变量
video_writer = None
is_recording = False
recording_filename = None
recording_start_time = None
recorded_frames = 0

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
    """初始化MediaPipe姿态检测"""
    global mp_pose, pose, mp_drawing
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    mp_drawing = mp.solutions.drawing_utils

def process_video_stream():
    """在后台线程中处理视频流 - 支持MediaPipe和YOLO"""
    global current_frame, is_processing, current_counter, current_visualizer
    global video_capture, session_data, video_writer, is_recording, recorded_frames
    
    counter_type = session_data.get('counter_type', 'mediapipe')
    
    # 获取视频FPS以获得适当的时序
    video_fps = 30  # 默认FPS
    if video_capture:
        video_fps = video_capture.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0 or video_fps > 60:
            video_fps = 30  # 回退到30 FPS
    
    # 计算适当的帧延迟
    frame_delay = 1.0 / video_fps  # 每帧秒数
    
    while is_processing and video_capture and video_capture.isOpened():
        frame_start_time = time.time()
        
        ret, frame = video_capture.read()
        if not ret:
            if session_data.get('video_source', '0').isdigit():
                # 相机断开连接
                break
            else:
                # 视频结束，重新开始
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
        # 保持原始帧用于录制（全分辨率）
        recording_frame = frame.copy()
        
        # 仅为网页显示调整帧大小
        if frame.shape[1] > 640:
            scale = 640 / frame.shape[1]
            frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
        
        if counter_type == 'mediapipe':
            # 使用MediaPipe处理人体动作计数器
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(frame_rgb)
            
            if results.pose_landmarks and current_counter:
                # 在网页显示帧上绘制姿态关键点
                mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                
                # 更新计数器
                old_count = current_counter.count
                count = current_counter.update(results.pose_landmarks)
                
                # 记录计数变化
                if count > old_count:
                    session_data['counts'].append({
                        'count': count,
                        'timestamp': datetime.now().isoformat(),
                        'validation_score': getattr(current_counter, 'validation_score', 1.0)
                    })
                
                session_data['current_count'] = count
                
                # 在网页帧上显示计数器信息
                cv2.putText(frame, f'{session_data["counter_name"]}: {count}', 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # 为网页显示添加时间戳
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # 在网页帧上绘制调试信息
                if current_visualizer:
                    current_visualizer.draw_debug_info(frame, current_counter, results.pose_landmarks)
                
                # 用于录制：在原始分辨率帧上绘制覆盖层
                if is_recording and video_writer is not None:
                    # 将关键点缩放到原始帧大小
                    scale_x = recording_frame.shape[1] / frame.shape[1]
                    scale_y = recording_frame.shape[0] / frame.shape[0]
                    
                    # 在录制帧上绘制姿态关键点
                    mp_drawing.draw_landmarks(recording_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                    
                    # 将计数器信息添加到录制帧（缩放）
                    cv2.putText(recording_frame, f'{session_data["counter_name"]}: {count}', 
                               (int(10 * scale_x), int(30 * scale_y)), cv2.FONT_HERSHEY_SIMPLEX, 
                               1 * min(scale_x, scale_y), (0, 255, 0), 2)
                    
                    # 将时间戳添加到录制帧
                    cv2.putText(recording_frame, timestamp, 
                               (int(10 * scale_x), recording_frame.shape[0] - int(10 * scale_y)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5 * min(scale_x, scale_y), (255, 255, 255), 1)
        
        elif counter_type == 'yolo':
            # 使用YOLO处理动物/物体计数器
            if current_counter:
                # 用网页显示帧更新计数器
                old_count = current_counter.count
                count = current_counter.update(frame)
                
                # 记录计数变化
                if count > old_count:
                    session_data['counts'].append({
                        'count': count,
                        'timestamp': datetime.now().isoformat(),
                        'confidence': getattr(current_counter.debug_info, 'confidence', 0.0)
                    })
                
                session_data['current_count'] = count
                
                # 获取用于显示的检测
                detections = current_counter.tracker.detect_objects(frame)
                best_detection = current_counter.tracker.get_best_detection(detections)
                
                # 在网页帧上用YOLO检测绘制调试信息
                frame = current_counter.draw_debug_info(frame, best_detection)
                
                # 为网页显示添加时间戳
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cv2.putText(frame, timestamp, (10, frame.shape[0] - 10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # 用于录制：处理并在原始分辨率帧上绘制
                if is_recording and video_writer is not None:
                    # 用原始帧更新计数器以获得适当的检测
                    recording_detections = current_counter.tracker.detect_objects(recording_frame)
                    recording_detection = current_counter.tracker.get_best_detection(recording_detections)
                    
                    # 在录制帧上绘制调试信息（全分辨率）
                    recording_frame = current_counter.draw_debug_info(recording_frame, recording_detection)
                    
                    # 将时间戳添加到录制帧
                    cv2.putText(recording_frame, timestamp, (10, recording_frame.shape[0] - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # 如果录制处于活动状态，则录制视频（使用带覆盖层的原始帧）
        if is_recording and video_writer is not None:
            try:
                video_writer.write(recording_frame)
                recorded_frames += 1
            except Exception:
                # 静默处理录制错误
                pass
        
        # 存储网页显示帧用于流式传输
        with frame_lock:
            current_frame = frame.copy()
        
        # 保持适当的帧率时序
        frame_process_time = time.time() - frame_start_time
        sleep_time = max(0, frame_delay - frame_process_time)
        time.sleep(sleep_time)

def generate_frames():
    """为视频流生成帧"""
    global current_frame
    
    # 网页流式传输的目标帧率
    target_fps = 25  # 略低于源以获得稳定的网页流式传输
    frame_delay = 1.0 / target_fps
    
    while True:
        frame_start_time = time.time()
        
        with frame_lock:
            if current_frame is not None:
                # 将帧编码为JPEG
                ret, buffer = cv2.imencode('.jpg', current_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # 为网页流式传输保持一致的帧率
        frame_process_time = time.time() - frame_start_time
        sleep_time = max(0, frame_delay - frame_process_time)
        time.sleep(sleep_time)

def list_counters_by_category():
    """返回按类别组织的计数器。"""
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
            # 静默跳过有问题的计数器
            pass
    
    return categorized

@app.route('/')
def index():
    """主页"""
    categorized_counters = list_counters_by_category()
    return render_template('index.html', counters=categorized_counters)

@app.route('/video_feed')
def video_feed():
    """视频流路由"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_counter', methods=['POST'])
def start_counter():
    """使用所选参数启动计数器 - 支持所有计数器类型"""
    global current_counter, current_visualizer, video_capture, is_processing
    global processing_thread, session_data
    
    try:
        data = request.get_json()
        counter_name = data['counter']
        video_source = data.get('video_source', '0')
        parameters = data.get('parameters', {})
        
        # 停止现有处理
        stop_counter()
        
        # 获取计数器类并创建实例
        CounterClass = get_counter(counter_name)
        if not CounterClass:
            return jsonify({'error': f'计数器 {counter_name} 未找到'}), 400
        
        current_counter = CounterClass()
        counter_type = get_counter_type(current_counter)
        
        # 初始化适当的检测系统
        if counter_type == 'mediapipe':
            # 为人体动作计数器初始化MediaPipe
            if mp_pose is None:
                initialize_mediapipe()
            current_visualizer = Visualizer(counter_name)
        elif counter_type == 'yolo':
            # YOLO计数器有自己的可视化
            current_visualizer = None
        
        # 应用自定义参数
        for param, value in parameters.items():
            if hasattr(current_counter, param):
                # 将字符串值转换为适当类型
                if param in ['threshold', 'validation_threshold', 'min_visibility', 'confidence_threshold']:
                    value = float(value)
                elif param in ['stable_frames', 'calibration_frames']:
                    value = int(value)
                elif param in ['enable_anti_cheat']:
                    value = bool(value)
                
                setattr(current_counter, param, value)
        
        # 初始化视频捕获
        if video_source.isdigit():
            video_capture = cv2.VideoCapture(int(video_source))
        else:
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
        
        return jsonify({
            'success': True, 
            'message': f'已启动 {counter_name} ({counter_type})',
            'counter_type': counter_type
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_counter', methods=['POST'])
def stop_counter():
    """停止计数器处理"""
    global is_processing, video_capture, processing_thread, current_frame
    global video_writer, is_recording, recording_filename
    
    is_processing = False
    
    # 如果录制处于活动状态，则停止录制
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
    """获取特定计数器的详细信息"""
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
        if hasattr(counter, 'threshold'):
            info['parameters']['threshold'] = {'type': 'float', 'default': counter.threshold, 'description': '运动检测阈值'}
        if hasattr(counter, 'stable_frames'):
            info['parameters']['stable_frames'] = {'type': 'int', 'default': counter.stable_frames, 'description': '稳定检测的帧数'}
        
        # MediaPipe特定参数
        if counter_type == 'mediapipe':
            if hasattr(counter, 'min_visibility'):
                info['parameters']['min_visibility'] = {'type': 'float', 'default': counter.min_visibility, 'description': '最小姿态可见性'}
            if hasattr(counter, 'validation_threshold'):
                info['parameters']['validation_threshold'] = {'type': 'float', 'default': counter.validation_threshold, 'description': '反作弊验证阈值'}
            if hasattr(counter, 'enable_anti_cheat'):
                info['parameters']['enable_anti_cheat'] = {'type': 'bool', 'default': counter.enable_anti_cheat, 'description': '启用反作弊验证'}
            
            # 为MediaPipe计数器添加描述
            info['description'] = f"使用MediaPipe进行人体{getattr(counter, 'logic_type', 'action')}检测"
        
        # YOLO特定参数
        elif counter_type == 'yolo':
            if hasattr(counter, 'confidence_threshold'):
                info['parameters']['confidence_threshold'] = {'type': 'float', 'default': counter.confidence_threshold, 'description': 'YOLO检测置信度阈值'}
            if hasattr(counter, 'calibration_frames'):
                info['parameters']['calibration_frames'] = {'type': 'int', 'default': counter.calibration_frames, 'description': '自动校准所需的帧数'}
            
            info['object_class'] = getattr(counter, 'object_class', 'unknown')
            info['logic_type'] = getattr(counter, 'logic_type', 'unknown')
            info['description'] = f"使用YOLO进行{counter.object_class} {counter.logic_type}检测"
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_session_data')
def get_session_data():
    """获取当前会话数据"""
    return jsonify(session_data)

@app.route('/save_session', methods=['POST'])
def save_session():
    """将会话数据保存到文件"""
    try:
        filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(f"sessions/{filename}", 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return jsonify({'success': True, 'filename': filename})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload_video', methods=['POST'])
def upload_video():
    """处理视频文件上传"""
    try:
        if 'video_file' not in request.files:
            return jsonify({'error': '未选择文件'}), 400
        
        file = request.files['video_file']
        if file.filename == '':
            return jsonify({'error': '未选择文件'}), 400
        
        if file and allowed_file(file.filename):
            # 安全化文件名并保存
            filename = secure_filename(file.filename)
            # 添加时间戳以避免冲突
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            return jsonify({
                'success': True, 
                'filename': filename,
                'filepath': filepath,
                'message': f'视频上传成功: {filename}'
            })
        else:
            return jsonify({'error': '无效的文件类型。允许的格式: ' + ', '.join(ALLOWED_EXTENSIONS)}), 400
            
    except Exception as e:
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

@app.route('/list_uploaded_videos')
def list_uploaded_videos():
    """列出所有上传的视频文件"""
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
        
        # 按修改时间排序（最新的在前）
        videos.sort(key=lambda x: os.path.getmtime(x['filepath']), reverse=True)
        return jsonify({'videos': videos})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_center_line', methods=['POST'])
def adjust_center_line():
    """调整物体计数器的中心线"""
    global current_counter
    
    try:
        data = request.get_json()
        adjustment = data.get('adjustment', 0)
        
        if current_counter and hasattr(current_counter, 'adjust_center_line'):
            # 根据调整值确定方向和数量
            if adjustment > 0:
                direction = 'down'
                amount = abs(adjustment * 20)  # 转换为像素数量
            else:
                direction = 'up'
                amount = abs(adjustment * 20)
            
            # 检查是否为SportsBallCounter（使用不同的方法签名）
            if hasattr(current_counter, 'object_class') and current_counter.object_class == 'sports ball':
                current_counter.adjust_center_line(direction, amount)
                current_line = getattr(current_counter, 'start_position', 0)
            else:
                # 动物计数器（dog/cat）使用不同的签名
                current_counter.adjust_center_line(direction, amount)
                current_line = getattr(current_counter, 'center_reference', getattr(current_counter, 'start_position', 0))
            
            return jsonify({
                'success': True, 
                'new_center_line': current_line,
                'message': f'中心线向{direction}调整到 {current_line:.1f}'
            })
        else:
            return jsonify({'error': '计数器不支持中心线调整'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reset_calibration', methods=['POST'])
def reset_calibration():
    """重置YOLO计数器的校准"""
    global current_counter
    
    try:
        if current_counter:
            # 检查计数器是否有重置方法
            if hasattr(current_counter, 'reset_to_auto_calibration'):
                current_counter.reset_to_auto_calibration()
                return jsonify({
                    'success': True, 
                    'message': '校准重置成功'
                })
            elif hasattr(current_counter, 'calibrated'):
                # 重置校准标志以触发重新校准
                current_counter.calibrated = False
                current_counter.position_history = []
                if hasattr(current_counter, 'start_position'):
                    current_counter.start_position = None
                if hasattr(current_counter, 'center_reference'):
                    current_counter.center_reference = None
                current_counter.state = "start"
                current_counter.count = 0  # 同时重置计数
                return jsonify({
                    'success': True, 
                    'message': '校准重置 - 将自动重新校准'
                })
            else:
                return jsonify({'error': '计数器不支持校准重置'}), 400
        else:
            return jsonify({'error': '没有活动的计数器'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_sensitivity', methods=['POST'])
def adjust_sensitivity():
    """调整YOLO计数器的敏感度"""
    global current_counter
    
    try:
        data = request.get_json()
        direction = data.get('direction', 'increase')
        
        if current_counter and hasattr(current_counter, 'adjust_sensitivity'):
            # 调用计数器的敏感度调整方法
            if hasattr(current_counter, 'object_class') and current_counter.object_class == 'sports ball':
                # SportsBallCounter使用不同的方法签名
                current_counter.adjust_sensitivity(direction, 0.1)
                return jsonify({
                    'success': True, 
                    'message': f'体育球检测的敏感度{direction}了'
                })
            else:
                # 动物计数器
                current_counter.adjust_sensitivity(direction, 0.1)
                return jsonify({
                    'success': True, 
                    'message': f'{current_counter.object_class}检测的敏感度{direction}了'
                })
        else:
            return jsonify({'error': '计数器不支持敏感度调整'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_sensitivity_absolute', methods=['POST'])
def adjust_sensitivity_absolute():
    """为YOLO计数器设置绝对敏感度值"""
    global current_counter
    
    try:
        data = request.get_json()
        value = data.get('value', 1.0)
        
        if current_counter and hasattr(current_counter, 'sensitivity_multiplier'):
            # 直接设置敏感度乘数
            current_counter.sensitivity_multiplier = float(value)
            
            # 用新的敏感度重新计算阈值
            if hasattr(current_counter, '_recalculate_thresholds'):
                current_counter._recalculate_thresholds()
            
            return jsonify({
                'success': True, 
                'message': f'{getattr(current_counter, "object_class", "计数器")}检测的敏感度设置为 {value:.1f}'
            })
        elif current_counter:
            # 如果计数器还没有sensitivity_multiplier，则添加它
            current_counter.sensitivity_multiplier = float(value)
            return jsonify({
                'success': True, 
                'message': f'敏感度初始化为 {value:.1f}'
            })
        else:
            return jsonify({'error': '没有活动的计数器'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_center_line_absolute', methods=['POST'])
def adjust_center_line_absolute():
    """为YOLO计数器设置绝对中心线位置"""
    global current_counter
    
    try:
        data = request.get_json()
        position = data.get('position', 500)
        
        if current_counter:
            # 根据计数器类型设置绝对位置
            if hasattr(current_counter, 'object_class') and current_counter.object_class == 'sports ball':
                # SportsBallCounter使用start_position
                current_counter.start_position = float(position)
                if hasattr(current_counter, '_recalculate_thresholds'):
                    current_counter._recalculate_thresholds()
                return jsonify({
                    'success': True, 
                    'new_center_line': position,
                    'message': f'地面线设置为 {position:.1f}px'
                })
            elif hasattr(current_counter, 'center_reference'):
                # 动物计数器使用center_reference
                current_counter.center_reference = float(position)
                if hasattr(current_counter, '_recalculate_thresholds'):
                    current_counter._recalculate_thresholds()
                return jsonify({
                    'success': True, 
                    'new_center_line': position,
                    'message': f'跳跃目标设置为 {position:.1f}px'
                })
            elif hasattr(current_counter, 'start_position'):
                # 回退到start_position
                current_counter.start_position = float(position)
                return jsonify({
                    'success': True, 
                    'new_center_line': position,
                    'message': f'中心线设置为 {position:.1f}px'
                })
            else:
                return jsonify({'error': '计数器不支持绝对定位'}), 400
        else:
            return jsonify({'error': '没有活动的计数器'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/adjust_parameter', methods=['POST'])
def adjust_parameter():
    """实时调整任何计数器参数"""
    global current_counter
    
    try:
        data = request.get_json()
        param_name = data.get('parameter')
        param_value = data.get('value')
        
        if not current_counter:
            return jsonify({'error': '没有活动的计数器'}), 400
        
        if not param_name or param_value is None:
            return jsonify({'error': '需要参数名称和值'}), 400
        
        # 将值转换为适当类型
        if param_name in ['stable_frames', 'calibration_frames']:
            param_value = int(param_value)
        else:
            param_value = float(param_value)
        
        # 检查计数器上是否存在参数
        if not hasattr(current_counter, param_name):
            return jsonify({'error': f'此计数器不支持参数 {param_name}'}), 400
        
        # 设置参数
        old_value = getattr(current_counter, param_name)
        setattr(current_counter, param_name, param_value)
        
        # 特定参数的特殊处理
        if param_name == 'confidence_threshold' and hasattr(current_counter, 'tracker'):
            # 更新YOLO跟踪器置信度阈值
            current_counter.tracker.confidence_threshold = param_value
        
        # 如果需要，重新计算阈值
        if hasattr(current_counter, '_recalculate_thresholds'):
            current_counter._recalculate_thresholds()
        
        return jsonify({
            'success': True, 
            'message': f'{param_name.replace("_", " ").title()}从 {old_value} 调整到 {param_value}',
            'old_value': old_value,
            'new_value': param_value
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_recording', methods=['POST'])
def start_recording():
    """开始录制带覆盖层的视频"""
    global video_writer, is_recording, recording_filename, recording_start_time, recorded_frames
    
    try:
        if not is_processing:
            return jsonify({'error': '没有活动的计数器会话可录制'}), 400
        
        if is_recording:
            return jsonify({'error': '录制已在进行中'}), 400
        
        # 创建录制目录
        os.makedirs('recordings', exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        counter_name = session_data.get('counter_name', 'unknown').replace(' ', '_')
        recording_filename = f"recordings/recording_{counter_name}_{timestamp}.mp4"
        
        # 从视频源获取原始帧尺寸（非调整大小的网页显示）
        original_width = 640
        original_height = 480
        
        if video_capture:
            # 获取实际视频尺寸
            original_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # 如果尺寸无效则回退
            if original_width <= 0 or original_height <= 0:
                original_width, original_height = 640, 480
        
        # 从视频源获取适当的FPS
        video_fps = 30.0  # 默认FPS
        if video_capture:
            source_fps = video_capture.get(cv2.CAP_PROP_FPS)
            if source_fps > 0 and source_fps <= 60:
                video_fps = source_fps
            else:
                video_fps = 30.0  # 回退
        
        # 用原始视频尺寸和正确FPS初始化视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(recording_filename, fourcc, video_fps, (original_width, original_height))
        
        if not video_writer.isOpened():
            return jsonify({'error': '初始化视频写入器失败'}), 500
        
        # 开始录制
        is_recording = True
        recording_start_time = time.time()
        recorded_frames = 0
        
        return jsonify({
            'success': True, 
            'message': f'录制开始，{video_fps:.1f} FPS ({original_width}x{original_height})',
            'filename': recording_filename,
            'fps': video_fps,
            'width': original_width,
            'height': original_height
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    """停止录制视频"""
    global video_writer, is_recording, recording_filename, recording_start_time, recorded_frames
    
    try:
        if not is_recording:
            return jsonify({'error': '没有正在进行的录制'}), 400
        
        # 停止录制
        is_recording = False
        
        if video_writer is not None:
            video_writer.release()
            video_writer = None
        
        # 计算持续时间
        duration = None
        if recording_start_time:
            duration = round(time.time() - recording_start_time, 2)
        
        # 获取文件信息
        file_info = {
            'filename': os.path.basename(recording_filename) if recording_filename else 'unknown',
            'duration': duration,
            'frames': recorded_frames
        }
        
        return jsonify({
            'success': True, 
            'message': '录制已停止',
            **file_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_latest_recording')
def download_latest_recording():
    """下载最新的录制"""
    try:
        if not recording_filename or not os.path.exists(recording_filename):
            return jsonify({'error': '没有可下载的录制'}), 404
        
        filename = os.path.basename(recording_filename)
        return send_file(recording_filename, as_attachment=True, download_name=filename)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # 创建必要的目录
    os.makedirs('sessions', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('recordings', exist_ok=True)
    
    print("🏋️ 多计数器Web界面启动中...")
    print("📱 访问地址: http://localhost:5000")
    
    try:
        # 设置Flask优雅处理错误
        app.config['PROPAGATE_EXCEPTIONS'] = False
        app.run(debug=False, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n⏹️ 用户停止了Web界面。")
    except Exception as e:
        print(f"❌ 启动Web界面时出错: {e}")
        input("按Enter退出...") 
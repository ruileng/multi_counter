"""
基于YOLO的动物和物体对象跟踪器。
处理检测、跟踪和运动模式分析。
"""

import cv2
import numpy as np
from typing import Optional, Tuple, List, Dict
import time

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("⚠️  YOLO not installed. Run: pip install ultralytics torch torchvision")

class YOLOTracker:
    """
    基于YOLO的对象跟踪器，用于计数重复性运动。
    """
    
    def __init__(self, object_class: str = "dog", confidence_threshold: float = 0.5):
        """
        初始化YOLO跟踪器。
        
        Args:
            object_class: 要跟踪的YOLO类别名称（例如："dog", "sports ball"）
            confidence_threshold: 检测的最小置信度
        """
        self.object_class = object_class.lower()
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.previous_center = None
        self.previous_bbox = None
        self.movement_history = []
        self.last_detection_time = 0
        
        # 初始化YOLO模型
        if YOLO_AVAILABLE:
            try:
                print(f"🔄 正在为'{object_class}'检测加载YOLO模型...")
                self.model = YOLO('yolov8n.pt')  # Nano模型（最快）
                print("✅ YOLO模型加载成功!")
            except Exception as e:
                print(f"❌ 加载YOLO模型时出错: {e}")
                self.model = None
        else:
            print("❌ YOLO不可用。请安装依赖项。")
    
    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """
        使用YOLO在帧中检测对象。
        
        Returns:
            检测到的对象列表，包含边界框和置信度
        """
        if not self.model:
            return []
        
        try:
            # 运行YOLO检测
            results = self.model(frame, verbose=False)
            detections = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # 获取类别名称
                        class_id = int(box.cls[0])
                        class_name = self.model.names[class_id].lower()
                        confidence = float(box.conf[0])
                        
                        # 按对象类别和置信度过滤
                        if (self.object_class in class_name or class_name in self.object_class) and confidence >= self.confidence_threshold:
                            # 获取边界框坐标
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            
                            detection = {
                                'class': class_name,
                                'confidence': confidence,
                                'bbox': (int(x1), int(y1), int(x2), int(y2)),
                                'center': (int((x1 + x2) / 2), int((y1 + y2) / 2)),
                                'width': int(x2 - x1),
                                'height': int(y2 - y1)
                            }
                            detections.append(detection)
            
            return detections
            
        except Exception as e:
            print(f"YOLO检测中出错: {e}")
            return []
    
    def get_best_detection(self, detections: List[Dict]) -> Optional[Dict]:
        """
        获取最佳检测（最高置信度或最接近前一个）。
        """
        if not detections:
            return None
        
        if len(detections) == 1:
            return detections[0]
        
        # 如果有前一次检测，优选最接近的
        if self.previous_center:
            best_detection = None
            min_distance = float('inf')
            
            for detection in detections:
                center = detection['center']
                distance = np.sqrt((center[0] - self.previous_center[0])**2 + 
                                 (center[1] - self.previous_center[1])**2)
                if distance < min_distance:
                    min_distance = distance
                    best_detection = detection
            
            return best_detection
        
        # 否则，返回最高置信度的
        return max(detections, key=lambda x: x['confidence'])
    
    def calculate_movement(self, current_center: Tuple[int, int]) -> Dict:
        """
        计算当前位置和前一位置之间的运动指标。
        """
        if not self.previous_center:
            self.previous_center = current_center
            return {'distance': 0, 'vertical_change': 0, 'horizontal_change': 0}
        
        # 计算运动
        dx = current_center[0] - self.previous_center[0]
        dy = current_center[1] - self.previous_center[1]
        distance = np.sqrt(dx**2 + dy**2)
        
        movement = {
            'distance': distance,
            'vertical_change': dy,  # 正值 = 向下，负值 = 向上
            'horizontal_change': dx,  # 正值 = 向右，负值 = 向左
            'previous_center': self.previous_center,
            'current_center': current_center
        }
        
        # 更新历史记录
        self.movement_history.append({
            'timestamp': time.time(),
            'center': current_center,
            'movement': movement
        })
        
        # 仅保留最近的历史记录（最后30帧）
        if len(self.movement_history) > 30:
            self.movement_history.pop(0)
        
        # 更新前一个中心点
        self.previous_center = current_center
        
        return movement
    
    def detect_bounce(self, movement: Dict, threshold: float = 30) -> bool:
        """
        检测对象是否在弹跳（上下运动）。
        改进的算法以获得更好的弹跳检测。
        """
        if len(self.movement_history) < 5:  # 需要更多历史记录以进行可靠检测
            return False
        
        # 获取最近的垂直运动
        recent_movements = self.movement_history[-5:]
        vertical_changes = [m['movement']['vertical_change'] for m in recent_movements]
        
        # 寻找弹跳模式：向下运动后跟向上运动
        # 弹跳应该显示：下降（正y）然后上升（负y）
        for i in range(len(vertical_changes) - 1):
            current_change = vertical_changes[i]
            next_change = vertical_changes[i + 1]
            
            # 检测弹跳：显著的向下运动后跟向上运动
            if (current_change > threshold and next_change < -threshold * 0.5):
                # 额外验证：检查对象是否确实先向下后向上移动
                if i >= 1:
                    prev_change = vertical_changes[i - 1]
                    # 确认弹跳前的向下趋势
                    if prev_change > 0:
                        return True
        
        return False
    
    def detect_jump(self, movement: Dict, threshold: float = 50) -> bool:
        """
        检测跳跃动作（显著的向上运动并返回）。
        改进的算法以获得更好的跳跃检测。
        """
        if len(self.movement_history) < 4:
            return False
        
        # 获取最近的运动
        recent_movements = self.movement_history[-4:]
        vertical_changes = [m['movement']['vertical_change'] for m in recent_movements]
        
        # 寻找跳跃模式：快速向上运动后向下返回
        # 跳跃应该显示：向上（负y）然后向下（正y）
        for i in range(len(vertical_changes) - 1):
            current_change = vertical_changes[i]
            next_change = vertical_changes[i + 1]
            
            # 检测跳跃：显著的向上运动后跟向下运动
            if (current_change < -threshold and next_change > threshold * 0.3):
                # 额外验证：检查持续的向上运动
                if i >= 1:
                    prev_change = vertical_changes[i - 1]
                    # 确认跳跃期间的向上趋势
                    if prev_change < 0:
                        return True
        
        return False
    
    def detect_movement_pattern(self, movement: Dict, pattern_type: str, threshold: float = 30) -> bool:
        """
        用于不同运动类型的高级模式检测。
        """
        if pattern_type == "bounce":
            return self.detect_bounce(movement, threshold)
        elif pattern_type == "jump":
            return self.detect_jump(movement, threshold)
        elif pattern_type == "oscillation":
            return self.detect_oscillation(movement, threshold)
        else:
            return movement['distance'] > threshold
    
    def detect_oscillation(self, movement: Dict, threshold: float = 30) -> bool:
        """
        检测振荡运动（来回移动）。
        """
        if len(self.movement_history) < 6:
            return False
        
        # 检查水平或垂直运动的振荡模式
        recent_movements = self.movement_history[-6:]
        horizontal_changes = [m['movement']['horizontal_change'] for m in recent_movements]
        vertical_changes = [m['movement']['vertical_change'] for m in recent_movements]
        
        # 计数方向变化
        h_direction_changes = 0
        v_direction_changes = 0
        
        for i in range(1, len(horizontal_changes)):
            if (horizontal_changes[i] > 0) != (horizontal_changes[i-1] > 0):
                h_direction_changes += 1
            if (vertical_changes[i] > 0) != (vertical_changes[i-1] > 0):
                v_direction_changes += 1
        
        # 如果多次方向变化则检测到振荡
        return (h_direction_changes >= 3 or v_direction_changes >= 3)
    
    def draw_detection(self, frame: np.ndarray, detection: Dict) -> np.ndarray:
        """
        在帧上绘制边界框和信息。
        """
        if not detection:
            return frame
        
        bbox = detection['bbox']
        center = detection['center']
        confidence = detection['confidence']
        class_name = detection['class']
        
        # 绘制边界框
        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
        
        # 绘制中心点
        cv2.circle(frame, center, 5, (0, 0, 255), -1)
        
        # 绘制标签
        label = f"{class_name}: {confidence:.2f}"
        cv2.putText(frame, label, (bbox[0], bbox[1] - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 绘制运动轨迹
        if len(self.movement_history) > 1:
            points = [m['center'] for m in self.movement_history[-10:]]  # 最后10个位置
            for i in range(1, len(points)):
                cv2.line(frame, points[i-1], points[i], (255, 0, 0), 2)
        
        return frame

# Available YOLO classes for reference
YOLO_CLASSES = {
    'animals': ['dog', 'cat', 'bird', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe'],
    'sports': ['sports ball', 'baseball bat', 'tennis racket', 'frisbee', 'skis', 'snowboard'],
    'objects': ['bottle', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'orange'],
    'vehicles': ['car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat']
}

def list_available_classes():
    """打印所有可用的YOLO类别。"""
    print("🎯 可用的YOLO类别:")
    for category, classes in YOLO_CLASSES.items():
        print(f"\n📂 {category.title()}:")
        for cls in classes:
            print(f"   • {cls}")

if __name__ == "__main__":
    # 测试跟踪器
    list_available_classes()
    
    # 使用示例
    tracker = YOLOTracker("dog")
    print(f"\n🐕 狗跟踪器已初始化: {tracker.model is not None}") 
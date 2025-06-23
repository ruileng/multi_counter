"""
YOLO-based object tracker for animals and objects.
Handles detection, tracking, and movement pattern analysis.
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
    YOLO-based object tracker for counting repetitive movements.
    """
    
    def __init__(self, object_class: str = "dog", confidence_threshold: float = 0.5):
        """
        Initialize YOLO tracker.
        
        Args:
            object_class: YOLO class name to track (e.g., "dog", "sports ball")
            confidence_threshold: Minimum confidence for detection
        """
        self.object_class = object_class.lower()
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.previous_center = None
        self.previous_bbox = None
        self.movement_history = []
        self.last_detection_time = 0
        
        # Initialize YOLO model
        if YOLO_AVAILABLE:
            try:
                print(f"🔄 Loading YOLO model for '{object_class}' detection...")
                self.model = YOLO('yolov8n.pt')  # Nano model (fastest)
                print("✅ YOLO model loaded successfully!")
            except Exception as e:
                print(f"❌ Error loading YOLO model: {e}")
                self.model = None
        else:
            print("❌ YOLO not available. Please install dependencies.")
    
    def detect_objects(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect objects in frame using YOLO.
        
        Returns:
            List of detected objects with bounding boxes and confidence
        """
        if not self.model:
            return []
        
        try:
            # Run YOLO detection
            results = self.model(frame, verbose=False)
            detections = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # Get class name
                        class_id = int(box.cls[0])
                        class_name = self.model.names[class_id].lower()
                        confidence = float(box.conf[0])
                        
                        # Filter by object class and confidence
                        if (self.object_class in class_name or class_name in self.object_class) and confidence >= self.confidence_threshold:
                            # Get bounding box coordinates
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
            print(f"Error in YOLO detection: {e}")
            return []
    
    def get_best_detection(self, detections: List[Dict]) -> Optional[Dict]:
        """
        Get the best detection (highest confidence or closest to previous).
        """
        if not detections:
            return None
        
        if len(detections) == 1:
            return detections[0]
        
        # If we have previous detection, prefer closest one
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
        
        # Otherwise, return highest confidence
        return max(detections, key=lambda x: x['confidence'])
    
    def calculate_movement(self, current_center: Tuple[int, int]) -> Dict:
        """
        Calculate movement metrics between current and previous position.
        """
        if not self.previous_center:
            self.previous_center = current_center
            return {'distance': 0, 'vertical_change': 0, 'horizontal_change': 0}
        
        # Calculate movement
        dx = current_center[0] - self.previous_center[0]
        dy = current_center[1] - self.previous_center[1]
        distance = np.sqrt(dx**2 + dy**2)
        
        movement = {
            'distance': distance,
            'vertical_change': dy,  # Positive = down, Negative = up
            'horizontal_change': dx,  # Positive = right, Negative = left
            'previous_center': self.previous_center,
            'current_center': current_center
        }
        
        # Update history
        self.movement_history.append({
            'timestamp': time.time(),
            'center': current_center,
            'movement': movement
        })
        
        # Keep only recent history (last 30 frames)
        if len(self.movement_history) > 30:
            self.movement_history.pop(0)
        
        # Update previous center
        self.previous_center = current_center
        
        return movement
    
    def detect_bounce(self, movement: Dict, threshold: float = 30) -> bool:
        """
        Detect if object is bouncing (up-down movement).
        Improved algorithm for better bounce detection.
        """
        if len(self.movement_history) < 5:  # Need more history for reliable detection
            return False
        
        # Get recent vertical movements
        recent_movements = self.movement_history[-5:]
        vertical_changes = [m['movement']['vertical_change'] for m in recent_movements]
        
        # Look for bounce pattern: down movement followed by up movement
        # A bounce should show: falling (positive y) then rising (negative y)
        for i in range(len(vertical_changes) - 1):
            current_change = vertical_changes[i]
            next_change = vertical_changes[i + 1]
            
            # Detect bounce: significant downward movement followed by upward movement
            if (current_change > threshold and next_change < -threshold * 0.5):
                # Additional validation: check if the object was actually moving down then up
                if i >= 1:
                    prev_change = vertical_changes[i - 1]
                    # Confirm downward trend before bounce
                    if prev_change > 0:
                        return True
        
        return False
    
    def detect_jump(self, movement: Dict, threshold: float = 50) -> bool:
        """
        Detect jumping motion (significant upward movement with return).
        Improved algorithm for better jump detection.
        """
        if len(self.movement_history) < 4:
            return False
        
        # Get recent movements
        recent_movements = self.movement_history[-4:]
        vertical_changes = [m['movement']['vertical_change'] for m in recent_movements]
        
        # Look for jump pattern: rapid upward movement followed by downward return
        # A jump should show: up (negative y) then down (positive y)
        for i in range(len(vertical_changes) - 1):
            current_change = vertical_changes[i]
            next_change = vertical_changes[i + 1]
            
            # Detect jump: significant upward movement followed by downward movement
            if (current_change < -threshold and next_change > threshold * 0.3):
                # Additional validation: check for sustained upward movement
                if i >= 1:
                    prev_change = vertical_changes[i - 1]
                    # Confirm upward trend during jump
                    if prev_change < 0:
                        return True
        
        return False
    
    def detect_movement_pattern(self, movement: Dict, pattern_type: str, threshold: float = 30) -> bool:
        """
        Advanced pattern detection for different movement types.
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
        Detect oscillating movement (back and forth).
        """
        if len(self.movement_history) < 6:
            return False
        
        # Check for oscillating pattern in horizontal or vertical movement
        recent_movements = self.movement_history[-6:]
        horizontal_changes = [m['movement']['horizontal_change'] for m in recent_movements]
        vertical_changes = [m['movement']['vertical_change'] for m in recent_movements]
        
        # Count direction changes
        h_direction_changes = 0
        v_direction_changes = 0
        
        for i in range(1, len(horizontal_changes)):
            if (horizontal_changes[i] > 0) != (horizontal_changes[i-1] > 0):
                h_direction_changes += 1
            if (vertical_changes[i] > 0) != (vertical_changes[i-1] > 0):
                v_direction_changes += 1
        
        # Oscillation detected if multiple direction changes
        return (h_direction_changes >= 3 or v_direction_changes >= 3)
    
    def draw_detection(self, frame: np.ndarray, detection: Dict) -> np.ndarray:
        """
        Draw bounding box and info on frame.
        """
        if not detection:
            return frame
        
        bbox = detection['bbox']
        center = detection['center']
        confidence = detection['confidence']
        class_name = detection['class']
        
        # Draw bounding box
        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
        
        # Draw center point
        cv2.circle(frame, center, 5, (0, 0, 255), -1)
        
        # Draw label
        label = f"{class_name}: {confidence:.2f}"
        cv2.putText(frame, label, (bbox[0], bbox[1] - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw movement trail
        if len(self.movement_history) > 1:
            points = [m['center'] for m in self.movement_history[-10:]]  # Last 10 positions
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
    """Print all available YOLO classes."""
    print("🎯 Available YOLO Classes:")
    for category, classes in YOLO_CLASSES.items():
        print(f"\n📂 {category.title()}:")
        for cls in classes:
            print(f"   • {cls}")

if __name__ == "__main__":
    # Test the tracker
    list_available_classes()
    
    # Example usage
    tracker = YOLOTracker("dog")
    print(f"\n🐕 Dog tracker initialized: {tracker.model is not None}") 
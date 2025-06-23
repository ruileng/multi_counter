"""
SportsBallCounter - Enhanced YOLO-based sports ball counter
Generated automatically for bounce_detection detection using landmark-based approach
"""

import cv2
import numpy as np
from yolo_tracker import YOLOTracker

class SportsBallCounter:
    def __init__(self):
        # YOLO Configuration
        self.object_class = "sports ball"
        self.detection_type = "yolo"
        self.logic_type = "bounce_detection"
        
        # Detection parameters
        self.threshold = 40
        self.confidence_threshold = 0.25  # Lowered for sports ball detection
        self.stable_frames = 5
        
        # Counter state
        self.count = 0
        self.state = "start"  # start, up, down, moving
        self.stable_count = 0
        
        # Landmark tracking (using bounding box as landmarks)
        self.start_position = None
        self.current_position = None
        self.up_threshold = None
        self.down_threshold = None
        
        # Movement history for pattern detection and adaptive thresholds
        self.position_history = []
        self.calibration_frames = 30  # Reduced for faster calibration
        self.calibrated = False
        
        # Adaptive threshold calculation
        self.position_variance = 0
        self.movement_range = 0
        self.adaptive_multiplier = 1.0
        
        # Frame scaling tracking
        self.original_frame_size = None
        self.display_scale = 1.0
        self.video_height = None
        
        # YOLO tracker
        self.tracker = YOLOTracker(
            object_class=self.object_class,
            confidence_threshold=self.confidence_threshold
        )
        
        # Debug info
        self.debug_info = {
            'detected': False,
            'confidence': 0.0,
            'state': self.state,
            'is_up': False,
            'is_down': False,
            'is_at_start': False,
            'position_y': 0,
            'start_y': 0,
            'up_threshold': 0,
            'down_threshold': 0,
            'movement_range': 0,
            'adaptive_multiplier': 1.0
        }
    
    def update(self, frame):
        """
        Update counter with new frame using landmark-based detection.
        
        Args:
            frame: OpenCV frame (numpy array)
            
        Returns:
            int: Current count
        """
        # Store original frame size for proper scaling
        if self.original_frame_size is None:
            self.original_frame_size = (frame.shape[1], frame.shape[0])  # width, height
            self.video_height = frame.shape[0]  # Store for threshold calculations
        
        # Detect objects in frame
        detections = self.tracker.detect_objects(frame)
        best_detection = self.tracker.get_best_detection(detections)
        
        if best_detection:
            self.debug_info['detected'] = True
            self.debug_info['confidence'] = best_detection['confidence']
            
            # Get position from bounding box center (in original coordinates)
            bbox = best_detection['bbox']
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            self.current_position = (center_x, center_y)
            
            # Calibration phase
            if not self.calibrated:
                self._calibrate_position_adaptive(center_y)
                return self.count
            
            # Update position tracking
            self.position_history.append(center_y)
            if len(self.position_history) > 20:  # Keep last 20 positions for analysis
                self.position_history.pop(0)
            
            # Apply detection logic
            
            self._detect_bounce(center_y)
            
            
            # Update debug info
            self._update_debug_info(center_y)
            
        else:
            self.debug_info['detected'] = False
            self.debug_info['confidence'] = 0.0
        
        self.debug_info['state'] = self.state
        return self.count
    
    def _calibrate_position_adaptive(self, center_y):
        """Enhanced calibration with adaptive threshold calculation."""
        self.position_history.append(center_y)
        
        if len(self.position_history) >= self.calibration_frames:
            # For bouncing objects, the ground should be the reference
            # Use the maximum Y position (bottom) as the ground reference
            sorted_positions = sorted(self.position_history)
            
            # Ground is near the maximum Y position (ball at rest/lowest point)
            ground_position = sorted_positions[-10:]  # Take average of bottom 10 positions
            self.start_position = sum(ground_position) / len(ground_position)
            
            # Calculate movement variance and range for adaptive thresholds
            positions_array = np.array(self.position_history)
            self.position_variance = np.std(positions_array)
            self.movement_range = np.max(positions_array) - np.min(positions_array)
            
            # Fixed, reasonable threshold calculation for bouncing balls
            # Base bounce height should be a reasonable fraction of movement range
            base_bounce_height = max(self.threshold, self.movement_range * 0.3)  # At least 30% of observed range
            ground_tolerance = 20  # Small tolerance around ground level
            
            # Ground reference thresholds (much simpler and more reliable)
            self.up_threshold = self.start_position - base_bounce_height  # Ball bounced up from ground
            self.down_threshold = self.start_position - ground_tolerance  # Ball returned near ground
            
            # Ensure thresholds are within reasonable video bounds
            video_height = 1080  # Assume standard video height, adjust if needed
            min_y = 50  # Leave space at top
            max_y = video_height - 50  # Leave space at bottom
            
            # Clamp thresholds to reasonable bounds
            self.up_threshold = max(min_y, min(self.up_threshold, self.start_position - 30))
            self.down_threshold = min(max_y, max(self.down_threshold, self.start_position - 50))
            
            # Ensure minimum bounce height
            min_bounce_height = 40
            if (self.start_position - self.up_threshold) < min_bounce_height:
                self.up_threshold = self.start_position - min_bounce_height
            
            # Set adaptive multiplier to a reasonable value for reporting
            self.adaptive_multiplier = base_bounce_height / self.threshold if self.threshold > 0 else 1.0
            
            self.calibrated = True
            print(f"🎯 SportsBallCounter calibrated (Ground Reference):")
            print(f"   Ground position: {self.start_position:.1f}")
            print(f"   Movement range: {self.movement_range:.1f}")
            print(f"   Bounce height: {self.start_position - self.up_threshold:.1f}")
            print(f"   Up threshold: {self.up_threshold:.1f}")
            print(f"   Down threshold: {self.down_threshold:.1f}")
            print(f"   Ground tolerance: {self.start_position - self.down_threshold:.1f}")
    
    def _detect_bounce(self, center_y):
        """Detect bouncing movement pattern with improved stability."""
        if self.state == "start":
            if center_y > self.down_threshold:
                self.state = "down"
                self.stable_count = 0
                print(f"🔽 Ball entered DOWN zone: {center_y:.1f} > {self.down_threshold:.1f}")
        
        elif self.state == "down":
            if center_y < self.up_threshold:
                self.stable_count += 1
                print(f"🔼 Ball in UP zone (frame {self.stable_count}/{self.stable_frames}): {center_y:.1f} < {self.up_threshold:.1f}")
                if self.stable_count >= self.stable_frames:
                    self._increment_count()
                    self.state = "start"
                    self.stable_count = 0
                    print(f"✅ Bounce confirmed! Returning to START state")
            elif center_y >= self.down_threshold:
                # Ball is still in down zone, maintain state
                pass
            else:
                # Ball is in middle zone (between up and down thresholds)
                # Reset stable count to prevent premature counting
                if self.stable_count > 0:
                    print(f"⚠️  Ball in middle zone, resetting stable count: {center_y:.1f}")
                self.stable_count = 0
    
    def _detect_jump(self, center_y):
        """Detect jumping movement pattern optimized for animals."""
        if self.state == "start":
            if center_y < self.up_threshold:
                self.state = "up"
                self.stable_count = 0
        
        elif self.state == "up":
            # More lenient return condition for animals
            return_threshold = self.start_position + (self.start_position - self.up_threshold) * 0.3
            if center_y > return_threshold:
                self.stable_count += 1
                if self.stable_count >= self.stable_frames:
                    self._increment_count()
                    self.state = "start"
                    self.stable_count = 0
            elif center_y > self.up_threshold:
                self.stable_count = 0
    
    def _detect_movement(self, center_y):
        """Detect general movement pattern with improved sensitivity."""
        if self.state == "start":
            if center_y < self.up_threshold or center_y > self.down_threshold:
                self.state = "moving"
                self.stable_count = 0
        
        elif self.state == "moving":
            # Dynamic return zone based on movement range
            return_zone = max(self.threshold * 0.3, self.movement_range * 0.15)
            if abs(center_y - self.start_position) < return_zone:
                self.stable_count += 1
                if self.stable_count >= self.stable_frames:
                    self._increment_count()
                    self.state = "start"
                    self.stable_count = 0
            else:
                self.stable_count = 0
    
    def _detect_vertical_movement(self, center_y):
        """Default vertical movement detection with adaptive thresholds."""
        if self.state == "start":
            if center_y < self.up_threshold:
                self.state = "up"
            elif center_y > self.down_threshold:
                self.state = "down"
        
        elif self.state == "up":
            if center_y > self.start_position:
                self._increment_count()
                self.state = "start"
        
        elif self.state == "down":
            if center_y < self.start_position:
                self._increment_count()
                self.state = "start"
    
    def _update_debug_info(self, center_y):
        """Update debug information."""
        self.debug_info.update({
            'position_y': center_y,
            'start_y': self.start_position or 0,
            'up_threshold': self.up_threshold or 0,
            'down_threshold': self.down_threshold or 0,
            'is_up': center_y < (self.up_threshold or float('inf')),
            'is_down': center_y > (self.down_threshold or float('-inf')),
            'is_at_start': abs(center_y - (self.start_position or center_y)) < (self.threshold * 0.3) if self.start_position else False,
            'movement_range': self.movement_range,
            'adaptive_multiplier': self.adaptive_multiplier
        })
    
    def _increment_count(self):
        """Increment the counter."""
        self.count += 1
        print(f"🎯 SportsBallCounter: {self.count} (sports ball)")
    
    def adjust_center_line(self, direction, amount=10):
        """Adjust the ground reference line for sports ball detection."""
        if not self.calibrated or self.start_position is None:
            print("⚠️  Please wait for calibration to complete before adjusting thresholds")
            return
        
        if direction == 'up':
            # Move ground reference up (smaller Y value)
            self.start_position -= amount
            print(f"🔼 Ground line moved UP: {self.start_position:.1f}")
        elif direction == 'down':
            # Move ground reference down (larger Y value)  
            self.start_position += amount
            print(f"🔽 Ground line moved DOWN: {self.start_position:.1f}")
        
        # Recalculate thresholds based on new ground position
        self._recalculate_thresholds()
    
    def adjust_sensitivity(self, direction, factor=0.1):
        """Adjust bounce detection sensitivity."""
        if not self.calibrated:
            print("⚠️  Please wait for calibration to complete before adjusting sensitivity")
            return
        
        if not hasattr(self, 'sensitivity_multiplier'):
            self.sensitivity_multiplier = 1.0
        
        if direction == 'increase':
            # More sensitive = smaller thresholds
            self.sensitivity_multiplier *= (1 - factor)
            print(f"➕ Sensitivity INCREASED (more sensitive): {self.sensitivity_multiplier:.2f}")
        elif direction == 'decrease':
            # Less sensitive = larger thresholds  
            self.sensitivity_multiplier *= (1 + factor)
            print(f"➖ Sensitivity DECREASED (less sensitive): {self.sensitivity_multiplier:.2f}")
        
        # Clamp sensitivity to reasonable bounds
        self.sensitivity_multiplier = max(0.3, min(3.0, self.sensitivity_multiplier))
        
        # Recalculate thresholds with new sensitivity
        self._recalculate_thresholds()
    
    def _recalculate_thresholds(self):
        """Recalculate bounce thresholds after manual adjustments."""
        if not self.calibrated or self.start_position is None:
            return
        
        # Get base bounce height (same as calibration logic)
        base_bounce_height = max(self.threshold, self.movement_range * 0.3)
        ground_tolerance = 20
        
        # Apply sensitivity multiplier
        sensitivity_mult = getattr(self, 'sensitivity_multiplier', 1.0)
        adjusted_bounce_height = base_bounce_height * sensitivity_mult
        adjusted_tolerance = ground_tolerance * sensitivity_mult
        
        # Recalculate thresholds
        self.up_threshold = self.start_position - adjusted_bounce_height
        self.down_threshold = self.start_position - adjusted_tolerance
        
        # Apply bounds checking
        video_height = getattr(self, 'video_height', 1080)
        margin = 50
        
        self.up_threshold = max(margin, min(self.up_threshold, self.start_position - 30))
        self.down_threshold = min(video_height - margin, max(self.down_threshold, self.start_position - 50))
        
        # Ensure minimum bounce height
        min_bounce_height = 40
        if (self.start_position - self.up_threshold) < min_bounce_height:
            self.up_threshold = self.start_position - min_bounce_height
        
        print(f"   New thresholds - Up: {self.up_threshold:.1f}, Down: {self.down_threshold:.1f}")
        print(f"   Bounce height: {self.start_position - self.up_threshold:.1f}px")
    
    def reset_to_auto_calibration(self):
        """Reset to original auto-calibrated values."""
        if not self.calibrated:
            print("⚠️  No calibration data available to reset to")
            return
        
        # Reset sensitivity multiplier
        self.sensitivity_multiplier = 1.0
        
        # Recalculate original thresholds
        self._recalculate_thresholds()
        
        print(f"🔄 Reset to auto-calibrated values:")
        print(f"   Ground position: {self.start_position:.1f}")
        print(f"   Up threshold: {self.up_threshold:.1f}")
        print(f"   Down threshold: {self.down_threshold:.1f}")
    
    def reset(self):
        """Reset the counter."""
        self.count = 0
        self.state = "start"
        self.stable_count = 0
        self.start_position = None
        self.current_position = None
        self.position_history.clear()
        self.calibrated = False
        self.position_variance = 0
        self.movement_range = 0
        self.adaptive_multiplier = 1.0
        self.original_frame_size = None
        self.display_scale = 1.0
        self.video_height = None
        if hasattr(self, 'sensitivity_multiplier'):
            self.sensitivity_multiplier = 1.0
        self.tracker.movement_history.clear()
        self.tracker.previous_center = None
    
    def draw_debug_info(self, frame, detection=None):
        """
        Simple, fast debug display with proper aspect ratio scaling.
        """
        # Get original dimensions
        original_height, original_width = frame.shape[:2]
        
        # Calculate proper scaling maintaining aspect ratio
        max_width = 800
        max_height = 600
        
        # Calculate scale factors for both width and height constraints
        scale_by_width = max_width / original_width
        scale_by_height = max_height / original_height
        
        # Use the smaller scale factor to ensure video fits within both constraints
        scale_factor = min(scale_by_width, scale_by_height)
        
        # Calculate final display dimensions
        display_width = int(original_width * scale_factor)
        display_height = int(original_height * scale_factor)
        
        # Resize with proper aspect ratio
        display_frame = cv2.resize(frame, (display_width, display_height))
        
        # Calculate scaling factors for coordinate conversion
        scale_x = display_width / original_width
        scale_y = display_height / original_height
        
        # Draw detection bounding box if available
        if detection:
            bbox = detection['bbox']
            
            x1 = int(bbox[0] * scale_x)
            y1 = int(bbox[1] * scale_y)
            x2 = int(bbox[2] * scale_x)
            y2 = int(bbox[3] * scale_y)
            
            # Draw bounding box
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Draw confidence
            cv2.putText(display_frame, f"{detection['class']} {detection['confidence']:.2f}", 
                       (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Draw threshold lines if calibrated
        if self.calibrated and self.start_position is not None:
            start_y = int(self.start_position * scale_y)
            up_y = int(self.up_threshold * scale_y) if self.up_threshold is not None else start_y - 50
            down_y = int(self.down_threshold * scale_y) if self.down_threshold is not None else start_y + 50
            
            # Ensure lines are within frame bounds
            start_y = max(5, min(display_height - 5, start_y))
            up_y = max(5, min(display_height - 5, up_y))
            down_y = max(5, min(display_height - 5, down_y))
            
            # Draw threshold lines with proper width
            cv2.line(display_frame, (0, start_y), (display_width, start_y), (0, 255, 255), 3)  # Yellow start line
            cv2.line(display_frame, (0, up_y), (display_width, up_y), (0, 255, 0), 3)        # Green up line  
            cv2.line(display_frame, (0, down_y), (display_width, down_y), (255, 0, 0), 3)    # Blue down line
            
            # Add labels
            cv2.putText(display_frame, "GROUND", (10, start_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            cv2.putText(display_frame, "BOUNCE", (10, up_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(display_frame, "RETURN", (10, down_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            # Show current ball position
            if detection:
                ball_center_y = (detection['bbox'][1] + detection['bbox'][3]) / 2
                ball_y_scaled = int(ball_center_y * scale_y)
                ball_x_center = display_width // 2
                cv2.circle(display_frame, (ball_x_center, ball_y_scaled), 5, (255, 255, 255), -1)  # White dot for ball center
        
        # Draw comprehensive status info
        status_lines = [
            f"Count: {self.count}",
            f"State: {self.state}",
            f"Detected: {self.debug_info['detected']}",
            f"Calibrated: {self.calibrated}",
            f"Video: {original_width}x{original_height} → {display_width}x{display_height}",
            f"Scale: {scale_factor:.2f}"
        ]
        
        if self.debug_info['detected']:
            status_lines.append(f"Confidence: {self.debug_info['confidence']:.2f}")
        
        # Add position info if calibrated
        if self.calibrated:
            status_lines.extend([
                f"Ball Y: {self.debug_info.get('position_y', 0):.1f}",
                f"Ground: {self.start_position:.1f}",
                f"Bounce Line: {self.up_threshold:.1f}",
                f"Return Line: {self.down_threshold:.1f}",
                f"Is Bouncing: {self.debug_info.get('is_up', False)}",
                f"Near Ground: {self.debug_info.get('is_down', False)}"
            ])
        
        # Draw status with background
        for i, line in enumerate(status_lines):
            y_pos = 30 + i * 20
            # Black background for text
            (text_width, text_height), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(display_frame, (5, y_pos - text_height - 2), (text_width + 10, y_pos + 3), (0, 0, 0), -1)
            # White text
            cv2.putText(display_frame, line, (8, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Show calibration progress if not calibrated
        if not self.calibrated:
            progress = len(self.position_history)
            total = self.calibration_frames
            progress_text = f"Calibrating: {progress}/{total}"
            cv2.putText(display_frame, progress_text, (10, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        return display_frame
    
    def get_debug_info(self):
        """Get debug information for web interface."""
        return {
            'count': self.count,
            'state': self.state,
            'detected': self.debug_info['detected'],
            'confidence': self.debug_info['confidence'],
            'object_class': self.object_class,
            'logic_type': self.logic_type,
            'calibrated': self.calibrated,
            'position_y': self.debug_info.get('position_y', 0),
            'start_y': self.debug_info.get('start_y', 0),
            'is_up': self.debug_info.get('is_up', False),
            'is_down': self.debug_info.get('is_down', False),
            'is_at_start': self.debug_info.get('is_at_start', False),
            'movement_range': self.debug_info.get('movement_range', 0),
            'adaptive_multiplier': self.debug_info.get('adaptive_multiplier', 1.0),
            'display_scale': self.display_scale
        } 
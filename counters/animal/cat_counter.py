"""
CatCounter - Enhanced YOLO-based cat counter
Generated automatically for movement_detection detection using landmark-based approach
"""

import cv2
import numpy as np
from yolo_tracker import YOLOTracker

class CatCounter:
    def __init__(self):
        # YOLO Configuration
        self.object_class = "cat"
        self.detection_type = "yolo"
        self.logic_type = "movement_detection"
        
        # Detection parameters
        self.threshold = 40
        self.confidence_threshold = 0.4
        self.stable_frames = 5
        
        # Counter state
        self.count = 0
        self.state = "start"  # start, jumped
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
        
        # YOLO tracker
        self.tracker = YOLOTracker(
            object_class=self.object_class,
            confidence_threshold=self.confidence_threshold
        )
        
        # Body height tracking for adaptive thresholds
        self.body_heights = []
        self.body_height = 0
        self.jump_threshold_px = 0
        self.jump_ratio_used = 0
        
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
        
        # Detect objects in frame
        detections = self.tracker.detect_objects(frame)
        best_detection = self.tracker.get_best_detection(detections)
        
        if best_detection:
            self.debug_info['detected'] = True
            self.debug_info['confidence'] = best_detection['confidence']
            
            # Extract center coordinates from detection
            x1, y1, x2, y2 = best_detection['bbox']
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            # Calculate and store body height
            body_height = y2 - y1
            self.body_heights.append(body_height)
            if len(self.body_heights) > 50:  # Keep last 50 measurements
                self.body_heights.pop(0)
            
            # Store position for calibration
            if not self.calibrated:
                self.position_history.append(center_y)
                if len(self.position_history) >= self.calibration_frames:
                    self._calibrate_movement_thresholds(self.position_history)
                    self.calibrated = True
                    print(f"🎯 CatCounter calibrated (Body-Height-Based Detection):")
                    print(f"   Center position: {self.start_position:.1f}")
                    print(f"   Body height: {self.body_height:.1f}px")
                    print(f"   Jump threshold: {self.jump_threshold_px:.1f}px ({self.jump_ratio_used:.1%} of body)")
                    print(f"   Center reference: {getattr(self, 'center_reference', self.start_position):.1f} (jump target)")
                    print(f"   Up threshold: {self.up_threshold:.1f}")
                    print(f"   Down threshold: {self.down_threshold:.1f}")
                    print(f"   Detection zone: {self.down_threshold - self.up_threshold:.1f}px")
                    print(f"🎮 KEYBOARD CONTROLS NOW ACTIVE:")
                    print(f"   ↑/W: Move center line up    ↓/S: Move center line down")
                    print(f"   +: Less sensitive (larger dead zone)    -: More sensitive")
                    print(f"   0: Reset to auto-calibration")
                    return self.count
            
            # Store position for movement detection
            self.position_history.append(center_y)
            
            # Update debug info
            self.debug_info.update({
                'position_x': center_x,
                'position_y': center_y,
                'is_up': center_y < self.up_threshold if self.up_threshold is not None else False,
                'is_down': center_y > self.down_threshold if self.down_threshold is not None else False
            })
            
            # Detect movement
            if self.logic_type == "movement_detection":
                self._detect_movement(center_y)
            elif self.logic_type == "bounce_detection":
                self._detect_bounce(center_y)
            
            # Update position tracking
            if len(self.position_history) > 20:  # Keep last 20 positions for analysis
                self.position_history.pop(0)
        
            # Apply detection logic
            
            self._detect_movement(center_y)
            
            
            # Update debug info
            self._update_debug_info(center_y)
            
        else:
            self.debug_info['detected'] = False
            self.debug_info['confidence'] = 0.0
        
        self.debug_info['state'] = self.state
        return self.count
    
    def _calibrate_movement_thresholds(self, positions):
        """Calculate movement thresholds based on body height and improved logic."""
        self.start_position = np.median(positions)
        
        # Calculate body height from recent detections
        if hasattr(self, 'body_heights') and self.body_heights:
            median_body_height = np.median(self.body_heights)
        else:
            # Fallback to standard deviation method if no body height data
            self.movement_range = np.std(positions) * 2
            median_body_height = max(60, self.movement_range)  # Minimum fallback
        
        # Define jumping thresholds based on body height ratios
        # For animals, a "jump" should be more conservative to avoid false positives
        # Real animal jumps are typically 50-80% of body height, but we detect smaller movements
        jump_ratio = 0.25  # 25% of body height for definitive jump (more conservative)
        movement_ratio = 0.15  # 15% of body height for movement detection (more selective)
        
        # Calculate thresholds
        jump_threshold = median_body_height * jump_ratio
        self.movement_range = max(median_body_height * movement_ratio * 2, 40)  # Minimum 40px
        
        # Use the larger threshold for more reliable detection
        detection_range = max(jump_threshold, self.movement_range / 2)
        
        # IMPORTANT: Move center reference away from resting position
        # The center line should be positioned where animal needs to jump UP to reach
        # This prevents counting when animal is just sitting/resting at initial position
        center_offset = median_body_height * 0.4  # Move center 40% of body height upward (much larger offset)
        self.center_reference = self.start_position - center_offset  # Higher up (smaller Y)
        
        # Calculate thresholds relative to the new center reference (not initial position)
        raw_up_threshold = self.center_reference - detection_range * 0.5  # Above center
        raw_down_threshold = self.center_reference + detection_range * 2.0  # Below center (must include initial position)
        
        # Ensure the initial resting position is well within the "down" zone
        min_distance_from_center = median_body_height * 0.2  # At least 20% of body height from center
        if abs(self.start_position - self.center_reference) < min_distance_from_center:
            # If still too close, move center even further up
            additional_offset = min_distance_from_center - abs(self.start_position - self.center_reference)
            self.center_reference -= additional_offset
        
        # Ensure thresholds are within video bounds with intelligent adjustment
        margin = 50
        video_height = 1080  # Could be made dynamic from frame.shape[0]
        
        # Apply bounds with intelligent adjustment
        if raw_up_threshold < margin:
            # Animal is too high in frame, shift detection zone down
            shift = margin - raw_up_threshold
            self.up_threshold = margin
            self.down_threshold = min(raw_down_threshold + shift, video_height - margin)
        elif raw_down_threshold > video_height - margin:
            # Animal is too low in frame, shift detection zone up
            shift = raw_down_threshold - (video_height - margin)
            self.down_threshold = video_height - margin
            self.up_threshold = max(raw_up_threshold - shift, margin)
        else:
            # Animal is well within bounds, use original calculations
            self.up_threshold = raw_up_threshold
            self.down_threshold = raw_down_threshold
        
        # Final safety check - ensure proper threshold order and minimum range
        if self.up_threshold >= self.down_threshold:
            # Emergency fallback: create small symmetric range around center
            center = self.start_position
            min_range = 40  # Minimum detection range
            self.up_threshold = max(center - min_range/2, margin)
            self.down_threshold = min(center + min_range/2, video_height - margin)
        
        # Recalculate movement range for consistency
        self.movement_range = self.down_threshold - self.up_threshold
        
        # Store body height info for debugging
        self.body_height = median_body_height
        self.jump_threshold_px = detection_range
        self.jump_ratio_used = detection_range / median_body_height if median_body_height > 0 else 0
    
    def _detect_bounce(self, center_y):
        """Detect bouncing movement pattern with adaptive sensitivity."""
        # Safety check - only run if thresholds are set
        if self.up_threshold is None or self.down_threshold is None:
            return
            
        if self.state == "start":
            if center_y > self.down_threshold:
                self.state = "down"
                self.stable_count = 0
        
        elif self.state == "down":
            if center_y < self.up_threshold:
                self.stable_count += 1
                if self.stable_count >= self.stable_frames:
                    self._increment_count()
                    self.state = "start"
                    self.stable_count = 0
            elif center_y < self.down_threshold:
                self.stable_count = 0
    
    def _detect_jump(self, center_y):
        """Detect jumping movement pattern optimized for animals."""
        # Safety check - only run if thresholds are set
        if self.up_threshold is None or self.start_position is None:
            return
            
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
        """Detect movement pattern that requires actually crossing the center reference line."""
        # Safety check - only run if calibration is complete
        if not self.calibrated or self.start_position is None:
            return
            
        # Use adjustable dead zone
        dead_zone_radius = self.get_current_dead_zone()
        
        # Use center_reference as the target line that must be crossed
        center_ref = getattr(self, 'center_reference', self.start_position)
        
        if self.state == "start":
            # Only trigger if animal moves significantly from resting position AND crosses center line
            distance_from_rest = abs(center_y - self.start_position)
            
            # First check: animal must move beyond dead zone from resting position
            if distance_from_rest > dead_zone_radius:
                # Second check: animal must actually cross the center reference line to count
                if center_y <= center_ref:  # Animal reached or crossed center line (jumped up)
                    self.state = "jumped"
                    self.stable_count = 0
                # If animal moves but doesn't reach center, don't count (just moving around)
        
        elif self.state == "jumped":
            # Animal has crossed center line, now wait for return to resting area
            # Return zone should be near the original resting position, not center
            return_zone = max(self.body_height * 0.2, 30) if hasattr(self, 'body_height') else 50
            
            # Count when animal returns to resting area after jumping
            if abs(center_y - self.start_position) < return_zone:
                self.stable_count += 1
                if self.stable_count >= self.stable_frames:
                    self._increment_count()
                    self.state = "start"
                    self.stable_count = 0
            else:
                # Reset stability if animal moves away from resting area again
                self.stable_count = 0
    
    def _detect_vertical_movement(self, center_y):
        """Default vertical movement detection with adaptive thresholds."""
        # Safety check - only run if thresholds are set
        if self.up_threshold is None or self.down_threshold is None or self.start_position is None:
            return
            
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
        print(f"🐱 CatCounter: {self.count} (cat)")
    
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
        
        # Draw threshold lines if calibrated (for movement detection)
        if self.calibrated and self.start_position is not None:
            # Use center_reference for the center line if available
            center_ref = getattr(self, 'center_reference', self.start_position)
            center_y = int(center_ref * scale_y)
            up_y = int(self.up_threshold * scale_y) if self.up_threshold is not None else center_y - 50
            down_y = int(self.down_threshold * scale_y) if self.down_threshold is not None else center_y + 50
            
            # Debug logging for line positions
            if hasattr(self, '_last_center_ref') and self._last_center_ref != center_ref:
                print(f"🎨 Drawing lines with NEW center_reference: {center_ref:.1f} (was {self._last_center_ref:.1f})")
                print(f"   Scaled center_y: {center_y}, up_y: {up_y}, down_y: {down_y}")
            self._last_center_ref = center_ref
            
            # Ensure lines are within frame bounds
            center_y = max(5, min(display_height - 5, center_y))
            up_y = max(5, min(display_height - 5, up_y))
            down_y = max(5, min(display_height - 5, down_y))
            
            # Draw threshold lines with proper width
            cv2.line(display_frame, (0, center_y), (display_width, center_y), (0, 255, 255), 3)  # Yellow center line
            cv2.line(display_frame, (0, up_y), (display_width, up_y), (0, 255, 0), 3)        # Green up line  
            cv2.line(display_frame, (0, down_y), (display_width, down_y), (255, 0, 0), 3)    # Blue down line
            
            # Add labels for movement detection
            cv2.putText(display_frame, "CENTER (JUMP TARGET)", (10, center_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            cv2.putText(display_frame, "HIGH JUMP", (10, up_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(display_frame, "REST ZONE", (10, down_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            # Show current animal position
            if detection:
                animal_center_y = (detection['bbox'][1] + detection['bbox'][3]) / 2
                animal_y_scaled = int(animal_center_y * scale_y)
                animal_x_center = display_width // 2
                cv2.circle(display_frame, (animal_x_center, animal_y_scaled), 5, (255, 255, 255), -1)  # White dot for animal center
        
        # Draw status info
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
            # Calculate dead zone for display
            dead_zone_radius = self.get_current_dead_zone()
            return_zone = max(self.body_height * 0.2, 30) if hasattr(self, 'body_height') else 50
            sensitivity_mult = getattr(self, 'sensitivity_multiplier', 1.0)
            
            status_lines.extend([
                f"Animal Y: {self.debug_info.get('position_y', 0):.1f}",
                f"Initial Pos: {self.start_position:.1f}",
                f"Center Ref: {getattr(self, 'center_reference', self.start_position):.1f} (ADJUSTABLE)",
                f"Body Height: {getattr(self, 'body_height', 0):.1f}px",
                f"Jump Threshold: {getattr(self, 'jump_threshold_px', 0):.1f}px",
                f"Dead Zone: ±{dead_zone_radius:.1f}px (×{sensitivity_mult:.1f})",
                f"Return Zone: ±{return_zone:.1f}px",
                f"Up Line: {self.up_threshold:.1f}",
                f"Down Line: {self.down_threshold:.1f}",
                f"State: {self.state}",
                f"Stable: {self.stable_count}/{self.stable_frames}"
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
    
    def adjust_center_line(self, direction, amount=10):
        """Adjust center reference line position in real-time."""
        if hasattr(self, 'center_reference') and self.center_reference is not None:
            if direction == 'up':
                self.center_reference -= amount  # Move up (smaller Y)
            elif direction == 'down':
                self.center_reference += amount  # Move down (larger Y)
            
            # Use actual frame dimensions instead of hardcoded 1080
            margin = 50
            if hasattr(self, 'original_frame_size') and self.original_frame_size:
                video_height = self.original_frame_size[1]  # height from stored frame size
            else:
                video_height = 1080  # fallback
            
            self.center_reference = max(margin, min(self.center_reference, video_height - margin))
            
            # Recalculate thresholds based on new center reference
            if hasattr(self, 'jump_threshold_px') and self.jump_threshold_px:
                detection_range = self.jump_threshold_px
                self.up_threshold = max(self.center_reference - detection_range * 0.5, margin)
                self.down_threshold = min(self.center_reference + detection_range * 2.0, video_height - margin)
            
            print(f"🎯 Center line moved {direction}: {self.center_reference:.1f}")
            print(f"   Up threshold: {self.up_threshold:.1f}")
            print(f"   Down threshold: {self.down_threshold:.1f}")
    
    def adjust_sensitivity(self, direction, factor=0.1):
        """Adjust detection sensitivity (dead zone size)."""
        if hasattr(self, 'body_height') and self.body_height > 0:
            current_dead_zone = max(15, self.body_height * 0.1)
            
            if direction == 'increase':
                # Increase dead zone (less sensitive)
                self.sensitivity_multiplier = getattr(self, 'sensitivity_multiplier', 1.0) + factor
                new_dead_zone = current_dead_zone * self.sensitivity_multiplier
                print(f"🔧 Sensitivity decreased (dead zone: {new_dead_zone:.1f}px)")
            elif direction == 'decrease':
                # Decrease dead zone (more sensitive)
                self.sensitivity_multiplier = max(0.3, getattr(self, 'sensitivity_multiplier', 1.0) - factor)
                new_dead_zone = current_dead_zone * self.sensitivity_multiplier
                print(f"🔧 Sensitivity increased (dead zone: {new_dead_zone:.1f}px)")
    
    def reset_to_auto_calibration(self):
        """Reset center line to automatically calibrated position."""
        if hasattr(self, 'body_height') and self.body_height > 0:
            # Recalculate original center reference
            center_offset = self.body_height * 0.4
            self.center_reference = self.start_position - center_offset
            self.sensitivity_multiplier = 1.0
            
            # Use actual frame dimensions
            margin = 50
            if hasattr(self, 'original_frame_size') and self.original_frame_size:
                video_height = self.original_frame_size[1]
            else:
                video_height = 1080
            
            # Recalculate thresholds
            detection_range = self.jump_threshold_px
            self.up_threshold = max(self.center_reference - detection_range * 0.5, margin)
            self.down_threshold = min(self.center_reference + detection_range * 2.0, video_height - margin)
            
            print(f"🔄 Reset to auto-calibrated center: {self.center_reference:.1f}")
            print(f"   Up threshold: {self.up_threshold:.1f}")
            print(f"   Down threshold: {self.down_threshold:.1f}")
    
    def get_current_dead_zone(self):
        """Get current dead zone radius with sensitivity adjustment."""
        if hasattr(self, 'body_height') and self.body_height > 0:
            base_dead_zone = max(15, self.body_height * 0.1)
            multiplier = getattr(self, 'sensitivity_multiplier', 1.0)
            return base_dead_zone * multiplier
        else:
            return max(20, self.threshold * 0.3) 
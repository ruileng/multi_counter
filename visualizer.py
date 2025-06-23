import cv2
import numpy as np

class Visualizer:
    def __init__(self, counter_name: str):
        self.counter_name = counter_name

    def draw_debug_info(self, frame, counter, landmarks):
        """
        Draws debugging information for the counter on the frame.
        """
        # --- Get relevant info from the counter ---
        state = counter.state
        landmark_idx = counter.landmark
        keypoint = landmarks.landmark[landmark_idx]
        
        # --- Draw a circle on the tracked landmark ---
        if keypoint.visibility > counter.min_visibility:
            height, width, _ = frame.shape
            center_coordinates = (int(keypoint.x * width), int(keypoint.y * height))
            cv2.circle(frame, center_coordinates, 10, (0, 255, 0), 3)

        # --- Display text info (state, validation score, etc.) ---
        if state == 'calibrating':
            info_text = f"Calibrating... ({counter.calibration_frames}/30)"
            cv2.putText(frame, info_text, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 165, 0), 2)
        else:
            info_text = f"State: {state.upper()}"
            cv2.putText(frame, info_text, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        
        # Display validation score
        validation_text = f"Validation: {counter.validation_score:.2f}"
        validation_color = (0, 255, 0) if counter.validation_score >= 0.4 else (0, 0, 255)
        cv2.putText(frame, validation_text, (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, validation_color, 2)
        
        # Show anti-cheat status if enabled
        if hasattr(counter, 'enable_anti_cheat') and counter.enable_anti_cheat:
            anti_cheat_text = f"Anti-Cheat: {'ON' if counter.enable_anti_cheat else 'OFF'}"
            cv2.putText(frame, anti_cheat_text, (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        
        # Show detailed debug info if available
        if hasattr(counter, 'debug_info') and counter.debug_info:
            debug = counter.debug_info
            
            # Show movement information
            if 'movement_from_start' in debug:
                movement_text = f"Movement: {debug['movement_from_start']:.3f}"
                cv2.putText(frame, movement_text, (10, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Show threshold information
            if 'threshold' in debug:
                threshold_text = f"Threshold: {debug['threshold']:.3f}"
                cv2.putText(frame, threshold_text, (10, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Show state conditions (updated field names)
            if 'is_down' in debug:
                down_status = "IS DOWN" if debug['is_down'] else "NOT DOWN"
                down_color = (0, 255, 0) if debug['is_down'] else (0, 0, 255)
                cv2.putText(frame, down_status, (10, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.7, down_color, 2)
            
            if 'is_up' in debug:
                up_status = "IS UP" if debug['is_up'] else "NOT UP"
                up_color = (0, 255, 0) if debug['is_up'] else (0, 0, 255)
                cv2.putText(frame, up_status, (10, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.7, up_color, 2)
            
            if 'is_at_start' in debug:
                start_status = "AT START" if debug['is_at_start'] else "NOT AT START"
                start_color = (0, 255, 0) if debug['is_at_start'] else (0, 0, 255)
                cv2.putText(frame, start_status, (10, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.7, start_color, 2)
            
            # Show form validation status
            if 'is_valid_form' in debug:
                form_status = "GOOD FORM" if debug['is_valid_form'] else "POOR FORM"
                form_color = (0, 255, 0) if debug['is_valid_form'] else (0, 0, 255)
                cv2.putText(frame, form_status, (10, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, form_color, 2)
            
            # Show stable counter
            if 'stable_counter' in debug:
                stable_text = f"Stable: {debug['stable_counter']}/{counter.stable_frames}"
                cv2.putText(frame, stable_text, (10, 390), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Show warning if validation is too low (but not during calibration)
        if counter.validation_score < 0.4 and state != 'calibrating':
            warning_text = "POOR FORM - Adjust your position"
            cv2.putText(frame, warning_text, (10, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # --- Draw movement visualization bars ---
        if counter.start_val is not None:
            self._draw_vertical_bar(frame, counter.start_val, keypoint.y, counter.threshold, counter.direction)

    def _draw_vertical_bar(self, frame, start_y_norm, current_y_norm, threshold_norm, direction):
        """
        Draws a vertical bar on the right side of the screen to show movement.
        Enhanced with better visibility and labels.
        """
        height, width, _ = frame.shape
        bar_x = width - 80  # Move further from edge
        bar_height = height - 200  # Make bar taller
        bar_start_y = 100
        
        # Draw the background of the bar (darker for better contrast)
        cv2.rectangle(frame, (bar_x - 15, bar_start_y), (bar_x + 15, bar_start_y + bar_height), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_x - 15, bar_start_y), (bar_x + 15, bar_start_y + bar_height), (200, 200, 200), 2)
        
        # Draw the current position (yellow ball)
        progress_y = int(bar_start_y + (current_y_norm * bar_height))
        cv2.circle(frame, (bar_x, progress_y), 20, (0, 255, 255), -1)  # Larger yellow ball
        cv2.circle(frame, (bar_x, progress_y), 20, (0, 0, 0), 2)  # Black outline

        # Draw the start position (green line)
        start_pixel_y = int(bar_start_y + (start_y_norm * bar_height))
        cv2.line(frame, (bar_x - 25, start_pixel_y), (bar_x + 25, start_pixel_y), (0, 255, 0), 3)

        # Draw the threshold lines (red lines)
        threshold_px = int(threshold_norm * bar_height)

        if direction == 'down-first':
            # Rep starts when we move down past the threshold
            threshold_y = start_pixel_y + threshold_px
            cv2.line(frame, (bar_x - 30, threshold_y), (bar_x + 30, threshold_y), (0, 0, 255), 4)  # Thicker red line
            # Add label
            cv2.putText(frame, "DOWN", (bar_x + 35, threshold_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        elif direction == 'up-first':
            # Rep starts when we move up past the threshold
            threshold_y = start_pixel_y - threshold_px
            cv2.line(frame, (bar_x - 30, threshold_y), (bar_x + 30, threshold_y), (0, 0, 255), 4)  # Thicker red line
            # Add label
            cv2.putText(frame, "UP", (bar_x + 35, threshold_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        # Add labels
        cv2.putText(frame, "START", (bar_x + 35, start_pixel_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, "CURRENT", (bar_x + 35, progress_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, "THRESH", (bar_x + 35, threshold_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    def _draw_jumping_jack_bar(self, frame, counter):
        """
        Draws a horizontal bar for jumping jack distance visualization.
        """
        if not hasattr(counter, 'debug_info') or not counter.debug_info:
            return
            
        debug = counter.debug_info
        if 'avg_distance' not in debug or 'start_val' not in debug:
            return
            
        height, width, _ = frame.shape
        bar_y = height - 100
        bar_width = width - 200
        bar_start_x = 100
        
        # Draw background bar
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (150, 150, 150), 2)
        
        # Calculate positions
        start_pos = int(bar_start_x + (counter.start_val * bar_width))
        current_pos = int(bar_start_x + (debug['avg_distance'] * bar_width))
        threshold_pos = int(bar_start_x + ((counter.start_val + counter.threshold) * bar_width))
        
        # Draw start position (green line)
        cv2.line(frame, (start_pos, bar_y - 30), (start_pos, bar_y + 30), (0, 255, 0), 3)
        cv2.putText(frame, "TOGETHER", (start_pos - 40, bar_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Draw threshold (red line)
        cv2.line(frame, (threshold_pos, bar_y - 30), (threshold_pos, bar_y + 30), (0, 0, 255), 4)
        cv2.putText(frame, "SPREAD", (threshold_pos - 30, bar_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # Draw current position (yellow ball)
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 255, 255), -1)
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 0, 0), 2)

    def _draw_distance_bar(self, frame, counter, landmarks):
        """
        Draws a bar for distance change visualization.
        """
        if not hasattr(counter, 'debug_info') or not counter.debug_info:
            return
            
        debug = counter.debug_info
        if 'current_distance' not in debug:
            return
            
        height, width, _ = frame.shape
        bar_y = height - 100
        bar_width = width - 200
        bar_start_x = 100
        
        # Draw background bar
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (150, 150, 150), 2)
        
        # Calculate positions (normalize distance to 0-1 range)
        max_distance = 0.5  # Maximum expected distance
        current_pos = int(bar_start_x + (debug['current_distance'] / max_distance) * bar_width)
        
        # Draw current position (yellow ball)
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 255, 255), -1)
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 0, 0), 2)
        
        # Add labels
        cv2.putText(frame, "DISTANCE", (bar_start_x, bar_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2) 
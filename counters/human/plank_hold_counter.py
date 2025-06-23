import mediapipe as mp
import numpy as np

class PlankHoldCounter:
    """
    A counter for the 'PlankHoldCounter' action, generated from a standardized template.
    This template focuses on robust, simple, and clear logic for exercise counting.
    Enhanced with optional anti-cheat validation using multiple landmarks.
    """
    def __init__(self):
        self.count = 0
        self.state = 'calibrating'  # Possible states: calibrating, start, down, up
        self.start_val = None
        self.calibration_frames = 0
        self.calibration_samples = []
        self.stable_counter = 0
        self.debug_info = {}
        self.validation_score = 1.0 # Start with a positive validation

        # --- Parameters from config ---
        self.logic_type = "vertical_movement"
        self.direction = "down-first"
        self.landmark = mp.solutions.pose.PoseLandmark.LEFT_SHOULDER.value
        self.aux_landmark = mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER.value
        self.min_visibility = 0.9
        self.threshold = 0.1
        self.stable_frames = 3
        
        # --- Anti-cheat validation landmarks (optional) ---
        self.validation_landmarks = [
            mp.solutions.pose.PoseLandmark.LEFT_SHOULDER.value,
            mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER.value,
            mp.solutions.pose.PoseLandmark.MOUTH_LEFT.value,
        ]
        self.enable_anti_cheat = True
        self.validation_threshold = 0.02
        
        # Store calibration values for validation landmarks
        self.validation_start_vals = {}

    def calibrate(self, current_val, landmarks=None):
        """Calibrates the starting position over a number of frames."""
        if self.calibration_frames < 30:
            self.calibration_samples.append(current_val)
            
            # Also calibrate validation landmarks if anti-cheat is enabled
            if self.enable_anti_cheat and landmarks:
                for val_landmark in self.validation_landmarks:
                    if val_landmark not in self.validation_start_vals:
                        self.validation_start_vals[val_landmark] = []
                    
                    val_keypoint = landmarks.landmark[val_landmark]
                    if val_keypoint.visibility > self.min_visibility:
                        self.validation_start_vals[val_landmark].append(val_keypoint.y)
            
            self.calibration_frames += 1
            return False
        
        self.start_val = np.median(self.calibration_samples)
        
        # Finalize validation landmark calibration
        if self.enable_anti_cheat:
            for val_landmark in self.validation_landmarks:
                if val_landmark in self.validation_start_vals and self.validation_start_vals[val_landmark]:
                    self.validation_start_vals[val_landmark] = np.median(self.validation_start_vals[val_landmark])
                else:
                    self.validation_start_vals[val_landmark] = None
        
        self.state = 'start'  # Set initial state after calibration
        self.calibration_samples = []
        print(f"[{self.__class__.__name__}] Calibration complete. Start value: {self.start_val:.3f}")
        return True

    def calculate_validation_score(self, landmarks, movement_from_start):
        """
        Calculates a validation score based on whether validation landmarks 
        are moving in coordination with the primary landmark.
        Returns a score between 0.0 (poor form/cheating) and 1.0 (good form).
        """
        if not self.enable_anti_cheat or not self.validation_landmarks:
            return 1.0
        
        valid_movements = 0
        total_landmarks = 0
        
        for val_landmark in self.validation_landmarks:
            if (val_landmark in self.validation_start_vals and 
                self.validation_start_vals[val_landmark] is not None):
                
                val_keypoint = landmarks.landmark[val_landmark]
                if val_keypoint.visibility > self.min_visibility:
                    val_movement = val_keypoint.y - self.validation_start_vals[val_landmark]
                    
                    # Check if validation landmark is moving in the same direction
                    # as the primary landmark (with some tolerance)
                    if abs(movement_from_start) > self.threshold:
                        # Primary landmark is moving significantly
                        if abs(val_movement) > self.validation_threshold:
                            # Validation landmark is also moving
                            # Check if they're moving in the same direction
                            if (movement_from_start > 0 and val_movement > 0) or \
                               (movement_from_start < 0 and val_movement < 0):
                                valid_movements += 1
                        # If validation landmark isn't moving much, it's suspicious
                    else:
                        # Primary landmark is near start, validation should be too
                        if abs(val_movement) < self.validation_threshold * 2:
                            valid_movements += 1
                    
                    total_landmarks += 1
        
        if total_landmarks == 0:
            return 1.0  # No validation landmarks available
        
        return valid_movements / total_landmarks

    def update(self, landmarks):
        """Updates the counter based on the new landmarks."""
        keypoint = landmarks.landmark[self.landmark]
        if keypoint.visibility < self.min_visibility:
            return self.count
        
        current_val = keypoint.y
        
        # --- Calibration Phase ---
        if self.state == 'calibrating':
            self.calibrate(current_val, landmarks)
            return self.count

        movement_from_start = current_val - self.start_val
        
        # --- Calculate validation score (anti-cheat) ---
        self.validation_score = self.calculate_validation_score(landmarks, movement_from_start)
        
        # --- State Conditions ---
        # Condition to enter the 'down' state (for down-first movements like squats/push-ups)
        is_down = movement_from_start > self.threshold
        # Condition to enter the 'up' state (for up-first movements)
        is_up = -movement_from_start > self.threshold
        # Condition to return to the 'start' state
        is_at_start = abs(movement_from_start) < (self.threshold * 0.5)
        
        # Apply anti-cheat validation - only count reps if validation score is good
        min_validation_score = 0.4  # Require at least 40% of validation landmarks to move properly
        is_valid_form = self.validation_score >= min_validation_score

        # Update debug info for the visualizer
        self.debug_info = {
            'movement_from_start': movement_from_start,
            'is_down': is_down,
            'is_up': is_up,
            'is_at_start': is_at_start,
            'stable_counter': self.stable_counter,
            'state': self.state,
            'validation_score': self.validation_score,
            'is_valid_form': is_valid_form,
            'anti_cheat_enabled': self.enable_anti_cheat
        }

        # --- State Machine (with validation) ---
        if self.direction == 'down-first':
            if self.state == 'start' and is_down and is_valid_form:
                self.state = 'down'
                print(f"[{self.__class__.__name__}] State: down (validation: {self.validation_score:.2f})")
            elif self.state == 'down' and is_at_start and is_valid_form:
                self.count += 1
                self.state = 'start'
                print(f"[{self.__class__.__name__}] Rep Complete! Count: {self.count} (validation: {self.validation_score:.2f})")
            elif (self.state == 'start' and is_down and not is_valid_form) or \
                 (self.state == 'down' and is_at_start and not is_valid_form):
                print(f"[{self.__class__.__name__}] Poor form detected! Validation: {self.validation_score:.2f}")

        elif self.direction == 'up-first':
            if self.state == 'start' and is_up and is_valid_form:
                self.state = 'up'
                print(f"[{self.__class__.__name__}] State: up (validation: {self.validation_score:.2f})")
            elif self.state == 'up' and is_at_start and is_valid_form:
                self.count += 1
                self.state = 'start'
                print(f"[{self.__class__.__name__}] Rep Complete! Count: {self.count} (validation: {self.validation_score:.2f})")
            elif (self.state == 'start' and is_up and not is_valid_form) or \
                 (self.state == 'up' and is_at_start and not is_valid_form):
                print(f"[{self.__class__.__name__}] Poor form detected! Validation: {self.validation_score:.2f}")
        
        return self.count
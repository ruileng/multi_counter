import cv2
import numpy as np

class Visualizer:
    def __init__(self, counter_name: str):
        self.counter_name = counter_name

    def draw_debug_info(self, frame, counter, landmarks):
        """
        在帧上为计数器绘制调试信息。
        """
        # --- 从计数器获取相关信息 ---
        state = counter.state
        landmark_idx = counter.landmark
        keypoint = landmarks.landmark[landmark_idx]
        
        # --- 在跟踪的关键点上绘制圆圈 ---
        if keypoint.visibility > counter.min_visibility:
            height, width, _ = frame.shape
            center_coordinates = (int(keypoint.x * width), int(keypoint.y * height))
            cv2.circle(frame, center_coordinates, 10, (0, 255, 0), 3)

        # --- 显示文本信息（状态、验证分数等）---
        if state == 'calibrating':
            info_text = f"校准中... ({counter.calibration_frames}/30)"
            cv2.putText(frame, info_text, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 165, 0), 2)
        else:
            info_text = f"状态: {state.upper()}"
            cv2.putText(frame, info_text, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        
        # 显示验证分数
        validation_text = f"验证: {counter.validation_score:.2f}"
        validation_color = (0, 255, 0) if counter.validation_score >= 0.4 else (0, 0, 255)
        cv2.putText(frame, validation_text, (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, validation_color, 2)
        
        # 如果启用反作弊功能，显示反作弊状态
        if hasattr(counter, 'enable_anti_cheat') and counter.enable_anti_cheat:
            anti_cheat_text = f"反作弊: {'开启' if counter.enable_anti_cheat else '关闭'}"
            cv2.putText(frame, anti_cheat_text, (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        
        # 如果可用，显示详细调试信息
        if hasattr(counter, 'debug_info') and counter.debug_info:
            debug = counter.debug_info
            
            # 显示运动信息
            if 'movement_from_start' in debug:
                movement_text = f"运动: {debug['movement_from_start']:.3f}"
                cv2.putText(frame, movement_text, (10, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # 显示阈值信息
            if 'threshold' in debug:
                threshold_text = f"阈值: {debug['threshold']:.3f}"
                cv2.putText(frame, threshold_text, (10, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # 显示状态条件（更新的字段名称）
            if 'is_down' in debug:
                down_status = "向下" if debug['is_down'] else "非向下"
                down_color = (0, 255, 0) if debug['is_down'] else (0, 0, 255)
                cv2.putText(frame, down_status, (10, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.7, down_color, 2)
            
            if 'is_up' in debug:
                up_status = "向上" if debug['is_up'] else "非向上"
                up_color = (0, 255, 0) if debug['is_up'] else (0, 0, 255)
                cv2.putText(frame, up_status, (10, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.7, up_color, 2)
            
            if 'is_at_start' in debug:
                start_status = "在起始位置" if debug['is_at_start'] else "非起始位置"
                start_color = (0, 255, 0) if debug['is_at_start'] else (0, 0, 255)
                cv2.putText(frame, start_status, (10, 330), cv2.FONT_HERSHEY_SIMPLEX, 0.7, start_color, 2)
            
            # 显示姿势验证状态
            if 'is_valid_form' in debug:
                form_status = "姿势良好" if debug['is_valid_form'] else "姿势不佳"
                form_color = (0, 255, 0) if debug['is_valid_form'] else (0, 0, 255)
                cv2.putText(frame, form_status, (10, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, form_color, 2)
            
            # 显示稳定计数器
            if 'stable_counter' in debug:
                stable_text = f"稳定: {debug['stable_counter']}/{counter.stable_frames}"
                cv2.putText(frame, stable_text, (10, 390), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 如果验证分数太低，显示警告（但校准期间不显示）
        if counter.validation_score < 0.4 and state != 'calibrating':
            warning_text = "姿势不佳 - 请调整您的位置"
            cv2.putText(frame, warning_text, (10, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # --- 绘制运动可视化条形图 ---
        if counter.start_val is not None:
            self._draw_vertical_bar(frame, counter.start_val, keypoint.y, counter.threshold, counter.direction)

    def _draw_vertical_bar(self, frame, start_y_norm, current_y_norm, threshold_norm, direction):
        """
        在屏幕右侧绘制垂直条形图以显示运动。
        增强可见性和标签的改进。
        """
        height, width, _ = frame.shape
        bar_x = width - 80  # 远离边缘移动
        bar_height = height - 200  # 使条形图更高
        bar_start_y = 100
        
        # 绘制条形图背景（更暗以获得更好的对比度）
        cv2.rectangle(frame, (bar_x - 15, bar_start_y), (bar_x + 15, bar_start_y + bar_height), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_x - 15, bar_start_y), (bar_x + 15, bar_start_y + bar_height), (200, 200, 200), 2)
        
        # 绘制当前位置（黄球）
        progress_y = int(bar_start_y + (current_y_norm * bar_height))
        cv2.circle(frame, (bar_x, progress_y), 20, (0, 255, 255), -1)  # 更大的黄球
        cv2.circle(frame, (bar_x, progress_y), 20, (0, 0, 0), 2)  # 黑色轮廓

        # 绘制起始位置（绿线）
        start_pixel_y = int(bar_start_y + (start_y_norm * bar_height))
        cv2.line(frame, (bar_x - 25, start_pixel_y), (bar_x + 25, start_pixel_y), (0, 255, 0), 3)

        # 绘制阈值线（红线）
        threshold_px = int(threshold_norm * bar_height)

        if direction == 'down-first':
            # 当我们向下移动超过阈值时开始重复
            threshold_y = start_pixel_y + threshold_px
            cv2.line(frame, (bar_x - 30, threshold_y), (bar_x + 30, threshold_y), (0, 0, 255), 4)  # 更粗的红线
            # 添加标签
            cv2.putText(frame, "向下", (bar_x + 35, threshold_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        elif direction == 'up-first':
            # 当我们向上移动超过阈值时开始重复
            threshold_y = start_pixel_y - threshold_px
            cv2.line(frame, (bar_x - 30, threshold_y), (bar_x + 30, threshold_y), (0, 0, 255), 4)  # 更粗的红线
            # 添加标签
            cv2.putText(frame, "向上", (bar_x + 35, threshold_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        # 添加标签
        cv2.putText(frame, "起始", (bar_x + 35, start_pixel_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, "当前", (bar_x + 35, progress_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, "阈值", (bar_x + 35, threshold_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    def _draw_jumping_jack_bar(self, frame, counter):
        """
        为开合跳距离可视化绘制水平条形图。
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
        
        # 绘制背景条形图
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (150, 150, 150), 2)
        
        # 计算位置
        start_pos = int(bar_start_x + (counter.start_val * bar_width))
        current_pos = int(bar_start_x + (debug['avg_distance'] * bar_width))
        threshold_pos = int(bar_start_x + ((counter.start_val + counter.threshold) * bar_width))
        
        # 绘制起始位置（绿线）
        cv2.line(frame, (start_pos, bar_y - 30), (start_pos, bar_y + 30), (0, 255, 0), 3)
        cv2.putText(frame, "并拢", (start_pos - 40, bar_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 绘制阈值（红线）
        cv2.line(frame, (threshold_pos, bar_y - 30), (threshold_pos, bar_y + 30), (0, 0, 255), 4)
        cv2.putText(frame, "分开", (threshold_pos - 30, bar_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # 绘制当前位置（黄球）
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 255, 255), -1)
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 0, 0), 2)

    def _draw_distance_bar(self, frame, counter, landmarks):
        """
        为距离变化可视化绘制条形图。
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
        
        # 绘制背景条形图
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_start_x, bar_y - 20), (bar_start_x + bar_width, bar_y + 20), (150, 150, 150), 2)
        
        # 计算位置（将距离标准化为0-1范围）
        max_distance = 0.5  # 预期的最大距离
        current_pos = int(bar_start_x + (debug['current_distance'] / max_distance) * bar_width)
        
        # 绘制当前位置（黄球）
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 255, 255), -1)
        cv2.circle(frame, (current_pos, bar_y), 15, (0, 0, 0), 2)
        
        # 添加标签
        cv2.putText(frame, "距离", (bar_start_x, bar_y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2) 
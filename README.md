# 🎯 Unified Multi-Counter System

A comprehensive real-time counting system that supports multiple detection technologies and counter types.

## 🌟 Features

### 🏃‍♀️ Human Action Counters (MediaPipe)
- **Exercise counting**: Push-ups, squats, jumping jacks, etc.
- **Real-time pose detection** using MediaPipe
- **Anti-cheat validation** for accurate counting
- **Customizable parameters** for different exercises

### 🐾 Animal Counters (YOLO)
- **Cat and dog movement detection**
- **Adaptive calibration** based on body size
- **Interactive keyboard controls** for threshold adjustment
- **Jump and movement pattern recognition**

### 🏀 Object Counters (YOLO)
- **Sports ball bounce detection**
- **Real-time object tracking**
- **Ground reference calibration**
- **Customizable sensitivity controls**

## 🚀 Quick Start

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Run Unified Web Interface
```bash
python unified_web_app.py
```
Access at: http://localhost:5000

### 3. Run Command Line Interface
```bash
# List available counters
python unified_main.py --list

# Run specific counter
python unified_main.py --counter SportsBallCounter --video 0

# Run with custom parameters
python unified_main.py --counter DogCounter --video 0 --threshold 50 --confidence 0.4
```

### 4. Admin Panel (Counter Management)
```bash
python admin_panel.py
```
Access at: http://localhost:5000

## 📊 Available Counter Types

### Human Action Counters
| Counter | Exercise | Detection |
|---------|----------|-----------|
| PushUpCounter | Push-ups | MediaPipe |
| SquatCounter | Squats | MediaPipe |
| JumpingJackCounter | Jumping Jacks | MediaPipe |
| BicepCurlCounter | Bicep Curls | MediaPipe |
| ... | Various exercises | MediaPipe |

### Animal Counters  
| Counter | Animal | Logic | Features |
|---------|--------|-------|----------|
| DogCounter | Dog | Movement Detection | Keyboard controls, adaptive calibration |
| CatCounter | Cat | Movement Detection | Keyboard controls, adaptive calibration |

### Object Counters
| Counter | Object | Logic | Features |
|---------|--------|-------|----------|
| SportsBallCounter | Sports Ball | Bounce Detection | Ground calibration, keyboard controls |

## 🎮 Keyboard Controls

### For Animal/Object Counters (YOLO):
- **W/S**: Move reference line UP/DOWN
- **+/-**: Adjust sensitivity (increase/decrease)
- **0**: Reset to auto-calibration
- **R**: Reset counter
- **Q**: Quit

### For All Counters:
- **R**: Reset counter
- **Q**: Quit

## 🛠️ System Architecture

```
📁 Unified Multi-Counter System
├── 🌐 Web Interface (unified_web_app.py)
├── 💻 Command Line (unified_main.py) 
├── ⚙️ Admin Panel (admin_panel.py)
├── 📊 Counter Modules
│   ├── 🏃‍♀️ Human (MediaPipe-based)
│   ├── 🐾 Animal (YOLO-based)
│   └── 🏀 Object (YOLO-based)
├── 🎨 Templates & UI
└── 📝 Documentation
```

## 📱 Web Interface Features

### Unified Dashboard
- **Categorized counter selection** (Human/Animal/Object)
- **Real-time video streaming**
- **Parameter configuration**
- **Session management**
- **Video file upload support**

### Live Statistics
- Current count display
- Session duration
- Detection confidence
- Counter type information

## ⚙️ Configuration Options

### MediaPipe Counters
```python
{
    "threshold": 40,           # Detection threshold
    "stable_frames": 5,        # Frames for stability
    "validation_threshold": 0.8, # Anti-cheat threshold
    "enable_anti_cheat": true  # Enable validation
}
```

### YOLO Counters
```python
{
    "threshold": 40,           # Detection threshold
    "confidence_threshold": 0.25, # YOLO confidence
    "stable_frames": 5,        # Stability frames
    "calibration_frames": 50   # Auto-calibration frames
}
```

## 🔧 Advanced Usage

### Adding New Counters
1. **Use Admin Panel** to generate new counters
2. **Or manually create** counter classes in `/counters/`
3. **Follow existing patterns** for MediaPipe or YOLO counters

### Custom Video Sources
- **Webcam**: Use `--video 0` or `--video 1`
- **Video file**: Use `--video path/to/video.mp4`
- **Web upload**: Use web interface upload feature

### Parameter Tuning
- **Threshold**: Sensitivity of detection
- **Confidence**: YOLO detection confidence
- **Stable frames**: How many frames to confirm detection
- **Calibration**: Auto-adjustment period for YOLO

## 🎯 Use Cases

### Fitness & Health
- **Personal training**: Count exercises automatically
- **Physical therapy**: Monitor rehabilitation exercises
- **Sports analysis**: Track athlete performance

### Pet Monitoring
- **Activity tracking**: Monitor pet movement and jumps
- **Behavior analysis**: Study pet activity patterns
- **Interactive play**: Engage pets with counting games

### Sports & Recreation
- **Ball games**: Count bounces, throws, catches
- **Training drills**: Automated repetition counting
- **Performance metrics**: Quantify sports activities

## 🔍 Troubleshooting

### Common Issues
1. **Camera not detected**: Check video source index
2. **Low detection accuracy**: Adjust threshold/confidence
3. **Keyboard controls not working**: Ensure counter is calibrated
4. **Web interface not loading**: Check port availability

### Performance Optimization
- **Reduce video resolution** for better performance
- **Adjust detection confidence** for accuracy vs speed
- **Use appropriate counter type** for your use case

## 📝 API Reference

### Counter Base Methods
```python
counter.update(frame)          # Update with new frame
counter.reset()                # Reset counter to 0
counter.get_debug_info()       # Get debug information
```

### YOLO Counter Extensions
```python
counter.adjust_center_line('up', 10)    # Move reference line
counter.adjust_sensitivity('increase')  # Change sensitivity
counter.reset_to_auto_calibration()     # Reset calibration
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Add new counter types or improve existing ones
4. Submit pull request with detailed description

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **MediaPipe** for human pose detection
- **YOLO** for object detection
- **OpenCV** for computer vision
- **Flask** for web interface

---

## 🎯 Quick Commands

```bash
# Web interface
python unified_web_app.py

# Command line - list counters
python unified_main.py --list

# Command line - specific counter
python unified_main.py --counter SportsBallCounter

# Admin panel
python admin_panel.py

# Legacy interfaces (still supported)
python main.py --counter PushUpCounter        # MediaPipe only
python yolo_main.py SportsBallCounter          # YOLO only
```

**🌟 The Unified Multi-Counter System brings together the best of both worlds - human action detection and object/animal tracking in one powerful, easy-to-use platform!** 
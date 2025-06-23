# 🏗️ Multi-Counter Project Structure

## 📁 Optimized Directory Structure

```
multiCounter/
├── 🌐 Core Web Application
│   ├── web_app.py              # Main web interface (user-facing)
│   ├── admin_panel.py          # Admin interface for counter management
│   └── templates/              # HTML templates
│       ├── index.html          # Main user interface
│       ├── admin_panel.html    # Admin panel interface
│       └── admin_login.html    # Admin login page
│
├── 🤖 Counter System
│   ├── counters/               # All counter implementations
│   │   ├── __init__.py         # Counter registry and loading system
│   │   ├── human/              # Human action counters (MediaPipe)
│   │   ├── animal/             # Animal counters (YOLO)
│   │   └── object/             # Object counters (YOLO)
│   ├── add_action.py           # Human counter generator
│   ├── yolo_generator.py       # YOLO counter generator
│   └── visualizer.py           # MediaPipe visualization
│
├── 🧠 YOLO Detection System
│   ├── yolo_tracker.py         # YOLO object tracking
│   ├── yolo_param_generator.py # YOLO parameter generation
│   └── yolov8n.pt             # YOLOv8 model weights
│
├── ⚙️ Configuration & Templates
│   ├── configs/                # Counter configuration files
│   └── templates/              # Code generation templates
│       ├── counter_template.py.j2         # MediaPipe counter template
│       ├── yolo_counter_template_v2.py.j2 # YOLO counter template
│       └── prompt_template.txt            # LLM prompt template
│
├── 📁 Data Directories
│   ├── videos/                 # Sample test videos
│   ├── uploads/                # User uploaded videos
│   ├── recordings/             # Recorded counter sessions
│   └── sessions/               # Saved session data
│
├── 🛠️ Utilities
│   ├── regenerate_counters.py  # Utility to regenerate all counters
│   └── requirements.txt        # Python dependencies
│
└── 📚 Documentation
    ├── README.md               # Main project documentation
    ├── PROJECT_SUMMARY.md      # Comprehensive feature summary
    └── PROJECT_STRUCTURE.md    # This file
```

## 🎯 Core Components

### **Web Interfaces**
- **`web_app.py`**: Main application serving the user interface at port 5000
- **`admin_panel.py`**: Administrative interface for counter management at port 5001

### **Counter System**
- **`counters/`**: Organized by type (human/animal/object) with automatic loading
- **`add_action.py`**: Generates MediaPipe-based human action counters using LLM
- **`yolo_generator.py`**: Creates YOLO-based animal and object counters

### **Detection Engines**
- **MediaPipe**: For human pose detection and exercise counting
- **YOLO**: For animal and object detection and movement tracking

### **Configuration**
- **`configs/`**: JSON configuration files for all generated counters
- **`templates/`**: Jinja2 templates for generating counter code

## 🚀 Key Features

### **User Interface (web_app.py)**
- ✅ Multi-counter support (18 built-in counters)
- ✅ Real-time video processing with webcam or uploaded videos
- ✅ Parameter adjustment (thresholds, sensitivity, center lines)
- ✅ Video recording with overlays
- ✅ Session saving and export

### **Admin Interface (admin_panel.py)**
- ✅ Counter generation (Human/Animal/Object)
- ✅ Counter deletion with force delete option
- ✅ System overview and statistics
- ✅ Categorized counter management

### **Counter Types**
- **Human Counters (15)**: Push-ups, squats, jumping jacks, etc.
- **Animal Counters (2)**: Cat and dog movement detection
- **Object Counters (1)**: Sports ball bounce detection

## 📦 Deployment Ready

### **Clean Structure**
- ❌ Removed redundant files (unified_*, main.py, yolo_main.py)
- ❌ Removed obsolete documentation files
- ❌ Removed test videos (kept 4 samples: dog.mp4, cat.mp4, bounce.mp4, squat.mp4)
- ❌ Removed IDE and cache files

### **Production Features**
- ✅ Robust error handling
- ✅ Threaded video processing
- ✅ File upload validation
- ✅ Session management
- ✅ Recording capabilities

## 🎬 Recording and Export

This version is optimized and ready for:
- **Demo recording**: Clean interface, no redundant files
- **Development**: Well-organized, maintainable structure
- **Deployment**: All functionality preserved, optimized file size

## 📊 File Count Summary

**Before Cleanup**: ~25 Python files + many redundant videos and docs
**After Cleanup**: 8 core Python files + essential templates and configs

**Size Reduction**: ~50% smaller while maintaining 100% functionality 
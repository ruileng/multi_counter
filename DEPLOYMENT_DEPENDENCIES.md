# 🚀 Deployment Dependencies Guide

## 📋 Current Environment Analysis

### **Development Environment Dependencies**
Based on the current conda environment `multi_counter`:

#### **🔥 GPU-Accelerated Dependencies (CUDA)**
```
torch==2.0.0+cu118              # PyTorch with CUDA 11.8 support
torchvision==0.15.1+cu118       # Computer vision with CUDA acceleration
```

#### **🤖 Core AI/ML Libraries**
```
ultralytics==8.3.157           # YOLOv8 object detection
mediapipe==0.10.11              # Google's pose detection
opencv-contrib-python==4.11.0.86 # Extended OpenCV functionality
opencv-python==4.6.0.66        # Computer vision processing
```

#### **🌐 Web Framework**
```
flask==3.0.3                   # Web application framework
jinja2==3.1.6                  # Template engine
werkzeug==3.0.6                # WSGI utilities
```

#### **📊 Data Processing**
```
numpy==1.24.4                  # Numerical computing
pandas==2.0.3                  # Data manipulation
pillow==10.4.0                 # Image processing
```

#### **🔧 Utilities**
```
requests==2.27.1               # HTTP requests
pyyaml==6.0.2                  # YAML configuration
tqdm==4.64.0                   # Progress bars
```

## ⚠️ **GPU vs CPU Deployment Considerations**

### **🎯 Current Setup (GPU-Optimized)**
- **CUDA Support**: PyTorch with CUDA 11.8 enables GPU acceleration
- **Performance**: Significantly faster YOLO inference (~5-10x speedup)
- **Memory**: GPU VRAM used for model inference
- **Use Case**: Development environment with NVIDIA GPU

### **☁️ CPU-Only Cloud Deployment**

#### **🔄 Required Changes for CPU Deployment**

1. **Replace CUDA PyTorch with CPU Version**:
```bash
# Remove CUDA versions
pip uninstall torch torchvision

# Install CPU-only versions
pip install torch==2.0.0+cpu torchvision==0.15.1+cpu -f https://download.pytorch.org/whl/torch_stable.html
```

2. **Performance Considerations**:
- **YOLO Inference**: 3-5x slower on CPU
- **MediaPipe**: Already optimized for CPU, minimal impact
- **Memory Usage**: Higher RAM usage instead of GPU VRAM

3. **Scaling Recommendations**:
- **Minimum**: 2 CPU cores, 4GB RAM
- **Recommended**: 4 CPU cores, 8GB RAM
- **Heavy Load**: 8 CPU cores, 16GB RAM

## 📦 Deployment-Ready Requirements Files

### **🖥️ CPU-Only Production (`requirements_cpu.txt`)**
```txt
# Core Web Framework
Flask==3.0.3
Jinja2==3.1.6
Werkzeug==3.0.6

# CPU-Only AI/ML Libraries
torch==2.0.0+cpu --find-links https://download.pytorch.org/whl/torch_stable.html
torchvision==0.15.1+cpu --find-links https://download.pytorch.org/whl/torch_stable.html
ultralytics==8.3.157
mediapipe==0.10.11

# Computer Vision (Headless for servers)
opencv-python-headless==4.6.0.66

# Data Processing
numpy==1.24.4
pandas==2.0.3
Pillow==10.4.0

# Utilities
requests==2.27.1
PyYAML==6.0.2
tqdm==4.64.0
```

### **🚀 GPU Production (`requirements_gpu.txt`)**
```txt
# Core Web Framework
Flask==3.0.3
Jinja2==3.1.6
Werkzeug==3.0.6

# GPU-Accelerated AI/ML Libraries
torch==2.0.0+cu118
torchvision==0.15.1+cu118
ultralytics==8.3.157
mediapipe==0.10.11

# Computer Vision
opencv-contrib-python==4.11.0.86

# Data Processing
numpy==1.24.4
pandas==2.0.3
Pillow==10.4.0

# Utilities
requests==2.27.1
PyYAML==6.0.2
tqdm==4.64.0
```

## 🔧 Platform-Specific Installation

### **☁️ Cloud Platforms (CPU-Only)**

#### **Heroku Deployment**
```bash
# Create requirements.txt for Heroku
cat > requirements.txt << EOF
Flask==3.0.3
torch==2.0.0+cpu --find-links https://download.pytorch.org/whl/torch_stable.html
torchvision==0.15.1+cpu --find-links https://download.pytorch.org/whl/torch_stable.html
ultralytics==8.3.157
mediapipe==0.10.11
opencv-python-headless==4.6.0.66
numpy==1.24.4
Pillow==10.4.0
requests==2.27.1
PyYAML==6.0.2
EOF
```

#### **Google Cloud Run / AWS Lambda**
```dockerfile
# CPU-optimized Dockerfile
FROM python:3.9-slim

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch
RUN pip install torch==2.0.0+cpu torchvision==0.15.1+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

# Install other dependencies
COPY requirements_cpu.txt .
RUN pip install -r requirements_cpu.txt
```

#### **Azure Container Instances**
```yaml
# azure-container.yaml
apiVersion: 2018-10-01
properties:
  containers:
  - name: multicounter
    properties:
      image: your-registry/multicounter:cpu
      resources:
        requests:
          cpu: 2
          memoryInGb: 4
      environmentVariables:
      - name: TORCH_CPU_ONLY
        value: "true"
```

### **🖥️ GPU-Enabled Deployment**

#### **NVIDIA Docker**
```dockerfile
# GPU-optimized Dockerfile
FROM nvidia/cuda:11.8-runtime-ubuntu20.04

# Install PyTorch with CUDA support
RUN pip install torch==2.0.0+cu118 torchvision==0.15.1+cu118
```

#### **Google Cloud AI Platform**
```bash
# Deploy with GPU support
gcloud run deploy multicounter \
  --image gcr.io/PROJECT/multicounter:gpu \
  --platform managed \
  --cpu 4 --memory 8Gi \
  --gpu 1 --gpu-type nvidia-tesla-t4
```

## ⚡ Performance Comparison

### **YOLO Inference Speed**
| Hardware | FPS (640x480) | FPS (1280x720) | Latency |
|----------|---------------|----------------|---------|
| **CPU (4 cores)** | 8-12 FPS | 3-5 FPS | 100-300ms |
| **GPU (GTX 1060)** | 35-45 FPS | 20-25 FPS | 20-50ms |
| **GPU (RTX 3070)** | 60+ FPS | 45+ FPS | 15-25ms |

### **MediaPipe Performance**
| Hardware | FPS Impact | Notes |
|----------|------------|--------|
| **CPU** | Minimal difference | Already CPU-optimized |
| **GPU** | Slight improvement | Some operations benefit from GPU |

## 🎯 Deployment Recommendations

### **For CPU-Only Cloud Deployment**
1. **Use `opencv-python-headless`** instead of full OpenCV
2. **Install CPU-only PyTorch** to reduce image size
3. **Optimize for memory usage** - limit concurrent requests
4. **Consider caching** model weights in container layers

### **For GPU-Enabled Deployment**
1. **Ensure CUDA compatibility** with deployment environment
2. **Use GPU-optimized base images** (nvidia/cuda)
3. **Monitor GPU memory usage** - YOLO models use ~2-4GB VRAM
4. **Scale based on GPU availability** rather than CPU cores

### **Hybrid Deployment Strategy**
```python
# Auto-detect GPU availability
import torch

if torch.cuda.is_available():
    print("🚀 GPU acceleration available")
    device = "cuda"
else:
    print("🖥️ Using CPU-only inference")
    device = "cpu"
```

## 📝 Migration Checklist

### **Before CPU-Only Deployment**
- [ ] Test with CPU-only PyTorch locally
- [ ] Measure performance impact on target resolution
- [ ] Adjust timeout settings for slower inference
- [ ] Update requirements.txt for CPU deployment
- [ ] Test model loading without CUDA

### **Performance Optimization for CPU**
- [ ] Reduce model input resolution if needed
- [ ] Implement frame skipping for real-time processing
- [ ] Use threading for UI responsiveness
- [ ] Consider model quantization for speed

This comprehensive guide ensures smooth deployment across different environments while maintaining optimal performance for your specific hardware setup. 
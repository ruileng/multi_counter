# 🎯 统一多计数器系统

一个支持多种检测技术和计数器类型的综合实时计数系统。

## 🌟 功能

### 🏃‍♀️ 人体动作计数器 (MediaPipe)
- **锻炼计数**：俯卧撑、深蹲、开合跳等。
- **实时姿态检测** 使用 MediaPipe
- **反作弊验证** 确保计数准确
- **可定制参数** 适用于不同的锻炼

### 🐾 动物计数器 (YOLO)
- **猫狗运动检测**
- **基于体型的自适应校准**
- **交互式键盘控制** 用于阈值调整
- **跳跃和运动模式识别**

### 🏀 物体计数器 (YOLO)
- **运动球弹跳检测**
- **实时物体跟踪**
- **地面参考校准**
- **可定制灵敏度控制**

## 🚀 快速开始

### 1. 安装
```bash
pip install -r requirements.txt
```

### 2. 运行统一网页界面
```bash
python unified_web_app.py
```
访问地址: http://localhost:5000

### 3. 运行命令行界面
```bash
# 列出可用计数器
python unified_main.py --list

# 运行特定计数器
python unified_main.py --counter SportsBallCounter --video 0

# 使用自定义参数运行
python unified_main.py --counter DogCounter --video 0 --threshold 50 --confidence 0.4
```

### 4. 管理面板 (计数器管理)
```bash
python admin_panel.py
```
访问地址: http://localhost:5000

## 📊 可用计数器类型

### 人体动作计数器
| 计数器 | 锻炼 | 检测 |
|---------|----------|-----------|
| PushUpCounter | 俯卧撑 | MediaPipe |
| SquatCounter | 深蹲 | MediaPipe |
| JumpingJackCounter | 开合跳 | MediaPipe |
| BicepCurlCounter | 二头肌弯举 | MediaPipe |
| ... | 各种锻炼 | MediaPipe |

### 动物计数器  
| 计数器 | 动物 | 逻辑 | 功能 |
|---------|--------|-------|----------|
| DogCounter | 狗 | 运动检测 | 键盘控制，自适应校准 |
| CatCounter | 猫 | 运动检测 | 键盘控制，自适应校准 |

### 物体计数器
| 计数器 | 物体 | 逻辑 | 功能 |
|---------|--------|-------|----------|
| SportsBallCounter | 运动球 | 弹跳检测 | 地面校准，键盘控制 |

## 🎮 键盘控制

### 对于动物/物体计数器 (YOLO):
- **W/S**: 向上/向下移动参考线
- **+/-**: 调整灵敏度（增加/减少）
- **0**: 重置为自动校准
- **R**: 重置计数器
- **Q**: 退出

### 对于所有计数器:
- **R**: 重置计数器
- **Q**: 退出

## 🛠️ 系统架构

```
📁 统一多计数器系统
├── 🌐 网页界面 (unified_web_app.py)
├── 💻 命令行 (unified_main.py) 
├── ⚙️ 管理面板 (admin_panel.py)
├── 📊 计数器模块
│   ├── 🏃‍♀️ 人体 (基于 MediaPipe)
│   ├── 🐾 动物 (基于 YOLO)
│   └── 🏀 物体 (基于 YOLO)
├── 🎨 模板和用户界面
└── 📝 文档
```

## 📱 网页界面功能

### 统一仪表盘
- **分类计数器选择** (人体/动物/物体)
- **实时视频流**
- **参数配置**
- **会话管理**
- **视频文件上传支持**

### 实时统计
- 当前计数显示
- 会话持续时间
- 检测置信度
- 计数器类型信息

## ⚙️ 配置选项

### MediaPipe 计数器
```python
{
    "threshold": 40,           # 检测阈值
    "stable_frames": 5,        # 稳定帧数
    "validation_threshold": 0.8, # 反作弊阈值
    "enable_anti_cheat": true  # 启用验证
}
```

### YOLO 计数器
```python
{
    "threshold": 40,           # 检测阈值
    "confidence_threshold": 0.25, # YOLO 置信度
    "stable_frames": 5,        # 稳定帧数
    "calibration_frames": 50   # 自动校准帧数
}
```

## 🔧 高级用法

### 添加新计数器
1. **使用管理面板** 生成新计数器
2. **或手动创建** 计数器类在 `/counters/`
3. **遵循现有模式** 用于 MediaPipe 或 YOLO 计数器

### 自定义视频源
- **摄像头**: 使用 `--video 0` 或 `--video 1`
- **视频文件**: 使用 `--video path/to/video.mp4`
- **网页上传**: 使用网页界面上传功能

### 参数调整
- **阈值**: 检测灵敏度
- **置信度**: YOLO 检测置信度
- **稳定帧数**: 确认检测的帧数
- **校准**: YOLO 的自动调整周期

## 🎯 使用案例

### 健身与健康
- **个人训练**: 自动计数锻炼
- **物理治疗**: 监控康复锻炼
- **体育分析**: 跟踪运动员表现

### 宠物监控
- **活动跟踪**: 监控宠物运动和跳跃
- **行为分析**: 研究宠物活动模式
- **互动游戏**: 通过计数游戏与宠物互动

### 体育与娱乐
- **球类运动**: 计数弹跳、投掷、接球
- **训练演练**: 自动重复计数
- **性能指标**: 量化体育活动

## 🔍 故障排除

### 常见问题
1. **未检测到摄像头**: 检查视频源索引
2. **检测精度低**: 调整阈值/置信度
3. **键盘控制无效**: 确保计数器已校准
4. **网页界面未加载**: 检查端口可用性

### 性能优化
- **降低视频分辨率** 以提高性能
- **调整检测置信度** 以平衡精度与速度
- **使用适当的计数器类型** 适合您的用例

## 📝 API 参考

### 计数器基本方法
```python
counter.update(frame)          # 使用新帧更新
counter.reset()                # 将计数器重置为0
counter.get_debug_info()       # 获取调试信息
```

### YOLO 计数器扩展
```python
counter.adjust_center_line('up', 10)    # 移动参考线
counter.adjust_sensitivity('increase')  # 改变灵敏度
counter.reset_to_auto_calibration()     # 重置校准
```

## 🤝 贡献

1. Fork 仓库
2. 创建功能分支: `git checkout -b feature-name`
3. 添加新计数器类型或改进现有计数器
4. 提交详细描述的 pull request

## 📄 许可证

此项目根据 MIT 许可证授权 - 详情请参阅 LICENSE 文件。

## 🙏 鸣谢

- **MediaPipe** 用于人体姿态检测
- **YOLO** 用于物体检测
- **OpenCV** 用于计算机视觉
- **Flask** 用于网页界面

---

## 🎯 快速命令

```bash
# 网页界面
python unified_web_app.py

# 命令行 - 列出计数器
python unified_main.py --list

# 命令行 - 特定计数器
python unified_main.py --counter SportsBallCounter

# 管理面板
python admin_panel.py

# 旧版界面（仍受支持）
python main.py --counter PushUpCounter        # 仅限 MediaPipe
python yolo_main.py SportsBallCounter          # 仅限 YOLO
```

**🌟 统一多计数器系统结合了人体动作检测和物体/动物跟踪的最佳功能，提供了一个强大且易于使用的平台！** 
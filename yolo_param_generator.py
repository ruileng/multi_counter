"""
使用LLM的YOLO参数生成器
使用Ollama为基于YOLO的计数器生成最优参数。
"""

import json
import subprocess
import sys
from yolo_tracker import YOLO_CLASSES

def generate_yolo_parameters(object_class, counter_type="general"):
    """
    使用LLM生成YOLO计数器参数。
    
    Args:
        object_class: YOLO对象类别（例如："dog", "sports ball"）
        counter_type: 计数器类型（"animal", "object", "vehicle"）
    """
    
    # 确定类别
    category = "object"  # 默认
    for cat, classes in YOLO_CLASSES.items():
        if object_class in classes:
            if cat == "animals":
                category = "animal"
            elif cat in ["sports", "objects"]:
                category = "object"
            elif cat == "vehicles":
                category = "vehicle"
            break
    
    # 根据类别创建专门的提示
    prompt = create_yolo_prompt(object_class, category)
    
    try:
        print(f"🤖 使用LLM为{object_class}（{category}）生成参数...")
        
        # 调用Ollama
        result = subprocess.run([
            'ollama', 'run', 'llama3', prompt
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ LLM错误: {result.stderr}")
            return get_default_parameters(object_class, category)
        
        # 解析LLM响应
        response = result.stdout.strip()
        parameters = parse_llm_response(response, object_class, category)
        
        print(f"✅ 为{object_class}生成了参数")
        return parameters
        
    except subprocess.TimeoutExpired:
        print("⏰ LLM超时，使用默认参数")
        return get_default_parameters(object_class, category)
    except Exception as e:
        print(f"❌ 生成参数时出错: {e}")
        return get_default_parameters(object_class, category)

def create_yolo_prompt(object_class, category):
    """为不同对象类别创建专门的提示。"""
    
    base_prompt = f"""
你是计算机视觉和对象跟踪方面的专家。为跟踪"{object_class}"的基于YOLO的计数器生成最优参数。

对象类别: {category}
可用逻辑类型:
- bounce_detection: 用于弹跳物体（球类、弹跳动物）
- jump_detection: 用于跳跃物体（动物、人）
- movement_detection: 用于一般运动跟踪
- oscillation: 用于来回运动

需要确定的参数:
1. logic_type: 选择最合适的检测逻辑
2. threshold: 像素运动阈值（20-100）
3. confidence_threshold: YOLO检测置信度（0.3-0.9）
4. stable_frames: 确认检测的帧数（1-10）
5. direction: 运动方向偏好（如果适用）

"""

    if category == "animal":
        specific_prompt = f"""
对于动物跟踪（{object_class}）:
- 考虑自然运动模式
- 动物可能有部分运动（非完整跳跃）
- 不同动物有不同的运动速度
- 考虑体型大小和典型行为

示例行为:
- 狗: 跳跃、跑步、玩耍
- 猫: 潜行、扑跃、攀爬
- 鸟: 跳跃、飞行、栖息
- 马: 奔跑、跳跃、小跑

生成能准确检测完整运动周期同时避免部分运动误报的参数。
"""
    
    elif category == "object":
        specific_prompt = f"""
对于物体跟踪（{object_class}）:
- 考虑物体运动的物理规律
- 物体遵循可预测的运动模式
- 体育球弹跳一致
- 考虑物体大小和重量影响

示例行为:
- 体育球: 弹跳、滚动、被投掷
- 瓶子/杯子: 被拿起、移动、放置
- 工具: 被使用、移动、操作

为此物体的特定物理规律和典型使用生成优化的参数。
"""
    
    else:  # vehicle
        specific_prompt = f"""
对于车辆跟踪（{object_class}）:
- 车辆以可预测的模式移动
- 考虑典型速度和运动类型
- 考虑大小差异
- 专注于进入/退出检测

为车辆运动或通过计数生成参数。
"""

    format_prompt = """
仅用以下精确格式响应有效的JSON对象:
{
    "logic_type": "bounce_detection|jump_detection|movement_detection|oscillation",
    "threshold": 30,
    "confidence_threshold": 0.7,
    "stable_frames": 3,
    "reasoning": "参数选择的简要说明"
}

JSON:"""

    return base_prompt + specific_prompt + format_prompt

def parse_llm_response(response, object_class, category):
    """解析LLM响应并提取参数。"""
    try:
        # 在响应中找到JSON
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            raise ValueError("响应中未找到JSON")
        
        json_str = response[json_start:json_end]
        params = json.loads(json_str)
        
        # 验证参数
        params = validate_parameters(params, object_class, category)
        
        return params
        
    except Exception as e:
        print(f"⚠️  解析LLM响应时出错: {e}")
        print(f"原始响应: {response}")
        return get_default_parameters(object_class, category)

def validate_parameters(params, object_class, category):
    """验证并在需要时纠正参数。"""
    
    # 验证logic_type
    valid_logic_types = ["bounce_detection", "jump_detection", "movement_detection", "oscillation"]
    if params.get("logic_type") not in valid_logic_types:
        if category == "animal":
            params["logic_type"] = "jump_detection"
        elif "ball" in object_class:
            params["logic_type"] = "bounce_detection"
        else:
            params["logic_type"] = "movement_detection"
    
    # 验证threshold
    threshold = params.get("threshold", 30)
    params["threshold"] = max(20, min(100, int(threshold)))
    
    # 验证confidence_threshold
    confidence = params.get("confidence_threshold", 0.7)
    params["confidence_threshold"] = max(0.3, min(0.9, float(confidence)))
    
    # 验证stable_frames
    frames = params.get("stable_frames", 3)
    params["stable_frames"] = max(1, min(10, int(frames)))
    
    return params

def get_default_parameters(object_class, category):
    """根据对象类别获取默认参数。"""
    
    if category == "animal":
        return {
            "logic_type": "jump_detection",
            "threshold": 40,
            "confidence_threshold": 0.6,
            "stable_frames": 4,
            "reasoning": "默认动物参数 - 跳跃检测的中等敏感度"
        }
    elif "ball" in object_class:
        return {
            "logic_type": "bounce_detection",
            "threshold": 35,
            "confidence_threshold": 0.7,
            "stable_frames": 3,
            "reasoning": "默认球类参数 - 为弹跳检测优化"
        }
    else:
        return {
            "logic_type": "movement_detection",
            "threshold": 30,
            "confidence_threshold": 0.5,
            "stable_frames": 3,
            "reasoning": "默认物体参数 - 一般运动检测"
        }

def test_parameter_generation():
    """测试不同对象类型的参数生成。"""
    
    test_objects = [
        ("dog", "animal"),
        ("sports ball", "object"),
        ("cat", "animal"),
        ("car", "vehicle"),
        ("bird", "animal")
    ]
    
    print("🧪 测试YOLO参数生成\n")
    
    for obj, expected_category in test_objects:
        print(f"测试: {obj}")
        params = generate_yolo_parameters(obj)
        print(f"  逻辑: {params['logic_type']}")
        print(f"  阈值: {params['threshold']}px")
        print(f"  置信度: {params['confidence_threshold']}")
        print(f"  稳定帧数: {params['stable_frames']}")
        print(f"  原因: {params['reasoning']}")
        print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        object_class = sys.argv[1]
        params = generate_yolo_parameters(object_class)
        print(json.dumps(params, indent=2))
    else:
        test_parameter_generation() 
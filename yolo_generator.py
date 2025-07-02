"""
YOLO计数器生成器
使用YOLO检测和LLM集成为动物和物体创建计数器。
"""

import os
import json
from jinja2 import Environment, FileSystemLoader
from yolo_tracker import YOLO_CLASSES
from yolo_param_generator import generate_yolo_parameters

def generate_yolo_counter(object_class, use_llm=True, **manual_params):
    """
    为指定对象生成基于YOLO的计数器。
    
    Args:
        object_class: YOLO对象类别（例如："dog", "sports ball"）
        use_llm: 是否使用LLM进行参数生成
        **manual_params: 手动参数覆盖
    """
    
    # 确定类别和文件夹
    category, folder = determine_category_and_folder(object_class)
    
    # 生成参数
    if use_llm and not manual_params:
        print(f"🤖 使用LLM为 {object_class} 生成参数...")
        params = generate_yolo_parameters(object_class)
    else:
        print(f"📝 为 {object_class} 使用手动参数...")
        params = manual_params or get_default_params_by_category(category)
    
    # 生成类名
    class_name = ''.join(word.capitalize() for word in object_class.split()) + "Counter"
    
    # 加载模板
    env = Environment(loader=FileSystemLoader('./templates'))
    template = env.get_template('yolo_counter_template_v2.py.j2')
    
    # 生成代码
    code = template.render(
        class_name=class_name,
        object_class=object_class,
        logic_type=params.get('logic_type', 'movement_detection'),
        threshold=params.get('threshold', 30),
        confidence_threshold=params.get('confidence_threshold', 0.5),
        stable_frames=params.get('stable_frames', 3)
    )
    
    # 如果文件夹不存在则创建
    folder_path = os.path.join('./counters', folder)
    os.makedirs(folder_path, exist_ok=True)
    
    # 保存到适当的文件夹
    filename = f"{object_class.replace(' ', '_').lower()}_counter.py"
    filepath = os.path.join(folder_path, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)
    
    print(f"✅ 生成YOLO计数器: {filepath}")
    
    # 返回用于JSON存储的配置
    config = {
        "name": class_name,
        "detection_type": "yolo",
        "object_class": object_class,
        "category": category,
        "folder": folder,
        "logic_type": params.get('logic_type', 'movement_detection'),
        "threshold": params.get('threshold', 30),
        "confidence_threshold": params.get('confidence_threshold', 0.5),
        "stable_frames": params.get('stable_frames', 3),
        "reasoning": params.get('reasoning', '生成的参数')
    }
    
    return config

def determine_category_and_folder(object_class):
    """确定对象的类别和适当的文件夹。"""
    
    for category, classes in YOLO_CLASSES.items():
        if object_class in classes:
            if category == "animals":
                return "animal", "animal"
            elif category in ["sports", "objects"]:
                return "object", "object"
            elif category == "vehicles":
                return "vehicle", "object"  # 将车辆放在object文件夹
    
    return "object", "object"  # 默认

def get_default_params_by_category(category):
    """根据类别获取默认参数。"""
    
    if category == "animal":
        return {
            "logic_type": "jump_detection",
            "threshold": 40,
            "confidence_threshold": 0.6,
            "stable_frames": 4
        }
    elif category == "object":
        return {
            "logic_type": "movement_detection",
            "threshold": 30,
            "confidence_threshold": 0.5,
            "stable_frames": 3
        }
    else:  # vehicle
        return {
            "logic_type": "movement_detection",
            "threshold": 50,
            "confidence_threshold": 0.7,
            "stable_frames": 5
        }

def create_sample_counters():
    """创建示例YOLO计数器用于使用LLM参数进行测试。"""
    
    sample_objects = [
        "dog",
        "cat", 
        "sports ball",
        "bird",
        "horse"
    ]
    
    configs = []
    for object_class in sample_objects:
        try:
            generated_config = generate_yolo_counter(object_class, use_llm=True)
            configs.append(generated_config)
        except Exception as e:
            print(f"❌ 生成 {object_class} 计数器时出错: {e}")
            # 回退到手动参数
            generated_config = generate_yolo_counter(object_class, use_llm=False)
            configs.append(generated_config)
    
    return configs

def regenerate_existing_counters():
    """使用LLM参数和适当的组织重新生成现有计数器。"""
    
    existing_objects = [
        "dog",
        "cat", 
        "sports ball"
    ]
    
    print("🔄 使用LLM参数重新生成现有计数器...")
    
    configs = []
    for object_class in existing_objects:
        try:
            config = generate_yolo_counter(object_class, use_llm=True)
            configs.append(config)
        except Exception as e:
            print(f"❌ 重新生成 {object_class} 计数器时出错: {e}")
    
    return configs

def list_yolo_options():
    """打印YOLO计数器生成的可用选项。"""
    print("🎯 YOLO计数器生成器选项\n")
    
    print("📂 可用对象类别:")
    for category, classes in YOLO_CLASSES.items():
        folder = "animal" if category == "animals" else "object"
        print(f"\n  {category.title()} → counters/{folder}/:")
        for cls in classes:
            print(f"    • {cls}")
    
    print("\n🔧 逻辑类型（LLM自动选择）:")
    print("  • bounce_detection - 用于弹跳物体（球类、弹跳动物）")
    print("  • jump_detection - 用于跳跃动作（动物、人）")
    print("  • movement_detection - 用于一般运动跟踪")
    print("  • oscillation - 用于来回运动")
    
    print("\n⚙️  参数（LLM优化）:")
    print("  • threshold: 像素运动距离（20-100）")
    print("  • confidence_threshold: YOLO检测置信度（0.3-0.9）")
    print("  • stable_frames: 确认检测的帧数（1-10）")
    
    print("\n🤖 LLM集成:")
    print("  • 基于对象类型的自动参数优化")
    print("  • 特定类别的行为分析")
    print("  • 基于物理的参数选择")

if __name__ == "__main__":
    print("🚀 带LLM集成的YOLO计数器生成器\n")
    
    # 显示可用选项
    list_yolo_options()
    
    print("\n" + "="*60)
    print("🧪 使用LLM参数重新生成现有计数器...")
    
    # 重新生成现有计数器
    configs = regenerate_existing_counters()
    
    print(f"\n✅ 重新生成了 {len(configs)} 个YOLO计数器:")
    for config in configs:
        print(f"  • {config['name']} ({config['object_class']}) → counters/{config['folder']}/")
        print(f"    逻辑: {config['logic_type']}, 阈值: {config['threshold']}px")
    
    print("\n🎉 YOLO计数器已准备好，使用LLM优化的参数!") 
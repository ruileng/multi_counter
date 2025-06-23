"""
YOLO Counter Generator
Creates counters for animals and objects using YOLO detection with LLM-generated parameters.
"""

import os
import json
from jinja2 import Environment, FileSystemLoader
from yolo_tracker import YOLO_CLASSES
from yolo_param_generator import generate_yolo_parameters

def generate_yolo_counter(object_class, use_llm=True, **manual_params):
    """
    Generate a YOLO-based counter for the specified object.
    
    Args:
        object_class: YOLO object class (e.g., "dog", "sports ball")
        use_llm: Whether to use LLM for parameter generation
        **manual_params: Manual parameter overrides
    """
    
    # Determine category and folder
    category, folder = determine_category_and_folder(object_class)
    
    # Generate parameters
    if use_llm and not manual_params:
        print(f"🤖 Using LLM to generate parameters for {object_class}...")
        params = generate_yolo_parameters(object_class)
    else:
        print(f"📝 Using manual parameters for {object_class}...")
        params = manual_params or get_default_params_by_category(category)
    
    # Generate class name
    class_name = ''.join(word.capitalize() for word in object_class.split()) + "Counter"
    
    # Load template
    env = Environment(loader=FileSystemLoader('./templates'))
    template = env.get_template('yolo_counter_template_v2.py.j2')
    
    # Generate code
    code = template.render(
        class_name=class_name,
        object_class=object_class,
        logic_type=params.get('logic_type', 'movement_detection'),
        threshold=params.get('threshold', 30),
        confidence_threshold=params.get('confidence_threshold', 0.5),
        stable_frames=params.get('stable_frames', 3)
    )
    
    # Create folder if it doesn't exist
    folder_path = os.path.join('./counters', folder)
    os.makedirs(folder_path, exist_ok=True)
    
    # Save to appropriate folder
    filename = f"{object_class.replace(' ', '_').lower()}_counter.py"
    filepath = os.path.join(folder_path, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)
    
    print(f"✅ Generated YOLO counter: {filepath}")
    
    # Return config for JSON storage
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
        "reasoning": params.get('reasoning', 'Generated parameters')
    }
    
    return config

def determine_category_and_folder(object_class):
    """Determine category and appropriate folder for the object."""
    
    for category, classes in YOLO_CLASSES.items():
        if object_class in classes:
            if category == "animals":
                return "animal", "animal"
            elif category in ["sports", "objects"]:
                return "object", "object"
            elif category == "vehicles":
                return "vehicle", "object"  # Put vehicles in object folder
    
    return "object", "object"  # Default

def get_default_params_by_category(category):
    """Get default parameters based on category."""
    
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
    """Create sample YOLO counters for testing with LLM parameters."""
    
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
            print(f"❌ Error generating {object_class} counter: {e}")
            # Fallback to manual parameters
            generated_config = generate_yolo_counter(object_class, use_llm=False)
            configs.append(generated_config)
    
    return configs

def regenerate_existing_counters():
    """Regenerate existing counters with LLM parameters and proper organization."""
    
    existing_objects = [
        "dog",
        "cat", 
        "sports ball"
    ]
    
    print("🔄 Regenerating existing counters with LLM parameters...")
    
    configs = []
    for object_class in existing_objects:
        try:
            config = generate_yolo_counter(object_class, use_llm=True)
            configs.append(config)
        except Exception as e:
            print(f"❌ Error regenerating {object_class} counter: {e}")
    
    return configs

def list_yolo_options():
    """Print available YOLO options for counter generation."""
    print("🎯 YOLO Counter Generator Options\n")
    
    print("📂 Available Object Classes:")
    for category, classes in YOLO_CLASSES.items():
        folder = "animal" if category == "animals" else "object"
        print(f"\n  {category.title()} → counters/{folder}/:")
        for cls in classes:
            print(f"    • {cls}")
    
    print("\n🔧 Logic Types (Auto-selected by LLM):")
    print("  • bounce_detection - For bouncing objects (balls, bouncing animals)")
    print("  • jump_detection - For jumping motions (animals, people)")
    print("  • movement_detection - For general movement tracking")
    print("  • oscillation - For back-and-forth movement")
    
    print("\n⚙️  Parameters (Optimized by LLM):")
    print("  • threshold: Movement distance in pixels (20-100)")
    print("  • confidence_threshold: YOLO detection confidence (0.3-0.9)")
    print("  • stable_frames: Frames to confirm detection (1-10)")
    
    print("\n🤖 LLM Integration:")
    print("  • Automatic parameter optimization based on object type")
    print("  • Category-specific behavior analysis")
    print("  • Physics-based parameter selection")

if __name__ == "__main__":
    print("🚀 YOLO Counter Generator with LLM Integration\n")
    
    # Show available options
    list_yolo_options()
    
    print("\n" + "="*60)
    print("🧪 Regenerating Existing Counters with LLM Parameters...")
    
    # Regenerate existing counters
    configs = regenerate_existing_counters()
    
    print(f"\n✅ Regenerated {len(configs)} YOLO counters:")
    for config in configs:
        print(f"  • {config['name']} ({config['object_class']}) → counters/{config['folder']}/")
        print(f"    Logic: {config['logic_type']}, Threshold: {config['threshold']}px")
    
    print("\n🎉 YOLO counters ready with LLM-optimized parameters!") 
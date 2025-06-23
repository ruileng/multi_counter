"""
YOLO Parameter Generator using LLM
Generates optimal parameters for YOLO-based counters using Ollama.
"""

import json
import subprocess
import sys
from yolo_tracker import YOLO_CLASSES

def generate_yolo_parameters(object_class, counter_type="general"):
    """
    Generate YOLO counter parameters using LLM.
    
    Args:
        object_class: YOLO object class (e.g., "dog", "sports ball")
        counter_type: Type of counter ("animal", "object", "vehicle")
    """
    
    # Determine category
    category = "object"  # default
    for cat, classes in YOLO_CLASSES.items():
        if object_class in classes:
            if cat == "animals":
                category = "animal"
            elif cat in ["sports", "objects"]:
                category = "object"
            elif cat == "vehicles":
                category = "vehicle"
            break
    
    # Create specialized prompt based on category
    prompt = create_yolo_prompt(object_class, category)
    
    try:
        print(f"🤖 Generating parameters for {object_class} ({category}) using LLM...")
        
        # Call Ollama
        result = subprocess.run([
            'ollama', 'run', 'llama3', prompt
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ LLM error: {result.stderr}")
            return get_default_parameters(object_class, category)
        
        # Parse LLM response
        response = result.stdout.strip()
        parameters = parse_llm_response(response, object_class, category)
        
        print(f"✅ Generated parameters for {object_class}")
        return parameters
        
    except subprocess.TimeoutExpired:
        print("⏰ LLM timeout, using default parameters")
        return get_default_parameters(object_class, category)
    except Exception as e:
        print(f"❌ Error generating parameters: {e}")
        return get_default_parameters(object_class, category)

def create_yolo_prompt(object_class, category):
    """Create specialized prompt for different object categories."""
    
    base_prompt = f"""
You are an expert in computer vision and object tracking. Generate optimal parameters for a YOLO-based counter that tracks "{object_class}".

Object Category: {category}
Available Logic Types:
- bounce_detection: For objects that bounce (balls, bouncing animals)
- jump_detection: For objects that jump (animals, people)
- movement_detection: For general movement tracking
- oscillation: For back-and-forth movement

Parameters to determine:
1. logic_type: Choose the most appropriate detection logic
2. threshold: Movement threshold in pixels (20-100)
3. confidence_threshold: YOLO detection confidence (0.3-0.9)
4. stable_frames: Frames to confirm detection (1-10)
5. direction: Movement direction preference if applicable

"""

    if category == "animal":
        specific_prompt = f"""
For ANIMAL tracking ({object_class}):
- Consider natural movement patterns
- Animals may have partial movements (not full jumps)
- Different animals have different movement speeds
- Account for body size and typical behavior

Example behaviors:
- Dogs: jumping, running, playing
- Cats: stalking, pouncing, climbing
- Birds: hopping, flying, perching
- Horses: galloping, jumping, trotting

Generate parameters that accurately detect complete movement cycles while avoiding false positives from partial movements.
"""
    
    elif category == "object":
        specific_prompt = f"""
For OBJECT tracking ({object_class}):
- Consider physics of object movement
- Objects follow predictable motion patterns
- Sports balls bounce consistently
- Consider object size and weight effects

Example behaviors:
- Sports balls: bouncing, rolling, being thrown
- Bottles/cups: being picked up, moved, placed
- Tools: being used, moved, manipulated

Generate parameters optimized for the specific physics and typical usage of this object.
"""
    
    else:  # vehicle
        specific_prompt = f"""
For VEHICLE tracking ({object_class}):
- Vehicles move in predictable patterns
- Consider typical speeds and movement types
- Account for size differences
- Focus on entry/exit detection

Generate parameters for counting vehicle movements or passages.
"""

    format_prompt = """
Respond ONLY with a valid JSON object in this exact format:
{
    "logic_type": "bounce_detection|jump_detection|movement_detection|oscillation",
    "threshold": 30,
    "confidence_threshold": 0.7,
    "stable_frames": 3,
    "reasoning": "Brief explanation of parameter choices"
}

JSON:"""

    return base_prompt + specific_prompt + format_prompt

def parse_llm_response(response, object_class, category):
    """Parse LLM response and extract parameters."""
    try:
        # Find JSON in response
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            raise ValueError("No JSON found in response")
        
        json_str = response[json_start:json_end]
        params = json.loads(json_str)
        
        # Validate parameters
        params = validate_parameters(params, object_class, category)
        
        return params
        
    except Exception as e:
        print(f"⚠️  Error parsing LLM response: {e}")
        print(f"Raw response: {response}")
        return get_default_parameters(object_class, category)

def validate_parameters(params, object_class, category):
    """Validate and correct parameters if needed."""
    
    # Validate logic_type
    valid_logic_types = ["bounce_detection", "jump_detection", "movement_detection", "oscillation"]
    if params.get("logic_type") not in valid_logic_types:
        if category == "animal":
            params["logic_type"] = "jump_detection"
        elif "ball" in object_class:
            params["logic_type"] = "bounce_detection"
        else:
            params["logic_type"] = "movement_detection"
    
    # Validate threshold
    threshold = params.get("threshold", 30)
    params["threshold"] = max(20, min(100, int(threshold)))
    
    # Validate confidence_threshold
    confidence = params.get("confidence_threshold", 0.7)
    params["confidence_threshold"] = max(0.3, min(0.9, float(confidence)))
    
    # Validate stable_frames
    frames = params.get("stable_frames", 3)
    params["stable_frames"] = max(1, min(10, int(frames)))
    
    return params

def get_default_parameters(object_class, category):
    """Get default parameters based on object category."""
    
    if category == "animal":
        return {
            "logic_type": "jump_detection",
            "threshold": 40,
            "confidence_threshold": 0.6,
            "stable_frames": 4,
            "reasoning": "Default animal parameters - moderate sensitivity for jump detection"
        }
    elif "ball" in object_class:
        return {
            "logic_type": "bounce_detection",
            "threshold": 35,
            "confidence_threshold": 0.7,
            "stable_frames": 3,
            "reasoning": "Default ball parameters - optimized for bounce detection"
        }
    else:
        return {
            "logic_type": "movement_detection",
            "threshold": 30,
            "confidence_threshold": 0.5,
            "stable_frames": 3,
            "reasoning": "Default object parameters - general movement detection"
        }

def test_parameter_generation():
    """Test parameter generation for different object types."""
    
    test_objects = [
        ("dog", "animal"),
        ("sports ball", "object"),
        ("cat", "animal"),
        ("car", "vehicle"),
        ("bird", "animal")
    ]
    
    print("🧪 Testing YOLO Parameter Generation\n")
    
    for obj, expected_category in test_objects:
        print(f"Testing: {obj}")
        params = generate_yolo_parameters(obj)
        print(f"  Logic: {params['logic_type']}")
        print(f"  Threshold: {params['threshold']}px")
        print(f"  Confidence: {params['confidence_threshold']}")
        print(f"  Stable Frames: {params['stable_frames']}")
        print(f"  Reasoning: {params['reasoning']}")
        print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        object_class = sys.argv[1]
        params = generate_yolo_parameters(object_class)
        print(json.dumps(params, indent=2))
    else:
        test_parameter_generation() 
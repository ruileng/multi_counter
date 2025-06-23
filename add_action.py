import os
import json
import re
import argparse
import ollama
from jinja2 import Environment, FileSystemLoader

# --- Configuration Paths ---
CONFIG_PATH = './configs/generated_counter_config.json'
PARAM_TEMPLATE_DIR = './templates'
COUNTER_TEMPLATE_DIR = './templates'
OUTPUT_DIR_HUMAN = './counters/human'  # For MediaPipe counters

# --- Part 1: Parameter Generation (from param_generator/generate_params.py) ---

def load_prompt_template():
    """Loads the prompt template from the file."""
    try:
        env = Environment(loader=FileSystemLoader(PARAM_TEMPLATE_DIR))
        return env.get_template('prompt_template.txt')
    except Exception as e:
        print(f"Error loading prompt template: {e}")
        return None

def normalize_llm_response(llm_config):
    """
    Normalizes the LLM response to match the expected field names.
    """
    if not llm_config:
        return None
    
    # Create a normalized config with expected field names
    normalized = {}
    
    # Map class_name to name
    normalized['name'] = llm_config.get('class_name', llm_config.get('name', 'UnknownCounter'))
    
    # Map logic_type
    normalized['logic_type'] = llm_config.get('logic_type', 'vertical_movement')
    
    # Map direction
    normalized['direction'] = llm_config.get('direction', 'up-first')
    
    # Map landmark names (handle both old and new field names)
    normalized['landmark_name'] = llm_config.get('landmark_name', 
                                                llm_config.get('primary_landmark_name', 'NOSE'))
    
    normalized['aux_landmark_name'] = llm_config.get('aux_landmark_name', 
                                                    llm_config.get('auxiliary_landmark_name', None))
    
    # Map confidence and threshold
    normalized['min_conf'] = llm_config.get('min_conf', 
                                           llm_config.get('min_confidence', 0.5))
    
    normalized['threshold'] = llm_config.get('threshold', 0.05)
    normalized['stable_frames'] = llm_config.get('stable_frames', 10)
    
    # Map anti-cheat validation parameters
    normalized['enable_anti_cheat'] = llm_config.get('enable_anti_cheat', False)
    normalized['validation_landmarks'] = llm_config.get('validation_landmarks', [])
    normalized['validation_threshold'] = llm_config.get('validation_threshold', 0.03)
    
    return normalized

def generate_config_from_llm(action_name: str, template):
    """Generates a single counter configuration by calling the Ollama LLM."""
    if not template:
        return None
    prompt = template.render(exercise_name=action_name)
    print(f"\n--- Generating config for: {action_name} ---")
    try:
        response = ollama.chat(
            model='llama3',
            messages=[{'role': 'user', 'content': prompt}],
            format='json' # Request JSON output directly
        )
        content = response['message']['content']
        print(f"LLM Response: {content}")
        raw_config = json.loads(content)
        # Normalize the response
        normalized_config = normalize_llm_response(raw_config)
        print(f"Normalized config: {normalized_config}")
        return normalized_config
    except Exception as e:
        print(f"An error occurred while communicating with Ollama or parsing JSON: {e}")
        return None

def update_config_file(new_configs):
    """Appends new configurations to the main config file, avoiding duplicates."""
    if not new_configs:
        print("No new configurations to add.")
        return
    
    existing_configs = []
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                raw_configs = json.load(f)
                # Normalize existing configs to ensure they have the right format
                for cfg in raw_configs:
                    normalized = normalize_llm_response(cfg)
                    if normalized:
                        existing_configs.append(normalized)
            except json.JSONDecodeError:
                print("Warning: Config file is empty or malformed. Starting fresh.")
    
    # Get existing names using the normalized format
    existing_names = {cfg['name'] for cfg in existing_configs}
    
    for new_cfg in new_configs:
        if new_cfg and new_cfg.get('name') not in existing_names:
            existing_configs.append(new_cfg)
            print(f"Adding new counter config: {new_cfg.get('name')}")
        else:
            print(f"Counter '{new_cfg.get('name')}' already exists or is invalid. Skipping.")
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(existing_configs, f, indent=2)
    print(f"\nSuccessfully updated {CONFIG_PATH}")


# --- Part 2: Code Generation (from generate_counter.py) ---

def camel_to_snake(name):
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

def generate_all_counters():
    """Reads the entire config file and generates all counter modules."""
    print("\n--- Generating counter code ---")
    try:
        if not os.path.exists(CONFIG_PATH):
            print(f"Error: Config file {CONFIG_PATH} does not exist.")
            return False
            
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            configs = json.load(f)
            
        if not configs:
            print("Warning: Config file is empty.")
            return True
            
        print(f"Found {len(configs)} counter configurations")
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: Cannot read or parse {CONFIG_PATH}: {e}")
        return False

    try:
        env = Environment(loader=FileSystemLoader(COUNTER_TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)
        template = env.get_template('counter_template.py.j2')
    except Exception as e:
        print(f"Error loading template: {e}")
        return False

    # Ensure output directories exist
    os.makedirs(OUTPUT_DIR_HUMAN, exist_ok=True)

    success_count = 0
    for i, cfg in enumerate(configs):
        try:
            class_name = cfg.get('name')
            if not class_name:
                print(f"Warning: Config {i} has no name, skipping")
                continue
                
            print(f"Generating {class_name}...")
            
            params = {
                'class_name': class_name,
                'logic_type': cfg.get('logic_type', 'vertical_movement'),
                'direction': cfg.get('direction', 'up-first'),
                'threshold': cfg.get('threshold', 0.1),
                'min_conf': cfg.get('min_conf', 0.7),
                'stable_frames': cfg.get('stable_frames', 3),
                'landmark_name': cfg.get('landmark_name', 'NOSE'),
                'aux_landmark_name': cfg.get('aux_landmark_name'),
                'enable_anti_cheat': cfg.get('enable_anti_cheat', False),
                'validation_landmarks': cfg.get('validation_landmarks', []),
                'validation_threshold': cfg.get('validation_threshold', 0.03)
            }
            
            code = template.render(**params)
            # All configs in generated_counter_config.json are human/MediaPipe counters
            output_path = os.path.join(OUTPUT_DIR_HUMAN, f"{camel_to_snake(class_name)}.py")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(code)
                
            print(f"✓ Generated {output_path}")
            success_count += 1
            
        except Exception as e:
            print(f"✗ Error generating {cfg.get('name', 'unknown')}: {e}")
            continue

    print(f"\nGeneration complete: {success_count}/{len(configs)} counters generated successfully")
    return success_count > 0

# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser(description="A tool to automatically add new action counters.")
    parser.add_argument('actions', nargs='+', help='A list of action names to generate configs for (e.g., "bicep curls", "jumping jacks").')
    args = parser.parse_args()

    # Step 1: Generate parameters from LLM
    prompt_template = load_prompt_template()
    if not prompt_template:
        return
    
    new_configs = []
    for action in args.actions:
        config = generate_config_from_llm(action, prompt_template)
        if config:
            new_configs.append(config)
    
    # Step 2: Update the master JSON config file
    update_config_file(new_configs)
    
    # Step 3: Regenerate all counter code from the updated config
    generate_all_counters()

    print("\nProcess complete. New counters are ready to use.")

if __name__ == '__main__':
    main() 
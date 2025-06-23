import json
import os
import re
from jinja2 import Environment, FileSystemLoader

def camel_to_snake(name):
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

def main():
    # Read the configuration
    with open('./configs/generated_counter_config.json', 'r', encoding='utf-8') as f:
        configs = json.load(f)
    
    # Set up template environment
    env = Environment(loader=FileSystemLoader('./templates'), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template('counter_template.py.j2')
    
    # Generate each counter
    for cfg in configs:
        class_name = cfg['name']
        params = {
            'class_name': class_name,
            'logic_type': cfg.get('logic_type', 'vertical_movement'),
            'direction': cfg.get('direction', 'up-first'),
            'threshold': cfg.get('threshold', 0.1),
            'min_conf': cfg.get('min_conf', 0.7),
            'stable_frames': cfg.get('stable_frames', 3),
            'landmark_name': cfg.get('landmark_name'),
            'aux_landmark_name': cfg.get('aux_landmark_name')
        }
        
        code = template.render(**params)
        output_path = os.path.join('./counters', f"{camel_to_snake(class_name)}.py")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"Generated {output_path}")
    
    print("All counters regenerated successfully!")

if __name__ == '__main__':
    main() 
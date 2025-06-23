from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
import time
from add_action import generate_config_from_llm, load_prompt_template, generate_all_counters, normalize_llm_response
from counters import list_counters, reload_counters
from unified_main import categorize_counters  # Import the categorization function

app = Flask(__name__)

# Simple password protection (in production, use proper authentication)
ADMIN_PASSWORD = "dev123"  # Change this!

def list_counters_by_category():
    """Returns counters organized by category for admin panel."""
    from counters import list_counters, get_counter
    
    categorized = {
        'Human': [],
        'Animal': [],
        'Object': []
    }
    
    all_counters = list_counters()
    for counter_name in all_counters:
        try:
            CounterClass = get_counter(counter_name)
            if CounterClass:
                temp_counter = CounterClass()
                
                # Determine counter type
                counter_type = 'mediapipe'  # default
                if hasattr(temp_counter, 'detection_type'):
                    counter_type = temp_counter.detection_type
                elif hasattr(temp_counter, 'object_class') and hasattr(temp_counter, 'tracker'):
                    counter_type = 'yolo'
                
                counter_info = {
                    'name': counter_name,
                    'type': counter_type,
                    'object_class': getattr(temp_counter, 'object_class', 'human'),
                    'logic_type': getattr(temp_counter, 'logic_type', 'exercise'),
                    'confidence_threshold': getattr(temp_counter, 'confidence_threshold', 0.5),
                    'threshold': getattr(temp_counter, 'threshold', 40),
                    'stable_frames': getattr(temp_counter, 'stable_frames', 5),
                    'description': getattr(temp_counter, 'description', ''),
                    'has_center_line': hasattr(temp_counter, 'adjust_center_line') or hasattr(temp_counter, 'start_position') or hasattr(temp_counter, 'center_reference')
                }
                
                if counter_type == 'yolo':
                    if counter_info['object_class'] in ['cat', 'dog', 'bird', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe']:
                        categorized['Animal'].append(counter_info)
                    else:
                        categorized['Object'].append(counter_info)
                else:
                    categorized['Human'].append(counter_info)
        except Exception:
            # Silently skip problematic counters
            pass
    
    return categorized

@app.route('/')
def admin_login():
    """Admin login page"""
    return render_template('admin_login.html')

@app.route('/login', methods=['POST'])
def login():
    """Handle admin login"""
    password = request.form.get('password')
    if password == ADMIN_PASSWORD:
        return redirect(url_for('admin_panel'))
    else:
        return render_template('admin_login.html', error="Invalid password")

@app.route('/admin')
def admin_panel():
    """Main admin panel with categorized counter view"""
    # Get categorized counters
    categorized_counters = list_counters_by_category()
    
    # Load current config
    config_path = './configs/generated_counter_config.json'
    current_config = []
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            current_config = json.load(f)
    
    # Count counters by type
    total_counters = sum(len(category) for category in categorized_counters.values())
    
    return render_template('admin_panel.html', 
                         categorized_counters=categorized_counters,
                         current_config=current_config,
                         total_counters=total_counters)

@app.route('/generate_human_counter', methods=['POST'])
def generate_human_counter():
    """Generate a new human action counter using MediaPipe"""
    try:
        data = request.get_json()
        exercise_name = data.get('exercise_name')
        
        if not exercise_name:
            return jsonify({'error': 'Exercise name is required'}), 400
        
        print(f"Generating human counter for: {exercise_name}")
        
        # Load prompt template
        template = load_prompt_template()
        if not template:
            return jsonify({'error': 'Could not load prompt template'}), 500
        
        # Generate config from LLM with specific human exercise context
        config = generate_config_from_llm(exercise_name, template)
        if not config:
            return jsonify({'error': 'Failed to generate counter config'}), 500
        
        # Ensure it's configured as a human counter
        config['detection_type'] = 'mediapipe'
        config['object_class'] = 'human'
        
        # Load existing config and check for duplicates
        config_path = './configs/generated_counter_config.json'
        existing_configs = []
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                existing_configs = json.load(f)
        
        existing_names = {cfg['name'] for cfg in existing_configs}
        if config['name'] in existing_names:
            return jsonify({'error': f'Counter {config["name"]} already exists'}), 400
        
        # Add new config
        existing_configs.append(config)
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(existing_configs, f, indent=2)
        
        # Regenerate all counter code
        success = generate_all_counters()
        if success:
            time.sleep(0.5)
            reload_counters()
            return jsonify({
                'success': True, 
                'message': f'Human counter {config["name"]} generated successfully',
                'config': config
            })
        else:
            return jsonify({'error': 'Failed to generate counter code'}), 500
        
    except Exception as e:
        print(f"Error in generate_human_counter: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_animal_counter', methods=['POST'])
def generate_animal_counter():
    """Generate a new animal counter using YOLO"""
    try:
        data = request.get_json()
        animal_type = data.get('animal_type')
        logic_type = data.get('logic_type', 'movement_detection')
        
        if not animal_type:
            return jsonify({'error': 'Animal type is required'}), 400
        
        print(f"Generating animal counter for: {animal_type} with logic: {logic_type}")
        
        # Create YOLO counter config for animals
        config = {
            'name': f'{animal_type.title()}Counter',
            'class_name': f'{animal_type.title()}Counter',
            'object_class': animal_type.lower(),
            'detection_type': 'yolo',
            'logic_type': logic_type,
            'threshold': 40,
            'confidence_threshold': 0.4,
            'stable_frames': 5,
            'calibration_frames': 30,
            'description': f'YOLO-based {animal_type} {logic_type} counter'
        }
        
        # Load existing config and check for duplicates
        config_path = './configs/yolo_counter_config.json'
        os.makedirs('./configs', exist_ok=True)
        
        existing_configs = []
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                existing_configs = json.load(f)
        
        existing_names = {cfg['name'] for cfg in existing_configs}
        if config['name'] in existing_names:
            return jsonify({'error': f'Counter {config["name"]} already exists'}), 400
        
        # Add new config
        existing_configs.append(config)
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(existing_configs, f, indent=2)
        
        # Generate YOLO counter using the yolo_generator
        from yolo_generator import generate_yolo_counter
        success = generate_yolo_counter(config)
        
        if success:
            reload_counters()
            return jsonify({
                'success': True, 
                'message': f'Animal counter {config["name"]} generated successfully',
                'config': config
            })
        else:
            return jsonify({'error': 'Failed to generate YOLO counter code'}), 500
        
    except Exception as e:
        print(f"Error in generate_animal_counter: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_object_counter', methods=['POST'])
def generate_object_counter():
    """Generate a new object counter using YOLO"""
    try:
        data = request.get_json()
        object_type = data.get('object_type')
        logic_type = data.get('logic_type', 'bounce_detection')
        
        if not object_type:
            return jsonify({'error': 'Object type is required'}), 400
        
        print(f"Generating object counter for: {object_type} with logic: {logic_type}")
        
        # Create YOLO counter config for objects
        config = {
            'name': f'{object_type.title().replace(" ", "")}Counter',
            'class_name': f'{object_type.title().replace(" ", "")}Counter',
            'object_class': object_type.lower(),
            'detection_type': 'yolo',
            'logic_type': logic_type,
            'threshold': 40,
            'confidence_threshold': 0.25,  # Lower for objects
            'stable_frames': 5,
            'calibration_frames': 30,
            'description': f'YOLO-based {object_type} {logic_type} counter'
        }
        
        # Load existing config and check for duplicates
        config_path = './configs/yolo_counter_config.json'
        os.makedirs('./configs', exist_ok=True)
        
        existing_configs = []
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                existing_configs = json.load(f)
        
        existing_names = {cfg['name'] for cfg in existing_configs}
        if config['name'] in existing_names:
            return jsonify({'error': f'Counter {config["name"]} already exists'}), 400
        
        # Add new config
        existing_configs.append(config)
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(existing_configs, f, indent=2)
        
        # Generate YOLO counter using the yolo_generator
        from yolo_generator import generate_yolo_counter
        success = generate_yolo_counter(config)
        
        if success:
            reload_counters()
            return jsonify({
                'success': True, 
                'message': f'Object counter {config["name"]} generated successfully',
                'config': config
            })
        else:
            return jsonify({'error': 'Failed to generate YOLO counter code'}), 500
        
    except Exception as e:
        print(f"Error in generate_object_counter: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_counter', methods=['POST'])
def generate_counter():
    """Generate a new counter (legacy endpoint for backward compatibility)"""
    try:
        data = request.get_json()
        exercise_name = data.get('exercise_name')
        
        if not exercise_name:
            return jsonify({'error': 'Exercise name is required'}), 400
        
        print(f"Generating counter for: {exercise_name}")  # Debug log
        
        # Load prompt template
        template = load_prompt_template()
        if not template:
            return jsonify({'error': 'Could not load prompt template'}), 500
        
        # Generate config from LLM
        config = generate_config_from_llm(exercise_name, template)
        if not config:
            return jsonify({'error': 'Failed to generate counter config'}), 500
        
        print(f"Generated config: {config}")  # Debug log
        
        # Load existing config
        config_path = './configs/generated_counter_config.json'
        existing_configs = []
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                existing_configs = json.load(f)
        
        # Check for duplicates
        existing_names = {cfg['name'] for cfg in existing_configs}
        if config['name'] in existing_names:
            return jsonify({'error': f'Counter {config["name"]} already exists'}), 400
        
        # Add new config
        existing_configs.append(config)
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(existing_configs, f, indent=2)
        
        print("Config saved, generating counter code...")  # Debug log
        
        # Regenerate all counter code
        try:
            success = generate_all_counters()
            if success:
                print("Counter code generated successfully")  # Debug log
                # Small delay to ensure file operations complete
                time.sleep(0.5)
                # Reload counters to make them available immediately
                reload_counters()
                print("Counters reloaded successfully")
            else:
                print("Counter code generation failed")
                return jsonify({'error': 'Failed to generate counter code'}), 500
        except Exception as gen_error:
            print(f"Error generating counter code: {gen_error}")
            return jsonify({'error': f'Failed to generate counter code: {str(gen_error)}'}), 500
        
        return jsonify({
            'success': True, 
            'message': f'Counter {config["name"]} generated successfully',
            'config': config
        })
        
    except Exception as e:
        print(f"Error in generate_counter: {e}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/delete_counter', methods=['POST'])
def delete_counter():
    """Delete a counter"""
    try:
        data = request.get_json()
        counter_name = data.get('counter_name')
        
        if not counter_name:
            return jsonify({'error': 'Counter name is required'}), 400
        
        print(f"Deleting counter: {counter_name}")  # Debug log
        
        # Step 1: Remove from config file
        config_path = './configs/generated_counter_config.json'
        if not os.path.exists(config_path):
            return jsonify({'error': 'Config file not found'}), 404
        
        with open(config_path, 'r') as f:
            configs = json.load(f)
        
        # Remove the counter
        original_count = len(configs)
        configs = [cfg for cfg in configs if cfg['name'] != counter_name]
        
        if len(configs) == original_count:
            return jsonify({'error': f'Counter {counter_name} not found in config'}), 404
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(configs, f, indent=2)
        
        print(f"Removed {counter_name} from config, {len(configs)} remaining")
        
        # Step 2: Find and delete the counter file
        from counters import get_counter
        counter_class = get_counter(counter_name)
        subdir = 'human'  # Default fallback
        
        if counter_class:
            try:
                # Determine the counter type and directory
                temp_counter = counter_class()
                counter_type = 'mediapipe'  # default
                if hasattr(temp_counter, 'detection_type'):
                    counter_type = temp_counter.detection_type
                elif hasattr(temp_counter, 'object_class') and hasattr(temp_counter, 'tracker'):
                    counter_type = 'yolo'
                
                # Determine subdirectory based on counter type
                if counter_type == 'yolo':
                    if hasattr(temp_counter, 'object_class'):
                        obj_class = temp_counter.object_class
                        if obj_class in ['cat', 'dog', 'bird', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe']:
                            subdir = 'animal'
                        else:
                            subdir = 'object'
                    else:
                        subdir = 'object'
                else:
                    subdir = 'human'
            except Exception as e:
                print(f"Error determining counter type: {e}")
                subdir = 'human'  # Fallback
        else:
            # Counter not in memory, check all possible locations
            subdirs_to_check = ['human', 'animal', 'object']
            subdir = 'human'  # Default
            
            # Use the same naming convention as the generator
            def camel_to_snake(name):
                import re
                s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
                return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
            
            counter_filename = camel_to_snake(counter_name) + '.py'
            
            # Check which subdirectory has the file
            for check_subdir in subdirs_to_check:
                check_file = f"./counters/{check_subdir}/{counter_filename}"
                if os.path.exists(check_file):
                    subdir = check_subdir
                    break
        
        # Create the filename (if not already created above)
        if 'counter_filename' not in locals():
            # Use the same naming convention as the generator
            def camel_to_snake(name):
                import re
                s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
                return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
            
            counter_filename = camel_to_snake(counter_name) + '.py'
        else:
            # Convert using same logic for consistency  
            def camel_to_snake(name):
                import re
                s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
                return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
            
            counter_filename = camel_to_snake(counter_name) + '.py'
        
        counter_file = f"./counters/{subdir}/{counter_filename}"
        
        print(f"Attempting to delete file: {counter_file}")  # Debug log
        
        if os.path.exists(counter_file):
            try:
                os.remove(counter_file)
                print(f"Deleted file: {counter_file}")  # Debug log
            except Exception as file_error:
                print(f"Error deleting file: {file_error}")
                return jsonify({'error': f'Failed to delete file: {str(file_error)}'}), 500
        else:
            print(f"File not found: {counter_file}")  # Debug log
        
        # Step 3: Try to regenerate all counter code with timeout
        regeneration_success = False
        try:
            print("Starting counter regeneration...")
            import signal
            import threading
            
            def timeout_handler():
                print("Regeneration timeout - skipping regeneration step")
                
            # Set a timeout for regeneration
            timer = threading.Timer(10.0, timeout_handler)  # 10 second timeout
            timer.start()
            
            try:
                success = generate_all_counters()
                timer.cancel()  # Cancel the timeout
                if success:
                    regeneration_success = True
                    print("Counter code regenerated after deletion")
                else:
                    print("Counter code regeneration failed after deletion")
            except Exception as gen_error:
                timer.cancel()
                print(f"Error regenerating counter code: {gen_error}")
                
        except Exception as timeout_error:
            print(f"Regeneration timeout or error: {timeout_error}")
        
        # Step 4: Reload counters to refresh the in-memory registry
        try:
            reload_counters()
            print("Counters reloaded after deletion")  # Debug log
        except Exception as reload_error:
            print(f"Error reloading counters: {reload_error}")
            # Don't fail the deletion if reload fails
        
        # Return success even if regeneration failed
        message = f'Counter {counter_name} deleted successfully'
        if not regeneration_success:
            message += ' (code regeneration skipped due to timeout - use "Regenerate All" if needed)'
        
        return jsonify({
            'success': True, 
            'message': message,
            'regeneration_success': regeneration_success
        })
        
    except Exception as e:
        print(f"Error in delete_counter: {e}")  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/force_delete_counter', methods=['POST'])
def force_delete_counter():
    """Force delete a counter without regenerating all code"""
    try:
        data = request.get_json()
        counter_name = data.get('counter_name')
        
        if not counter_name:
            return jsonify({'error': 'Counter name is required'}), 400
        
        print(f"Force deleting counter: {counter_name}")  # Debug log
        
        # Step 1: Remove from config file
        config_path = './configs/generated_counter_config.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                configs = json.load(f)
            
            original_count = len(configs)
            configs = [cfg for cfg in configs if cfg['name'] != counter_name]
            
            if len(configs) < original_count:
                with open(config_path, 'w') as f:
                    json.dump(configs, f, indent=2)
                print(f"Removed {counter_name} from config")
        
        # Step 2: Find and delete file in all possible locations
        def camel_to_snake(name):
            import re
            s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
            return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
        
        counter_filename = camel_to_snake(counter_name) + '.py'
        subdirs_to_check = ['human', 'animal', 'object']
        
        files_deleted = []
        for subdir in subdirs_to_check:
            counter_file = f"./counters/{subdir}/{counter_filename}"
            if os.path.exists(counter_file):
                try:
                    os.remove(counter_file)
                    files_deleted.append(counter_file)
                    print(f"Deleted file: {counter_file}")
                except Exception as file_error:
                    print(f"Error deleting file {counter_file}: {file_error}")
        
        # Step 3: Reload counters only (no regeneration)
        try:
            reload_counters()
            print("Counters reloaded after force deletion")
        except Exception as reload_error:
            print(f"Error reloading counters: {reload_error}")
        
        if files_deleted:
            message = f'Counter {counter_name} force deleted successfully. Files removed: {", ".join(files_deleted)}'
        else:
            message = f'Counter {counter_name} removed from config (no files found to delete)'
        
        return jsonify({
            'success': True, 
            'message': message,
            'files_deleted': files_deleted
        })
        
    except Exception as e:
        print(f"Error in force_delete_counter: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/regenerate_all', methods=['POST'])
def regenerate_all():
    """Regenerate all counter code"""
    try:
        success = generate_all_counters()
        if success:
            # Reload counters to make them available immediately
            reload_counters()
            print("All counters regenerated and reloaded successfully")
            return jsonify({
                'success': True, 
                'message': 'All counters regenerated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to regenerate some or all counters'
            }), 500
    except Exception as e:
        print(f"Error in regenerate_all: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Multi Counter Admin Panel...")
    print("Admin Panel will be available at: http://localhost:5001")
    print("Default password: dev123")
    
    try:
        # Set Flask to handle errors gracefully
        app.config['PROPAGATE_EXCEPTIONS'] = False
        app.run(debug=False, host='0.0.0.0', port=5001, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\nAdmin panel stopped by user.")
    except Exception as e:
        print(f"Error starting admin panel: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...") 
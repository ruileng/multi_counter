from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
import time
from add_action import generate_config_from_llm, load_prompt_template, generate_all_counters
from counters import list_counters, reload_counters

app = Flask(__name__)
ADMIN_PASSWORD = "dev123"  # 请更改此密码!

def get_counter_type(counter):
    """确定计数器类型"""
    return getattr(counter, 'detection_type', 'yolo' if hasattr(counter, 'tracker') else 'mediapipe')

def list_counters_by_category():
    """返回按类别组织的计数器"""
    from counters import get_counter
    
    categorized = {'Human': [], 'Animal': [], 'Object': []}
    
    for counter_name in list_counters():
        try:
            CounterClass = get_counter(counter_name)
            if not CounterClass:
                continue
                
            temp_counter = CounterClass()
            counter_type = get_counter_type(temp_counter)
            
            counter_info = {
                'name': counter_name,
                'type': counter_type,
                'object_class': getattr(temp_counter, 'object_class', 'human'),
                'logic_type': getattr(temp_counter, 'logic_type', 'exercise'),
                'confidence_threshold': getattr(temp_counter, 'confidence_threshold', 0.5),
                'threshold': getattr(temp_counter, 'threshold', 40),
                'stable_frames': getattr(temp_counter, 'stable_frames', 5),
                'description': getattr(temp_counter, 'description', ''),
                'has_center_line': hasattr(temp_counter, 'adjust_center_line') or hasattr(temp_counter, 'start_position')
            }
            
            if counter_type == 'yolo':
                category = 'Animal' if counter_info['object_class'] in ['cat', 'dog', 'bird', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe'] else 'Object'
            else:
                category = 'Human'
            
            categorized[category].append(counter_info)
        except:
            pass
    
    return categorized

@app.route('/')
def admin_login():
    """管理员登录页面"""
    return render_template('admin_login.html')

@app.route('/login', methods=['POST'])
def login():
    """处理管理员登录"""
    password = request.form.get('password')
    if password == ADMIN_PASSWORD:
        return redirect(url_for('admin_panel'))
    return render_template('admin_login.html', error="密码无效")

@app.route('/admin')
def admin_panel():
    """主管理面板"""
    categorized_counters = list_counters_by_category()
    
    config_path = './configs/generated_counter_config.json'
    current_config = []
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            current_config = json.load(f)
    
    total_counters = sum(len(category) for category in categorized_counters.values())
    
    return render_template('admin_panel.html', 
                         categorized_counters=categorized_counters,
                         current_config=current_config,
                         total_counters=total_counters)

def save_counter_config(config, config_type='generated'):
    """保存计数器配置"""
    config_files = {
        'generated': './configs/generated_counter_config.json',
        'yolo': './configs/yolo_counter_config.json'
    }
    
    config_path = config_files.get(config_type, config_files['generated'])
    os.makedirs('./configs', exist_ok=True)
    
    existing_configs = []
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            existing_configs = json.load(f)
    
    existing_names = {cfg['name'] for cfg in existing_configs}
    if config['name'] in existing_names:
        return False, f'计数器 {config["name"]} 已存在'
    
    existing_configs.append(config)
    
    with open(config_path, 'w') as f:
        json.dump(existing_configs, f, indent=2)
    
    return True, '保存成功'

def generate_and_reload():
    """生成计数器并重新加载"""
    success = generate_all_counters()
    if success:
        time.sleep(0.5)
        reload_counters()
        return True
    return False

@app.route('/generate_human_counter', methods=['POST'])
def generate_human_counter():
    """生成人体动作计数器"""
    try:
        data = request.get_json()
        exercise_name = data.get('exercise_name')
        
        if not exercise_name:
            return jsonify({'error': '锻炼名称是必需的'}), 400
        
        print(f"正在生成人体计数器: {exercise_name}")
        
        template = load_prompt_template()
        if not template:
            return jsonify({'error': '无法加载提示模板'}), 500
        
        config = generate_config_from_llm(exercise_name, template)
        if not config:
            return jsonify({'error': '生成计数器配置失败'}), 500
        
        config.update({
            'detection_type': 'mediapipe',
            'object_class': 'human'
        })
        
        success, message = save_counter_config(config, 'generated')
        if not success:
            return jsonify({'error': message}), 400
        
        if generate_and_reload():
            return jsonify({
                'success': True, 
                'message': f'人体计数器 {config["name"]} 生成成功',
                'config': config
            })
        else:
            return jsonify({'error': '生成计数器代码失败'}), 500
        
    except Exception as e:
        print(f"generate_human_counter 错误: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_animal_counter', methods=['POST'])
def generate_animal_counter():
    """生成动物计数器"""
    try:
        data = request.get_json()
        animal_type = data.get('animal_type')
        logic_type = data.get('logic_type', 'movement_detection')
        
        if not animal_type:
            return jsonify({'error': '动物类型是必需的'}), 400
        
        print(f"正在生成动物计数器: {animal_type}，逻辑: {logic_type}")
        
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
            'description': f'基于YOLO的{animal_type}{logic_type}计数器'
        }
        
        success, message = save_counter_config(config, 'yolo')
        if not success:
            return jsonify({'error': message}), 400
        
        if generate_and_reload():
            return jsonify({
                'success': True, 
                'message': f'动物计数器 {config["name"]} 生成成功',
                'config': config
            })
        else:
            return jsonify({'error': '生成计数器代码失败'}), 500
        
    except Exception as e:
        print(f"generate_animal_counter 错误: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_object_counter', methods=['POST'])
def generate_object_counter():
    """生成物体计数器"""
    try:
        data = request.get_json()
        object_type = data.get('object_type')
        logic_type = data.get('logic_type', 'bounce_detection')
        
        if not object_type:
            return jsonify({'error': '物体类型是必需的'}), 400
        
        print(f"正在生成物体计数器: {object_type}，逻辑: {logic_type}")
        
        config = {
            'name': f'{object_type.title()}Counter',
            'class_name': f'{object_type.title()}Counter',
            'object_class': object_type.lower(),
            'detection_type': 'yolo',
            'logic_type': logic_type,
            'threshold': 40,
            'confidence_threshold': 0.5,
            'stable_frames': 5,
            'calibration_frames': 30,
            'description': f'基于YOLO的{object_type}{logic_type}计数器'
        }
        
        success, message = save_counter_config(config, 'yolo')
        if not success:
            return jsonify({'error': message}), 400
        
        if generate_and_reload():
            return jsonify({
                'success': True, 
                'message': f'物体计数器 {config["name"]} 生成成功',
                'config': config
            })
        else:
            return jsonify({'error': '生成计数器代码失败'}), 500
        
    except Exception as e:
        print(f"generate_object_counter 错误: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate_counter', methods=['POST'])
def generate_counter():
    """通用计数器生成"""
    try:
        data = request.get_json()
        counter_type = data.get('type')
        
        if counter_type == 'human':
            return generate_human_counter()
        elif counter_type == 'animal':
            return generate_animal_counter()
        elif counter_type == 'object':
            return generate_object_counter()
        else:
            return jsonify({'error': '无效的计数器类型'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def camel_to_snake(name):
    """将驼峰命名转换为蛇形命名"""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

def delete_counter_from_config(counter_name, config_path):
    """从配置文件中删除计数器"""
    if not os.path.exists(config_path):
        return False, "配置文件不存在"
    
    try:
        with open(config_path, 'r') as f:
            configs = json.load(f)
        
        original_count = len(configs)
        configs = [cfg for cfg in configs if cfg.get('name') != counter_name]
        
        if len(configs) == original_count:
            return False, "计数器未在配置中找到"
        
        with open(config_path, 'w') as f:
            json.dump(configs, f, indent=2)
        
        return True, "从配置中删除成功"
    except Exception as e:
        return False, f"删除配置失败: {str(e)}"

def delete_counter_file(counter_name):
    """删除计数器文件"""
    file_name = f"{camel_to_snake(counter_name)}.py"
    file_path = os.path.join("./counters", file_name)
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return True, f"文件 {file_name} 删除成功"
        except Exception as e:
            return False, f"删除文件失败: {str(e)}"
    else:
        return False, f"文件 {file_name} 不存在"

@app.route('/delete_counter', methods=['POST'])
def delete_counter():
    """删除计数器"""
    try:
        data = request.get_json()
        counter_name = data.get('counter_name')
        
        if not counter_name:
            return jsonify({'error': '计数器名称是必需的'}), 400
        
        print(f"正在删除计数器: {counter_name}")
        
        # 从配置文件中删除
        config_paths = [
            './configs/generated_counter_config.json',
            './configs/yolo_counter_config.json'
        ]
        
        deleted_from_config = False
        for config_path in config_paths:
            success, message = delete_counter_from_config(counter_name, config_path)
            if success:
                deleted_from_config = True
                break
        
        # 删除文件
        file_success, file_message = delete_counter_file(counter_name)
        
        if deleted_from_config or file_success:
            if generate_and_reload():
                return jsonify({
                    'success': True, 
                    'message': f'计数器 {counter_name} 删除成功'
                })
            else:
                return jsonify({'error': '重新生成计数器失败'}), 500
        else:
            return jsonify({'error': '计数器删除失败'}), 400
        
    except Exception as e:
        print(f"delete_counter 错误: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/force_delete_counter', methods=['POST'])
def force_delete_counter():
    """强制删除计数器"""
    try:
        data = request.get_json()
        counter_name = data.get('counter_name')
        
        if not counter_name:
            return jsonify({'error': '计数器名称是必需的'}), 400
        
        print(f"强制删除计数器: {counter_name}")
        
        # 删除文件
        file_success, file_message = delete_counter_file(counter_name)
        
        # 从所有配置文件中删除
        config_paths = [
            './configs/generated_counter_config.json',
            './configs/yolo_counter_config.json'
        ]
        
        for config_path in config_paths:
            delete_counter_from_config(counter_name, config_path)
        
        if generate_and_reload():
            return jsonify({
                'success': True, 
                'message': f'计数器 {counter_name} 强制删除成功'
            })
        else:
            return jsonify({'error': '重新生成计数器失败'}), 500
        
    except Exception as e:
        print(f"force_delete_counter 错误: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/regenerate_all', methods=['POST'])
def regenerate_all():
    """重新生成所有计数器"""
    try:
        print("重新生成所有计数器...")
        
        if generate_and_reload():
            return jsonify({
                'success': True, 
                'message': '所有计数器重新生成成功'
            })
        else:
            return jsonify({'error': '重新生成失败'}), 500
        
    except Exception as e:
        print(f"regenerate_all 错误: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🔧 管理面板启动中...")
    print("📱 访问地址: http://localhost:5001")
    print("🔑 密码: dev123")
    
    try:
        app.run(debug=False, host='0.0.0.0', port=5001, threaded=True)
    except KeyboardInterrupt:
        print("\n⏹️ 管理面板被用户停止。")
    except Exception as e:
        print(f"❌ 启动管理面板时出错: {e}")
        input("按回车键退出...") 
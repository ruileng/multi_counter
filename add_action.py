import os
import json
import re
import argparse
import ollama
from jinja2 import Environment, FileSystemLoader

# --- 配置路径 ---
CONFIG_PATH = './configs/generated_counter_config.json'
PARAM_TEMPLATE_DIR = './templates'
COUNTER_TEMPLATE_DIR = './templates'
OUTPUT_DIR_HUMAN = './counters/human'  # 用于MediaPipe计数器

# --- 第一部分：参数生成（来自param_generator/generate_params.py）---

def load_prompt_template():
    """从文件加载提示模板。"""
    try:
        env = Environment(loader=FileSystemLoader(PARAM_TEMPLATE_DIR))
        return env.get_template('prompt_template.txt')
    except Exception as e:
        print(f"加载提示模板时出错: {e}")
        return None

def normalize_llm_response(llm_config):
    """
    标准化LLM响应以匹配预期的字段名称。
    """
    if not llm_config:
        return None
    
    # 创建具有预期字段名称的标准化配置
    normalized = {}
    
    # 将class_name映射到name
    normalized['name'] = llm_config.get('class_name', llm_config.get('name', 'UnknownCounter'))
    
    # 映射logic_type
    normalized['logic_type'] = llm_config.get('logic_type', 'vertical_movement')
    
    # 映射direction
    normalized['direction'] = llm_config.get('direction', 'up-first')
    
    # 映射关键点名称（处理新旧字段名称）
    normalized['landmark_name'] = llm_config.get('landmark_name', 
                                                llm_config.get('primary_landmark_name', 'NOSE'))
    
    normalized['aux_landmark_name'] = llm_config.get('aux_landmark_name', 
                                                    llm_config.get('auxiliary_landmark_name', None))
    
    # 映射置信度和阈值
    normalized['min_conf'] = llm_config.get('min_conf', 
                                           llm_config.get('min_confidence', 0.5))
    
    normalized['threshold'] = llm_config.get('threshold', 0.05)
    normalized['stable_frames'] = llm_config.get('stable_frames', 10)
    
    # 映射反作弊验证参数
    normalized['enable_anti_cheat'] = llm_config.get('enable_anti_cheat', False)
    normalized['validation_landmarks'] = llm_config.get('validation_landmarks', [])
    normalized['validation_threshold'] = llm_config.get('validation_threshold', 0.03)
    
    return normalized

def generate_config_from_llm(action_name: str, template):
    """通过调用Ollama LLM生成单个计数器配置。"""
    if not template:
        return None
    prompt = template.render(exercise_name=action_name)
    print(f"\n--- 为以下项目生成配置: {action_name} ---")
    try:
        response = ollama.chat(
            model='llama3',
            messages=[{'role': 'user', 'content': prompt}],
            format='json' # 直接请求JSON输出
        )
        content = response['message']['content']
        print(f"LLM响应: {content}")
        raw_config = json.loads(content)
        # 标准化响应
        normalized_config = normalize_llm_response(raw_config)
        print(f"标准化配置: {normalized_config}")
        return normalized_config
    except Exception as e:
        print(f"与Ollama通信或解析JSON时发生错误: {e}")
        return None

def update_config_file(new_configs):
    """将新配置追加到主配置文件，避免重复。"""
    if not new_configs:
        print("没有新配置要添加。")
        return
    
    existing_configs = []
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            try:
                raw_configs = json.load(f)
                # 标准化现有配置以确保它们具有正确的格式
                for cfg in raw_configs:
                    normalized = normalize_llm_response(cfg)
                    if normalized:
                        existing_configs.append(normalized)
            except json.JSONDecodeError:
                print("警告: 配置文件为空或格式错误。重新开始。")
    
    # 使用标准化格式获取现有名称
    existing_names = {cfg['name'] for cfg in existing_configs}
    
    for new_cfg in new_configs:
        if new_cfg and new_cfg.get('name') not in existing_names:
            existing_configs.append(new_cfg)
            print(f"添加新计数器配置: {new_cfg.get('name')}")
        else:
            print(f"计数器'{new_cfg.get('name')}'已存在或无效。跳过。")
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(existing_configs, f, indent=2)
    print(f"\n成功更新 {CONFIG_PATH}")


# --- 第二部分：代码生成（来自generate_counter.py）---

def camel_to_snake(name):
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

def generate_all_counters():
    """读取整个配置文件并生成所有计数器模块。"""
    print("\n--- 生成计数器代码 ---")
    try:
        if not os.path.exists(CONFIG_PATH):
            print(f"错误: 配置文件 {CONFIG_PATH} 不存在。")
            return False
            
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            configs = json.load(f)
            
        if not configs:
            print("警告: 配置文件为空。")
            return True
            
        print(f"找到 {len(configs)} 个计数器配置")
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"错误: 无法读取或解析 {CONFIG_PATH}: {e}")
        return False

    try:
        env = Environment(loader=FileSystemLoader(COUNTER_TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)
        template = env.get_template('counter_template.py.j2')
    except Exception as e:
        print(f"加载模板时出错: {e}")
        return False

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR_HUMAN, exist_ok=True)

    success_count = 0
    for i, cfg in enumerate(configs):
        try:
            class_name = cfg.get('name')
            if not class_name:
                print(f"警告: 配置 {i} 没有名称，跳过")
                continue
                
            print(f"生成 {class_name}...")
            
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
            # generated_counter_config.json中的所有配置都是人体/MediaPipe计数器
            output_path = os.path.join(OUTPUT_DIR_HUMAN, f"{camel_to_snake(class_name)}.py")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(code)
                
            print(f"✓ 生成 {output_path}")
            success_count += 1
            
        except Exception as e:
            print(f"✗ 生成 {cfg.get('name', 'unknown')} 时出错: {e}")
            continue

    print(f"\n生成完成: {success_count}/{len(configs)} 个计数器成功生成")
    return success_count > 0

# --- 主执行 ---

def main():
    parser = argparse.ArgumentParser(description="自动添加新动作计数器的工具。")
    parser.add_argument('actions', nargs='+', help='要生成配置的动作名称列表（例如"bicep curls", "jumping jacks"）。')
    args = parser.parse_args()

    # 步骤1：从LLM生成参数
    prompt_template = load_prompt_template()
    if not prompt_template:
        return
    
    new_configs = []
    for action in args.actions:
        config = generate_config_from_llm(action, prompt_template)
        if config:
            new_configs.append(config)
    
    # 步骤2：更新主JSON配置文件
    update_config_file(new_configs)
    
    # 步骤3：从更新的配置重新生成所有计数器代码
    generate_all_counters()

    print("\n过程完成。新计数器已准备好使用。")

if __name__ == '__main__':
    main() 
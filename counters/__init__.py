"""
Multi-Counter Module
Provides access to all counter types: Human (MediaPipe), Animal (YOLO), and Object (YOLO)
"""

import os
import importlib
import inspect
from typing import Dict, List, Any

# Global registry for all counter classes
_counter_registry = {}

def _load_counter_module(module_path: str, category: str):
    """Load a single counter module and register its classes."""
    try:
        # Convert file path to module name
        module_name = module_path.replace('.py', '').replace('/', '.').replace('\\', '.')
        if module_name.startswith('.'):
            module_name = module_name[1:]
        
        print(f"Importing {module_name}...")
        
        # Import the module
        module = importlib.import_module(module_name)
        
        # Find counter classes in the module
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if name.endswith('Counter') and obj.__module__ == module_name:
                _counter_registry[name] = obj
                print(f"✓ Successfully loaded {name} ({category})")
                
    except Exception as e:
        print(f"✗ Failed to load {module_path}: {e}")

def _discover_counters():
    """Discover and load all counter modules."""
    print("Loading counter modules...")
    _counter_registry.clear()
    
    # Load human counters (MediaPipe)
    human_dir = os.path.join(os.path.dirname(__file__), 'human')
    if os.path.exists(human_dir):
        for file in os.listdir(human_dir):
            if file.endswith('_counter.py'):
                module_path = f"counters.human.{file}"
                _load_counter_module(module_path, "Human")
    
    # Load animal counters (YOLO)
    animal_dir = os.path.join(os.path.dirname(__file__), 'animal')
    if os.path.exists(animal_dir):
        for file in os.listdir(animal_dir):
            if file.endswith('_counter.py'):
                module_path = f"counters.animal.{file}"
                _load_counter_module(module_path, "Animal")
    
    # Load object counters (YOLO)
    object_dir = os.path.join(os.path.dirname(__file__), 'object')
    if os.path.exists(object_dir):
        for file in os.listdir(object_dir):
            if file.endswith('_counter.py'):
                module_path = f"counters.object.{file}"
                _load_counter_module(module_path, "Object")
    
    print(f"Counter loading complete. Total counters loaded: {len(_counter_registry)}")
    print(f"Available counters: {list(_counter_registry.keys())}")

def list_counters() -> List[str]:
    """Return a list of all available counter names."""
    if not _counter_registry:
        _discover_counters()
    return list(_counter_registry.keys())

def get_counter(counter_name: str):
    """Get a counter class by name."""
    if not _counter_registry:
        _discover_counters()
    return _counter_registry.get(counter_name)

def reload_counters():
    """Reload all counter modules (useful after generating new counters)."""
    print("Reloading counter modules...")
    
    # Clear import cache for counter modules
    modules_to_remove = []
    for module_name in list(importlib.sys.modules.keys()):
        if module_name.startswith('counters.'):
            modules_to_remove.append(module_name)
    
    for module_name in modules_to_remove:
        del importlib.sys.modules[module_name]
    
    # Rediscover all counters
    _discover_counters()
    print("Counter reload complete.")

# Auto-load counters when module is imported
_discover_counters()

# Export main functions
__all__ = ['list_counters', 'get_counter', 'reload_counters'] 
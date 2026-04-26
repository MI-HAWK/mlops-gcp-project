import os
import yaml

def load_config(env_override=None):
    env = env_override or os.getenv("ENV", "dev")
    config_path = os.path.join(os.path.dirname(__file__), f"../../config/{env}.yaml")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration for environment '{env}' not found at {config_path}")
        
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config

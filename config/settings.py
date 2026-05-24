import os
from pathlib import Path
from pydantic import BaseModel, Field

try:
    import yaml
except ImportError:
    yaml = None


class LLMConfig(BaseModel):
    model: str = "gemini-2.5-pro"
    temperature: float = 0.1
    max_output_tokens: int = 8192
    timeout_seconds: int = 60


class MemoryConfig(BaseModel):
    dsm_path: str = ".sharrowkin/dsm"
    rld_path: str = ".sharrowkin/rld"
    enable_rld: bool = True
    decay_rate: float = 0.05
    max_segments: int = 1000


class ExecutionConfig(BaseModel):
    max_iterations: int = 30
    strict_mode: bool = True
    enable_semantic_graph: bool = True
    ui_delays_enabled: bool = False  # ✅ NEW: Disable UI delays for production


class AgentConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    github_token: str | None = None


def load_config(workspace_path: str | Path | None = None) -> AgentConfig:
    """Load configuration from sharrowkin.yaml.
    
    Searches in:
    1. The provided workspace_path
    2. The current working directory
    3. The parent repository root
    """
    config_paths = []
    
    if workspace_path:
        config_paths.append(Path(workspace_path) / "sharrowkin.yaml")
        
    config_paths.extend([
        Path.cwd() / "sharrowkin.yaml",
        Path(__file__).parent.parent.parent / "sharrowkin.yaml"
    ])
    
    for path in config_paths:
        if path.exists() and yaml:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return AgentConfig(**data)
            except Exception as e:
                print(f"[CONFIG] Error loading {path}: {e}")
                
    # Fallback to default if no yaml found
    return AgentConfig()

# Global config instance that can be imported directly
global_config = load_config()
SETTINGS = global_config  # Alias for backward compatibility

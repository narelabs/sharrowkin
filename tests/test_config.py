import os
import tempfile
from pathlib import Path
from config import load_config, AgentConfig


def test_default_config():
    """Verify that defaults are used when no config file is found."""
    # Temporarily load from a non-existent path to force defaults
    config = load_config("/nonexistent/workspace")
    assert isinstance(config, AgentConfig)
    assert config.llm.model == "gemini-2.5-pro"
    assert config.memory.decay_rate == 0.05
    assert config.execution.max_iterations == 30


def test_custom_config_parsing():
    """Verify that configuration parses correct custom YAML values."""
    yaml_content = """
llm:
  model: "custom-gemini"
  temperature: 0.7
  max_output_tokens: 4096
  timeout_seconds: 30
memory:
  decay_rate: 0.1
  max_segments: 500
execution:
  max_iterations: 15
  strict_mode: false
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        config_file = tmp_path / "sharrowkin.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(yaml_content)
            
        config = load_config(tmp_path)
        assert config.llm.model == "custom-gemini"
        assert config.llm.temperature == 0.7
        assert config.llm.max_output_tokens == 4096
        assert config.llm.timeout_seconds == 30
        assert config.memory.decay_rate == 0.1
        assert config.memory.max_segments == 500
        assert config.execution.max_iterations == 15
        assert config.execution.strict_mode is False

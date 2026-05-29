"""Tests for config.settings module."""
import pytest
from pathlib import Path
from config.settings import LLMConfig, MemoryConfig


def test_llm_config_defaults():
    """Test LLMConfig with default values."""
    config = LLMConfig()
    assert config.model is not None
    assert config.temperature >= 0.0
    assert config.max_output_tokens > 0
    assert config.timeout_seconds > 0


def test_llm_config_custom():
    """Test LLMConfig with custom values."""
    config = LLMConfig(
        model="custom-model",
        temperature=0.5,
        max_output_tokens=2000,
        timeout_seconds=60,
    )
    assert config.model == "custom-model"
    assert config.temperature == 0.5
    assert config.max_output_tokens == 2000
    assert config.timeout_seconds == 60


def test_memory_config_defaults():
    """Test MemoryConfig with default values."""
    config = MemoryConfig()
    assert isinstance(config.dsm_path, Path)
    assert isinstance(config.rld_path, Path)
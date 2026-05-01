"""Unit tests for src.utils.config."""
import os
import pytest

pytestmark = pytest.mark.unit


class TestLoadConfig:
    def test_load_dev_config(self):
        from src.utils.config import load_config
        config = load_config(env_override="dev")
        assert config['env'] == 'dev'
        assert config['training']['n_estimators'] == 10
        assert config['training']['max_depth'] == 5
        assert 'model_name' in config

    def test_load_staging_config(self):
        from src.utils.config import load_config
        config = load_config(env_override="staging")
        assert config['env'] == 'staging'
        assert config['training']['n_estimators'] == 50

    def test_load_prod_config(self):
        from src.utils.config import load_config
        config = load_config(env_override="prod")
        assert config['env'] == 'prod'
        assert config['training']['n_estimators'] == 100

    def test_missing_config_raises(self):
        from src.utils.config import load_config
        with pytest.raises(FileNotFoundError):
            load_config(env_override="nonexistent")

    def test_env_variable_override(self, monkeypatch):
        from src.utils.config import load_config
        monkeypatch.setenv("ENV", "staging")
        config = load_config()
        assert config['env'] == 'staging'

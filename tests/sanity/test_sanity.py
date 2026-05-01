"""Sanity / smoke tests — quick checks that everything can import and basic ops work."""
import pytest

pytestmark = pytest.mark.sanity


class TestImports:
    def test_import_config(self):
        from src.utils.config import load_config
        assert callable(load_config)

    def test_import_train(self):
        from src.model.train import train_model, encode_features, compute_metrics
        assert callable(train_model)
        assert callable(encode_features)
        assert callable(compute_metrics)

    def test_import_predict(self):
        from src.api.predict import app
        assert app is not None

    def test_import_schema(self):
        from src.utils.schema import validate_schema
        assert callable(validate_schema)

    def test_import_drift(self):
        from src.utils.drift import compute_psi, check_drift
        assert callable(compute_psi)
        assert callable(check_drift)

    def test_import_promote(self):
        from src.utils.promote import promote_model, swap_champion
        assert callable(promote_model)


class TestConfigLoads:
    def test_dev_config_loads(self):
        from src.utils.config import load_config
        config = load_config(env_override="dev")
        assert config is not None
        assert 'env' in config


class TestFastAppInstantiates:
    def test_app_has_routes(self):
        from src.api.predict import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/predict" in routes
        assert "/" in routes
        assert "/ready" in routes
        assert "/metrics" in routes


class TestModelPrediction:
    def test_random_forest_returns_float(self):
        from sklearn.ensemble import RandomForestRegressor
        import numpy as np
        X = np.array([[1, 2, 3, 4, 5, 6, 7, 8, 9]])
        y = [10000]
        rf = RandomForestRegressor(n_estimators=2, random_state=42)
        rf.fit(X, y)
        pred = rf.predict(X)[0]
        assert isinstance(pred, float)


class TestSchemaValidation:
    def test_valid_data_passes(self, sample_flight_data):
        from src.utils.schema import validate_schema
        result = validate_schema(sample_flight_data)
        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_invalid_data_fails(self):
        import pandas as pd
        from src.utils.schema import validate_schema
        bad_df = pd.DataFrame({'wrong_col': [1, 2, 3]})
        result = validate_schema(bad_df)
        assert result['valid'] is False

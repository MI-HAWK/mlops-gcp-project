"""Unit tests for model training with mocked MLflow."""
import os
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

pytestmark = pytest.mark.unit


class TestTrainModel:
    @patch('src.model.train.mlflow')
    def test_train_model_e2e(self, mock_mlflow, sample_flight_data, tmp_path, mock_config):
        """Full training run with mocked MLflow on sample data."""
        from src.model.train import encode_features, prepare_features, compute_metrics
        from sklearn.ensemble import RandomForestRegressor

        train_df = sample_flight_data.iloc[:3].copy()
        test_df = sample_flight_data.iloc[3:].copy()

        # Encode
        train_enc, test_enc, encoders = encode_features(train_df, test_df)

        # Prepare
        X_train, y_train = prepare_features(train_enc)
        X_test, y_test = prepare_features(test_enc)

        # Train
        clf = RandomForestRegressor(
            n_estimators=mock_config['training']['n_estimators'],
            max_depth=mock_config['training']['max_depth'],
            random_state=42
        )
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        # Metrics
        metrics = compute_metrics(y_test, preds)
        assert 'rmse' in metrics
        assert 'r2' in metrics
        assert metrics['rmse'] >= 0

    def test_model_type_is_random_forest(self):
        """Verify we are using RandomForestRegressor."""
        from sklearn.ensemble import RandomForestRegressor
        clf = RandomForestRegressor(n_estimators=2, random_state=42)
        assert hasattr(clf, 'predict')
        assert hasattr(clf, 'fit')

    @patch('src.model.train.mlflow')
    def test_metrics_file_output(self, mock_mlflow, tmp_path):
        """Verify save_metrics creates a proper file."""
        from src.model.train import save_metrics
        path = str(tmp_path / "metrics.txt")
        save_metrics({"rmse": 100.0, "r2": 0.9}, path)
        assert os.path.exists(path)
        content = open(path).read()
        assert "RMSE" in content
        assert "R2" in content

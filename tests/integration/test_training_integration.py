"""Integration test for the full training pipeline on sample data."""
import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.integration


class TestTrainingPipeline:
    @patch('src.model.train.mlflow')
    def test_full_pipeline_produces_artifacts(self, mock_mlflow, sample_flight_data, tmp_path):
        """Run the training pipeline end-to-end and verify outputs."""
        from src.model.train import encode_features, prepare_features, compute_metrics, save_metrics
        from sklearn.ensemble import RandomForestRegressor
        import joblib

        train_df = sample_flight_data.iloc[:3].copy()
        test_df = sample_flight_data.iloc[3:].copy()

        # Step 1: Encode
        train_enc, test_enc, encoders = encode_features(train_df, test_df)
        assert len(encoders) == 4  # ohe, stops_map, class_map, nominal_cols

        # Step 2: Prepare features
        X_train, y_train = prepare_features(train_enc)
        X_test, y_test = prepare_features(test_enc)
        assert 'price' not in X_train.columns
        assert len(y_train) == 3

        # Step 3: Train
        clf = RandomForestRegressor(n_estimators=10, max_depth=5, random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        assert len(preds) == len(y_test)

        # Step 4: Metrics
        metrics = compute_metrics(y_test, preds)
        assert metrics['rmse'] >= 0
        assert -1 <= metrics['r2'] <= 1

        # Step 5: Save artifacts
        metrics_path = str(tmp_path / "metrics.txt")
        save_metrics(metrics, metrics_path)
        assert os.path.exists(metrics_path)

        encoder_path = str(tmp_path / "encoders.joblib")
        joblib.dump(encoders, encoder_path)
        assert os.path.exists(encoder_path)

        # Verify encoder can be reloaded
        loaded = joblib.load(encoder_path)
        assert set(loaded.keys()) == set(encoders.keys())

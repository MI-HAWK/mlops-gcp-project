"""Unit tests for encoder logic extracted from train.py."""
import pytest
import pandas as pd
import numpy as np

pytestmark = pytest.mark.unit


class TestEncodeFeatures:
    def test_encode_returns_encoders_dict(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features
        _, _, encoders = encode_features(sample_train_df, sample_test_df)
        assert isinstance(encoders, dict)
        assert 'ohe' in encoders
        assert 'stops_map' in encoders
        assert 'class_map' in encoders

    def test_encoded_columns_are_numeric(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features
        train_enc, test_enc, _ = encode_features(sample_train_df, sample_test_df)
        for col in train_enc.columns:
            if col not in ['flight_id', 'event_timestamp']:
                assert pd.api.types.is_numeric_dtype(train_enc[col]), f"{col} not numeric in train"
                assert pd.api.types.is_numeric_dtype(test_enc[col]), f"{col} not numeric in test"

    def test_encode_does_not_modify_original(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features
        original_train = sample_train_df.copy()
        encode_features(sample_train_df, sample_test_df)
        pd.testing.assert_frame_equal(sample_train_df, original_train)


class TestComputeMetrics:
    def test_returns_rmse_and_r2(self):
        from src.model.train import compute_metrics
        y_true = pd.Series([100, 200, 300])
        y_pred = pd.Series([110, 190, 310])
        metrics = compute_metrics(y_true, y_pred)
        assert 'rmse' in metrics
        assert 'r2' in metrics
        assert metrics['rmse'] >= 0
        assert metrics['r2'] <= 1.0

    def test_perfect_predictions(self):
        from src.model.train import compute_metrics
        y = pd.Series([1, 2, 3, 4, 5])
        metrics = compute_metrics(y, y)
        assert metrics['rmse'] == 0.0
        assert metrics['r2'] == 1.0


class TestSaveMetrics:
    def test_creates_metrics_file(self, tmp_path):
        from src.model.train import save_metrics
        path = str(tmp_path / "metrics.txt")
        save_metrics({"rmse": 123.45, "r2": 0.95}, path)
        with open(path) as f:
            content = f.read()
        assert "RMSE: 123.45" in content
        assert "R2: 0.95" in content


class TestPrepareFeatures:
    def test_drops_target_and_extra_cols(self, sample_train_df):
        from src.model.train import prepare_features
        # Give sample df columns it drops
        sample_train_df['flight_id'] = 'AI-101'
        sample_train_df['event_timestamp'] = pd.Timestamp.now()
        X, y = prepare_features(sample_train_df)
        assert 'price' not in X.columns
        assert 'flight_id' not in X.columns
        assert 'event_timestamp' not in X.columns
        assert y is not None
        assert len(y) == len(sample_train_df)

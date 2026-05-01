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
        assert 'airline' in encoders
        assert 'class' in encoders

    def test_encoded_columns_are_numeric(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features, CATEGORICAL_COLS
        train_enc, test_enc, _ = encode_features(sample_train_df, sample_test_df)
        for col in CATEGORICAL_COLS:
            assert pd.api.types.is_numeric_dtype(train_enc[col]), f"{col} not numeric in train"
            assert pd.api.types.is_numeric_dtype(test_enc[col]), f"{col} not numeric in test"

    def test_encode_does_not_modify_original(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features
        original_train = sample_train_df.copy()
        encode_features(sample_train_df, sample_test_df)
        pd.testing.assert_frame_equal(sample_train_df, original_train)

    def test_encoder_roundtrip(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features
        _, _, encoders = encode_features(sample_train_df, sample_test_df)
        # Verify we can inverse transform
        for col, le in encoders.items():
            encoded = le.transform(sample_train_df[col].astype(str))
            decoded = le.inverse_transform(encoded)
            np.testing.assert_array_equal(decoded, sample_train_df[col].astype(str).values)

    def test_custom_categorical_cols(self, sample_train_df, sample_test_df):
        from src.model.train import encode_features
        _, _, encoders = encode_features(
            sample_train_df, sample_test_df,
            categorical_cols=['airline', 'class']
        )
        assert len(encoders) == 2
        assert 'airline' in encoders
        assert 'source_city' not in encoders


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
        X, y = prepare_features(sample_train_df)
        assert 'price' not in X.columns
        assert 'flight' not in X.columns
        assert y is not None
        assert len(y) == len(sample_train_df)

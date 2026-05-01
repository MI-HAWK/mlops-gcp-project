import os
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder
import mlflow
import mlflow.sklearn
import joblib

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.config import load_config


# ---------------------------------------------------------------------------
# Extracted helper functions — testable independently
# ---------------------------------------------------------------------------

CATEGORICAL_COLS = [
    'airline', 'source_city', 'departure_time',
    'stops', 'arrival_time', 'destination_city', 'class'
]

DROP_COLS = ['price', 'flight', 'Unnamed: 0']


def encode_features(train_df, test_df, categorical_cols=None):
    """Fit LabelEncoders on combined data and transform both splits.

    Returns:
        (train_df, test_df, encoders) — DataFrames with encoded columns
        and the dict of fitted LabelEncoder instances.
    """
    if categorical_cols is None:
        categorical_cols = CATEGORICAL_COLS

    train_df = train_df.copy()
    test_df = test_df.copy()
    combined_df = pd.concat([train_df, test_df], axis=0)

    encoders = {}
    for col in categorical_cols:
        le = LabelEncoder()
        le.fit(combined_df[col].astype(str))
        train_df[col] = le.transform(train_df[col].astype(str))
        test_df[col] = le.transform(test_df[col].astype(str))
        encoders[col] = le

    return train_df, test_df, encoders


def compute_metrics(y_true, y_pred):
    """Return a dict with RMSE and R2."""
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    r2 = r2_score(y_true, y_pred)
    return {"rmse": rmse, "r2": r2}


def save_metrics(metrics_dict, path="metrics.txt"):
    """Persist metrics to a text file for CML / DVC."""
    with open(path, "w") as f:
        for key, value in metrics_dict.items():
            f.write(f"{key.upper()}: {value}\n")


def prepare_features(df, drop_cols=None):
    """Drop non-feature columns and return X, y."""
    if drop_cols is None:
        drop_cols = DROP_COLS
    X = df.drop(drop_cols, axis=1, errors='ignore')
    y = df['price'] if 'price' in df.columns else None
    return X, y


# ---------------------------------------------------------------------------
# Main training orchestrator — unchanged behaviour, calls helpers
# ---------------------------------------------------------------------------

def train_model():
    config = load_config()
    env = config['env']
    print(f"Starting training pipeline for environment: {env}")

    # Paths based on environment dataset
    train_data_path = f"data/{env}_train.csv"
    test_data_path = f"data/{env}_test.csv"

    if not (os.path.exists(train_data_path) and os.path.exists(test_data_path)):
        print(f"Data files {train_data_path} or {test_data_path} not found.")
        exit(1)

    train_df = pd.read_csv(train_data_path)
    test_df = pd.read_csv(test_data_path)

    # Preprocessing — now via helper
    train_df, test_df, encoders = encode_features(train_df, test_df)

    X_train, y_train = prepare_features(train_df)
    X_test, y_test = prepare_features(test_df)

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(f"flight-pricing-{env}")

    with mlflow.start_run():
        n_estimators = config['training']['n_estimators']
        max_depth = config['training']['max_depth']

        mlflow.log_params({"n_estimators": n_estimators, "max_depth": max_depth})

        clf = RandomForestRegressor(n_estimators=n_estimators, max_depth=max_depth, random_state=42)
        clf.fit(X_train, y_train)

        preds = clf.predict(X_test)
        metrics = compute_metrics(y_test, preds)

        mlflow.log_metrics(metrics)
        print(f"Metrics - RMSE: {metrics['rmse']:.2f}, R2: {metrics['r2']:.2f}")

        # Save encoders locally
        os.makedirs("models", exist_ok=True)
        joblib.dump(encoders, "models/encoders.joblib")

        # Log model
        mlflow.sklearn.log_model(clf, "model", registered_model_name=f"{config['model_name']}-{env}")

        # Output CML report data
        save_metrics(metrics, "metrics.txt")

if __name__ == "__main__":
    train_model()

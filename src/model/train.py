import os
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import OneHotEncoder
import mlflow
import mlflow.sklearn
import joblib

import sys
import logging
from pythonjsonlogger import jsonlogger

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.config import load_config
from src.utils.feast_utils import get_training_features

# Configure structured JSON logging
logger = logging.getLogger("train_job")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# ---------------------------------------------------------------------------
# Extracted helper functions — testable independently
# ---------------------------------------------------------------------------

NOMINAL_COLS = [
    'airline', 'source_city', 'destination_city',
    'departure_time', 'arrival_time', 'route'
]
ORDINAL_COLS = ['stops', 'class']

DROP_COLS = ['price', 'flight_id', 'event_timestamp', 'Unnamed: 0']

def encode_features(train_df, test_df):
    """Apply OneHotEncoding to nominal features and map ordinal features.
    
    Returns:
        (train_df, test_df, encoders)
    """
    train_df = train_df.copy()
    test_df = test_df.copy()
    
    # 1. Manual Ordinal Encoding
    stops_map = {'zero': 0, 'one': 1, 'two_or_more': 2}
    class_map = {'Economy': 0, 'Business': 1}
    
    for df in [train_df, test_df]:
        if 'stops' in df.columns:
            df['stops'] = df['stops'].map(stops_map).fillna(0)
        if 'class' in df.columns:
            df['class'] = df['class'].map(class_map).fillna(0)
    
    # 2. OneHotEncoding for Nominal Columns
    # Fit on both train and test to ensure consistent categories
    ohe = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    combined_df = pd.concat([train_df, test_df], axis=0)
    
    existing_nominal_cols = [col for col in NOMINAL_COLS if col in combined_df.columns]
    ohe.fit(combined_df[existing_nominal_cols])
    
    def apply_ohe(df):
        encoded = ohe.transform(df[existing_nominal_cols])
        encoded_df = pd.DataFrame(
            encoded,
            columns=ohe.get_feature_names_out(existing_nominal_cols),
            index=df.index
        )
        df_dropped = df.drop(columns=existing_nominal_cols)
        return pd.concat([df_dropped, encoded_df], axis=1)

    train_df = apply_ohe(train_df)
    test_df = apply_ohe(test_df)
    
    encoders = {
        'ohe': ohe,
        'stops_map': stops_map,
        'class_map': class_map,
        'nominal_cols': existing_nominal_cols
    }

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
    
    # Get y from 'price' column if it exists
    y = df['price'] if 'price' in df.columns else None
    
    # Ensure we drop the target column and unused id/timestamp cols
    cols_to_drop = [c for c in drop_cols if c in df.columns]
    X = df.drop(columns=cols_to_drop)
    
    return X, y


# ---------------------------------------------------------------------------
# Main training orchestrator — integrates Feast and OHE
# ---------------------------------------------------------------------------

def train_model():
    config = load_config()
    env = config['env']
    logger.info("Starting training pipeline", extra={"environment": env})

    # Paths based on environment dataset
    train_data_path = f"data/{env}_train.csv"
    test_data_path = f"data/{env}_test.csv"

    if not (os.path.exists(train_data_path) and os.path.exists(test_data_path)):
        logger.error("Data files not found", extra={"train_data_path": train_data_path, "test_data_path": test_data_path})
        exit(1)

    train_raw = pd.read_csv(train_data_path)
    test_raw = pd.read_csv(test_data_path)
    
    # Convert event_timestamp for Feast
    train_raw['event_timestamp'] = pd.to_datetime(train_raw['event_timestamp'], utc=True)
    test_raw['event_timestamp'] = pd.to_datetime(test_raw['event_timestamp'], utc=True)
    
    logger.info("Fetching features from Feast offline store")
    train_entity_df = train_raw[['flight_id', 'event_timestamp']]
    test_entity_df = test_raw[['flight_id', 'event_timestamp']]
    
    train_features = get_training_features(train_entity_df)
    test_features = get_training_features(test_entity_df)
    
    # Re-join the target column (price) back to the features
    train_df = pd.merge(train_features, train_raw[['flight_id', 'event_timestamp', 'price']], on=['flight_id', 'event_timestamp'], how='left')
    test_df = pd.merge(test_features, test_raw[['flight_id', 'event_timestamp', 'price']], on=['flight_id', 'event_timestamp'], how='left')

    # Preprocessing — now via helper (OHE and Ordinal)
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
        logger.info("Training metrics", extra={"rmse": metrics['rmse'], "r2": metrics['r2']})

        # Save encoders locally and log to MLflow so the serving container can download them
        os.makedirs("models", exist_ok=True)
        joblib.dump(encoders, "models/encoders.joblib")
        mlflow.log_artifact("models/encoders.joblib", artifact_path="encoders")

        # Log model
        mlflow.sklearn.log_model(clf, "model", registered_model_name=f"{config['model_name']}-{env}")

        # Output CML report data
        save_metrics(metrics, "metrics.txt")

if __name__ == "__main__":
    train_model()

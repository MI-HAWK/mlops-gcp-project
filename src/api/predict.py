import os
import time
import joblib
import pandas as pd
from fastapi import FastAPI
import mlflow.sklearn
from pydantic import BaseModel

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.config import load_config

app = FastAPI()

# Global variables to hold the loaded model and encoders
model = None
encoders = None
model_version_info = {}

# Metrics tracking for champion/challenger
request_metrics = {
    "total_requests": 0,
    "errors": 0,
    "latencies": [],
    "predictions": [],
}

class PredictionRequest(BaseModel):
    airline: str
    source_city: str
    departure_time: str
    stops: str
    arrival_time: str
    destination_city: str
    class_type: str
    duration: float
    days_left: int

@app.on_event("startup")
def load_assets():
    global model, encoders, model_version_info
    config = load_config()
    env = config['env']

    # Determine model version from env var (for champion/challenger)
    model_role = os.environ.get("MODEL_VERSION", "latest")

    # In a full Feast implementation, we'd pull features from the online store.
    # Here we are relying on direct API payload for prediction to simplify the API structure.

    # Load MLflow tracking
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    model_name = f"{config['model_name']}-{env}"

    # Try fetching the model from registry.
    try:
        if model_role in ("champion", "challenger"):
            model_uri = f"models:/{model_name}@{model_role}"
        else:
            model_uri = f"models:/{model_name}/latest"
        model = mlflow.sklearn.load_model(model_uri)
        model_version_info = {"name": model_name, "role": model_role, "uri": model_uri}
    except Exception as e:
        print(f"Warning: could not load model from MLflow: {e}")
        model = None

    try:
        client = mlflow.tracking.MlflowClient()
        if model_role in ("champion", "challenger"):
            mv = client.get_model_version_by_alias(model_name, model_role)
        else:
            versions = client.get_latest_versions(model_name)
            mv = versions[-1] if versions else None

        if mv:
            encoder_path = mlflow.artifacts.download_artifacts(
                f"runs:/{mv.run_id}/encoders/encoders.joblib"
            )
            encoders = joblib.load(encoder_path)
        else:
            encoders = joblib.load("models/encoders.joblib")
    except Exception as e:
        print(f"Warning: could not load encoders from MLflow ({e}), trying local path...")
        try:
            encoders = joblib.load("models/encoders.joblib")
        except Exception as e2:
            print(f"Warning: could not load encoders locally: {e2}")
            encoders = None

@app.get("/")
def root():
    return {"status": "ok", "message": "API root. Use /health or /predict"}

@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": model is not None, "env": load_config()['env']}

@app.get("/ready")
def ready():
    """Kubernetes readiness probe — returns 200 only if model is loaded."""
    if model is not None and encoders is not None:
        return {"status": "ready", "model_version": model_version_info}
    return {"status": "not_ready"}, 503

@app.get("/metrics")
def metrics():
    """Expose request metrics for champion/challenger comparison."""
    lats = request_metrics["latencies"]
    return {
        "model_version": model_version_info,
        "total_requests": request_metrics["total_requests"],
        "errors": request_metrics["errors"],
        "avg_latency_ms": round(sum(lats) / len(lats), 2) if lats else 0,
        "p95_latency_ms": round(sorted(lats)[int(len(lats)*0.95)] if lats else 0, 2),
        "avg_prediction": round(sum(request_metrics["predictions"]) / len(request_metrics["predictions"]), 2) if request_metrics["predictions"] else 0,
    }

@app.post("/predict")
def predict(req: PredictionRequest):
    start_time = time.time()
    request_metrics["total_requests"] += 1

    if model is None or encoders is None:
        request_metrics["errors"] += 1
        return {"error": "Model or encoders not loaded properly"}

    # Format exactly as pandas DF expected by model
    df = pd.DataFrame([{
        "airline": req.airline,
        "source_city": req.source_city,
        "departure_time": req.departure_time,
        "stops": req.stops,
        "arrival_time": req.arrival_time,
        "destination_city": req.destination_city,
        "class": req.class_type,
        "duration": req.duration,
        "days_left": req.days_left
    }])

    # Apply encoders
    for col, enc in encoders.items():
        if col in df.columns:
            # Handle unknown labels gracefully if needed, here we assume all known
            try:
                df[col] = enc.transform(df[col].astype(str))
            except ValueError:
                request_metrics["errors"] += 1
                return {"error": f"Unknown value in column {col}"}

    pred = model.predict(df)[0]
    elapsed = (time.time() - start_time) * 1000

    # Track metrics
    request_metrics["latencies"].append(elapsed)
    request_metrics["predictions"].append(float(pred))
    # Keep only last 1000 entries to bound memory
    if len(request_metrics["latencies"]) > 1000:
        request_metrics["latencies"] = request_metrics["latencies"][-1000:]
        request_metrics["predictions"] = request_metrics["predictions"][-1000:]

    return {"prediction_price": float(pred)}

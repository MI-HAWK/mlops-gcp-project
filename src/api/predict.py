import asyncio
import os
import time
import joblib
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import mlflow.sklearn
from pydantic import BaseModel

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.config import load_config

app = FastAPI()

model = None
encoders = None
model_info = {}

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
async def startup_event():
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, load_assets)

def load_assets():
    global model, encoders, model_info
    config = load_config()
    env = config['env']

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    model_name = f"{config['model_name']}-{env}"

    try:
        model_uri = f"models:/{model_name}/latest"
        model = mlflow.sklearn.load_model(model_uri)
        model_info = {"name": model_name, "uri": model_uri}
    except Exception as e:
        print(f"Warning: could not load model from MLflow: {e}")
        model = None

    try:
        client = mlflow.tracking.MlflowClient()
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
    if model is not None and encoders is not None:
        return {"status": "ready", "model": model_info}
    return JSONResponse(status_code=503, content={"status": "not_ready"})

@app.get("/metrics")
def metrics():
    lats = request_metrics["latencies"]
    return {
        "model": model_info,
        "model_version": model_info.get("name", "unknown"),
        "total_requests": request_metrics["total_requests"],
        "errors": request_metrics["errors"],
        "avg_latency_ms": round(sum(lats) / len(lats), 2) if lats else 0,
        "p95_latency_ms": round(sorted(lats)[int(len(lats) * 0.95)] if lats else 0, 2),
        "avg_prediction": round(sum(request_metrics["predictions"]) / len(request_metrics["predictions"]), 2) if request_metrics["predictions"] else 0,
    }

@app.post("/predict")
def predict(req: PredictionRequest):
    start_time = time.time()
    request_metrics["total_requests"] += 1

    if model is None or encoders is None:
        request_metrics["errors"] += 1
        return {"error": "Model or encoders not loaded properly"}

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

    for col, enc in encoders.items():
        if col in df.columns:
            try:
                df[col] = enc.transform(df[col].astype(str))
            except ValueError:
                request_metrics["errors"] += 1
                return {"error": f"Unknown value in column {col}"}

    pred = model.predict(df)[0]
    elapsed = (time.time() - start_time) * 1000

    request_metrics["latencies"].append(elapsed)
    request_metrics["predictions"].append(float(pred))
    if len(request_metrics["latencies"]) > 1000:
        request_metrics["latencies"] = request_metrics["latencies"][-1000:]
        request_metrics["predictions"] = request_metrics["predictions"][-1000:]

    return {"prediction_price": float(pred)}

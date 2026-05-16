import asyncio
import os
import time
import joblib
import pandas as pd
import logging
from pythonjsonlogger import jsonlogger
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
import mlflow.sklearn
from pydantic import BaseModel
import prometheus_client

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from src.utils.config import load_config

# Configure structured JSON logging
logger = logging.getLogger("ml_api")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# Configure OpenTelemetry Tracing
tracer_provider = TracerProvider()
try:
    cloud_trace_exporter = CloudTraceSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(cloud_trace_exporter))
except Exception as e:
    logger.warning("Could not initialize CloudTraceSpanExporter. Traces will not be sent to GCP.", extra={"error": str(e), "trace_id": ""})
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

# Configure Prometheus Metrics
REQUEST_COUNT = prometheus_client.Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'http_status'])
REQUEST_LATENCY = prometheus_client.Histogram('http_request_latency_seconds', 'HTTP Request Latency', ['method', 'endpoint'])
PREDICTION_VALUE = prometheus_client.Histogram('model_prediction_value', 'Model Prediction Value')

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)

model = None
encoders = None
model_info = {}

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
        logger.info("Model loaded successfully", extra={"model_uri": model_uri, "trace_id": ""})
    except Exception as e:
        logger.error("Warning: could not load model from MLflow", extra={"error": str(e), "trace_id": ""})
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
            logger.info("Encoders loaded from MLflow", extra={"trace_id": ""})
        else:
            encoders = joblib.load("models/encoders.joblib")
            logger.info("Encoders loaded locally", extra={"trace_id": ""})
    except Exception as e:
        logger.warning("Warning: could not load encoders from MLflow, trying local path...", extra={"error": str(e), "trace_id": ""})
        try:
            encoders = joblib.load("models/encoders.joblib")
            logger.info("Encoders loaded locally after MLflow failure", extra={"trace_id": ""})
        except Exception as e2:
            logger.error("Warning: could not load encoders locally", extra={"error": str(e2), "trace_id": ""})
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
    return Response(content=prometheus_client.generate_latest(), media_type="text/plain")

@app.post("/predict")
def predict(req: PredictionRequest):
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, "032x") if current_span.is_recording() else ""
    
    start_time = time.time()
    
    if model is None or encoders is None:
        REQUEST_COUNT.labels(method='POST', endpoint='/predict', http_status=500).inc()
        logger.error("Model or encoders not loaded properly", extra={"trace_id": trace_id})
        return JSONResponse(status_code=500, content={"error": "Model or encoders not loaded properly"})

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

    df['route'] = df['source_city'] + '_' + df['destination_city']

    # Ordinal encoding
    if 'stops' in df.columns and 'stops_map' in encoders:
        df['stops'] = df['stops'].map(encoders['stops_map']).fillna(0)
    if 'class' in df.columns and 'class_map' in encoders:
        df['class'] = df['class'].map(encoders['class_map']).fillna(0)

    # OneHotEncoding
    if 'ohe' in encoders and 'nominal_cols' in encoders:
        ohe = encoders['ohe']
        nom_cols = encoders['nominal_cols']
        try:
            encoded = ohe.transform(df[nom_cols])
            encoded_df = pd.DataFrame(encoded, columns=ohe.get_feature_names_out(nom_cols), index=df.index)
            df = pd.concat([df.drop(columns=nom_cols), encoded_df], axis=1)
        except Exception as e:
            REQUEST_COUNT.labels(method='POST', endpoint='/predict', http_status=400).inc()
            logger.error("Error during encoding", extra={"error": str(e), "trace_id": trace_id})
            return JSONResponse(status_code=400, content={"error": f"Error during encoding: {str(e)}"})

    if hasattr(model, 'feature_names_in_'):
        try:
            df = df[model.feature_names_in_]
        except Exception as e:
            REQUEST_COUNT.labels(method='POST', endpoint='/predict', http_status=400).inc()
            logger.error("Feature mismatch", extra={"error": str(e), "trace_id": trace_id})
            return JSONResponse(status_code=400, content={"error": f"Feature mismatch: {str(e)}"})

    try:
        pred = model.predict(df)[0]
    except Exception as e:
        REQUEST_COUNT.labels(method='POST', endpoint='/predict', http_status=500).inc()
        logger.error("Prediction failed", extra={"error": str(e), "trace_id": trace_id})
        return JSONResponse(status_code=500, content={"error": f"Prediction failed: {str(e)}"})
    
    elapsed = time.time() - start_time
    REQUEST_LATENCY.labels(method='POST', endpoint='/predict').observe(elapsed)
    REQUEST_COUNT.labels(method='POST', endpoint='/predict', http_status=200).inc()
    PREDICTION_VALUE.observe(float(pred))

    logger.info("Prediction successful", extra={"prediction_price": float(pred), "latency_s": elapsed, "trace_id": trace_id})
    return {"prediction_price": float(pred)}

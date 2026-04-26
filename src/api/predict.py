import os
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
    global model, encoders
    config = load_config()
    env = config['env']
    
    # In a full Feast implementation, we'd pull features from the online store.
    # Here we are relying on direct API payload for prediction to simplify the API structure.
    
    # Load MLflow tracking
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    model_name = f"{config['model_name']}-{env}"
    
    # Try fetching the latest production model from registry
    try:
        model_uri = f"models:/{model_name}/latest"
        model = mlflow.sklearn.load_model(model_uri)
    except Exception as e:
        print(f"Warning: could not load model from MLflow: {e}")
        model = None
        
    try:
        encoders = joblib.load("models/encoders.joblib")
    except Exception as e:
        encoders = None

@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": model is not None, "env": load_config()['env']}

@app.post("/predict")
def predict(req: PredictionRequest):
    if model is None or encoders is None:
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
                return {"error": f"Unknown value in column {col}"}
                
    pred = model.predict(df)[0]
    return {"prediction_price": float(pred)}

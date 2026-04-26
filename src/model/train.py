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
    
    # Preprocessing (simplified)
    # Fit LabelEncoder on the combined data to avoid unseen categorical issues
    combined_df = pd.concat([train_df, test_df], axis=0)
    
    categorical_cols = ['airline', 'source_city', 'departure_time', 'stops', 'arrival_time', 'destination_city', 'class']
    encoders = {}
    for col in categorical_cols:
        le = LabelEncoder()
        le.fit(combined_df[col].astype(str))
        train_df[col] = le.transform(train_df[col].astype(str))
        test_df[col] = le.transform(test_df[col].astype(str))
        encoders[col] = le
        
    X_train = train_df.drop(['price', 'flight'], axis=1, errors='ignore')
    y_train = train_df['price']
    
    X_test = test_df.drop(['price', 'flight'], axis=1, errors='ignore')
    y_test = test_df['price']
    
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(f"flight-pricing-{env}")
    
    with mlflow.start_run():
        n_estimators = config['training']['n_estimators']
        max_depth = config['training']['max_depth']
        
        mlflow.log_params({"n_estimators": n_estimators, "max_depth": max_depth})
        
        clf = RandomForestRegressor(n_estimators=n_estimators, max_depth=max_depth, random_state=42)
        clf.fit(X_train, y_train)
        
        preds = clf.predict(X_test)
        rmse = mean_squared_error(y_test, preds, squared=False)
        r2 = r2_score(y_test, preds)
        
        mlflow.log_metrics({"rmse": rmse, "r2": r2})
        print(f"Metrics - RMSE: {rmse:.2f}, R2: {r2:.2f}")
        
        # Save encoders locally
        os.makedirs("models", exist_ok=True)
        joblib.dump(encoders, "models/encoders.joblib")
        
        # Log model
        mlflow.sklearn.log_model(clf, "model", registered_model_name=f"{config['model_name']}-{env}")
        
        # Output CML report data
        with open("metrics.txt", "w") as f:
            f.write(f"RMSE: {rmse}\nR2: {r2}\n")

if __name__ == "__main__":
    train_model()

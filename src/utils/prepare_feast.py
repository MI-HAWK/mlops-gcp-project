import pandas as pd
import os

def prepare(env="dev"):
    csv_path = f"data/{env}_train.csv"
    pq_path = f"data/{env}_train.parquet"
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        if 'event_timestamp' in df.columns:
            df['event_timestamp'] = pd.to_datetime(df['event_timestamp'], utc=True)
        df.to_parquet(pq_path, index=False)
        print(f"Prepared {pq_path} from {csv_path} for Feast offline store.")
    else:
        print(f"Warning: {csv_path} not found.")

if __name__ == "__main__":
    env = os.getenv("ENV", "dev")
    prepare(env)

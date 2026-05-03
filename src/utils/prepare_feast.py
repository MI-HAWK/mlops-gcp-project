import pandas as pd
import os

def prepare(env="dev"):
    csv_path = f"data/{env}_train.csv"
    pq_path = f"data/{env}_train.parquet"
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        if 'event_timestamp' in df.columns:
            df['event_timestamp'] = pd.to_datetime(df['event_timestamp'], utc=True)
        
        # Protect GitHub Actions (7GB RAM limit) from OOMing on large production datasets
        if len(df) > 50000:
            df = df.sample(n=50000, random_state=42)
            # Overwrite the CSV so train.py reads the exact same sampled rows
            df.to_csv(csv_path, index=False)

        df.to_parquet(pq_path, index=False)
        print(f"Prepared {pq_path} from {csv_path} for Feast offline store (sampled to {len(df)} rows).")
    else:
        print(f"Warning: {csv_path} not found.")

if __name__ == "__main__":
    env = os.getenv("ENV", "dev")
    prepare(env)

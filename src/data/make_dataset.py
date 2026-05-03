import pandas as pd
import os
from sklearn.model_selection import train_test_split

def create_splits(input_path="Clean_Dataset.csv", output_dir="data"):
    print("Loading dataset...")
    df = pd.read_csv(input_path)
    
    # Preprocessing for Feast
    if 'flight' in df.columns:
        df = df.rename(columns={'flight': 'flight_id'})
    
    # Add event_timestamp for Feast offline store compatibility
    df['event_timestamp'] = pd.Timestamp.now(tz='UTC')
    
    # Add new route feature
    if 'source_city' in df.columns and 'destination_city' in df.columns:
        df['route'] = df['source_city'] + '_' + df['destination_city']
    
    # Create once: Full Dataset -> Train / Test (80 / 20)
    train_full, test_fixed = train_test_split(df, test_size=0.2, random_state=42)
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Global train size: {len(train_full)}, Global test size: {len(test_fixed)}")
    
    # DEV dataset - 1% of train, fixed test
    dev_train = train_full.sample(frac=0.05, random_state=42)
    
    # STAGING dataset - 20% of train, same test
    staging_train = train_full.sample(frac=0.20, random_state=42)
    
    # PROD dataset - 100% of train, same test
    prod_train = train_full
    
    # Save DEV datasets
    dev_train.to_csv(os.path.join(output_dir, "dev_train.csv"), index=False)
    test_fixed.to_csv(os.path.join(output_dir, "dev_test.csv"), index=False)
    print(f"DEV split: {len(dev_train)} train rows, {len(test_fixed)} test rows")
    
    # Save STAGING datasets
    staging_train.to_csv(os.path.join(output_dir, "staging_train.csv"), index=False)
    test_fixed.to_csv(os.path.join(output_dir, "staging_test.csv"), index=False)
    print(f"STAGING split: {len(staging_train)} train rows, {len(test_fixed)} test rows")
    
    # Save PROD datasets
    prod_train.to_csv(os.path.join(output_dir, "prod_train.csv"), index=False)
    test_fixed.to_csv(os.path.join(output_dir, "prod_test.csv"), index=False)
    print(f"PROD split: {len(prod_train)} train rows, {len(test_fixed)} test rows")

if __name__ == "__main__":
    create_splits()

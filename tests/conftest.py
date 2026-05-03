"""Shared pytest fixtures for the entire test suite."""
import os
import sys
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from sklearn.preprocessing import LabelEncoder

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Force dev config for tests
os.environ.setdefault("ENV", "dev")


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_flight_data():
    """Minimal flight pricing DataFrame for testing."""
    df = pd.DataFrame({
        'airline': ['Vistara', 'Air_India', 'Indigo', 'Vistara', 'SpiceJet'],
        'flight_id': ['UK-1', 'AI-2', 'IN-3', 'UK-4', 'SJ-5'],
        'source_city': ['Delhi', 'Mumbai', 'Bangalore', 'Delhi', 'Kolkata'],
        'departure_time': ['Morning', 'Evening', 'Afternoon', 'Night', 'Morning'],
        'stops': ['one', 'zero', 'two_or_more', 'one', 'zero'],
        'arrival_time': ['Afternoon', 'Night', 'Morning', 'Evening', 'Afternoon'],
        'destination_city': ['Mumbai', 'Delhi', 'Chennai', 'Hyderabad', 'Delhi'],
        'class': ['Business', 'Economy', 'Economy', 'Business', 'Economy'],
        'duration': [5.5, 2.0, 3.5, 4.0, 6.0],
        'days_left': [15, 3, 45, 1, 20],
        'price': [12000, 3500, 4200, 15000, 2800],
    })
    df['event_timestamp'] = pd.Timestamp.now(tz='UTC')
    df['route'] = df['source_city'] + '_' + df['destination_city']
    return df


@pytest.fixture
def sample_train_df(sample_flight_data):
    return sample_flight_data.iloc[:3].copy()


@pytest.fixture
def sample_test_df(sample_flight_data):
    return sample_flight_data.iloc[3:].copy()


@pytest.fixture
def mock_encoders():
    """Mock the new encoders layout."""
    from sklearn.preprocessing import OneHotEncoder
    import pandas as pd
    
    stops_map = {'zero': 0, 'one': 1, 'two_or_more': 2}
    class_map = {'Economy': 0, 'Business': 1}
    
    nom_cols = ['airline', 'source_city', 'destination_city', 'departure_time', 'arrival_time', 'route']
    df = pd.DataFrame({
        'airline': ['Air_India', 'Indigo'],
        'source_city': ['Bangalore', 'Delhi'],
        'destination_city': ['Chennai', 'Delhi'],
        'departure_time': ['Afternoon', 'Evening'],
        'arrival_time': ['Afternoon', 'Evening'],
        'route': ['Bangalore_Chennai', 'Delhi_Delhi']
    })
    ohe = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    ohe.fit(df)
    
    return {
        'ohe': ohe,
        'stops_map': stops_map,
        'class_map': class_map,
        'nominal_cols': nom_cols
    }


@pytest.fixture
def mock_config():
    """Dev config as a dict."""
    return {
        'env': 'dev',
        'gcs_bucket': 'gs://test-bucket',
        'model_name': 'flight-pricing-model',
        'dvc_remote': 'dev-gcs',
        'feast_offline_store_type': 'file',
        'training': {
            'n_estimators': 10,
            'max_depth': 5,
        }
    }


# ---------------------------------------------------------------------------
# FastAPI test client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(mock_encoders):
    """FastAPI TestClient with mocked model and encoders."""
    from fastapi.testclient import TestClient
    from sklearn.ensemble import RandomForestRegressor
    import pandas as pd

    ohe = mock_encoders['ohe']
    nom_cols = mock_encoders['nominal_cols']
    
    df = pd.DataFrame({
        'airline': ['Air_India', 'Indigo'],
        'source_city': ['Bangalore', 'Delhi'],
        'destination_city': ['Chennai', 'Delhi'],
        'departure_time': ['Afternoon', 'Evening'],
        'arrival_time': ['Afternoon', 'Evening'],
        'route': ['Bangalore_Chennai', 'Delhi_Delhi'],
        'stops': [0, 1],
        'class': [0, 1],
        'duration': [5.0, 2.0],
        'days_left': [10, 5],
    })
    
    encoded = ohe.transform(df[nom_cols])
    encoded_df = pd.DataFrame(encoded, columns=ohe.get_feature_names_out(nom_cols))
    X = pd.concat([df.drop(columns=nom_cols), encoded_df], axis=1)
    
    y = [10000, 5000]
    rf = RandomForestRegressor(n_estimators=2, random_state=42)
    rf.fit(X, y)

    # Patch the module globals
    import src.api.predict as predict_module
    predict_module.model = rf
    predict_module.encoders = mock_encoders
    predict_module.model_version_info = {"name": "test", "role": "latest"}

    client = TestClient(predict_module.app)
    yield client

    # Cleanup
    predict_module.model = None
    predict_module.encoders = None


@pytest.fixture
def valid_predict_payload():
    """Valid prediction request payload."""
    return {
        "airline": "Vistara",
        "source_city": "Delhi",
        "departure_time": "Morning",
        "stops": "one",
        "arrival_time": "Afternoon",
        "destination_city": "Mumbai",
        "class_type": "Business",
        "duration": 5.5,
        "days_left": 15
    }

from feast import Entity, Field, FeatureView, FileSource
from feast.types import Float32, Int32, String
from datetime import timedelta
import os

# Define the flight as an entity
flight = Entity(name="flight", join_keys=["flight_id"])

# Determine data path from environment
_env = os.getenv("ENV", "dev")
_data_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", f"{_env}_train.csv")
)

# Defining the offline source
flight_stats_source = FileSource(
    path=_data_path,
    timestamp_field="event_timestamp",
)

# Define feature view with ALL feature fields
flight_features = FeatureView(
    name="flight_features",
    entities=[flight],
    ttl=timedelta(days=1),
    schema=[
        Field(name="duration", dtype=Float32),
        Field(name="days_left", dtype=Int32),
        Field(name="airline", dtype=String),
        Field(name="source_city", dtype=String),
        Field(name="departure_time", dtype=String),
        Field(name="stops", dtype=String),
        Field(name="arrival_time", dtype=String),
        Field(name="destination_city", dtype=String),
        Field(name="class", dtype=String),
    ],
    online=True,
    source=flight_stats_source,
    tags={"env": _env},
)

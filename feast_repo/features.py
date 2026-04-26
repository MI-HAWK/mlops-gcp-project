from feast import Entity, Field, FeatureView, FileSource
from feast.types import Float32, Int32, String
from datetime import timedelta

# Define the flight as an entity
flight = Entity(name="flight", join_keys=["flight_id"])

# Defining the offline source
flight_stats_source = FileSource(
    path="../data/staging_dataset.csv",
    timestamp_field="event_timestamp",
)

# Define feature view
flight_features = FeatureView(
    name="flight_features",
    entities=[flight],
    ttl=timedelta(days=1),
    schema=[
        Field(name="duration", dtype=Float32),
        Field(name="days_left", dtype=Int32),
        Field(name="airline", dtype=String),
        Field(name="source_city", dtype=String),
        Field(name="destination_city", dtype=String),
        Field(name="class", dtype=String),
    ],
    online=True,
    source=flight_stats_source,
    tags={},
)

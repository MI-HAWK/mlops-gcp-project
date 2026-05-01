"""Feast feature store utilities.

Provides helper functions for offline (training) and online (inference)
feature retrieval. Falls back gracefully if Feast is unavailable.
"""
import os
import pandas as pd


def get_feast_store(repo_path=None):
    """Initialize and return a Feast FeatureStore instance."""
    from feast import FeatureStore
    if repo_path is None:
        repo_path = os.path.join(os.path.dirname(__file__), '..', '..', 'feast_repo')
    return FeatureStore(repo_path=repo_path)


def get_training_features(entity_df, feature_refs=None, repo_path=None):
    """Retrieve features from Feast offline store for training.

    Args:
        entity_df: DataFrame with entity keys and event_timestamp.
        feature_refs: List of feature references (e.g. 'flight_features:duration').
        repo_path: Path to feast repo directory.

    Returns:
        DataFrame with joined features.
    """
    if feature_refs is None:
        feature_refs = [
            "flight_features:duration",
            "flight_features:days_left",
            "flight_features:airline",
            "flight_features:source_city",
            "flight_features:destination_city",
            "flight_features:departure_time",
            "flight_features:arrival_time",
            "flight_features:stops",
            "flight_features:class",
        ]

    store = get_feast_store(repo_path)
    training_df = store.get_historical_features(
        entity_df=entity_df,
        features=feature_refs,
    ).to_df()
    return training_df


def get_online_features(entity_dict, feature_refs=None, repo_path=None):
    """Retrieve features from Feast online store for inference.

    Args:
        entity_dict: Dict with entity key values (e.g. {'flight_id': ['AI-101']}).
        feature_refs: List of feature references.
        repo_path: Path to feast repo directory.

    Returns:
        Dict of feature name → value.
    """
    if feature_refs is None:
        feature_refs = [
            "flight_features:duration",
            "flight_features:days_left",
        ]

    store = get_feast_store(repo_path)
    result = store.get_online_features(
        features=feature_refs,
        entity_rows=[entity_dict],
    ).to_dict()
    return result


def materialize_features(repo_path=None, start_date=None, end_date=None):
    """Materialize features from offline to online store."""
    from datetime import datetime, timedelta
    store = get_feast_store(repo_path)
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(days=7)
    store.materialize(start_date=start_date, end_date=end_date)
    print(f"Materialized features from {start_date} to {end_date}")

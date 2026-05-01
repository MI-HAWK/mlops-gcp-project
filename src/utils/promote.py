"""MLflow model promotion utility.

Manages champion/challenger lifecycle in the MLflow Model Registry.
"""
import mlflow
from mlflow.tracking import MlflowClient
import os


def get_mlflow_client():
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    return MlflowClient(tracking_uri)


def promote_model(model_name, version, target_alias="champion"):
    """Set an alias on a specific model version in the registry.

    Args:
        model_name: Registered model name (e.g. 'flight-pricing-model-prod').
        version: Model version number to promote.
        target_alias: Alias to assign ('champion' or 'challenger').
    """
    client = get_mlflow_client()
    client.set_registered_model_alias(model_name, target_alias, version)
    print(f"Model '{model_name}' v{version} promoted to alias '{target_alias}'")
    return {"model_name": model_name, "version": version, "alias": target_alias}


def get_champion_version(model_name):
    """Get the current champion model version."""
    client = get_mlflow_client()
    try:
        mv = client.get_model_version_by_alias(model_name, "champion")
        return mv.version
    except Exception:
        return None


def get_latest_version(model_name):
    """Get the latest model version from the registry."""
    client = get_mlflow_client()
    versions = client.get_latest_versions(model_name)
    if versions:
        return max(versions, key=lambda v: int(v.version)).version
    return None


def archive_model(model_name, version):
    """Archive a model version by setting alias to 'archived'."""
    client = get_mlflow_client()
    try:
        client.set_registered_model_alias(model_name, f"archived-v{version}", version)
        print(f"Model '{model_name}' v{version} archived")
    except Exception as e:
        print(f"Warning: could not archive model: {e}")


def swap_champion(model_name, new_version):
    """Full promotion: archive old champion, promote new one."""
    old_champ = get_champion_version(model_name)
    if old_champ:
        archive_model(model_name, old_champ)
    return promote_model(model_name, new_version, "champion")


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "flight-pricing-model-prod"
    ver = sys.argv[2] if len(sys.argv) > 2 else "1"
    swap_champion(name, ver)

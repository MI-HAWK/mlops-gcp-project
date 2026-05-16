"""Integration tests for the FastAPI prediction endpoints."""
import pytest

pytestmark = pytest.mark.integration


class TestHealthEndpoint:
    def test_health_returns_200(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "model_loaded" in data
        assert "env" in data

    def test_health_model_loaded(self, api_client):
        resp = api_client.get("/health")
        data = resp.json()
        assert data["model_loaded"] is True


class TestRootEndpoint:
    def test_root_returns_ok(self, api_client):
        resp = api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestReadyEndpoint:
    def test_ready_when_model_loaded(self, api_client):
        resp = api_client.get("/ready")
        assert resp.status_code == 200


class TestMetricsEndpoint:
    def test_metrics_returns_structure(self, api_client):
        resp = api_client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "http_requests_total" in text
        assert "http_request_latency_seconds" in text


class TestPredictEndpoint:
    def test_predict_valid_payload(self, api_client, valid_predict_payload):
        resp = api_client.post("/predict", json=valid_predict_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "prediction_price" in data
        assert isinstance(data["prediction_price"], float)

    def test_predict_missing_fields_returns_422(self, api_client):
        resp = api_client.post("/predict", json={"airline": "Vistara"})
        assert resp.status_code == 422  # Pydantic validation error

    def test_predict_unknown_category_is_ignored(self, api_client):
        payload = {
            "airline": "UNKNOWN_AIRLINE_XYZ",
            "source_city": "Delhi",
            "departure_time": "Morning",
            "stops": "one",
            "arrival_time": "Afternoon",
            "destination_city": "Mumbai",
            "class_type": "Business",
            "duration": 5.5,
            "days_left": 15
        }
        resp = api_client.post("/predict", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # Should return a prediction because OneHotEncoder(handle_unknown='ignore') handles it
        assert "prediction_price" in data

    def test_predict_updates_metrics(self, api_client, valid_predict_payload):
        # Make a prediction
        api_client.post("/predict", json=valid_predict_payload)

        # Check metrics updated (Prometheus text format)
        resp = api_client.get("/metrics")
        text = resp.text
        assert "http_requests_total" in text
        assert "model_prediction_value" in text

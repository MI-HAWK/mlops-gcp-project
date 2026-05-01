"""Champion vs Challenger model comparison utility.

Queries both model endpoints and compares latency + prediction quality.
"""
import time
import statistics
import requests

DEFAULT_TEST_PAYLOAD = {
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


def query_model(endpoint_url, payload=None, n_requests=10):
    if payload is None:
        payload = DEFAULT_TEST_PAYLOAD
    latencies, predictions, errors = [], [], 0
    for _ in range(n_requests):
        try:
            start = time.time()
            resp = requests.post(f"{endpoint_url}/predict", json=payload, timeout=10)
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                latencies.append(elapsed)
                if "prediction_price" in data:
                    predictions.append(data["prediction_price"])
            else:
                errors += 1
        except Exception:
            errors += 1
    if not latencies:
        return {"error": "All requests failed", "error_count": errors, "success_count": 0}
    s = sorted(latencies)
    return {
        "success_count": len(latencies), "error_count": errors,
        "latency_p50_ms": round(s[int(len(s)*0.5)], 2),
        "latency_p95_ms": round(s[min(int(len(s)*0.95), len(s)-1)], 2),
        "latency_mean_ms": round(statistics.mean(latencies), 2),
        "prediction_mean": round(statistics.mean(predictions), 2) if predictions else None,
    }


def compare_models(champion_url, challenger_url, n_requests=20, payload=None):
    champ = query_model(champion_url, payload, n_requests)
    chall = query_model(challenger_url, payload, n_requests)
    rec, reasons = "NO_CHANGE", []
    if "error" in champ or "error" in chall:
        rec = "INCONCLUSIVE"
        reasons.append("One or both models had failures")
    else:
        if chall["latency_p50_ms"] < champ["latency_p50_ms"]:
            reasons.append("Challenger has lower latency")
            rec = "PROMOTE_CHALLENGER"
        if chall["error_count"] > champ["error_count"]:
            reasons.append("Challenger has more errors")
            rec = "NO_CHANGE"
    return {"champion": champ, "challenger": chall, "recommendation": rec, "reasons": reasons}


def generate_report(comparison):
    lines = ["# Champion vs Challenger Report", "",
             "| Metric | Champion | Challenger |", "|--------|----------|------------|"]
    for k in ["success_count","error_count","latency_p50_ms","latency_p95_ms","prediction_mean"]:
        lines.append(f"| {k} | {comparison['champion'].get(k,'N/A')} | {comparison['challenger'].get(k,'N/A')} |")
    lines.extend(["", f"## Recommendation: **{comparison['recommendation']}**", ""])
    for r in comparison.get("reasons", []):
        lines.append(f"- {r}")
    return "\n".join(lines)

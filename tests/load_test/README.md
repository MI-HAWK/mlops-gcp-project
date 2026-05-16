# MLOps Performance Benchmarking

This directory contains scripts and documentation for running load, stress, and autoscaling tests against the ML API using `wrk`.

## Prerequisites
- Install [wrk](https://github.com/wg/wrk).
- Get the external IP of the production LoadBalancer:
  ```bash
  export PROD_IP=$(kubectl get svc ml-api-prod-svc -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
  ```

## 1. Concurrency Test (Throughput & Latency)
Test the API's standard throughput capability and monitor p95/p99 latency (Industry standard SLO: p95 < 150ms).
```bash
wrk -t4 -c100 -d30s -s tests/load_test/benchmark.lua http://$PROD_IP/predict
```
- `-t4`: Use 4 threads
- `-c100`: Maintain 100 concurrent HTTP connections
- `-d30s`: Run for 30 seconds

## 2. Stress Test (Autoscaling Validation)
Push the service beyond its current limits to trigger the `HorizontalPodAutoscaler` (HPA).
```bash
wrk -t8 -c500 -d120s -s tests/load_test/benchmark.lua http://$PROD_IP/predict
```
While running this test, open another terminal to monitor HPA:
```bash
kubectl get hpa ml-api-prod-hpa -w
```
You should observe CPU/Memory utilization spike and the replica count scale up from `2` up to `10`.

## 3. Observability Validation
While generating load, verify that:
1. **Logs**: Structured JSON logs stream into GCP Cloud Logging with unique `trace_id` values.
2. **Traces**: GCP Cloud Trace shows distributed traces, capturing request latency breakdown.
3. **Metrics**: GCP Managed Prometheus captures `http_requests_total` and `http_request_latency_seconds` under heavy load.

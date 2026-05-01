# GCP Infrastructure Execution Guide

This guide details the exact configurations to deploy and initialize the environments for the 3-tier MLOps project. Ensure you run this inside the Google Cloud Shell or a local terminal authenticated with `gcloud`.

## Ensure Initialization
Run in **Cloud Shell or local terminal**:
```bash
gcloud auth login
export PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
gcloud config set project $PROJECT_ID
export REGION="us-central1"
```

## 0. Enable Required GCP APIs
Run in **Cloud Shell or local terminal**. This enables all GCP services used by the pipeline:
```bash
gcloud services enable \
    container.googleapis.com \
    artifactregistry.googleapis.com \
    compute.googleapis.com \
    iamcredentials.googleapis.com \
    storage.googleapis.com
```

## 1. Cloud Storage Buckets (Data Isolation)
Create buckets for data versions and DVC remotes:
```bash
# DEV Bucket (Small data, fast iter)
gsutil mb -l $REGION gs://${PROJECT_ID}-mlops-dev-data

# STAGING Bucket
gsutil mb -l $REGION gs://${PROJECT_ID}-mlops-staging-data

# PROD Bucket
gsutil mb -l $REGION gs://${PROJECT_ID}-mlops-prod-data
```

## 2. Artifact Registry (For Docker Images)
```bash
gcloud artifacts repositories create ml-repo \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repository for flight pricing API"
```

## 3. Kubernetes Clusters (GKE)
*Note: Depending on budget, you may want to use Autopilot or minimum node configurations.*

```bash
# Staging Cluster (regional)
gcloud container clusters create staging-gke-cluster \
    --region $REGION \
    --num-nodes 1 \
    --machine-type n1-standard-2 \
    --disk-size 30

# Prod Cluster (zonal — must be us-central1-a; all prod workflows hardcode this zone)
gcloud container clusters create prod-gke-cluster \
    --zone us-central1-a \
    --num-nodes 1 \
    --machine-type n1-standard-2 \
    --disk-size 30

```

## 4. Git & DVC Initialization
On your **local machine**:
```bash
# Ensure you are in the project folder
git init

# Re-slice dataset to ensure sizes if make_dataset failed earlier
python src/data/make_dataset.py

# Initialize DVC
dvc init

# Setup DVC Remotes
dvc remote add -d dev-gcs gs://${PROJECT_ID}-mlops-dev-data
dvc remote add staging-gcs gs://${PROJECT_ID}-mlops-staging-data
dvc remote add prod-gcs gs://${PROJECT_ID}-mlops-prod-data

# Track Data (Dev first)
dvc add data/dev_train.csv data/dev_test.csv
dvc push -r dev-gcs

# Track others
dvc add data/staging_train.csv data/staging_test.csv
dvc push -r staging-gcs

dvc add data/prod_train.csv data/prod_test.csv
dvc push -r prod-gcs

# Commit tracker files
git add .
git commit -m "Initialize DVC, code, and CI/CD pipelines"
```

## 5. Identity and Access Management (IAM) & Security

We use Workload Identity Federation (WIF) to allow GitHub Actions to authenticate to GCP without using long-lived JSON keys. 

### Create Service Account & Grant Roles
Run in **Cloud Shell or local terminal**:
```bash
# Set your GitHub Username/Org and Repo Name
export GITHUB_REPO="<YOUR_GITHUB_ORG>/<YOUR_REPO_NAME>"

# Create the Service Account
gcloud iam service-accounts create github-actions-sa \
    --description="Service account for GitHub Actions CI/CD" \
    --display-name="GitHub Actions SA"

export SA_EMAIL="github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant least-privilege roles needed for MLOps pipeline
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/container.developer"
```

### Configure Workload Identity Federation
```bash
# Enable IAM Credentials API
gcloud services enable iamcredentials.googleapis.com

# Create Workload Identity Pool
gcloud iam workload-identity-pools create github-pool-v2 \
    --location="global" \
    --description="Pool for GitHub Actions" \
    --display-name="GitHub Actions Pool"

export WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe github-pool-v2 --location="global" --format="value(name)")

# Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
    --location="global" \
    --workload-identity-pool="github-pool-v2" \
    --display-name="GitHub Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com"

# Allow GitHub Repo to impersonate the Service Account
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_REPO}"

# Get the Provider ID to put in GitHub Secrets
gcloud iam workload-identity-pools providers describe github-provider \
    --location="global" \
    --workload-identity-pool="github-pool-v2" \
    --format="value(name)"
```

## 6. Central MLflow Tracking Server (Compute VM)

To track experiments centrally, we will spin up a small Virtual Machine that automatically installs and runs MLflow in the background via a startup script.

Run in **Cloud Shell or local terminal**:
```bash
# Allow web traffic to port 5000 (MLflow default port)
gcloud compute firewall-rules create allow-mlflow-5000 \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:5000 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=mlflow-server

# Create the VM with an automated startup script
gcloud compute instances create mlflow-tracking-server \
    --zone=us-central1-a \
    --machine-type=e2-standard-2 \
    --tags=mlflow-server \
    --metadata=startup-script="#! /bin/bash
    sudo apt-get update
    sudo apt-get install python3-pip -y
    pip3 install mlflow --break-system-packages
    nohup python3 -m mlflow server   --host 0.0.0.0   --port 5000   --allowed-hosts '*'   --cors-allowed-origins '*' > mlflow.log 2>&1 &"

# Get the Public IP Address of your new server
gcloud compute instances describe mlflow-tracking-server \
    --zone=us-central1-a \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

> **Note:** Wait about 2 to 3 minutes for the VM to fully finish downloading and installing Python/MLflow in the background before trying to access the IP!

## 7. GitHub Actions Secrets Setup
In your **GitHub Repository**, navigate to **Settings > Secrets and variables > Actions** and add:
- `GCP_PROJECT`: Your project ID.
- `WIF_PROVIDER`: The output from the final `providers describe` command in Section 5.
- `WIF_SERVICE_ACCOUNT`: The email of your service account (`github-actions-sa@...`).
- `MLFLOW_TRACKING_URI`: Take the IP address printed from Section 6 and write exactly: `http://<YOUR_IP_ADDRESS>:5000`

*(Important Note: You do NOT need to create a secret called `GITHUB_TOKEN`. GitHub automatically provides this behind the scenes. However, you MUST give it permission to write comments: Go to **Settings > Actions > General**, scroll down to **Workflow permissions**, and select **Read and write permissions**, then click Save).*

---

## 8. Kubernetes ConfigMap — Prod and Staging Clusters
The champion and challenger deployments read `MLFLOW_TRACKING_URI` from a Kubernetes ConfigMap named `mlflow-config`. Create it in both clusters after the MLflow VM is running and you have its IP from Section 6.

### Prod Cluster
Run in **Cloud Shell or local terminal**:
```bash
# Point kubectl at the prod cluster (zonal — must match the zone used at creation)
gcloud container clusters get-credentials prod-gke-cluster \
    --zone us-central1-a

# Replace <YOUR_MLFLOW_IP> with the IP printed in Section 6
kubectl create configmap mlflow-config \
    --from-literal=MLFLOW_TRACKING_URI=http://<YOUR_MLFLOW_IP>:5000

# Verify
kubectl get configmap mlflow-config -o yaml
```

### Staging Cluster
```bash
gcloud container clusters get-credentials staging-gke-cluster \
    --region us-central1

kubectl create configmap mlflow-config \
    --from-literal=MLFLOW_TRACKING_URI=http://<YOUR_MLFLOW_IP>:5000
```

> **Note:** If the MLflow VM is ever recreated and gets a new IP, patch both ConfigMaps without deleting them:
> ```bash
> kubectl create configmap mlflow-config \
>     --from-literal=MLFLOW_TRACKING_URI=http://<NEW_IP>:5000 \
>     --dry-run=client -o yaml | kubectl apply -f -
> ```
> Run this on each cluster after switching contexts.

## 9. GKE BackendConfig — Prod Ingress
`infra/k8s/prod/ingress.yaml` references a GKE `BackendConfig` named `ml-api-backend-config` to configure health checks on the Cloud Load Balancer. Apply it to the prod cluster once, before the first prod deployment, or the ingress will fail to provision correctly.

Run in **Cloud Shell or local terminal** (with prod cluster credentials active from the previous section):
```bash
kubectl apply -f - <<'EOF'
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: ml-api-backend-config
spec:
  healthCheck:
    checkIntervalSec: 30
    port: 8080
    type: HTTP
    requestPath: /health
EOF
```

## 10. CI/CD Pipeline Overview
The pipeline has five GitHub Actions workflows. Pushes and PRs to specific branches trigger them automatically — no manual action is needed except for model promotion (Section 12).

| Workflow | File | Trigger | What It Does |
|---|---|---|---|
| CI — Dev | `1-ci-dev.yaml` | PR → `develop` | Runs unit/integration/sanity tests, trains on dev data, enforces quality gate (RMSE ≤ 5% regression); posts CML report on PR |
| CD — Staging | `2-cd-staging.yaml` | Push → `develop` | Trains on staging data, builds `flight-pricing-api` Docker image, pushes to Artifact Registry (`staging-latest` tag), deploys to `staging-gke-cluster` |
| CI — Prod | `3-ci-prod.yaml` | PR → `main` | Full test suite + schema validation (`src.utils.schema`) + drift check (PSI ≤ 0.2, advisory) + trains on prod data + strict gate (RMSE ≤ 2%); posts CML report |
| CD — Prod | `4-cd-prod.yaml` | Push → `main` | Registers model as `challenger` in MLflow, builds challenger image, deploys champion + challenger to `prod-gke-cluster` with 50/50 NGINX traffic split via `infra/k8s/prod/` manifests |
| Promote Model | `5-promote-model.yaml` | Manual dispatch (GitHub UI) | Sets MLflow `champion` alias, updates `traffic-split-config` ConfigMap, restarts NGINX splitter, scales loser to 0, re-tags winning image as `champion-latest` |

**Branch strategy:**
- Work on feature branches → open PR to `develop` (triggers CI-Dev)
- Merge to `develop` → staging deploys automatically (triggers CD-Staging)
- Open PR from `develop` → `main` (triggers CI-Prod)
- Merge to `main` → prod deploys automatically (triggers CD-Prod)

## 11. First-Time End-to-End Pipeline Run
Follow this sequence exactly on the first run. GitHub Actions steps are fully automatic — you only trigger them by opening PRs or merging.

### Step 1 — Authenticate Locally and Push Data to DVC Remotes
Run **locally** in the project root:
```bash
# Allow local gcloud to access GCS on your behalf
gcloud auth application-default login

# Generate dataset splits (creates dev/staging/prod CSVs under data/)
python src/data/make_dataset.py

# Track and push dev data
dvc add data/dev_train.csv data/dev_test.csv
dvc push -r dev-gcs

# Track and push staging data
dvc add data/staging_train.csv data/staging_test.csv
dvc push -r staging-gcs

# Track and push prod data
dvc add data/prod_train.csv data/prod_test.csv
dvc push -r prod-gcs

# Commit the .dvc pointer files
git add data/*.dvc .dvc/config
git commit -m "Add DVC-tracked datasets for all environments"
git push origin develop
```

### Step 2 — Trigger Dev CI (PR to develop)
Run **locally**:
```bash
git checkout -b feature/initial-model
# make any code change, then:
git add -A && git commit -m "Initial model version"
git push origin feature/initial-model
```
Open a **Pull Request** on GitHub from `feature/initial-model` → `develop`. This triggers `1-ci-dev.yaml` automatically. A CML report comment appears on the PR with RMSE metrics and a comparison against the base branch. Merge the PR when the quality gate passes (green check).

### Step 3 — Staging Deployment (automatic after merge to develop)
Merging the PR in Step 2 triggers `2-cd-staging.yaml`. Monitor it in **GitHub → Actions tab**. It will train on staging data, build the image, and deploy to `staging-gke-cluster`. After the workflow completes:
```bash
# Run in Cloud Shell or local terminal
gcloud container clusters get-credentials staging-gke-cluster --region us-central1
kubectl get service ml-api-staging-svc   # note the EXTERNAL-IP column
curl http://<STAGING_LB_IP>/health
curl http://<STAGING_LB_IP>/ready
```

### Step 4 — Trigger Prod CI (PR to main)
On **GitHub**, open a Pull Request from `develop` → `main`. This triggers `3-ci-prod.yaml`. It runs schema validation, PSI drift detection (comparing prod vs dev data), and a stricter RMSE gate (≤ 2%). A CML report is posted on the PR. Merge when it passes.

### Step 5 — Prod Deployment (automatic after merge to main)
Merging triggers `4-cd-prod.yaml`. It registers the model as `challenger` in MLflow, builds the image, and deploys the full champion-challenger setup to `prod-gke-cluster`. After it completes:
```bash
# Run in Cloud Shell or local terminal
gcloud container clusters get-credentials prod-gke-cluster --zone us-central1-a
# The ingress provisions a Cloud Load Balancer — allow 2-3 minutes for an IP to appear
kubectl get ingress ml-pricing-ingress
curl http://<INGRESS_ADDRESS>/health
```
> **Note:** On the first deployment there is no prior champion image. The workflow will use the challenger image for both the champion and challenger deployments. A true A/B split activates from the second prod deployment onward.

## 12. Monitor and Promote Models (Champion-Challenger)

### Check Live Metrics
Run in **Cloud Shell or local terminal** with prod cluster credentials active:
```bash
# Forward each service locally to query /metrics without exposing them publicly
kubectl port-forward service/ml-api-champion-svc 8081:80 &
kubectl port-forward service/ml-api-challenger-svc 8082:80 &

curl http://localhost:8081/metrics   # champion: avg_latency_ms, p95_latency_ms, avg_prediction, total_requests
curl http://localhost:8082/metrics   # challenger: same fields
```

Or run the built-in comparison script **locally** (requires the port-forwards above to be active):
```bash
python -c "
from src.utils.compare_models import compare_models, generate_report
result = compare_models('http://localhost:8081', 'http://localhost:8082', n_requests=20)
print(generate_report(result))
"
```
The report will output a recommendation: `PROMOTE_CHALLENGER`, `NO_CHANGE`, or `INCONCLUSIVE`.

### Promote via GitHub Actions
Go to **GitHub → Actions → Promote Model → Run workflow** and fill in:
- `winner`: `challenger` (default) or `champion`
- `traffic_weight`: `100` to route all traffic to the winner, or a lower value for a gradual rollout (e.g. `80`)
- `model_version`: leave blank to use the latest registered version in MLflow

The workflow will:
1. Set the MLflow `champion` alias on the winning model version (archiving the old one as `archived-v{version}`)
2. Update the `traffic-split-config` ConfigMap with the new weights
3. Restart the NGINX `traffic-splitter` deployment so it picks up the new ConfigMap
4. Scale the losing deployment to 0 replicas (when `traffic_weight` is 100)
5. Re-tag the winning Docker image as `champion-latest` in Artifact Registry

# GCP Infrastructure Execution Guide

This guide details the exact configurations to deploy and initialize the environments for the 3-tier MLOps project. Ensure you run this inside the Google Cloud Shell or a local terminal authenticated with `gcloud`.

## Ensure Initialization
```bash
gcloud auth login
export PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
gcloud config set project $PROJECT_ID
export REGION="us-central1"
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
# Staging Cluster
gcloud container clusters create staging-gke-cluster \
    --region $REGION \
    --num-nodes 1 \
    --machine-type n1-standard-2 \
    --disk-size 30

# Prod Cluster
gcloud container clusters create prod-gke-cluster \
    --zone us-central1-a \
    --num-nodes 1 \
    --machine-type n1-standard-2 \
    --disk-size 30

```

## 4. Git & DVC Initialization
On your local machine or dev environment:
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
gcloud iam workload-identity-pools create github-pool \
    --location="global" \
    --description="Pool for GitHub Actions" \
    --display-name="GitHub Actions Pool"

export WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe github-pool --location="global" --format="value(name)")

# Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
    --location="global" \
    --workload-identity-pool="github-pool" \
    --display-name="GitHub Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --issuer-uri="https://token.actions.githubusercontent.com"

# Allow GitHub Repo to impersonate the Service Account
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_REPO}"

# Get the Provider ID to put in GitHub Secrets
gcloud iam workload-identity-pools providers describe github-provider \
    --location="global" \
    --workload-identity-pool="github-pool" \
    --format="value(name)"
```

## 6. GitHub Actions Secrets Setup
In your GitHub Repository, navigate to **Settings > Secrets and variables > Actions** and add:
- `GCP_PROJECT`: Your project ID.
- `WIF_PROVIDER`: The output from the final `providers describe` command above.
- `WIF_SERVICE_ACCOUNT`: The email of your service account (`github-actions-sa@...`).
- `MLFLOW_TRACKING_URI`: The URI for your MLFlow setup (e.g., Databricks, or a managed VM).
- `GITHUB_TOKEN`: Ensure workflows have Write access.

# GCP Infrastructure Teardown Guide

To stop incurring charges and save costs, you need to delete the resources created during the setup phase. 

> [!WARNING]
> This will permanently delete your GKE clusters, storage buckets (including all data), artifact registry, compute engine VM, and IAM configurations. Make sure you have backed up any necessary data before running these commands.

Run the following commands in your Google Cloud Shell or a local terminal authenticated with `gcloud`.

## 1. Set Environment Variables
Ensure your environment variables are set correctly before running the deletion commands.
```bash
export PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
gcloud config set project $PROJECT_ID
export REGION="us-central1"
```

## 2. Clean Up Kubernetes Workloads (Before Deleting Clusters)
Delete all Kubernetes resources **before** deleting the GKE clusters. Deleting a cluster while a GCE Ingress or LoadBalancer Service still exists leaves behind orphaned Cloud Load Balancers that continue to incur charges even after the cluster is gone.

### Prod Cluster
Run in **Cloud Shell or local terminal**:
```bash
gcloud container clusters get-credentials prod-gke-cluster \
    --zone us-central1-a

# Delete the ingress first — this signals GKE to deprovision the Cloud Load Balancer
kubectl delete ingress ml-pricing-ingress --ignore-not-found

# Delete the deployment and service
kubectl delete deployment ml-api-prod --ignore-not-found
kubectl delete service ml-api-prod-svc --ignore-not-found

# Delete configmaps, BackendConfig, and HPA
kubectl delete configmap mlflow-config --ignore-not-found
kubectl delete backendconfig ml-api-backend-config --ignore-not-found
kubectl delete hpa ml-api-prod-hpa --ignore-not-found

# Confirm nothing remains
kubectl get all
```

### Staging Cluster
```bash
gcloud container clusters get-credentials staging-gke-cluster \
    --region us-central1

# Delete the LoadBalancer service first
kubectl delete service ml-api-staging-svc --ignore-not-found

kubectl delete deployment ml-api-staging --ignore-not-found
kubectl delete configmap mlflow-config --ignore-not-found

kubectl get all
```

> [!WARNING]
> Wait for load balancers to fully deprovision before proceeding. Verify they are gone with:
> ```bash
> gcloud compute forwarding-rules list | grep -E "staging|prod"
> ```
> Proceed only when the list is empty.

## 3. Delete Compute Engine VM & Firewall (MLflow Server)
```bash
# Delete the MLflow VM
gcloud compute instances delete mlflow-tracking-server \
    --zone=us-central1-a --quiet

# First, list all firewall rules to see which ones you created
gcloud compute firewall-rules list

# Then delete only YOUR custom rules (do NOT delete GCP defaults like default-allow-ssh)
# Replace the name(s) below with whatever you see in the list above
gcloud compute firewall-rules delete allow-mlflow-5000 --quiet
```

> [!WARNING]
> Do **NOT** delete GCP default rules like `default-allow-ssh`, `default-allow-internal`, `default-allow-icmp`, `default-allow-rdp`, or any `gke-*` rules. Only delete rules you explicitly created.

## 4. Delete GKE Clusters
```bash
# Delete Staging Cluster
gcloud container clusters delete staging-gke-cluster \
    --region $REGION --quiet

# Delete Prod Cluster
gcloud container clusters delete prod-gke-cluster \
    --zone us-central1-a --quiet
```

## 5. Delete Artifact Registry Repository
```bash
# Delete the Docker repository and all images inside it
gcloud artifacts repositories delete ml-repo \
    --location=$REGION --quiet
```

## 6. Delete Cloud Storage Buckets
```bash
# Force delete buckets and all their contents (DVC data, model artifacts)
gcloud storage rm --recursive gs://${PROJECT_ID}-mlops-dev-data
gcloud storage rm --recursive gs://${PROJECT_ID}-mlops-staging-data
gcloud storage rm --recursive gs://${PROJECT_ID}-mlops-prod-data
```

## 7. Delete IAM & Workload Identity Federation (Optional)
If you want to completely clean up the Service Account and Workload Identity Pool used for GitHub Actions:

```bash
export SA_EMAIL="github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Delete the Service Account
gcloud iam service-accounts delete $SA_EMAIL --quiet

# Delete the Workload Identity Pool (this also deletes its providers)
gcloud iam workload-identity-pools delete github-pool-v8 \
    --location="global" --quiet
```

## 8. Disable GCP Observability APIs (Optional)
If you wish to completely stop all billing and disable tracing/monitoring:
```bash
gcloud services disable \
    cloudtrace.googleapis.com \
    monitoring.googleapis.com \
    logging.googleapis.com \
    --force
```

> [!TIP]
> After running these commands, verify in the [Google Cloud Console](https://console.cloud.google.com/billing) that no unexpected resources are still running to ensure you are not billed further.

## 9. Verification Commands
Run these commands to verify that the resources are successfully deleted. If a resource is deleted, the command should return empty output, or an error stating the resource was not found.

```bash
# 1. Verify VM Instances (should not list mlflow-tracking-server)
gcloud compute instances list

# 2. Verify Firewall Rules (should not list any mlflow rules)
gcloud compute firewall-rules list | grep "allow-mlflow"

# 3. Verify GKE Clusters (should be empty)
gcloud container clusters list

# 4. Verify Artifact Registry (should not list ml-repo)
gcloud artifacts repositories list --location=$REGION

# 5. Verify Storage Buckets (should not list the mlops buckets)
gcloud storage ls | grep "mlops"

# 6. Verify Service Accounts (should not list github-actions-sa)
gcloud iam service-accounts list | grep "github-actions-sa"

# 7. Verify Workload Identity Pools (should not list github-pool-v4)
gcloud iam workload-identity-pools list --location="global"

# 8. Verify no orphaned Cloud Load Balancers remain (critical — these cost money)
gcloud compute forwarding-rules list
gcloud compute target-http-proxies list
gcloud compute backend-services list | grep "ml-api"
```

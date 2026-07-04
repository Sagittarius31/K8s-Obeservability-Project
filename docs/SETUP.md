# Setup guide

This walks through the whole project end to end. Examples use AWS EKS, with
GKE/AKS equivalents noted where the commands differ. Everything after
"Install the monitoring stack" is identical regardless of cloud provider,
since it's all just `kubectl` and `helm` talking to the Kubernetes API.

Estimated time: 1.5-2.5 hours the first time through.

## 0. Prerequisites

- `kubectl`, `helm` (v3), `docker` installed locally
- A container registry you can push to (Docker Hub free tier is fine, or
  ECR/GCR/ACR if you're already in that cloud)
- One of:
  - AWS account + `eksctl` + `aws` CLI configured
  - GCP account + `gcloud` CLI configured
  - Azure account + `az` CLI configured
- A Slack workspace where you can add an Incoming Webhook (optional but
  recommended - this is what makes the alerting piece feel real)

## 1. Create the cluster

**EKS:**
```bash
eksctl create cluster \
  --name k8s-observability-demo \
  --region us-east-1 \
  --nodes 2 \
  --node-type t3.medium \
  --managed
```

**GKE:**
```bash
gcloud container clusters create k8s-observability-demo \
  --num-nodes 2 \
  --machine-type e2-medium \
  --zone us-central1-a
```

**AKS:**
```bash
az group create --name k8s-observability-demo-rg --location eastus
az aks create --resource-group k8s-observability-demo-rg \
  --name k8s-observability-demo \
  --node-count 2 \
  --node-vm-size Standard_B2s \
  --generate-ssh-keys
az aks get-credentials --resource-group k8s-observability-demo-rg \
  --name k8s-observability-demo
```

Verify: `kubectl get nodes` should show 2 Ready nodes.

> Cost note: a 2-node t3.medium/e2-medium cluster on free-tier credits will
> burn through them in days if left running. Tear it down at the end (see
> Cleanup) or stop it when you're not actively working on it.

## 2. Build and push the app image

```bash
cd app
docker build -t <YOUR_REGISTRY>/k8s-observability-demo-app:latest .
docker push <YOUR_REGISTRY>/k8s-observability-demo-app:latest
cd ..
```

Then edit `k8s/deployment.yaml` and replace `<YOUR_REGISTRY>/...` with your
actual image path.

## 3. Install the monitoring stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f monitoring/prometheus-values.yaml
```

This single chart installs the Prometheus Operator, Prometheus, Grafana,
Alertmanager, kube-state-metrics, and node-exporter. Give it 2-3 minutes,
then check everything is up:

```bash
kubectl get pods -n monitoring
```

### 3a. Configure Slack alerting (optional but worth doing)

Open `monitoring/alertmanager-config.yaml`, paste your real Slack webhook URL
in, then either:
- merge the `alertmanager.config` block into `prometheus-values.yaml` and
  re-run the `helm install` above as `helm upgrade`, or
- `helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack -n monitoring -f monitoring/prometheus-values.yaml -f monitoring/alertmanager-config.yaml`

### 3b. Install prometheus-adapter (for custom-metric autoscaling)

```bash
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --namespace monitoring \
  -f monitoring/prometheus-adapter-values.yaml

# Verify the custom metric becomes available (may take ~1 min):
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1" | jq .
```

## 4. Deploy the app

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/servicemonitor.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f monitoring/alert-rules.yaml
```

Check the app is running and Prometheus has picked it up:
```bash
kubectl get pods -n demo-app
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# open http://localhost:9090/targets - you should see demo-app/demo-app as UP
```

## 5. Import the Grafana dashboard

```bash
kubectl create configmap demo-app-dashboard \
  --from-file=monitoring/grafana-dashboard.json \
  -n monitoring
kubectl label configmap demo-app-dashboard \
  grafana_dashboard=1 -n monitoring
```

The Grafana sidecar (enabled in `prometheus-values.yaml`) auto-detects
ConfigMaps with that label and loads the dashboard within ~1 minute.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# open http://localhost:3000 - user: admin, password: from prometheus-values.yaml
```

## 6. Generate traffic and watch it work

```bash
kubectl port-forward -n demo-app svc/demo-app 8080:80 &

# simple loop
while true; do curl -s http://localhost:8080/work > /dev/null; done
```

For real load testing (to trigger the HPA), use `hey` or `k6`:
```bash
hey -z 5m -c 50 http://localhost:8080/work
```

Watch the HPA react in real time:
```bash
kubectl get hpa -n demo-app -w
```

Watch alerts fire (once error rate or latency thresholds are crossed):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093
# open http://localhost:9093
```

## 7. Cleanup

```bash
helm uninstall kube-prometheus-stack -n monitoring
helm uninstall prometheus-adapter -n monitoring
kubectl delete namespace demo-app monitoring

# then delete the cluster itself
eksctl delete cluster --name k8s-observability-demo          # EKS
gcloud container clusters delete k8s-observability-demo       # GKE
az group delete --name k8s-observability-demo-rg              # AKS
```

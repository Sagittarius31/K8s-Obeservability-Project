# Kubernetes observability platform

A small instrumented microservice deployed on Kubernetes with full
production-style observability: metrics collection, dashboards, alerting to
Slack, and autoscaling driven by real traffic instead of just CPU.

Built as a hands-on DevOps project to demonstrate working knowledge of
Prometheus, Grafana, Alertmanager, and the Kubernetes autoscaling APIs - not
just "I deployed a pod."

## What this demonstrates

- Writing application code that exposes custom Prometheus metrics (counters,
  histograms, gauges) rather than relying only on infrastructure metrics
- Using the Prometheus Operator's CRDs (`ServiceMonitor`, `PrometheusRule`)
  instead of hand-editing `prometheus.yml`
- Building real Grafana dashboards (request rate, error rate, latency
  percentiles) and understanding the PromQL behind them
- Configuring multi-severity Alertmanager routing to Slack
- Horizontal Pod Autoscaling on a **custom metric** (requests/sec via
  Prometheus Adapter) combined with a CPU fallback, which is what real
  services use because CPU is a poor proxy for load on I/O-bound apps
- Running all of this on a real managed Kubernetes cluster (EKS/GKE/AKS),
  not just Minikube

## Architecture

```
app pods (Flask, /metrics) --scraped by ServiceMonitor--> Prometheus
                                                              |
                                                  +-----------+-----------+
                                                  |                       |
                                               Grafana               Alertmanager
                                            (dashboards)                  |
                                                                        Slack
```

Separately, Prometheus Adapter exposes a custom metric
(`http_requests_per_second`) derived from Prometheus data through the
`custom.metrics.k8s.io` API, which the HPA reads to scale pods based on
actual traffic.

## Project structure

```
app/                          sample Flask app instrumented with prometheus_client
  app.py
  requirements.txt
  Dockerfile
k8s/                           core Kubernetes manifests
  namespace.yaml
  deployment.yaml
  service.yaml
  servicemonitor.yaml          tells Prometheus Operator to scrape the app
  hpa.yaml                     scales on custom metric + CPU
monitoring/
  prometheus-values.yaml       Helm values for kube-prometheus-stack
  prometheus-adapter-values.yaml  custom metric rule for the HPA
  alert-rules.yaml             PrometheusRule: error rate, latency, crashloops, memory
  alertmanager-config.yaml     Slack routing by severity
  grafana-dashboard.json       importable dashboard (request rate, errors, p95/p99, replicas)
docs/
  SETUP.md                     full step-by-step setup guide
```

## Quick start

See [`docs/SETUP.md`](docs/SETUP.md) for the complete walkthrough
(cluster creation through load testing). Short version:

```bash
# 1. Build & push the app image, update k8s/deployment.yaml with your registry
# 2. Install the monitoring stack
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/prometheus-values.yaml

# 3. Deploy the app + monitoring config
kubectl apply -f k8s/
kubectl apply -f monitoring/alert-rules.yaml
```

## Why these design choices

**Custom metrics over CPU-only autoscaling.** Most fresher projects stop at
`autoscaling/v2` with CPU targets. This one scales on `http_requests_per_second`
because that's a far more accurate signal of real load for a web service, and
demonstrates the metrics pipeline end to end: app → Prometheus → Adapter →
HPA.

**ServiceMonitor/PrometheusRule CRDs over static config.** Hand-editing
`prometheus.yml` doesn't scale past one service and isn't how teams actually
run Prometheus Operator in production. Using the CRDs shows you understand
the GitOps-friendly, declarative pattern.

**Multi-severity Slack routing.** A single "send everything to one channel"
Alertmanager config is the most common shortcut. Routing critical vs warning
alerts to different channels (and demonstrating `for:` durations to avoid
alert flapping) is a small detail that signals you've thought about
alert fatigue.

## Possible extensions

If you want to push this further for an interview talking point:
- Add **Loki** for log aggregation alongside the metrics (same Grafana, one
  more datasource)
- Add **Tempo** or **Jaeger** for distributed tracing if you split the app
  into 2+ services
- Front the whole deployment with **ArgoCD** for GitOps instead of manual
  `kubectl apply`
- Add a **GitHub Actions** pipeline that builds, pushes, and deploys on
  every push to main

## Cleanup

Don't forget to tear the cluster down when you're done - see the Cleanup
section in `docs/SETUP.md`. A running EKS/GKE/AKS cluster will consume
free-tier credits quickly.

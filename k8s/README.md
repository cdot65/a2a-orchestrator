# Kubernetes Deployment (Talos + Traefik)

Deploys the orchestrator, recipe-url, and recipe-gen agents into namespace `a2a` on a Talos Kubernetes cluster. Traefik handles TLS termination via an `IngressRoute` CRD.

## Why shell agent is excluded

The shell agent spawns Docker containers for command sandboxing. That pattern is incompatible with Kubernetes without significant redesign (Job API, gVisor, or similar). It is excluded from this deployment. K8s-native sandbox support is follow-up work.

## Prerequisites

- Talos Kubernetes cluster (any recent version)
- Traefik installed with a `websecure` entrypoint on port 443
- cert-manager (recommended) or a pre-provisioned TLS certificate
- `kubectl` with cluster access
- Docker (to build and push the image)

## Build and push the image

```bash
docker build -t ghcr.io/cdot65/a2a-orchestrator:latest .
docker push ghcr.io/cdot65/a2a-orchestrator:latest
```

## Deploy

### 1. Create namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 2. Create the Anthropic API key secret

```bash
kubectl -n a2a create secret generic anthropic \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Provide a TLS certificate

Option A — cert-manager (recommended): create a `Certificate` resource or use an `Issuer`/`ClusterIssuer` annotation strategy that targets secret `a2a-tls` in namespace `a2a`.

Option B — manual:

```bash
kubectl -n a2a create secret tls a2a-tls --cert=tls.crt --key=tls.key
```

### 4. Customize the IngressRoute hostname

Edit `k8s/ingressroute.yaml` and replace `a2a.example.com` with your actual domain.

### 5. Apply everything

```bash
kubectl apply -k k8s/
```

## Verify

```bash
kubectl -n a2a get pods,svc,ingressroute
```

All three pods should reach `Running` state with readiness probes passing on `/.well-known/agent-card.json`.

## Smoke test

```bash
# Agent card via HTTPS
curl -sk https://a2a.example.com/.well-known/agent-card.json | jq .

# OpenAI-compat model list
curl -sk https://a2a.example.com/v1/models | jq .

# Chat completion
curl -sk -X POST https://a2a.example.com/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"a2a-orchestrator","messages":[{"role":"user","content":"Give me a vegan ramen recipe"}],"stream":false}' \
  | jq .
```

## Customization

| Variable | Default | Description |
|---|---|---|
| `A2A_DISCOVERY_URLS` | set in orchestrator deployment | Comma-separated full base URLs for peer agents |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model for all agents |
| `LOG_FORMAT` | `json` | `json` or `pretty` |
| `RECIPES_DIR` | `/data/recipes` | Mount path for recipe storage (emptyDir — not persistent by default) |

To persist recipes across pod restarts, replace the `recipes` `emptyDir` volume with a `PersistentVolumeClaim`.

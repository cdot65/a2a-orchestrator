---
title: Kubernetes (Example)
---

# Kubernetes (Example)

The `k8s/` directory contains example manifests targeting a Talos cluster with Traefik for ingress. Treat them as a reference, not a turnkey deploy.

!!! info "No CI"
    This repo intentionally ships **no** GitHub Actions workflow that builds or pushes images. Build and roll the deployments yourself.

## What's in `k8s/`

| File | Purpose |
|---|---|
| `namespace.yaml` | `a2a` namespace |
| `deployment-orchestrator.yaml` | Orchestrator + Service |
| `deployment-recipe-url.yaml` | recipe-url + Service |
| `deployment-recipe-gen.yaml` | recipe-gen + Service |
| `ingressroute.yaml` | Traefik IngressRoute terminating TLS at `a2a.dev.cdot.io` |
| `middleware-ratelimit.yaml` | Traefik per-IP rate-limit middleware (defense in depth) |
| `kustomization.yaml` | Kustomize entrypoint listing the above |
| `secret.example.yaml` | Template for the `anthropic` Secret (don't commit the real one) |
| `cluster-setup/` | One-time RBAC + a self-hosted runner Deployment, kept as reference |

## Pod hardening

Every deployment runs:

- Non-root (`runAsUser: 10001`)
- `readOnlyRootFilesystem: true`
- All Linux capabilities dropped
- `seccompProfile: RuntimeDefault`
- `allowPrivilegeEscalation: false`

Writable directories use `emptyDir` mounts (`/tmp`, `/data/recipes`).

## Discovery

The orchestrator deployment sets:

```yaml
env:
  - name: A2A_DISCOVERY_URLS
    value: "http://recipe-url.a2a.svc.cluster.local:8001,http://recipe-gen.a2a.svc.cluster.local:8002"
```

`A2A_DISCOVERY_URLS` takes precedence over `A2A_DISCOVERY_PORTS`, so the orchestrator looks up its peers via the in-cluster Service DNS names instead of `localhost:PORT`.

## Secret

Create the `anthropic` Secret manually (don't commit it):

```bash
kubectl -n a2a create secret generic anthropic \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-...
```

## Image registry

The example manifests reference `ghcr.io/cdot65/a2a-orchestrator:talos`. Replace with your own registry path. You'll also need an `imagePullSecrets` entry pointing at your GHCR pull secret (`ghcr-login-secret` in the example).

## Build, push, roll

```bash
docker buildx build --platform linux/amd64 --push \
  --tag ghcr.io/<you>/a2a-orchestrator:latest .

kubectl -n a2a apply -k k8s/

kubectl -n a2a rollout restart \
  deployment/orchestrator deployment/recipe-url deployment/recipe-gen
```

## Verify

```bash
kubectl -n a2a get pods,svc,ingressroute
curl -sk https://<your-ingress-host>/.well-known/agent-card.json | jq .
```

`scripts/verify-deployment.py` performs schema-validated end-to-end checks against a deployed instance.

## Why no shell agent in k8s

The shell agent's sandbox spawns a Docker container per request. That works on a developer laptop but not on Kubernetes without significant additional plumbing (privileged DinD, gVisor, Kata, or moving to the Job API). The repo deliberately keeps the example deploy minimal and treats k8s-native sandboxing as follow-up work.

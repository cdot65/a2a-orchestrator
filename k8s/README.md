# Kubernetes Deployment (Talos + Traefik)

Deploys the orchestrator, recipe-url, and recipe-gen agents into namespace `a2a` on a Talos Kubernetes cluster. Traefik handles TLS termination via an `IngressRoute` CRD using the `*.cdot.io` wildcard cert.

## Why shell agent is excluded

The shell agent spawns Docker containers for command sandboxing. That pattern is incompatible with Kubernetes without significant redesign (Job API, gVisor, or similar). It is excluded from this deployment. K8s-native sandbox support is follow-up work.

## One-time cluster setup

See [`k8s/cluster-setup/README.md`](cluster-setup/README.md) for the steps you run once: creating the namespace, mirroring the GHCR pull secret and wildcard TLS secret from `truffles-dev`, creating the Anthropic API key secret, and deploying the self-hosted runner RBAC + Deployment.

## Per-deploy (manual)

This repo intentionally ships **no** auto-deploy workflow. Build and push the image yourself:

```bash
docker buildx build --platform linux/amd64 --push \
  --tag ghcr.io/<you>/a2a-orchestrator:latest .
```

Then roll the deployments:

```bash
kubectl -n a2a rollout restart deployment/orchestrator
kubectl -n a2a rollout restart deployment/recipe-url
kubectl -n a2a rollout restart deployment/recipe-gen
```

## Verify

```bash
kubectl -n a2a get pods,svc,ingressroute
curl -sk https://a2a.dev.cdot.io/.well-known/agent-card.json | jq .
```

## Customization

| Variable | Default | Description |
|---|---|---|
| `A2A_DISCOVERY_URLS` | set in orchestrator deployment | Comma-separated full base URLs for peer agents |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model for all agents |
| `LOG_FORMAT` | `json` | `json` or `pretty` |
| `RECIPES_DIR` | `/data/recipes` | Mount path for recipe storage (emptyDir — not persistent by default) |

To persist recipes across pod restarts, replace the `recipes` `emptyDir` volume with a `PersistentVolumeClaim`.

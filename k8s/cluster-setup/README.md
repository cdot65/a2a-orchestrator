# One-time cluster setup

Run these steps once per cluster. CI handles all subsequent deploys.

## 1. Create namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

## 2. Mirror GHCR pull secret

Copy `ghcr-login-secret` from `truffles-dev` into `a2a`:

```bash
kubectl --context talos -n truffles-dev get secret ghcr-login-secret -o yaml \
  | sed 's/namespace: truffles-dev/namespace: a2a/' \
  | grep -v '^  resourceVersion:\|^  uid:\|^  creationTimestamp:' \
  | kubectl apply -f -
```

## 3. Mirror wildcard TLS secret

The IngressRoute uses `wildcard-cdot-io-tls` (covers `*.cdot.io`). Copy it from `truffles-dev`:

```bash
kubectl --context talos -n truffles-dev get secret wildcard-cdot-io-tls -o yaml \
  | sed 's/namespace: truffles-dev/namespace: a2a/' \
  | grep -v '^  resourceVersion:\|^  uid:\|^  creationTimestamp:' \
  | kubectl apply -f -
```

## 4. Create Anthropic API key secret

```bash
kubectl -n a2a create secret generic anthropic \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-...
```

## 5. Apply runner RBAC and runner Deployment

```bash
kubectl apply -f k8s/cluster-setup/rbac.yaml -f k8s/cluster-setup/runner.yaml
```

This grants `github-runner-sa` (in `github-runner` ns) permission to manage deployments in `a2a`, and creates the `a2a-runner` Deployment that registers a self-hosted runner to `cdot65/a2a-orchestrator`.

## 6. DNS

Point `a2a.dev.cdot.io` at the Talos cluster's Traefik ingress IP. For a home cluster this is typically a static A record or an external-dns annotation.

## Apply all k8s manifests

```bash
kubectl apply -k k8s/
```

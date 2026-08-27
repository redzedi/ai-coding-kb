---
name: "praxis-module-actions"
title: "Facets Module Actions"
description: "Create Tekton-based operational actions for Facets module resources. Covers Kubernetes and AWS action types using the terraform-provider-facets, action design patterns by module type, parameter handling, credential injection, and best practices."
triggers: ["action", "tekton", "tekton action", "module action", "operational action", "facets action", "resource action"]
version: "1.0"
category: "development"
tags: ["terraform", "tekton", "actions", "operations", "kubernetes", "aws", "workflow", "module"]
icon: "⚡"
---

> **Execution context** — this was authored for in-process MCP
> in agent-factory. You're running it from a local AI host installed by
> `praxis login`, so MCP tools are NOT directly callable here.
> Whenever this references an MCP tool, shell out to `praxis`:
>
> ```
> # Says:          run_k8s_cli(integration_name="prod", command="get pods")
> # You run:       praxis mcp k8s_cli run_k8s_cli \
>                  --arg integration_name=prod --arg command='get pods'
> ```
>
> Rewrite rule: any `<mcp>.<fn>(args)` or bare `<fn>` reference becomes
> `praxis mcp <mcp> <fn> --arg k=v ...` (or `--body '<json>'` for nested
> args). The CLI authenticates as your Praxis user and runs the call
> server-side under your org's managed cloud / k8s credentials — your
> laptop never holds AWS / kube / terraform secrets.
>
> If `praxis mcp <mcp> <fn>` returns 404, that tool isn't yet exposed
> by the gateway; fall back to whatever non-MCP path the body suggests.
>
> **`raptor` is the exception — it is a LOCAL CLI, not a gateway tool.**
> Run `raptor …` commands directly in your shell; never route them
> through `praxis mcp` (there is no `raptor_cli` gateway tool). If
> `command -v raptor` finds nothing, ask the user to install it; if
> `raptor whoami` fails, ask the user to run `raptor login` first. In
> `praxis status --json`, `tools` is an ARRAY — find the entry whose
> `tool` is `raptor`; if that entry's `stale` is true, offer to run
> `raptor upgrade` (ask first — never auto-run it).
>
> Raptor's profile is NOT praxis's profile — check the `raptor` block in
> `praxis status --json`. If `pinned` is true, prefix EVERY raptor command
> with `FACETS_PROFILE=<profile>` (env vars don't persist across shell
> calls). If `matches_praxis_url` is false unexpectedly, raptor is aimed at a
> DIFFERENT control plane than praxis: ask the user before any write.
>
> **Discovering what's available** — to see every MCP and function the
> gateway exposes, run `praxis mcp --json` (live fetch). A snapshot
> from your last `praxis login` lives at `~/.praxis/mcp-tools.json` —
> grep that file when you need the tool list without making a network call.

# Facets Module Actions Guide

A comprehensive reference for creating Tekton-based operational actions for Facets module resources.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Action Types](#3-action-types)
4. [Schema Reference](#4-schema-reference)
5. [Module Variable Mapping](#5-module-variable-mapping)
6. [Action Design Guidelines](#6-action-design-guidelines)
7. [Common Action Patterns](#7-common-action-patterns)
8. [Download Artifacts](#8-download-artifacts)
9. [Raptor CLI Commands](#9-raptor-cli-commands)
10. [Best Practices and Anti-Patterns](#10-best-practices-and-anti-patterns)

---

## 1. Overview

### What Are Actions?

Actions are **operational workflows** attached to Facets module resources. Unlike modules (which provision infrastructure), actions let users **operate** on deployed resources — restart pods, scale instances, take backups, download kubeconfigs, etc.

Actions are:
- Defined as **Terraform resources** inside a module's codebase (in `actions.tf`)
- Deployed alongside the module's infrastructure during a release
- Visible as **clickable buttons** in the Facets UI for every resource instance across all environments
- Executed as **Tekton Tasks** running in isolated Kubernetes pods with auto-injected credentials

### Actions vs Modules

| Aspect | Modules | Actions |
|--------|---------|---------|
| **Purpose** | Provision infrastructure | Operate on infrastructure |
| **When** | During releases | On-demand by users |
| **Terraform resource** | `aws_*`, `kubernetes_*`, etc. | `facets_tekton_action_kubernetes`, `facets_tekton_action_aws` |
| **Provider** | Cloud/K8s providers via inputs | `facets` provider |
| **File** | `main.tf`, `cluster.tf`, etc. | `actions.tf` |
| **User interaction** | Blueprint configuration | Click button in UI, provide params |

---

## 2. Architecture

### How Actions Work

```
Module code (actions.tf)
    │
    ▼ (deployed via release)
Tekton Task created in cluster
    │
    ▼ (user clicks action in Facets UI)
TaskRun created with:
  - Auto-injected credentials (kubeconfig or AWS)
  - User-provided parameters
  - User identity (FACETS_USER_EMAIL)
    │
    ▼
Steps execute sequentially in isolated pods
    │
    ▼
Results visible in Facets UI (logs, status)
```

### Key Concepts

1. **One Action = One Tekton Task** with one or more sequential steps
2. **Credential injection** is automatic — a setup step is prepended by the provider
3. **Labels** are auto-generated for linking actions to resources in the UI
4. **Parameters** allow user input at trigger time
5. **Actions are scoped** to a specific resource in a specific environment

---

## 3. Action Types

> **CRITICAL: Only Kubernetes and AWS action types are available. Do NOT attempt Azure, GCP, or any other provider.**

### Decision Matrix

| Use Case | Resource Type | Credential Injection |
|----------|--------------|---------------------|
| kubectl operations | `facets_tekton_action_kubernetes` | RBAC-scoped kubeconfig |
| Pod management (restart, scale, logs) | `facets_tekton_action_kubernetes` | RBAC-scoped kubeconfig |
| Helm operations | `facets_tekton_action_kubernetes` | RBAC-scoped kubeconfig |
| K8s config/secret management | `facets_tekton_action_kubernetes` | RBAC-scoped kubeconfig |
| AWS API calls (S3, RDS, EC2, etc.) | `facets_tekton_action_aws` | IRSA role chaining |
| Cross-account AWS operations | `facets_tekton_action_aws` | IRSA role chaining |

### Kubernetes Actions (`facets_tekton_action_kubernetes`)

When triggered:
1. Facets UI populates `FACETS_USER_KUBECONFIG` with the user's **base64-encoded, RBAC-scoped** kubeconfig
2. A `setup-credentials` step is **automatically prepended** that decodes the kubeconfig to `/workspace/.kube/config` and sets `KUBECONFIG`
3. Your steps run with full kubectl access scoped to the user's permissions

### AWS Actions (`facets_tekton_action_aws`)

When triggered:
1. The TaskRun uses the `facets-workflows-sa` ServiceAccount with IRSA
2. A `setup-aws-credentials` step is **automatically prepended** that assumes the target IAM role (from provider config)
3. Your steps run with the assumed role's AWS permissions

**Prerequisites for AWS actions:**
- Provider must include `aws` block with `assume_role` configuration
- `facets-workflows-sa` ServiceAccount must have IRSA annotation
- IRSA role must have `sts:AssumeRole` permission on the target role
- Target role must trust the IRSA role

---

## 4. Schema Reference

### 4.1 Kubernetes Action Schema

#### Required Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `name` | String | Display name shown in UI |
| `facets_resource_name` | String | Resource name from blueprint (use `var.instance_name`) |
| `facets_environment` | Object | Environment config (use `var.environment`) |
| `facets_environment.unique_name` | String | Unique name of the environment |
| `facets_resource` | Object | Resource definition (use `var.instance`) |
| `facets_resource.kind` | String | Resource kind (e.g., "service", "postgres") |
| `facets_resource.flavor` | String | Resource flavor (e.g., "k8s", "aws") |
| `facets_resource.version` | String | Resource version |
| `facets_resource.spec` | Dynamic | Additional specs (can be `{}`) |
| `steps` | List | Workflow steps (see below) |

#### Step Arguments

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `name` | String | Yes | Step name |
| `image` | String | Yes | Container image |
| `script` | String | Yes | Script to execute |
| `env` | List | No | Environment variables (`name`, `value` pairs) |
| `resources` | Object | No | Compute resources (`requests`, `limits` with `cpu`, `memory`) |

#### Optional Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `description` | String | - | Description shown in UI |
| `namespace` | String | `"tekton-pipelines"` | K8s namespace for Tekton resources |
| `labels` | Map(String) | - | Custom labels (merged with auto-generated) |
| `params` | List | - | Custom parameters (`name`, `type` pairs) |

#### Auto-Injected Parameters

| Parameter | Description |
|-----------|-------------|
| `FACETS_USER_EMAIL` | Email of the user triggering the action |
| `FACETS_USER_KUBECONFIG` | Base64-encoded kubeconfig with user's RBAC permissions |

#### Computed Attributes

| Attribute | Description |
|-----------|-------------|
| `id` | Resource ID in format `namespace/task_name` |
| `task_name` | Generated Tekton Task name (hash-based, max 63 chars) |
| `step_action_name` | Generated StepAction name for credential setup |

### 4.2 AWS Action Schema

Same as Kubernetes action schema with these differences:

- **No `labels` argument** — AWS actions don't support custom labels
- **No `FACETS_USER_KUBECONFIG`** — Instead, AWS credentials are injected via environment variables by the setup step
- **Requires provider AWS configuration:**

```hcl
provider "facets" {
  aws = {
    region = "us-east-1"
    assume_role = {
      role_arn     = "arn:aws:iam::123456789012:role/TargetRole"
      session_name = "my-workflow"       # Optional
      external_id  = "unique-external-id"  # Optional
    }
  }
}
```

---

## 5. Module Variable Mapping

When writing actions inside a Facets module, **always use module variables** — never hardcode resource names or environments.

### Standard Mapping

```hcl
resource "facets_tekton_action_kubernetes" "restart_pods" {
  name                 = "Restart Pods"
  description          = "Performs a rollout restart of the deployment"
  facets_resource_name = var.instance_name        # Module's resource name
  facets_environment   = var.environment           # Environment object (has unique_name)
  facets_resource      = var.instance              # Resource instance (has kind, flavor, version, spec)

  steps = [
    {
      name   = "restart"
      image  = "bitnami/kubectl:1.28"
      script = <<-EOT
        #!/bin/bash
        set -e
        kubectl rollout restart deployment/${var.instance.metadata.name} -n ${var.environment.namespace}
        kubectl rollout status deployment/${var.instance.metadata.name} -n ${var.environment.namespace}
      EOT
    }
  ]
}
```

### Variable Reference

| Variable | Type | Contains | Used For |
|----------|------|----------|----------|
| `var.instance_name` | String | Blueprint resource name | `facets_resource_name` |
| `var.environment` | Object | `.unique_name`, `.name`, `.namespace`, `.cloud_tags` | `facets_environment`, script references |
| `var.instance` | Object | `.kind`, `.flavor`, `.version`, `.spec`, `.metadata` | `facets_resource`, script references |

---

## 6. Action Design Guidelines

### Rule 1: Only K8s and AWS Actions

Only `facets_tekton_action_kubernetes` and `facets_tekton_action_aws` exist. Do not attempt to create actions for Azure, GCP, or any other cloud provider. If the module targets Azure/GCP, actions are not yet supported for those clouds.

### Rule 2: Suggest Meaningful Actions

Do not suggest random actions just for the sake of it. Every action must represent a **frequent workflow** that users will actually need.

**Think from two perspectives:**

**Developer POV** — What do developers need to do regularly?
- Restart/bounce services after config changes
- Check pod status and recent logs
- Test connectivity to databases or APIs
- Download kubeconfig for local debugging
- Scale services up for testing, down after

**DevOps POV** — What operational tasks are common?
- Scale databases up during peak, down on weekends
- Take and download backups before major changes
- Rotate credentials or certificates
- Run health checks and diagnostics
- Flush caches after deployments
- Download artifacts or configurations

### Rule 3: Get User Approval Before Implementing

**NEVER implement actions without presenting them to the user first.** Always propose actions as a table and wait for approval:

```
I recommend these actions for your [module_type] module:

| Action | Description | Type | Rationale |
|--------|-------------|------|-----------|
| Restart Pods | Rollout restart of deployment | K8s | Common after config changes |
| Scale Deployment | Scale replicas up or down | K8s | Needed for load testing and cost saving |
| View Pod Status | List pods and their status | K8s | Quick health check without CLI access |

Which of these should I implement? Any others you'd like to add?
```

---

## 7. Common Action Patterns

### 7.1 Kubernetes Cluster — Download Kubeconfig

```hcl
resource "facets_tekton_action_kubernetes" "download_kubeconfig" {
  name                 = "Download Kubeconfig"
  description          = "Downloads a fresh kubeconfig for the cluster"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  steps = [
    {
      name   = "export-kubeconfig"
      image  = "bitnami/kubectl:1.28"
      script = <<-EOT
        #!/bin/bash
        set -e
        echo "=== Kubeconfig for ${var.instance_name} ==="
        echo "Environment: ${var.environment.unique_name}"
        echo ""
        echo "--- BEGIN KUBECONFIG ---"
        cat $KUBECONFIG
        echo "--- END KUBECONFIG ---"
        echo ""
        echo "Copy the content between BEGIN and END markers."
      EOT
    }
  ]
}
```

### 7.2 Service (K8s) — Restart Pods

```hcl
resource "facets_tekton_action_kubernetes" "restart_pods" {
  name                 = "Restart Pods"
  description          = "Performs a rollout restart of the deployment"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  steps = [
    {
      name   = "rollout-restart"
      image  = "bitnami/kubectl:1.28"
      script = <<-EOT
        #!/bin/bash
        set -e
        DEPLOYMENT="${var.instance.metadata.name}"
        NAMESPACE="${var.environment.namespace}"

        echo "Restarting deployment/$DEPLOYMENT in namespace $NAMESPACE..."
        kubectl rollout restart deployment/$DEPLOYMENT -n $NAMESPACE
        echo "Waiting for rollout to complete..."
        kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE --timeout=300s
        echo "Restart completed successfully."
      EOT
    }
  ]
}
```

### 7.3 Service (K8s) — Scale Deployment

```hcl
resource "facets_tekton_action_kubernetes" "scale_deployment" {
  name                 = "Scale Deployment"
  description          = "Scale the deployment to a specified number of replicas"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  params = [
    {
      name = "REPLICAS"
      type = "string"
    }
  ]

  steps = [
    {
      name   = "scale"
      image  = "bitnami/kubectl:1.28"
      script = <<-EOT
        #!/bin/bash
        set -e
        DEPLOYMENT="${var.instance.metadata.name}"
        NAMESPACE="${var.environment.namespace}"
        REPLICAS="$(params.REPLICAS)"

        echo "Scaling deployment/$DEPLOYMENT to $REPLICAS replicas..."
        kubectl scale deployment/$DEPLOYMENT --replicas=$REPLICAS -n $NAMESPACE
        echo "Waiting for rollout..."
        kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE --timeout=300s
        echo "Scale completed. Current pods:"
        kubectl get pods -n $NAMESPACE -l app=$DEPLOYMENT
      EOT
    }
  ]
}
```

### 7.4 Service (K8s) — View Pod Status

```hcl
resource "facets_tekton_action_kubernetes" "pod_status" {
  name                 = "View Pod Status"
  description          = "Shows current pod status, events, and recent logs"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  steps = [
    {
      name   = "check-status"
      image  = "bitnami/kubectl:1.28"
      script = <<-EOT
        #!/bin/bash
        set -e
        DEPLOYMENT="${var.instance.metadata.name}"
        NAMESPACE="${var.environment.namespace}"

        echo "=== Deployment Status ==="
        kubectl get deployment/$DEPLOYMENT -n $NAMESPACE -o wide

        echo ""
        echo "=== Pods ==="
        kubectl get pods -n $NAMESPACE -l app=$DEPLOYMENT -o wide

        echo ""
        echo "=== Recent Events ==="
        kubectl get events -n $NAMESPACE --field-selector involvedObject.kind=Pod \
          --sort-by='.lastTimestamp' | tail -20
      EOT
    }
  ]
}
```

### 7.5 RDS Database (AWS) — Create Snapshot

```hcl
resource "facets_tekton_action_aws" "create_snapshot" {
  name                 = "Create DB Snapshot"
  description          = "Creates a manual snapshot of the RDS instance"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  params = [
    {
      name = "SNAPSHOT_SUFFIX"
      type = "string"
    }
  ]

  steps = [
    {
      name   = "create-snapshot"
      image  = "amazon/aws-cli:2.15"
      script = <<-EOT
        #!/bin/bash
        set -e
        DB_IDENTIFIER="${var.instance.metadata.name}"
        SNAPSHOT_ID="$DB_IDENTIFIER-$(params.SNAPSHOT_SUFFIX)-$(date +%Y%m%d-%H%M)"

        echo "Creating snapshot $SNAPSHOT_ID for RDS instance $DB_IDENTIFIER..."
        aws rds create-db-snapshot \
          --db-instance-identifier "$DB_IDENTIFIER" \
          --db-snapshot-identifier "$SNAPSHOT_ID"

        echo "Waiting for snapshot to complete..."
        aws rds wait db-snapshot-available \
          --db-snapshot-identifier "$SNAPSHOT_ID"

        echo "Snapshot $SNAPSHOT_ID created successfully."
        aws rds describe-db-snapshots \
          --db-snapshot-identifier "$SNAPSHOT_ID" \
          --query 'DBSnapshots[0].{ID:DBSnapshotIdentifier,Status:Status,Size:AllocatedStorage,Created:SnapshotCreateTime}' \
          --output table
      EOT
    }
  ]
}
```

### 7.6 RDS Database (AWS) — Scale Instance

```hcl
resource "facets_tekton_action_aws" "scale_instance" {
  name                 = "Scale DB Instance"
  description          = "Modify RDS instance class (e.g., scale down on weekends)"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  params = [
    {
      name = "INSTANCE_CLASS"
      type = "string"
    },
    {
      name = "APPLY_IMMEDIATELY"
      type = "string"
    }
  ]

  steps = [
    {
      name   = "scale-rds"
      image  = "amazon/aws-cli:2.15"
      script = <<-EOT
        #!/bin/bash
        set -e
        DB_IDENTIFIER="${var.instance.metadata.name}"
        INSTANCE_CLASS="$(params.INSTANCE_CLASS)"
        APPLY_NOW="$(params.APPLY_IMMEDIATELY)"

        echo "Current instance details:"
        aws rds describe-db-instances \
          --db-instance-identifier "$DB_IDENTIFIER" \
          --query 'DBInstances[0].{Class:DBInstanceClass,Status:DBInstanceStatus}' \
          --output table

        echo "Modifying to $INSTANCE_CLASS (apply immediately: $APPLY_NOW)..."
        APPLY_FLAG=""
        if [ "$APPLY_NOW" = "true" ]; then
          APPLY_FLAG="--apply-immediately"
        else
          APPLY_FLAG="--no-apply-immediately"
        fi

        aws rds modify-db-instance \
          --db-instance-identifier "$DB_IDENTIFIER" \
          --db-instance-class "$INSTANCE_CLASS" \
          $APPLY_FLAG

        echo "Modification initiated. Check status in AWS Console."
      EOT
    }
  ]
}
```

### 7.7 S3 Bucket (AWS) — List Objects

```hcl
resource "facets_tekton_action_aws" "list_objects" {
  name                 = "List Bucket Contents"
  description          = "Lists objects in the S3 bucket with optional prefix filter"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  params = [
    {
      name = "PREFIX"
      type = "string"
    }
  ]

  steps = [
    {
      name   = "list-s3"
      image  = "amazon/aws-cli:2.15"
      script = <<-EOT
        #!/bin/bash
        set -e
        BUCKET="${var.instance.metadata.name}"
        PREFIX="$(params.PREFIX)"

        echo "=== Objects in s3://$BUCKET/$PREFIX ==="
        aws s3 ls "s3://$BUCKET/$PREFIX" --human-readable --summarize
      EOT
    }
  ]
}
```

### 7.8 Redis/ElastiCache (K8s) — Flush Cache

```hcl
resource "facets_tekton_action_kubernetes" "flush_cache" {
  name                 = "Flush Cache"
  description          = "Flushes all data from the Redis cache"
  facets_resource_name = var.instance_name
  facets_environment   = var.environment
  facets_resource      = var.instance

  steps = [
    {
      name   = "flush-redis"
      image  = "redis:7-alpine"
      script = <<-EOT
        #!/bin/sh
        set -e
        REDIS_HOST="${var.instance.metadata.name}.${var.environment.namespace}.svc.cluster.local"
        REDIS_PORT="6379"

        echo "Connecting to $REDIS_HOST:$REDIS_PORT..."
        echo "Current DB size:"
        redis-cli -h $REDIS_HOST -p $REDIS_PORT DBSIZE

        echo "Flushing all databases..."
        redis-cli -h $REDIS_HOST -p $REDIS_PORT FLUSHALL

        echo "DB size after flush:"
        redis-cli -h $REDIS_HOST -p $REDIS_PORT DBSIZE
        echo "Cache flushed successfully."
      EOT
    }
  ]
}
```

---

## 8. Download Artifacts

Actions can produce downloadable outputs. Since Tekton steps run in ephemeral pods, outputs need to be either:
- **Printed to stdout** (visible in action run logs in the UI)
- **Uploaded to S3** (for binary/large files)

### Pattern: Print to Logs

For text output (kubeconfigs, status reports, small exports):

```hcl
steps = [
  {
    name   = "export-data"
    image  = "bitnami/kubectl:1.28"
    script = <<-EOT
      #!/bin/bash
      set -e
      echo "--- BEGIN OUTPUT ---"
      kubectl get configmap my-config -n $NAMESPACE -o yaml
      echo "--- END OUTPUT ---"
      echo "Copy content between BEGIN and END markers."
    EOT
  }
]
```

### Pattern: Upload to S3

For binary files (database dumps, large exports):

```hcl
# AWS action with S3 upload
steps = [
  {
    name   = "backup-and-upload"
    image  = "amazon/aws-cli:2.15"

    resources = {
      requests = {
        cpu    = "500m"
        memory = "1Gi"
      }
      limits = {
        cpu    = "1000m"
        memory = "2Gi"
      }
    }

    script = <<-EOT
      #!/bin/bash
      set -e
      TIMESTAMP=$(date +%Y%m%d-%H%M%S)
      BUCKET="${var.instance.spec.backup_bucket}"
      KEY="backups/${var.instance_name}/$TIMESTAMP/backup.sql.gz"

      echo "Creating backup..."
      # ... backup logic ...

      echo "Uploading to s3://$BUCKET/$KEY..."
      aws s3 cp /workspace/backup.sql.gz "s3://$BUCKET/$KEY"

      echo "Generating pre-signed download URL (valid 1 hour)..."
      URL=$(aws s3 presign "s3://$BUCKET/$KEY" --expires-in 3600)
      echo ""
      echo "=== DOWNLOAD URL ==="
      echo "$URL"
      echo "==================="
      echo "URL expires in 1 hour."
    EOT
  }
]
```

---

## 9. Raptor CLI Commands

The following raptor commands are available for managing actions. Resources are specified using the `RESOURCE_TYPE/RESOURCE_NAME` format (e.g., `service/agent`). Actions can be referenced by either their hash name or human-readable display name (e.g., `rollout-restart-deployment`).

### List Actions

```bash
# List all actions available for a resource
raptor get actions RESOURCE_TYPE/RESOURCE_NAME -p PROJECT -e ENVIRONMENT

# Example
raptor get actions service/agent -p my-project -e production
```

### Trigger an Action

```bash
# Trigger an action with parameters
raptor trigger action RESOURCE_TYPE/RESOURCE_NAME -p PROJECT -e ENVIRONMENT -a ACTION_NAME [--param KEY=VALUE]...

# Trigger and wait for completion (streams logs when done)
raptor trigger action RESOURCE_TYPE/RESOURCE_NAME -p PROJECT -e ENVIRONMENT -a ACTION_NAME -w

# Example
raptor trigger action service/agent -p my-project -e production -a rollout-restart-deployment -w
```

### View Action History

```bash
# List all action runs for a resource
raptor get action-runs RESOURCE_TYPE/RESOURCE_NAME -p PROJECT -e ENVIRONMENT

# Filter by specific action
raptor get action-runs RESOURCE_TYPE/RESOURCE_NAME -p PROJECT -e ENVIRONMENT --action ACTION_NAME

# Example
raptor get action-runs service/agent -p my-project -e production --action rollout-restart-deployment
```

### View Action Logs

```bash
# Get logs for a specific run
raptor get action-run-logs RESOURCE_TYPE/RESOURCE_NAME RUN_NAME -p PROJECT -e ENVIRONMENT -a ACTION_NAME

# Stream logs in real-time
raptor get action-run-logs RESOURCE_TYPE/RESOURCE_NAME RUN_NAME -p PROJECT -e ENVIRONMENT -a ACTION_NAME -f

# Example
raptor get action-run-logs service/agent c2c132ae4e6c6d7929dedc8b6db328ca80288940 -p my-project -e production -a rollout-restart-deployment
```

---

## 10. Best Practices and Anti-Patterns

### Best Practices

| Practice | Reason |
|----------|--------|
| Use `set -e` in all scripts | Fail fast on errors instead of silently continuing |
| Always use `var.instance_name` for `facets_resource_name` | Never hardcode — ensures actions are linked to the correct resource |
| Put all actions in a dedicated `actions.tf` file | Keeps operational concerns separate from infrastructure provisioning |
| Add `description` to every action | Makes actions discoverable and understandable in the UI |
| Set `resources.requests` and `resources.limits` | Prevents resource-hungry steps from impacting the cluster |
| Use `params` for user-controllable inputs | Avoids hardcoding values that may differ between invocations |
| Pin container image versions | `bitnami/kubectl:1.28` not `bitnami/kubectl:latest` |
| Print clear output in scripts | Users read logs in the UI — make them informative |
| Validate params before destructive operations | `if [ -z "$REPLICAS" ]; then echo "Error: REPLICAS required"; exit 1; fi` |

### Anti-Patterns

| Anti-Pattern | Why It's Bad |
|-------------|--------------|
| Modifying infrastructure state (creating resources, changing configs) | That's what Terraform/releases are for — actions should be operational |
| Embedding secrets in scripts | Use env vars, params, or auto-injected credentials instead |
| Using `latest` image tags | Breaks reproducibility — pin to specific versions |
| Creating overly broad "do everything" actions | Prefer focused, single-purpose actions |
| Skipping error handling (`set -e`) | Silent failures make debugging impossible |
| Hardcoding resource names, namespaces, or environments | Use module variables (`var.instance_name`, `var.environment`) |
| Creating actions for Azure/GCP | Not supported — only K8s and AWS action types exist |
| Long-running actions without resource limits | Can starve the cluster — always set requests/limits for heavy work |
| Actions that duplicate release functionality | If it should run during deploy, put it in the module, not an action |

### File Organization

```
my-module/
├── facets.yaml
├── variables.tf
├── locals.tf
├── main.tf           # Infrastructure provisioning
├── outputs.tf
├── versions.tf
└── actions.tf        # All operational actions (this file)
```

Keep all actions in a single `actions.tf` file. This makes it easy to:
- Find all actions for a module
- Review operational capabilities at a glance
- Enable/disable actions by commenting out resources

## Sensitive Values in Raptor Commands — NEVER Put Secrets in the Chat

**CRITICAL RULE: NEVER ask the user to type a sensitive value (password, token, API
key, secret) in the chat.** Typing it in chat means the LLM sees it — it will be stored
in conversation history and logs. This is forbidden regardless of which tool you use to
ask (AskUserQuestion, chat message, follow-up question — all forbidden for secrets).

**Mandatory workflow — no exceptions:**

You run under the user's own shell — there is no vault or modal here. Keep the secret
out of the chat by having the user put it in an environment variable in their terminal,
then reference the *variable* (never the value) in raptor commands:

```bash
# 1. The user runs this in their own terminal. `read -rs` reads at a silent prompt,
#    so the value is never pasted into the chat and never reaches the LLM or transcript:
read -rs MY_DB_PASS; export MY_DB_PASS

# 2. Reference the env var in the raptor command. The user's shell expands "$MY_DB_PASS"
#    locally — the literal value never appears in what you (the LLM) emit or log.
#    Secrets never take a stack-level --value — set them per environment:
raptor create variable MY_DB_PASS -p myproject --secret --env-values prod="$MY_DB_PASS"
```

If a value should not even transit an env var, ask the user to run the single sensitive
raptor command themselves and paste back only the (non-sensitive) result.

**If the user offers to type the value in chat, redirect them:**
"Please don't paste it in chat — export it in your shell (`read -rs MY_DB_PASS; export
MY_DB_PASS`) and I'll reference `$MY_DB_PASS`, so the value never enters our conversation."

The `--secret` flag marks the variable as sensitive in the Facets Control Plane
(masked in UI, not returned in plain-text API responses).

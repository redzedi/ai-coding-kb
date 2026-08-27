---
name: "praxis-terraform_import"
description: Import existing cloud infrastructure into Facets-managed Terraform state.
  Guides through resource discovery, module preparation, incremental import block
  construction, drift reconciliation, and safe apply.
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

# Terraform State Import into Facets

Import existing cloud infrastructure into Facets-managed Terraform state without destroying or recreating resources.

---

## Step 1: Identify the Target Resource

**Goal:** Understand exactly what the user wants to import.

### Actions:
1. Ask the user for:
   - **Resource type and name** from the Facets blueprint (e.g., `kubernetes_cluster/siera-api`)
   - **Cloud account** — which AWS/GCP/Azure account holds the resource
   - **Region** — where the resource lives
   - **Resource ID/name** — the actual cloud resource identifier (e.g., EKS cluster name, RDS instance ID)

2. Download the current module to understand what Terraform resources it creates:
   ```bash
   raptor get iac-module <type>/<flavor>/<version> --save-to /tmp/module
   ```

3. Read the module's `.tf` files to catalog all `resource` blocks — these are the resources that will need importing:
   - Main resources (e.g., `aws_eks_cluster.this`)
   - Supporting resources (IAM roles, security groups, policies, addons)
   - Note which use `count` vs `for_each` — this affects import block syntax

4. Read the resource's blueprint JSON to understand the current spec configuration.

---

## Step 2: Discover AWS Resources

**Goal:** Collect all cloud resource IDs/ARNs that map to the module's Terraform resources.

### Actions:
Use Cloud CLI (`run_cloud_cli`) to list resources. Example for EKS:

```bash
# Cluster details
eks describe-cluster --name <cluster-name> --region <region> --output json

# Security groups
ec2 describe-security-groups --filters "Name=tag:kubernetes.io/cluster/<cluster-name>,Values=owned" --region <region> --output json

# IAM roles (check cluster's role_arn from describe-cluster output)
iam get-role --role-name <role-name> --output json

# EKS addons
eks list-addons --cluster-name <cluster-name> --region <region> --output json

# OIDC provider
iam list-open-id-connect-providers --output json

# Security group rules
ec2 describe-security-group-rules --filters "Name=group-id,Values=<sg-id>" --region <region> --output json

# CloudWatch log groups (verify they exist before importing)
logs describe-log-groups --log-group-name-prefix /aws/eks/<cluster-name> --region <region> --output json
```

Build a mapping of: `Terraform resource address → AWS resource ID`

**Important:** Only add resources to imports.tf that actually exist in AWS. Verify with Cloud CLI first. Resources the module defines but that don't exist in AWS (e.g., CloudWatch log group when logging is disabled) should NOT be imported — let Terraform create them.

---

## Step 3: Optionally Create a Dedicated Import Flavor

**Goal:** Decide whether to use the existing module flavor or create a dedicated import flavor.

### Decision:
Ask the user:
- **Use existing flavor** — import directly, handle drifts via blueprint config changes
- **Create dedicated import flavor** — fork the module for import-specific adjustments

### If creating import flavor:
1. Download the current module:
   ```bash
   raptor get iac-module <type>/<flavor>/<version> --save-to /tmp/module/<import_flavor>
   ```

2. Update `facets.yaml` — change flavor name to the import flavor name

3. **CRITICAL: Remove all `depends_on` blocks** from resources that will be imported.

   **Why:** Terraform 1.5.x has a bug/limitation where it cannot import a resource when any resource listed in its `depends_on` is also being imported in the same operation. The import fails with "Cannot import to non-existent resource address" even though the address is valid. Since all resources already exist in AWS, dependency ordering is irrelevant during import. This is the single biggest gotcha in the import workflow.

   Example — the `aws_eks_cluster.this` resource typically has:
   ```hcl
   depends_on = [
     aws_iam_role_policy_attachment.this,
     aws_security_group_rule.cluster,
     aws_security_group_rule.node,
     aws_cloudwatch_log_group.this,
     aws_iam_policy.cni_ipv6_policy,
   ]
   ```
   Comment out or remove the entire `depends_on` block for the import flavor.

4. Publish:
   ```bash
   raptor create iac-module -f /tmp/module/<import_flavor> --publish --skip-validation
   ```

5. Create resource-type-mapping if needed:
   ```bash
   raptor create resource-type-mapping <cloud> --resource-type <type>/<import_flavor>
   ```

6. Update the blueprint resource to use the new flavor and apply:
   ```bash
   raptor apply resource -p <project> -f <resource.json>
   ```

---

## Step 4: Run a Targeted Plan

**Goal:** Get exact Terraform resource addresses from a plan output.

### Actions:
```bash
raptor create release -p <project> -e <environment> --plan --target <resource_type>/<resource_name>
```

**Critical:** Always use `--target` during import workflow to isolate from other modules.

### Wait for completion and fetch logs:

**Never use `sleep` or `tail` to wait for logs — this wastes tokens on partial output.** Instead, poll the release status in a loop:

```bash
while true; do
  STATUS=$(raptor get release -p <project> -e <environment> <release-id> -o json 2>/dev/null | grep -o '"status":"[^"]*"' | head -1)
  echo "$STATUS"
  if echo "$STATUS" | grep -qE 'COMPLETED|FAILED|SUCCESS'; then break; fi
  sleep 15
done
```

Then fetch logs only once complete:
```bash
raptor logs release -p <project> -e <environment> <release-id> > plan-logs.txt
```

### Extract resource addresses:
```bash
grep 'will be created' plan-logs.txt
```

This gives exact Terraform addresses like:
```
module.level2.module.<type>_<name>.module.<submodule>.<resource>.<name>[<key>]
```

---

## Step 5: Build imports.tf Incrementally (Bottom-Up)

**Goal:** Add import blocks one at a time (or in small batches), verifying each with a plan.

### Import Order (bottom-up):
Start with leaf resources that have no dependencies, then work up:

1. **Security group rules** (`aws_security_group_rule`)
2. **IAM policy attachments** (`aws_iam_role_policy_attachment`)
3. **IAM policies** (`aws_iam_policy`)
4. **Security groups** (`aws_security_group`)
5. **IAM roles** (`aws_iam_role`)
6. **CloudWatch log groups** (`aws_cloudwatch_log_group`) — only if they exist in AWS
7. **OIDC provider** (`aws_iam_openid_connect_provider`)
8. **Addons** (`aws_eks_addon`)
9. **Main resource** (e.g., `aws_eks_cluster`)

### Import Block Syntax:
```hcl
import {
  to = module.level2.module.<type>_<name>.module.<submodule>.<resource>.<name>[<key>]
  id = "<aws-resource-id>"
}
```

For `count`-based resources: `resource.name[0]`
For `for_each`-based resources: `resource.name["key"]`

**IMPORTANT:** Terraform 1.5.x does NOT support `for_each` inside import blocks. That feature requires Terraform 1.7+. Always use individual import blocks per resource instance.

### Base64 Technique:

Always use base64 encoding to pass the imports.tf content via custom release. This avoids shell escaping issues with quotes, brackets, and special characters in HCL.

```bash
# Encode locally
base64 -w0 /path/to/imports.tf

# Custom release command — always cat the file for debugging visibility in logs
raptor create custom-release -p <project> -e <environment> \
  -c "echo '<BASE64_STRING>' | base64 -d > imports.tf && echo '=== imports.tf ===' && cat imports.tf && echo '=================' && terraform plan"
```

**Always print the imports.tf in the custom release command** (`cat imports.tf`) so its contents appear in the logs for debugging.

### Incremental Process:
1. Maintain a single imports.tf file locally — add resources to it progressively
2. Base64 encode the file
3. Run custom release with `terraform plan`
4. Poll status until complete, then fetch logs once
5. Check logs — grep for `Preparing import`, `Error`, `forces replacement`
6. If successful, add the next batch of resources to imports.tf
7. Repeat until all resources are included

### Log Analysis:
```bash
raptor logs release -p <project> -e <environment> <release-id> > import-logs.txt

# Check for errors
grep -E 'Error|Cannot|non-existent' import-logs.txt

# Check successful imports
grep 'Preparing import' import-logs.txt

# Check for forced replacements (CRITICAL — these destroy resources)
grep 'forces replacement' import-logs.txt

# Check for in-place updates
grep 'will be updated' import-logs.txt

# Check plan summary
grep 'Plan:' import-logs.txt
```

---

## Step 6: Reconcile Diffs Per Resource

**Goal:** For each imported resource, resolve all plan diffs until clean.

### Diff Categories and Safety Assessment:

#### 1. `# forces replacement` — DANGEROUS, MUST FIX
These will **destroy and recreate** the resource. The imported resource gets deleted.
- **Fix options:**
  - Add the field to `lifecycle { ignore_changes = [...] }` in the module
  - Match the value exactly in the module or blueprint spec
- **Always fix these before any apply**

#### 2. `~ update in-place` — ASSESS SAFETY PER FIELD
These modify the resource without destroying it. Educate the user on each:

**Generally safe updates (low risk):**
- `tags` / `tags_all` — Adding/removing tags doesn't affect resource functionality
- `description` fields — Metadata only
- `assume_role_policy` additions — Adding new actions (e.g., `sts:TagSession`) is additive
- `force_detach_policies` — Operational preference, doesn't affect running workloads

**Potentially risky updates (assess carefully):**
- `enabled_cluster_log_types` — Changes what gets logged; adding types is safe, removing could lose audit trail
- `authentication_mode` — Changing auth mode on EKS (e.g., CONFIG_MAP → API_AND_CONFIG_MAP) is additive and safe, but narrowing is risky
- `subnet_ids` — Adding subnets is safe, removing could affect scheduling
- `security_group_ids` — Changing SG associations could break network connectivity
- `cluster_version` — Version changes trigger upgrades, should be intentional

**Risky updates (warn user):**
- `vpc_config` changes (especially subnet removal)
- `encryption_config` changes
- `role_arn` on anything — changing IAM associations can break permissions
- `service_ipv4_cidr` / network CIDR changes

#### 3. `+ create` — NEW RESOURCES
Resources the module wants to create that don't exist in AWS.
- Usually fine to create (e.g., Facets metadata resources, new tags)
- But warn if creating cloud resources that cost money (node groups, addons)

#### 4. `- destroy` — RESOURCE DELETION
**Always warn the user.** This usually means the module doesn't define something that exists in state.

### Decision Flow for Each Diff:
Present each diff to the user with safety context:
- **"Ignore drift"** → Add to `ignore_changes` in the module
- **"Allow change"** → Let Terraform update the field (explain if safe or risky)
- **"Make configurable"** → Add a spec field in `facets.yaml` schema, wire through module, update blueprint to match AWS value. Then actually update the module, republish, and re-plan to verify.

### After each module change:
```bash
# Republish
raptor create iac-module -f /path/to/module --publish --skip-validation

# Re-run plan with imports (always cat the file)
B64=$(base64 -w0 /path/to/imports.tf)
raptor create custom-release -p <project> -e <environment> \
  -c "echo '${B64}' | base64 -d > imports.tf && echo '=== imports.tf ===' && cat imports.tf && echo '=================' && terraform plan"

# Poll status, then verify
grep 'forces replacement' logs.txt  # Should return nothing
grep 'Plan:' logs.txt               # Check counts
```

---

## Step 7: Apply with User Review

**Goal:** Actually import all resources into Terraform state.

**⚠️ CRITICAL: Always warn user and get explicit approval before applying.**

Present a summary before applying:
- Number of resources to import
- Number of in-place updates (and what fields change)
- Number of new resources to create
- Confirm: **0 to destroy**

The apply command imports resources into state AND applies any remaining diffs. Only proceed when:
- All `forces replacement` diffs are resolved
- User has reviewed and approved all remaining in-place changes
- Plan summary shows **no destroys**

```bash
raptor create custom-release -p <project> -e <environment> \
  -c "echo '<BASE64>' | base64 -d > imports.tf && echo '=== imports.tf ===' && cat imports.tf && echo '=================' && terraform apply -auto-approve"
```

---

## Step 8: Update Blueprint Spec

**Goal:** Align the blueprint configuration with actual AWS state.

After import, the blueprint may specify features that don't exist in AWS (e.g., addons not installed, node groups not present). Update the blueprint JSON to match reality:

```bash
# Get current resource config
raptor get resource -p <project> -t <type> -n <name> -o json > resource.json

# Edit to match actual AWS state (disable non-existent addons, remove phantom node groups, etc.)
# Then apply
raptor apply resource -p <project> -f resource.json
```

---

## Step 9: Final Verification

**Goal:** Confirm clean state — no changes needed.

```bash
raptor create release -p <project> -e <environment> --plan --target <resource_type>/<resource_name>
```

Expected output:
```
Plan: 0 to add, 0 to change, 0 to destroy.
```

If not zero, repeat steps 6-8 until clean.

---

## Key Learnings and Gotchas

- **Terraform 1.5.x does NOT support `for_each` in import blocks** — use individual blocks per resource
- **Terraform 1.5.x cannot import a resource alongside its `depends_on` targets** — this is the #1 blocker. Remove all `depends_on` blocks in the import flavor module. The error message ("Cannot import to non-existent resource address") is misleading — the address is valid, but the `depends_on` conflict prevents resolution.
- **Always use base64** for imports.tf in custom releases — shell escaping breaks with quotes and brackets
- **Always cat imports.tf in the custom release command** — so the file contents appear in logs for debugging
- **Always use `--target`** when running plans during import workflow
- **Import order matters** — import dependencies first (IAM role before cluster, since cluster references `aws_iam_role.this[0].arn`)
- **`(known after apply)` on ForceNew fields** means a dependency isn't in state yet — import that dependency first
- **Custom release does NOT support `--target` flag** — but you can add `-target=...` inside the terraform command itself
- **Never apply without user review** — plans are safe, applies are not
- **Never use sleep/tail to wait for logs** — poll release status in a loop, fetch logs only once complete. This avoids wasting tokens on partial/repeated log output.
- **Save all logs to files** and grep with patterns rather than reading raw output
- **Verify resources exist in AWS before importing** — use Cloud CLI. If a resource doesn't exist (e.g., CloudWatch log group when logging is disabled), don't add it to imports.tf.
- **Assess update safety per field** — not all in-place updates are equal; tags are safe, network changes are risky. Always educate the user on the risk level and seek their direction.

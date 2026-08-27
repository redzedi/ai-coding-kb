# Facets YAML Schema Reference

`facets.yaml` defines module identity, developer-facing configuration schema (spec), inputs/outputs, UI rendering, and sample config.

---

## 1. Complete Structure

```yaml
intent: <technology>              # e.g. postgres
flavor: <variant>                 # e.g. aws-rds
version: "1.0"                    # quoted semver
description: One-line description

intentDetails:                    # REQUIRED — every facets.yaml must have this
  type: <category>                # see valid values below
  description: Full description
  displayName: Human Name
  iconUrl: https://raw.githubusercontent.com/Facets-cloud/facets-modules-redesign/main/icons/<name>.svg

clouds: [aws, gcp, azure, kubernetes]

# Optional: for modules with artifact references (e.g. docker image)
artifact_inputs:
  primary:
    attribute_path: spec.release.image
    artifact_type: docker_image

# Optional: required for modules with Kubernetes functionality (enables K8s Explorer in CP UI)
controlPlaneUISettings:
  enableKubernetesExplorer: true

inputs:
  <name>:
    type: "@facets/<output_type>"
    displayName: Human Name
    description: What this provides
    optional: false
    default:
      resource_type: <type>
      resource_name: default
    providers: [aws]              # only if provider flows through this input

outputs:
  default:
    type: "@facets/<output_type>"
    title: Description
  attributes:                     # only for provider-exposing modules (dual-output pattern)
    type: "@facets/<generic_type>"
    title: Description
    providers:
      <provider>:
        source: hashicorp/<provider>
        version: x.y.z
        attributes:
          <attr>: <tf_expression>

spec:
  title: Schema Title
  description: Schema description
  type: object
  x-ui-order: [field1, field2]
  properties:
    <field>:
      type: string|number|boolean|object|array
      title: Field Title
      description: Field description
      # JSON Schema constraints + x-ui tags

sample:
  kind: <intent>
  flavor: <flavor>
  version: "1.0"
  disabled: false
  spec:
    # mirrors spec with valid values for all required fields
```

**Valid `intentDetails.type` values:** `Cloud & Infrastructure`, `Datastores`, `Kubernetes`, `Monitoring & Observability`, `Operators`

---

## 2. Required Fields Checklist

Before finishing any `facets.yaml`, verify all are present:
- [ ] `intent`, `flavor`, `version` (quoted), `description`
- [ ] `intentDetails` with `type`, `description`, `displayName`, `iconUrl`
- [ ] `clouds` array
- [ ] `spec` with complete schema — no `type: any`
- [ ] `sample` with valid values for every `required` field
- [ ] `inputs` with correct `@facets/<output_type>` types
- [ ] `outputs` with correct `@facets/<output_type>` types

---

## 3. Spec Schema — Type Decision Rules

| Situation | Use |
|-----------|-----|
| Finite known set of values (3–20 options) | `type: string` + `enum: [...]` |
| Structured string (CIDR, ARN, DNS, port) | `type: string` + `pattern: regex` |
| On/off toggle | `type: boolean` |
| Numeric with bounds | `type: number` + `minimum`/`maximum` |
| Named sub-sections grouping related fields | `type: object` with nested `properties` + `x-ui-order` |
| List of typed items | `type: array` with `items` schema |
| Dynamic keys / map / dict | `type: object` + `patternProperties` |
| Free-form key-value or arbitrary YAML | `type: object` + `x-ui-yaml-editor: true` |
| Multi-line text | `type: string` + `x-ui-textarea: true` |
| Code with syntax highlighting | `type: string` + `x-ui-editor: true` + `x-ui-editor-language: <lang>` |

### patternProperties — CRITICAL shape

`required` must go INSIDE the pattern definition, never as a sibling:

```yaml
tolerations:
  type: object
  patternProperties:
    ^[a-zA-Z0-9_.-]*$:
      type: object
      properties:
        key: {type: string}
        operator: {type: string, enum: [Equal, Exists]}
      required: [key, operator]   # ← INSIDE pattern, NOT outside tolerations
```

### Validation constraints

- **string**: `minLength`, `maxLength`, `pattern` — **no lookahead/lookbehind in regex**
- **number**: `minimum`, `maximum`
- **object**: `required: [field1, field2]`
- **enum**: no duplicate values

```
# BAD pattern — lookahead not supported:
pattern: ^(?!0$)([1-9][0-9]{0,3})$

# GOOD:
pattern: ^([1-9][0-9]{0,3})$

# BAD enum — duplicate value:
enum: [X-Frame-Options, Cache-Control, Cache-Control]
```

### Common validation patterns

```
DNS name:    ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$
DB name:     ^[a-zA-Z][a-zA-Z0-9_]*$  (+ minLength:1, maxLength:63)
Port:        type:integer, minimum:1, maximum:65535
CPU:         ^([0-9]+m|[0-9]+(\.[0-9]+)?)$
Memory:      ^[0-9]+(Mi|Gi)$
ARN:         ^arn:aws:[a-z0-9-]+:[a-z0-9-]*:[0-9]{12}:.+$
Semver:      ^\d+\.\d+(\.[0-9]+)?$
CIDR:        ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$
```

---

## 4. x-ui Tags — Complete Reference

| Goal | Tag(s) |
|------|--------|
| Control field display order | `x-ui-order: [f1, f2]` on parent object |
| Collapsible section (collapsed by default) | `x-ui-toggle: false` on parent; `x-ui-toggle: true` on child to auto-expand |
| Hide field from UI (internal/programmatic) | `x-ui-skip: true` |
| Read-only after initial creation | `x-ui-immutable: true` |
| Show only at environment level (no blueprint default) | `x-ui-overrides-only: true` |
| Lock to blueprint level (no env override) | `x-ui-override-disable: true` |
| Require elevated permission (`CRITICAL_RESOURCE_WRITE`) to edit | `x-ui-critical: true` |
| Show/hide based on another field's value (single) | `x-ui-visible-if: {field: spec.x, values: [v]}` |
| Show/hide based on multiple conditions | `x-ui-visible-if: [{field: a, values: [v1]}, {field: b, values: [v2]}]` |
| Dropdown populated from another spec field path | `x-ui-dynamic-enum: spec.path.*.field` |
| Tooltip shown when dynamic enum dropdown is disabled | `x-ui-disable-tooltip: "No items configured"` |
| Dropdown from API endpoint | `x-ui-api-source: {endpoint: ..., labelKey: ..., valueKey: ...}` |
| Allow manual typing in a dropdown | `x-ui-typeable: true` |
| Dropdown showing resources of a specific output type | `x-ui-output-type: <type>` |
| Output reference picker widget (filters by output type via API) | `x-ui-output: true` + `x-ui-output-type: <type>` |
| Regex extraction inside `x-ui-api-source.dynamicProperties` | `x-ui-lookup-regex: <pattern>` |
| Secret store reference picker | `x-ui-secret-ref: true` |
| Variable store reference picker | `x-ui-variable-ref: true` |
| Artifact reference picker (docker image, zip, etc.) | `x-ui-artifact: true` |
| Mask/hide sensitive value in UI display | `x-ui-mask: true` |
| Multi-select dropdown | `x-ui-multi-select: true` (on `type: array`) |
| Constrain multi-select item count | `x-ui-select-min: N` + `x-ui-select-max: N` |
| Radio buttons instead of dropdown | `x-ui-radio: true` (on enum field) |
| Preserve enum order (no alphabetical sort) | `x-ui-no-sort: true` |
| Show label instead of value after selection | `x-ui-show-label-selected: true` |
| Monaco code editor | `x-ui-editor: true` + `x-ui-editor-language: <lang>` |
| YAML editor widget (for `type: object`) | `x-ui-yaml-editor: true` |
| Multiline textarea | `x-ui-textarea: true` |
| Command/args array input widget | `x-ui-command: true` |
| Hint text in empty input field | `x-ui-placeholder: example-value` |
| Custom validation error message | `x-ui-error-message: "text"` |
| Cross-field value comparison with error | `x-ui-compare: {field: spec.x, comparator: <=, x-ui-error-message: "text"}` |
| Enforce unique values within an array | `x-ui-unique: true` |
| Validate each item as it's entered in an array | `x-ui-array-input-validation: {pattern: ..., errorMessage: ...}` |
| Custom error for uniqueness violation on pattern field | `x-ui-unique-pattern-error-message: "text"` |
| Flatten UI hierarchy (hide parent key label) | `x-ui-ignore-parentkey: true` |
| Override the title shown for a field | `x-ui-title-replace: "New Title"` |
| Enable blueprint inheritance merging | `x-ui-allow-blueprint-merge: true` |
| Allow user to edit the map key in patternProperties | `x-ui-allow-title-edit: true` |

**Comparators for `x-ui-compare`:** `<`, `<=`, `>`, `>=`, `==`, `!=`

### x-ui-toggle shape

```yaml
cloud_permissions:
  type: object
  title: Cloud Permissions
  x-ui-toggle: false          # section collapsed by default
  properties:
    aws:
      type: object
      title: AWS
      x-ui-toggle: true       # this sub-section auto-expands within parent
```

### x-ui-api-source shapes

**Basic dropdown from API:**
```yaml
instance_class:
  type: string
  title: Instance Class
  x-ui-api-source:
    endpoint: /cc-ui/v1/dropdown/aws/rds/instance-classes
    method: GET                     # optional, default GET
    params: {engine: postgres}      # optional static query params
    labelKey: name
    valueKey: value
    filterConditions:               # optional server-side filter
      - field: type
        value: current-generation
  x-ui-typeable: true
```

**Dynamic URL tokens + value template:**
```yaml
service_name:
  type: string
  title: Service Name
  x-ui-api-source:
    endpoint: /cc-ui/v1/dropdown/stack/{{stackName}}/service/{{serviceName}}/overview
    dynamicProperties:
      serviceName:
        key: service_name           # spec field to extract from
        lookup: regex
        x-ui-lookup-regex: \${[^.]+\.([^.]+).*   # regex to extract token
    valueTemplate: ${service.{{value}}.out.attributes.name}
```

**Dropdown filtered by resource type with value template:**
```yaml
config_map_name:
  type: string
  title: Config Map
  x-ui-api-source:
    endpoint: /cc-ui/v1/dropdown/stack/{{stackName}}/resources-info
    params: {includeContent: false}
    labelKey: resourceName
    valueKey: resourceName
    valueTemplate: ${config_map.{{value}}.out.attributes.name}
    filterConditions:
      - field: resourceType
        value: config_map
  x-ui-typeable: true
```

---

## 5. Inputs & Outputs

### Input definition

```yaml
inputs:
  cloud_account:
    type: "@facets/aws_cloud_account"
    displayName: Cloud Account
    description: AWS account for resource creation
    optional: false
    default: {resource_type: cloud_account, resource_name: default}
    providers: [aws]              # REQUIRED if provider flows through this input

  network_details:
    type: "@facets/aws-vpc-details"
    displayName: Network
    optional: false
    default: {resource_type: network, resource_name: default}

  kubernetes_details:
    type: "@facets/eks"
    displayName: Kubernetes Cluster
    optional: true
    providers: [kubernetes, helm]  # add helm if main.tf contains helm resources
```

### Output — simple (no providers)

```yaml
outputs:
  default:
    type: "@facets/postgres"
    title: PostgreSQL Database Output
```

### Output — provider-exposing (dual-output convention)

Rule: `default` = cloud-specific type, NO providers. `attributes` = generic type, WITH providers.

```yaml
outputs:
  default:
    type: "@facets/eks"
    title: EKS Cluster Attributes
  attributes:
    type: "@facets/kubernetes-details"
    title: Kubernetes Cluster Output
    providers:
      kubernetes:
        source: hashicorp/kubernetes
        version: 2.38.0
        attributes:
          host: cluster_endpoint
          cluster_ca_certificate: cluster_ca_certificate
          exec:
            api_version: kubernetes_provider_exec.api_version
            command: kubernetes_provider_exec.command
            args: kubernetes_provider_exec.args
      helm:
        source: hashicorp/helm
        version: 2.17.0
        attributes:
          kubernetes:
            host: cluster_endpoint
            cluster_ca_certificate: cluster_ca_certificate
```

---

## 6. Sample Rules

1. Every `required` spec field must appear in `sample`, even with an empty/default value.
2. Sample enum values must be valid options from the schema enum list.
3. Use `{}` for `type: object` fields, `[]` for `type: array` — **never `null`**.
4. For `type: object` with `patternProperties`, use `{}` not `[]`.

```yaml
# BAD — null and wrong type for patternProperties object:
sample:
  spec:
    values: null
    tolerations: []   # WRONG: tolerations is type:object with patternProperties

# GOOD:
sample:
  spec:
    values: {}
    tolerations: {}   # correct for type:object with patternProperties
```

**Full sample example:**
```yaml
sample:
  kind: postgres
  flavor: aws-rds
  version: "1.0"
  disabled: false
  spec:
    version_config:
      engine_version: "16.12"
      database_name: postgres
    sizing:
      instance_class: db.t3.small
      allocated_storage: 100
      read_replica_count: 0
    security_config:
      deletion_protection: true
    restore_config:
      restore_from_backup: false
    imports: {}
```

---

## 7. Common Patterns

### Grouped configuration sections

```yaml
spec:
  type: object
  x-ui-order: [basic_config, advanced_config, security_config]
  properties:
    basic_config:
      type: object
      title: Basic Configuration
      x-ui-order: [name, version]
      properties:
        name: {type: string, title: Name}
        version: {type: string, title: Version}
      required: [name, version]
```

### Conditional field (shown only when another field is true)

```yaml
enable_ssl:
  type: boolean
  title: Enable SSL
  default: true

ssl_certificate:
  type: string
  title: SSL Certificate ARN
  x-ui-visible-if:
    field: spec.enable_ssl
    values: [true]
  x-ui-placeholder: arn:aws:acm:region:account:certificate/id
```

### Restore / import section (override-only, revealed by toggle)

```yaml
restore_config:
  type: object
  title: Restore Operations
  x-ui-overrides-only: true       # only configurable at environment level
  properties:
    restore_from_backup:
      type: boolean
      title: Restore from Backup
      default: false
    source_db_instance_identifier:
      type: string
      title: Source DB Instance Identifier
      x-ui-visible-if:
        field: spec.restore_config.restore_from_backup
        values: [true]
```

### Resource requests / limits with cross-field comparison

```yaml
resources:
  type: object
  title: Resource Limits
  x-ui-order: [cpu_limit, memory_limit, cpu_request, memory_request]
  properties:
    cpu_limit:
      type: string
      title: CPU Limit
      pattern: ^([0-9]+m|[0-9]+(\.[0-9]+)?)$
      default: "1"
      x-ui-placeholder: "1.0 or 1000m"
    cpu_request:
      type: string
      title: CPU Request
      pattern: ^([0-9]+m|[0-9]+(\.[0-9]+)?)$
      x-ui-compare: {field: spec.resources.cpu_limit, comparator: <=, x-ui-error-message: CPU request cannot exceed CPU limit}
      x-ui-placeholder: "0.5 or 500m"
    memory_limit:
      type: string
      title: Memory Limit
      pattern: ^[0-9]+(Mi|Gi)$
      default: "1Gi"
      x-ui-placeholder: "1Gi or 1024Mi"
    memory_request:
      type: string
      title: Memory Request
      pattern: ^[0-9]+(Mi|Gi)$
      x-ui-compare: {field: spec.resources.memory_limit, comparator: <=, x-ui-error-message: Memory request cannot exceed memory limit}
      x-ui-placeholder: "512Mi or 1Gi"
```

### Secret field

```yaml
db_password:
  type: string
  title: Database Password
  x-ui-secret-ref: true
  x-ui-placeholder: Select or enter secret reference
```

### Environment variable map (free-form)

```yaml
env_vars:
  type: object
  title: Environment Variables
  x-ui-yaml-editor: true
  x-ui-allow-title-edit: true
  patternProperties:
    ^[a-zA-Z_][a-zA-Z0-9_]*$:
      type: string
```

---

## 8. Critical Validation Rules

- `intentDetails` is **REQUIRED** in every `facets.yaml`.
- **Never** use `type: any` — always define complete schemas.
- **No** regex lookahead/lookbehind in `pattern` values.
- **No** duplicate values in `enum` arrays.
- `required` goes **INSIDE** `patternProperties` pattern definition, never as a sibling to the pattern.
- **No** `metadata:` top-level key in `facets.yaml`.
- Modules exposing providers **MUST** use the dual-output pattern (`default` + `attributes`).
- For `type: object` with `patternProperties`, sample value must be `{}` not `[]` or `null`.

**Validate before upload:**
```bash
raptor create iac-module -f <module-path> --dry-run
# Security scan failure (not a schema issue): add --skip-security-scan
# NEVER use: --skip-validation
```

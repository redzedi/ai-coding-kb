<!-- last-updated: 2026-04-09 | journals: 76 -->

## Patterns & Conventions

- **Maven version chain**: Updating a leaf dependency in a multi-module Maven project requires bumping every library up the chain. Never change just the leaf. Example: cubesdk → brands-api → brands-commons → brands-service — each must be re-versioned and refs updated. (journal-maven-library-version-chain)
- **Databricks DDL migrations**: Repo `databricks-schema-management`, files in `resources/db_migration/ESM/CLIENT_CATALOG/<SCHEMA>/YYYY_MM_DD__<description>.yaml`, format `DDLType: create_view` with `changeSets`. Branch name = JIRA ticket ID. (journal-3p-filter)
- **Branching convention (CIQ)**: Sync `develop-occ` with `master-dbx` before creating feature branches to avoid merge conflicts. (journal-taxonomy-d)
- **Disabling tests**: Always get Suman's approval before disabling any test, even pre-existing failing ones. (journal-taxonomy-d)
- **jenv + Maven**: Run `jenv local 1.8` as a separate command first, then Maven. Do NOT combine in one shell line — it breaks JAVA_HOME. Pre-push hook needs `JAVA_HOME=/Users/sumanyadav/.jenv/versions/1.8` set explicitly. (learnings-from-riq-1325)
- **Mockito matchers**: ALL arguments in a mocked call must use matchers — cannot mix raw values with `anyX()`. Use `eq("string")` for literal args. (learnings-from-riq-1325)
- **Fallback with string replacement**: Never use `.replace(exactSqlSnippet, "")` as fallback — brittle against whitespace/formatting changes. Short-circuit with `return Collections.emptyList()` when preconditions guarantee zero results. (ciq-dashboards_pr_2381_review)
- **Redis set() exception handling**: Wrap Redis `set()` calls in try-catch: `try { redisTemplate.opsForValue().set(...); } catch (Exception e) { LOG.warn(...); }`. (ciq-dashboards_reviewer-feedback)
- **MySQL composite index column order**: Place most selective + frequently-filtered-together columns adjacent. `(page_id, is_delete, widget_id)` beats `(page_id, widget_id, is_delete)` when most queries filter `page_id + is_delete` together — leftmost prefix matching stops at first skipped column. (dashboard-config-service_INDEX_COLUMN_ORDER_ANALYSIS.md)
- **MySQL online index creation**: InnoDB supports `ALGORITHM=INPLACE, LOCK=NONE` by default since 5.6 — no table locks. Use explicit syntax in production to fail-fast if online isn't possible. Main risk is IOPS budget on RDS, not locking. (dashboard-config-service_MYSQL_ONLINE_INDEX_CREATION.md)
- **`Thread.currentThread().getId()` deprecated**: Prefer `threadId()` in newer JDKs. (omni-api-service_reviewer-feedback.md)
- **PySpark parallel prep + serial write**: `ThreadPoolExecutor` for `prepare_dataframe()` across aggregators, then serial Delta writes to prevent concurrent-append conflicts. 40–60% latency reduction for multi-aggregator workflows. (omni-edm-workflow_performance-optimization-summary.md)
- **Materialize broadcast DataFrames before joining**: Call `.cache()` then `.count()` on small lookup tables before `broadcast()` to force materialization and avoid repeated scans during join. (omni-edm-workflow_performance-optimization-summary.md)
- **Exponential backoff for Delta ConcurrentAppendException**: `max_retries=8`, `wait = initial_backoff_sec * 2^(attempt-1)`. Reduces parallel-aggregator workflow failures 80%+. (omni-edm-workflow_performance-optimization-summary.md)
- **Always apply client_id/date filters immediately after `spark.read.table()`**: Predicate pushdown only fires if filters appear before transformations. Pre-calculate `allowed_ids_list` once in source schema module setup. 20–40% I/O reduction. (omni-edm-workflow_performance-optimization-summary.md)

## Architecture Decisions

### CIQ BI Platform Data Flow
```
UI → dashboard-service (V1: /entity/metrics/data, V2: /data)
   → brands-service (/cube/execute, cubesdk generates SQL)
   → Databricks SQL Warehouse
```
- dashboard-service is API gateway; brands-service loads cube JSON and generates SQL via cubesdk. (journal-3p-filter)
- **Metric → cube name mapping**: `metric_registar` table's `source` column (JSON `{"cubeName": "...", "sourceKey": "..."}`) → `MetricDao.findByMetricNameIn()` → `InsightsTransformer.convertToInsightsSource()` → `cubeRequest.setCubeName()`. Cube name extracted from **first metric** in source map. (data-api-flow-analysis)
- **Metric name pattern**: `{cubeName}__{measureName}` is a convention, but actual mapping is always authoritative in `metric_registar.source` JSON — never parse the name directly. (ciq-dashboards_request-trace-po-fill-rate)

### CIQ Alert Pipeline Architecture
```
Databricks table (client_catalog.aramus.<alert_table>)
   ↓ AlertGenerator (athena_aramus-workflow) queries via SQL from alert_generation_config
   ↓ Transforms → S3 + SQS → Elasticsearch bulk index (alertsystem/alert)
   ↓ RecommendationESServiceImpl queries ES
   ↓ athena_aramus REST API (/rest/alert, /rest/marketing) serves frontend
```
- **Critical**: athena_aramus API reads from **Elasticsearch, not Databricks directly**. SQL for alert selection lives in athena_alertmodulusconfig `configs/brand_alerts/{prod,beta,qa}/<AlertName>/alert.json`. (journal-ciq-etl-ingestion-role-programmer)
- **CIQ repo roles**: `custom_pa_workspace` = CCP workflow YAML + SQL modules; `athena_aramus-workflow` = orchestration/triggers/AlertGenerator; `athena_aramus` = product REST microservice; `athena_alertmodulusconfig` = alert SQL configs per env; `data-testing-worker` = QA query banks; `db-update-scripts` = DDL/metadata; `qa_orchestrator` = `workflow_to_resource_mapping.json`. (journal-ciq-etl-ingestion-role-programmer)

### alert_sales_decrease_wf (CCP Workflow)
- Defined in `custom_pa_workspace/ccp-configs/workflows/alert_sales_decrease_wf.yaml`. Triggered by `AlertEstimateE2eTrigger` in athena_aramus-workflow; metadata from `aramus.alert_estimate_workflow_metadata` + `aramus.alert_type_alert_name_mapping` (filter: `estimate_workflow_trigger = true`).
- Variables: `client_id`, `alertname`, `rundate`. Warehouse: DEMO_WH X_SMALL (`4815d160e782df10`). Output: `client_catalog.aramus.alert_sales_decrease` (Delta Lake, partitioned by CLIENT_ID, 1.6M+ rows, 27 clients). Alert Type ID = 71, 264 clients with workflow trigger.
- Dependency chain: base modules → `alert_sales_decrease_broken` → `alert_sales_decrease_helper` → `alert_sales_decrease` (postProcess: delete then insert for client_id + feed_date). (custom_pa_workspace_alert_sales_decrease_wf-end-to-end-analysis)

### registryId Semantics (CRITICAL — commonly misunderstood)
- `registryId` = **data service/API endpoint**, NOT product offering. `product` field = business product (SalesIQ, MarketingIQ, DSA).
- Known values: `1` = BRANDS_SERVICE (`/cube/execute`), `16` = OMNI_API_SERVICE (`/cube/execute`), `23` = OMNI_API_DSA (`/rest/omni/v1/dsa/data`).
- Same `registryId` can serve metrics from multiple product offerings. Request splitting is always by endpoint, not by product. (ciq-dashboards_journal-data-api-role-programmer)

### Widget Config Role in Data API
- `widgetId` drives: (1) payload transformer selection (`uiComponent`), (2) flag overrides (`metricDataApiTemplate` takes higher priority than request flags), (3) request splitting across registries, (4) custom entity logic (`customMetadata`), (5) response transformer selection, (6) template config lookup per `(widgetId, dataGroup)`.
- **`lineChart` and `trendSpeedometer`** widgets: `LinePayloadTransformerV3Impl` forces `timeseriesEnabled=true` unconditionally, regardless of request value.
- If template operations contain `"timeseriesEnabled": true`, request's `false` is ignored — template takes priority.
- With `timeseriesEnabled=true`, cubesdk uses cube's `timeSeriesSource` table instead of main `source` table. (ciq-dashboards_journal-data-api-role-programmer, timeseries-enabled-override-analysis)

### Request Splitting for Multiple Registries
- Triggered when: multiple `registryId` values in metrics + `orderBy` on a metric + `rows` specified.
- `isMultipleRegistryIdsDataRequest()` detects; splits metrics by `registryId`, creates per-registry `EntityDataRequest` with filtered widget config, executes in parallel.
- **Filtered widget config** preserves all widget properties — only `metrics` map is filtered per registry. Secondary request has `orderBy` and `pagination` set to null. (ciq-dashboards_journal-data-api-role-programmer, widget-usage-and-preview-flag-analysis)

### 1P vs 3P Common Filter
- **1P**: Parameterized UDF `brands_cubes.common_filter_udf(#CLIENT_ID_PARAM)` — client_id substituted at SQL gen time, guaranteeing filter pushdown.
- **3P**: Plain VIEW `seller_cubes.common_filter_view` — client_id added as WHERE clause, pushdown depends entirely on optimizer. (journal-3p-filter)

### Databricks Catalog Layers (3P)
- `client_catalog.seller_cubes.common_filter_view` — direct view, use for investigation.
- `client_view_catalog.seller_cubes.common_filter_view` — row-level security wrapper; may return 0 rows. Always query `client_catalog` when debugging. (journal-3p-filter)

### TaxonomySelectInfo DTO (cubesdk)
- Introduced to make the inner/outer query contract explicit: returns `selectClause`, `filterAliases`, `filterSourceColumns`. Avoids fragile assumptions between `getSelectClauseWithTaxonomyDimensions` and the dedup wrapper.
- Fix for taxonomy+dedup bug: `isFilterTableColumn(dimension, catalogName)` replaces the short-circuit `isDedupEnabled || ...` — only `dimension*` columns are guaranteed across all filter tables. (journal-taxonomy-d, rca-invalid-query-taxonomy-dimensions)

### brands-service Warehouse Selection Logic
- Priority order: explicit `warehouseId` → session `load_type=etl` (RMM ETL wh) → username is `ciq-llm-service*` (Ally Insights wh) → referer match in `HEAVY_PAGES` (heavy wh, currently empty) → default wh.
- **Heavy warehouse is never used** — `HeavyLoadRequestConfig.HEAVY_PAGES` is an empty list. **RMM ETL warehouse** (`d9369c57eb514078`) only fires when HTTP request sends `load_type: etl` header. Code: `DataAccessService.getDatabricksEndpoint()`, `getWarehouseId(referer)`. (databricks-warehouse-cost-optimization-analysis)

### brands-service Databricks Connection Pooling
- **No connection pooling.** Each request opens a new JDBC connection and closes it after use.
- Peak concurrency = 50 threads × N pods → can hit Databricks' 1,000-query queue limit with 10–20 pods. Fix: pool 10–20 connections/pod. (databricks-connection-pooling-impact-scalability-cost)

### dedupBeforeRollup Configuration Flow
- Source: `template_config` DB table, `operations` JSON field. **PK is `(widgetId, dataGroup)`** — each data group has its own row, so a single widget split into 2 bundle requests can legitimately have different `dedupBeforeRollup` values.
- Both `/data` and `/download/v3/widget/report` converge at `DataApiServiceImpl.transformPayloadForV1DataApi()` → `PayloadTransformerImpl.getOperations()` → `InsightsTransformer.createCubeExecutionRequest()` (lines 1215–1238). Template config operations take **higher priority** than request-level flags. (dedup-before-rollup-flow-analysis)

### cubesdk SQL Audit Comments Destroy Databricks Cache
- cubesdk appends `/**{"clientId":..., "userName":..., "pageUrl":...}**/` per-request → unique `statement_text` per user/page → Databricks uses full `statement_text` as cache key → cross-user cache sharing eliminated.
- Measured: **6.2% cache hit rate** (commented) vs **48.5%** (uncommented). Est. ~$1,900/month savings from removal.
- Fix: Replace `CommonUtils.addMetadataComment()` with `SET QUERY_TAGS` on the JDBC `Connection`. Call sites: `CellMetrics.execute()` (2 overloads). Query tag max 128 chars. (audit-comment-cache-impact)

### Min-Date Prefetch Mechanism (cubesdk)
- `MinimumDateHelper.setMinDate()` runs before the main cube query to fetch/cache `min(date_col)` per cube source. Query: `select coalesce(min(%s), '9999-12-31') as min_date from %s where %s`.
- **Skip conditions**: no timeseries dimension, `getLatestAvailableInsteadOfRollup=true`, neither PVP nor YOY enabled, `timeSeriesDimensionEnabled` custom flag.
- **Cache hit**: Java string comparison → literal `TRUE`/`FALSE` appended to WHERE — O(1), no DB subquery. **Cache miss**: standalone query executes, cached in Redis key `"query:{clientId}:{retailer}:min_date_{cubeSource}_{formattedSource}"`.
- **If minimumCubeDate NULL**: correlated subquery embedded in main query → full table scan on every execution.
- **`GET_MIN_DATE_LINKED_CLIENTS` constant is DEAD CODE** — never referenced; linked-client support is handled inline. (cubesdk_get-min-date-investigation)

### Max-Date Query Generation (cubesdk / dashboard-service)
Three mechanisms generate `SELECT MAX(feed_date)` queries; a 4th cache (Mechanism D) already stores the answers but isn't wired to A/B/C:
- **A. Embedded subquery** (`LATEST_INSTEAD_OF_ROLLUP_CLAUSE` / `CUBE_LATEST_CLAUSE`): in `BasicQueryGeneratorImpl.getWhereClause()` ~1293-1355. Part of cube SQL string — no separate JDBC call.
- **B. Standalone pre-flight** (`adjustPvpDateAsPerAvailableMaxDate()`): separate JDBC call, request-scoped in-memory cache only; does NOT persist across requests. Flag `adjustPvpDateByMaxDate` NOT wired in standard InsightsTransformer flow.
- **C. Dashboard-service direct**: MTF calendar, budget dates, market share — direct JDBC in dashboard-service.
- **D. `calender_dates` RDS table**: ETL-driven, Redis-fronted via `CachedDbObjectManagerImpl`. 45K rows, 987 clients, 172 cube sources. **Already stores exact data A/B/C query Databricks for.** (max-date-query-code-flow)
- **Optimization plan (`preResolvedMaxDate`)**: Add field to `CubeExecutionRequest`; dashboard-service populates from `calender_dates` Redis in `InsightsTransformer.resolvePreResolvedMaxDate()`; cubesdk uses literal date instead of subquery. Safety: only substitute when `cached_max <= to_date`; PVP queries excluded. Deploy cubesdk first (null default = safe), then dashboard-service. Est. ~$700-750/month savings. (max-date-cache-execution-plan)

### DSA Reporting Warehouse Cost Profile
- `dsa_reporting_wh` (`fcf485c1acd18e10`): **$13,946/month** post-migration (Mar 11, 2026). 93.9% of cost = DSA weighted score queries from `omni-api-service`.
- Weighted score query: `WITH sum AS (...), WeightedScores AS (...)` CTE — scans `dsa_scorecard_final_display` **twice** (aggregate + re-join to detail rows). 624K queries/month, 3.9% cache hit rate, 16.7 TB spill.
- **Window-function refactor status (unconfirmed)**: Replace self-join with `SUM(...) OVER (PARTITION BY client_id, measure, measure_display)` in `base_filtered` CTE. 23/27 measures match exactly; 4 differ at 10⁻¹³ precision only. BUT forensic profiling showed +20s wall clock on new plan due to new Sort node (`10339`) with 381 MB disk spill; old cache hit rate 46% vs new 20% confounds comparison — result inconclusive. Source SQL: `looker_aggregation_base_cte.sql`. (dsa-reporting-wh-deep-dive, omni-api-service_FORENSIC_REPORT.md)
- **Right-sizing: Do NOT downgrade to SMALL.** 4,046 queries (2.1%) have >4x parallelism; 7,677 queries (4%) already spill. **70.2% of cluster-minutes are wasted** due to scale-down lag — no config lever fixes this. (right-size-fcf485c1acd18e10)

### Heavy Cube Query Patterns (brands-service warehouse)
- 4 domains cost **$9,678/month**: iacos ($3,971), sov ($3,736), edm_product ($1,958), keyword_engagement ($13).
- **`edm_forecast_plan_combined` CTE**: appears across iacos + sov + edm_product, 7,957 task-min, $1,762/month total.
- **`count(*) OVER()` + `ROW_NUMBER()` combination**: 5.8x slower than `count(*) OVER()` alone. Forces full sort. Generated by cubesdk for dedup + pagination.
- **Share percentage self-join (SOV)**: Fix: `sum(metric) / SUM(SUM(metric)) OVER ()`. (heavy-cube-query-analysis)

### Lookup Query Caching (cubesdk)
- **`date_range_lookup`**: 242K queries/month, $1,073/month, **6.2% Databricks cache hit rate**. Fix: Redis key `max_date:{catalog}.{schema}.{table}:{column}` with 6h TTL. Change in cubesdk `BasicQueryGeneratorImpl`. (lookup-query-caching-analysis)
- **`omni_metric_name_lookup` LIKE pattern**: matched both simple lookups ($22/mo, 85.5% cached) AND analytical CTEs ($1,606/mo). Always verify actual query text before attributing cost to a pattern. (lookup-query-caching-analysis)

### ciq-configservice Dictionary Whitelisting Flow
- `ModuleTypeConfigServiceImpl.getDataSourceLevelDictionary()` applies layers in order: (1) DB query filter (retailer, module_type, data_source_id, is_deleted=false) → (2) product tag OR-match → (3) channel gating (Target RMS only) → (4) disabled visualization types → (5) `isDisabledForMetricsList` flag. Non-selective default: if metadata is null/empty → metric is whitelisted. (dictionary-whitelisting-flow-analysis)

### ciq-configservice Bulk Widget Creation Plan
- `WidgetChanges.createNewWidget` performs Redis + DB lookups **once per widget** (O(n)). Plan: `createNewWidgets(List<>)` bulk entry point → batch template fetch (`findAllByWidgetIdIn`) → static config staging (Redis `mget` + DB miss fill) → per-widget processor loop. Staging runs **outside** transaction; persistence stays in `PersonalizationTransactionalService`. (create-page-bulk-widget-caching-plan)
- **create-page hotspots**: (1) `WidgetDao.findByWidgetIdForCreate` called once per widget (~0.54s each) → batch with `findAllById`; (2) `parallelStream` + `@Transactional` spawns separate transactions (9 commits × 0.63s = 5.6s total) → switch to sequential or `@Transactional(propagation=MANDATORY)`; (3) `SQSHelper` re-fetches each widget for instrumentation → pass hydrated entities; (4) static config Redis misses per widget (~1.5s total) → request-scoped `StaticConfigCacheContext` (Caffeine or `ThreadLocal`). (dashboard-config-service_create-page-analysis.md)
- Caching tier order: L1 (Caffeine in-process) → L2 (Redis) → DB → async backfill both. Non-transactional `RedisTemplate` bean (`redisTemplateNonTx`) for cache writes. Feature toggle: `cache.l1.enabled`. Caffeine version: `2.9.3` (last Java 8 compatible). TTL is mandatory even with explicit invalidation. (learnings-from-riq-1325, dashboard-config-service_create-page-l1-cache-plan.md)

### DSA Pagination (omni-api-service / dashboard-service)
- DSA metrics route: `DataApiController` → `DsaTransformer` → `EntityDataExtractor` → `OMNI_API_DSA`. dashboard-service cannot enforce pagination itself for DSA — it delegates the full `EntityDataRequest` body.
- **Pagination bug root cause candidates**: (1) `CacheKeyUtil.getRequestHash()` strips `operations.page` before hashing → Redis returns stale page-1 data; (2) `OMNI_API_DSA` ignores `operations.page`; (3) operations map mutated before hashing. (data-api-pagination-rca)

### ciq-configservice Widget Index Strategy
- **Recommended indexes for `widget` table**: `idx_page_widget (page_id, widget_id)` + `idx_page_default (page_id, default_id)`. ~5-6 MB total, ~3-5% INSERT overhead (acceptable vs 200-500ms API time).
- `idx_page_default` is the ONLY option solving `findByPageIdAndDefaultId` efficiently (~5 rows vs 150k full scan). Only called for GBO pages — not regular create-page flow.
- `idx_page_widget` solves general page queries + covers `ORDER BY widget_id`. Existing `idx_crp (retailer, client_name, page_id, widget_id)` handles client-level fetches — no change needed.
- Including `is_delete` (boolean, 95% = false) in the index gives only ~5-10% improvement but adds 20-30% write overhead — not worth it. `NOT IN` on `widget_id` forces MySQL optimizer to use PRIMARY key range scan (75k rows) even when a better index exists — always verify with EXPLAIN. (dashboard-config-service_INDEX_ALTERNATIVES_ANALYSIS, dashboard-config-service_INDEX_USAGE_ANALYSIS.md)

### Redis Request Coalescing Lock Pattern
- Use Lua compare-and-delete (`if GET(key)==token then DEL`) — never use unconditional `DEL`; a stale leader will delete a successor's lock. Same pattern for heartbeat renewals (compare-and-renew).
- Duplicate Lua script strings across production class and integration test create drift risk — use package-private constants or a shared `CoalescingLuaScripts` type.
- Production `RedisTemplate` uses `JdkSerializationRedisSerializer`; integration tests using `StringRedisSerializer` prove script logic but not prod byte-exact encoding — optionally add one IT with JDK serializer. (omni-api-service_reviewer-feedback-v2.md)

### Databricks Warehouse Right-Sizing Guide
- **Parallelization Factor (PF) 10 ≈ 1 Databricks worker node**: PF < 80 → Medium (8 workers); PF 80–160 → Large; PF > 160 → X-Large. (omni-api-service_warehouse_f4c6da006757d77e_rightsizing.md)
- **max_clusters cap**: `max_clusters=40` on always-on warehouse = worst case 40 × 40 DBU/hr = 1,600 DBU/hr ($638/hr). Cap at 5–8 for Large. Saves $1K–3K/month with no functional impact.
- **X-Large → Large downsize**: $10K–12K/month savings, zero code change. Medium sizing blocked until high-PF queries are optimized first.
- **5.8% of queries can carry 56% of compute work**: Optimize the heaviest queries before downsizing cluster — wrong order causes P95 regression 1.3–2x. (omni-api-service_warehouse_f4c6da006757d77e_rightsizing.md)

### omni-edm-workflow Performance Patterns
- **Source schema module pattern**: Thread-safe singleton (keyed by `ModuleClass_clientId`) loads and caches shared DataFrames once before any aggregator runs; `teardown()` unpersists after all aggregators complete. 30–50% cost reduction. (omni-edm-workflow_performance-optimization-summary.md)
- **Validation is read-only — move it to parallel phase**: Running `entity.validate(df)` in serial write phase blocks throughput; run during parallel prep, pass `validate_df=False` to write call. 15–20% time reduction in serial phase. (omni-edm-workflow_performance-optimization-summary.md)

## Gotchas & Watch-outs

- **Window functions block filter pushdown**: If `client_id` is NOT in `PARTITION BY`, Databricks cannot push `WHERE client_id = X` below the window — forces full table scan. Fix: add tenant key to PARTITION BY. Verified: 128s → 16s, all spill eliminated. (journal-3p-filter)
- **Cluster size masks inefficiency**: Larger cluster (X_SMALL→LARGE) throws parallelism at a bad plan. Always fix the plan, not just resize. (journal-3p-filter)
- **brands-service `bundleCubeExecutionRequest`**: Map key is the bundle group identifier (e.g. `ams_campaigns_asin_workbench_v2`), NOT the cube name. (journal-3p-filter)
- **`filterEntities` in cube request**: `[0]` = filter column, `[1]` = source column, `[2]` = optional extra join column. Pre-populated by dashboard-service. (journal-3p-filter)
- **`commonFilterEnabled`**: Per-bundle flag overrides top-level flag. Cube JSON's `enableCommonFilter` can also be overridden by the request. (journal-3p-filter)
- **Taxonomy bug origin**: `isDedupEnabled || dimension.getSource().startsWith("dimension")` short-circuits to `true` for ALL dimensions when dedup is on. Bug introduced in UIPLATFORM-215; fix is catalog-aware `isFilterTableColumn()`. (journal-taxonomy-d, rca-invalid-query-taxonomy-dimensions)
- **Taxonomy+dedup bug only triggers when ALL THREE**: `taxonomyGroupBy.isEnabled=true` + `dedupBeforeRollup=true` + at least one groupBy dimension starts with "dimension". UI drill-down bypasses the taxonomy join — explains why UI works but download fails. (rca-invalid-query-taxonomy-dimensions)
- **Catalog-specific filter table schemas**: `CAMPAIGN_INTERNAL_CATALOGUE` → `campaign_filter_table` (has `campaign_name`, etc). `SKU_INTERNAL_CATALOGUE` → `catalog_filter_view` (only `dimension*`, `product_name`, `account_name`, `brand`). (journal-taxonomy-d)
- **Jira API v3 via Atlassian MCP**: Pass markdown directly as string for description — MCP handles markdown-to-ADF. Do NOT pass raw ADF objects. (journal-3p-filter)
- **Verify data assumptions with actual queries**: Don't state data facts without verifying against prod data. (journal-3p-filter)
- **Delta Lake merge-on-read amplification**: `dsa_competitor_staging_scorecard` reads 8.3B rows physically vs 268M logical (31x). Fix: `OPTIMIZE + VACUUM`. (DSA_spillover_query_profile_summary)
- **Self-join CTE pattern causes double full scan**: `WITH max_dates AS (SELECT MAX(...))` + join back = two independent scans. Fix: `MAX(...) OVER (PARTITION BY ...)`. (query_profile_analysis_new_2)
- **Runtime-computed predicates block partition pruning**: `scorecard_date = (subquery)` cannot be pushed into partition pruning — requires static/literal predicates. (DSA_spillover_query_profile_summary)
- **Databricks 1,000-query queue limit**: brands-service can saturate this under peak load with no connection pooling. (databricks-connection-pooling-impact-scalability-cost)
- **Large IN-list defeats partition pruning**: 300+ client_ids in single IN-list. Fix: batch or cache. (bi-offline-workload-wh-deep-dive)
- **DSA weighted score self-join double-scan**: CTE `sum` aggregates → CTE `WeightedScores` re-scans same table + JOINs. Always replace with `SUM(...) OVER (PARTITION BY ...)` window. (dsa-reporting-wh-deep-dive)
- **CONCAT/regexp_replace blocks Delta file-stat pushdown**: `CONCAT('dsa_m_', regexp_replace(lower(measure), '[^a-z0-9]', '_')) IN (...)` forces full partition scan. Fix: reverse-map `dsa_m_*` keys to raw measure names, emit `measure IN (...)` directly. (dsa-spill-reduction-investigation)
- **Z-ORDER not useful for `dsa_scorecard_final_display`**: Already partitioned by `(client_id, date, scorecard_type)` — non-partition filters are non-selective or computed expressions that can't use file stats. (dsa-spill-reduction-investigation)
- **Multi-client IN-list on DSA table**: 30 client_ids → scans 38M+ rows, 0.6 GB spill, 300s avg. Fix: split into per-client queries. (dsa-reporting-wh-deep-dive)
- **LIKE pattern cost attribution**: A single LIKE can match both cheap lookups and expensive analytical CTEs. Always inspect actual query text before attributing cost. (lookup-query-caching-analysis)
- **`count(*) OVER()` + `ROW_NUMBER()` combination**: 5.8x slower than `count(*) OVER()` alone in cubesdk. Forces full sort + full materialization before pagination. (heavy-cube-query-analysis)
- **DB query is fast (4–14ms); 250ms latency is network + Hibernate overhead**: EXPLAIN ANALYZE with PRIMARY key range scan at 4–14ms means DB is optimal. Network (~150ms) + JPA entity hydration (~100ms) is the bottleneck. Use native queries or DTO projections for hot paths. (explain-analyze-interpretation)
- **Redis `HashOperations` type**: `RedisTemplate<String, Object>` gives `HashOperations<String, Object, Object>` — second param is `Object` not `String`. Use `any()` not `anyString()` when mocking. (learnings-from-riq-1325)
- **`adjustPvpDateByMaxDate` NOT wired in standard flow**: `InsightsTransformer.setFlags()` does NOT set this flag; a test explicitly asserts it stays false. (max-date-query-code-flow)
- **Calendar refresh V2 missing `LOAD_TYPE=ETL_LOAD` header**: Causes ~1,700 queries/3-days to hit interactive BI warehouse instead of `rmm_etl_wh`. Fix: one-line change in `InsightsCalendarDataProviderAsync.refreshCalenderDataV2()` ~line 306. (max-date-query-code-flow)
- **Range-bounded MAX subquery**: Always check `isDateWithinRange(preResolvedMaxDate, from, to)` before substituting literal. PVP queries use `DATEADD(DAY, -1, MAX(...))` — exclude from literal substitution in first iteration. (max-date-cache-execution-plan)
- **Warehouse scale-down lag drives idle waste**: 70% of `fcf485c1acd18e10` cluster-minutes are wasted. Cause is multi-cluster scale-down cascade (6→5→4→1). No config lever fixes this; query optimization is the only path. (right-size-fcf485c1acd18e10)
- **Widget table fragmentation (144%)**: `widget` table has 6.9GB free > 4.8GB data. Even simple single-ID lookups take ~250ms baseline — primary bottleneck is network + Hibernate, not index efficiency. (widget-query-performance-analysis)
- **Negative caching for `getActivePlanKpi()`**: Cache `""` with 1h TTL for empty results; cache-read uses `cachedResponse != null` which correctly distinguishes cache miss (null) from cached empty (""). (progress, reviewer-feedback)
- **Empty `measuresList` in `setBundleCubeRequest`**: Caused by `dataGroup` mismatch — bundle request key must exactly match metric's `dataGroup` from config service (case-insensitive). Check at `InsightsTransformer.setBundleCubeRequest` lines 280-293. (ciq-dashboards_empty-measurelist-debug-analysis)
- **`is_preview_data_req` header**: Controls staging vs production data source selection. Affects `DataTableType` selection for DSA metrics; also propagated to brands-service and config-service headers. (ciq-dashboards_journal-data-api-role-programmer)
- **min-date `GET_MIN_DATE` full-scan risk**: `select coalesce(min(date_col), '9999-12-31') from <TABLE> where client_id=X` has no date range — scans all historical data. Each pod restart or cache flush triggers this for every active client×cube. (cubesdk_get-min-date-investigation)
- **`page_level_calendar` table has NO indexes**: Full table scan (type=ALL, 205 rows) on every `/page/widgets/v2/list` request. Fix: `CREATE INDEX idx_defaultpage_retailer ON page_level_calendar (default_page_id, retailer)`. (dashboard-config-service_API_FLOW_ANALYSIS_page_widgets_v2_list)
- **`product_retailer_page_mapping` has no composite index**: Queries on `(product, retailer, client_name, module_type, template_type)` do full 406k-row scan. Fix: `CREATE INDEX idx_product_retailer_module_template ON product_retailer_page_mapping (product, retailer, client_name, module_type, template_type)`. (dashboard-config-service_API_PERF_ANALYSIS_widget_templates)
- **`IN (SELECT ...)` subquery pattern defeats MySQL optimizer**: Rewrite to `INNER JOIN` to allow indexes on both tables. (dashboard-config-service_API_PERF_ANALYSIS_widget_templates)
- **JSON operations in SQL block indexing**: `JSON_VALID()`, `JSON_CONTAINS_PATH()`, `json_extract()` on TEXT columns cannot use indexes. Move JSON filtering to application layer (stream filter after query). (dashboard-config-service_API_PERF_ANALYSIS_widget_templates)
- **Low-selectivity boolean in composite index**: `is_delete` (95% = false) adds ~20-30% write overhead for only ~5-10% query speedup — not worth it. (dashboard-config-service_INDEX_ALTERNATIVES_ANALYSIS)
- **`NOT IN` forces wrong index in MySQL**: Optimizer picks PRIMARY key range scan for `widget_id NOT IN (...)` even when a better index exists — always verify with EXPLAIN when NOT IN is involved. (dashboard-config-service_INDEX_USAGE_ANALYSIS.md)
- **Redis caching masks index benchmarks**: With fixed `pageId`/`widgetId` in load tests, request 2+ are Redis cache hits — DB queries never execute. Always disable cache and randomize IDs when benchmarking index changes. (dashboard-config-service_PERFORMANCE_TEST_ANALYSIS.md)
- **`parallelStream` + `@Transactional` spawns separate transactions**: In `PageChanges.personalizeWidgetAndView`, 9 parallel commits × ~0.63s each (~5.6s total). Switch to sequential or `@Transactional(propagation=MANDATORY)` on `WidgetChanges`. (dashboard-config-service_create-page-analysis.md)
- **Databricks A/B query profile comparisons are confounded by cache state**: Cache hit rate changing 46%→20% between runs can make a faster query appear slower. Always note cache state when comparing profiles. (omni-api-service_FORENSIC_REPORT.md)
- **Redis lock safety (request coalescing)**: `redisTemplate.delete(lockKey)` without comparing leader token can delete a new leader's lock. Use Lua GET+conditional DEL. Unconditional heartbeat can also extend a new owner's TTL — compare-and-renew is the fix. (omni-api-service_reviewer-feedback.md, omni-api-service_reviewer-feedback-v2.md)
- **`@PreDestroy` heartbeat shutdown needs `awaitTermination`**: `shutdown()` alone doesn't wait for in-flight scheduled tasks; add short `awaitTermination` + `shutdownNow()` for deterministic cleanup. (omni-api-service_reviewer-feedback.md)
- **Follower timeout log uses config budget, not actual elapsed time**: Use `System.currentTimeMillis() - startMs` for accuracy; `startMs` is already tracked. (omni-api-service_reviewer-feedback.md)
- **OPTIMIZE without partition filter is catastrophically expensive**: Bare `OPTIMIZE <table>` on listing tables caused 4,590h waste/month; one run timed out burning 1,657h for nothing. Always scope with `WHERE date >= current_date - INTERVAL N DAYS`. (omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)
- **Non-dbt OPTIMIZE commands running outside pipeline = invisible waste**: Bare OPTIMIZE on `core_all_location_daily_sku_listing_status` consumed 2,628h (8% of total). Identify and route into dbt with retry + timeout config. (omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)
- **Failed + canceled queries = 13% of warehouse cost**: 4,343 compute-hours wasted ($2,600/month). Root causes: OPTIMIZE timeout, Delta concurrent modification, missing `statement_timeout_seconds`. (omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)
- **DSA Redis cache blast radius**: `*_dsa` key invalidated by `dsa-cache-warmup` Lambda after every EDM refresh, wiping ALL hash fields for the client. Not a bug, but blast radius could be narrowed to only clients with actual data changes. (omni-api-service_dsa-cache-deep-dive.md)
- **~44% of DSA cache misses are genuinely unique requests**: Cartesian product of date ranges × measure groups × filters — no caching strategy can eliminate these. Avoid over-investing in DSA cache tuning. (omni-api-service_dsa-cache-deep-dive.md)
- **Single dbt model can dominate warehouse cost**: `core_multi_location_daily_sku_listing_status_v3` = 33% of all compute (10,911h/month, 45 runs). Full-table refresh strategy drives 6 TB read per run — switch to incremental. (omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)

## Tool & Workflow Preferences

- **Databricks query profile analysis**: Check `SCAN_PARTITIONS` for partition columns, `FILTERS` for pushed predicates, spill metrics on Window/Sort nodes, `Reused Exchange` for shared scans. High scan row count vs logical rows → Delta Lake merge-on-read / deletion vectors. (journal-3p-filter)
- **Bitbucket code search**: Use MCP server `user-bitbucket4` (not `user-bitbucket-cloud`). Workspace = `commerceiq`. Tool = `search_code` with `query` + `workspace` (no repoSlug — code search is workspace-level only). `user-bitbucket-cloud` returns 404 for `search_code`. (AGENT.md, journal-ciq-etl-ingestion-role-programmer)
- **Finding table/workflow consumers**: Run `search_code` with table name, qualified name, and workflow name. Check athena_alertmodulusconfig for alert SQL configs. (journal-ciq-etl-ingestion-role-programmer)
- **Bitbucket `search_repositories`**: Filter `q` param requires **spaces around operators**: `name ~ "value"` (not `name~"value"`). Missing spaces → 400. (search-repositories-fix-analysis)
- **Bitbucket `merge_pull_request`**: Request body key must be `merge_strategy`, not `type`. (bitbucket-mcp-tools-final-status)
- **dbx-dev queries prod system tables**: `system.compute.warehouses`, `system.query.history`, and `system.billing.usage` are synced from prod into dbx-dev. Use dbx-dev MCP to query prod warehouse metadata and costs without prod access. (databricks-warehouse-cost-optimization-analysis)
- **Cost attribution query**: `system.billing.usage` — group by `usage_metadata.warehouse_id`, filter `record_type = 'ORIGINAL'`. Include failed/canceled queries separately — they represent real DBU spend. (databricks-warehouse-cost-optimization-analysis, omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)

## Project-Specific Notes

### athena_aramus-workflow / Alert Pipeline

- **CommonWorkflowProperties.java**: Maps workflow → repo (`WORKFLOW_REPO_BRANCH_MAP`), variables (`WORKFLOW_VARIABLE_LIST_MAP`), project (`WORKFLOW_PROJECT_MAP`). Central registry for all CCP workflows.
- **Trigger path**: `AlertEstimateE2eTrigger.runJob()` → queries `aramus.alert_estimate_workflow_metadata` JOIN `aramus.alert_type_alert_name_mapping` (filter: `estimate_workflow_trigger=true`) → `CCPUtils.getCCPEntity()` → Databricks workflow trigger. Branch: `master` (prod), `release` (qa), `develop` (others).
- **AlertGenerator**: Loads SQL from `alert_generation_config` → queries Databricks table → transforms → pushes to S3, SQS → Elasticsearch bulk index. **Not a real-time push** — batch process after ETL.
- **Execution tracking**: `aramus.client_modulus_run_details` logs client_details_id, start_time, end_time, trigger_params, modulus_workflow, status.
- **Elasticsearch clusters**: beta = `vpc-brandalerts-beta-*`, qa = `vpc-brandalerts-qa-*`, prod = `vpc-brandalerts-sales-prod-*`, index = `alertsystem/alert`. (custom_pa_workspace_alert_sales_decrease_wf-end-to-end-analysis)

### athena_brands-modulus-service (cubesdk / brands-service)

- **Key code location — common filter selection**: `BasicQueryGeneratorImpl.getCommonFilterQuery()` line 472-474; constants in `Constants.java` (`AMAZON_3P_COMMON_FILTER_CUBE_VIEW` vs `COMMON_FILTER_CUBE_VIEW`). (journal-3p-filter)
- **cubesdk version scheme**: `1.0.1.87.X-TIQ-RELEASE` — patch increment on each change. (journal-taxonomy-d)
- **Taxonomy groupBy trigger**: Taxonomy join only fires when `taxonomyGroupBy.isEnabled=true` AND at least one groupBy dimension starts with "dimension" (`checkIfGroupedByTaxonomyDimensions()`). (journal-taxonomy-d)
- **seller_cubes.common_filter_view structure**: 4 CTEs — `common_filter_fact_table` (a), `client_internal_catalog` (b), `brands_common_filter_fact_table` (c), `campaigns_asin_workbench` (d). Final SELECT: `a LEFT JOIN b LEFT JOIN c LEFT JOIN d` on `(asin, client_id)`. (journal-3p-filter)
- **Prod warehouses** (all SERVERLESS): default `de174e171ce90e15` (LARGE, 2–5 clusters, 10 min stop), RMM ETL `d9369c57eb514078` (X_SMALL, 1–10 clusters, 1 min stop), Ally Insights `516bae2db745259c` (MEDIUM, 1–2 clusters, 5 min stop), heavy `ccd1b022cc7564af` (LARGE, unused). (databricks-warehouse-cost-optimization-analysis)
- **DSA offline warehouse** `bi_offline_workload_wh` (`0e9defc6e2ac907e`): MEDIUM serverless, DSA batch refresh, ~$485/month, idle 98.3%. UAT companion `b27cdee285fddf7b` (~$290/month). (bi-offline-workload-wh-deep-dive)
- **DSA migration (Mar 11, 2026)**: Heavy DSA refresh queries moved from `de174e171ce90e15` to `bi_offline_workload_wh` + `bi_offline_workload_wh_uat`. Only `mg_weights_check` (~$150/month) remains on main warehouse. (dsa-scorecard-cost-deep-dive)
- **Dormant warehouse `2a7ec31458add6fc`**: Only 9 active days in 365 days, 763 DBUs, last activity Feb 25 2026. Recommend decommission or consolidate. (right-size-2a7ec31458add6fc)
- **BIPLATFORM-628 filter-dimensions cache** (PR approved): Cache key = `all_dimensions_for_filter_{clientId}_{filterName}`; invalidation prefix `all_dimensions_for_filter_{clientId}_*` cleared in `refreshFilterCache()`. (reviewer-feedback)
- **Integration tests for taxonomy/dedup**: Use `cubesdk-integration-tests-new` (Spark-based, real CSV data), NOT brands-service mock unit tests — `TaxonomyDedupQueryGenerationTest` is placeholder only. (taxonomy-dedup-integration-test-location-analysis)
- **BIPLATFORM-649 completed**: cubesdk → `1.0.1.87.16-TIQ-RELEASE`, brands-api/brands-commons → `1.0.1.89.12-DBX-RELEASE`, brands-service → `1.0.2.87`. Branch: `BIPLATFORM-649-cubesdk-version-upgrade`. (progress)
- **`edm_forecast_plan_combined` CTE cost**: $1,762/month across iacos + sov + edm_product. Source: cube queries joining `client_catalog.omni.product_metrics_performance_plan_forecast`. (heavy-cube-query-analysis)
- **`date_range_lookup` caching opportunity**: 242K queries/month, $1,073/month, 6.2% Databricks cache hit. Redis key `max_date:{catalog}.{schema}.{table}:{column}`, 6h TTL. Change: cubesdk `BasicQueryGeneratorImpl`. (lookup-query-caching-analysis)
- **`preResolvedMaxDate` optimization** (planned): Field on `CubeExecutionRequest`. Population in `InsightsTransformer.resolvePreResolvedMaxDate()` from `CachedDbObjectManagerImpl.getCalenderDateRange()`. Consumption in `BasicQueryGeneratorImpl.getWhereClause()`. Est. ~$700-750/month savings. (max-date-cache-execution-plan)

### omni-api-service (DSA)

- All DSA queries route to `dsa_reporting_wh` (`fcf485c1acd18e10`). Post-migration cost: ~$13,946/month.
- **Weighted score entry point**: `DSAController.getDSAMetricsData()` → `DataServiceImpl` → `QueryGetterFactory.getQueryGetter({uiComponent}_{dataSourceId}_query_getter)` → `QueryGeneratorScorecard`/`QueryGeneratorGlobal` → `looker_aggregation_base_cte.sql`.
- **Multi-client queries**: `DsaClientMapping.getLinkedDsaClientIds()` — copilot accounts produce 30-client IN-lists → scans 38M+ rows, 0.6 GB spill, 300s avg. Break into per-client queries.
- **DSA spill table**: `client_catalog.edm_derived.dsa_scorecard_final_display`, 524 GB, 158K files, 7.8B rows, partitioned by `(client_id, date, scorecard_type)`. (dsa-spill-reduction-investigation, dsa-reporting-wh-deep-dive)
- **Optimization priority**: S1 = window function refactor in `looker_aggregation_base_cte.sql` (structurally sound, prod A/B confounded by cache — needs clean re-test) → S2 = per-client query splitting for large clients → S3 = application-level Redis cache (TTL 6–12h). (dsa-reporting-wh-deep-dive)
- **dbt pipeline warehouse** `f15f1d4fa5e32ffc`: INSERT/REPLACE/MERGE/OPTIMIZE via `PyDatabricksSqlConnector`. Dominated by `core_multi_location_daily_sku_listing_status_v3` (33% compute, full-table refresh). (omni-api-service_warehouse_f15f1d4fa5e32ffc_analysis.md)
- **Request coalescing**: Lua compare-and-delete for lock ownership; heartbeat via compare-and-renew. Duplicate Lua strings across class + test = drift risk — use shared constants. (omni-api-service_reviewer-feedback-v2.md)

### dsa-scorecards-orchestrator (Node.js DSA service)

- **Warehouse**: `f4c6da006757d77e` (X-Large, $28K/month). **Right-size to Large**: saves $10K–12K/month immediately; only 5.8% of queries need X-Large parallelism (PF > 160). Cap `max_clusters` at 5–8. (omni-api-service_warehouse_f4c6da006757d77e_rightsizing.md)
- **Health-check query (`addition.sql`)** runs every ~54s → 50K queries/month of trivial overhead. Increase health-check interval to 5–10 min. (dsa-scorecards-orchestrator_warehouse_cost_spike_analysis.plan.md)
- **`retailersWithBadGathers.sql`** = 26% of compute (avg 122s). Candidate for materialized view or application-level caching. (dsa-scorecards-orchestrator_warehouse_cost_spike_analysis.plan.md)
- **`clientTaxonomy` / `core_client_products DISTINCT`**: 33K+ queries/month — slowly-changing reference data, ideal for Redis cache with 15–30 min TTL. (dsa-scorecards-orchestrator_warehouse_cost_spike_analysis.plan.md)

### ciq-configservice (dashboard-config-service)

- **Dictionary whitelisting**: `ModuleTypeConfigServiceImpl.getDataSourceLevelDictionary()`. Multi-layer: DB query → product tag OR-match → channel gating (Target RMS only via `isTargetIqEnabledForClient()`) → disabled visualizations → `isDisabledForMetricsList`. Default is allow. (dictionary-whitelisting-flow-analysis)
- **Non-transactional Redis template**: Use separate `redisTemplateNonTx` bean (`setEnableTransactionSupport(false)`) for cache write operations to avoid blocking transaction commits. (learnings-from-riq-1325)
- **L1 cache (Caffeine)**: `LocalCacheRegistry` holds in-process caches. Lookup order: L1 → Redis → DB → async backfill both. Feature toggle: `cache.l1.enabled`. TTL defaults: 30min widget-lists, 6h templates and static configs. (learnings-from-riq-1325)
- **ConfigType enum**: `getConfigType()` returns lowercase strings ("widget", "page"), not uppercase. Use lowercase in matchers. (learnings-from-riq-1325)
- **Maven `.m2` hygiene**: Never create `.m2` in project directory. Add `/.m2/` to `.gitignore`. Always use default `$HOME/.m2`. (learnings-from-riq-1325)
- **PR structure**: Problem Statement → Root Causes → Summary of Changes → Notable Classes → Future Changes. Review full commit history, not just latest commit. (learnings-from-riq-1325)
- **BIPLATFORM-624 completed**: Negative caching fix for `getActivePlanKpi()` in both ciq-configservice (PR #1055) and ciq-dashboards (PR #2405). Cache `""` with 1h TTL for empty results. (progress)
- **`/page/widgets/v2/list` DB tables**: `page_level_calendar` has NO indexes — full scan on every request. Fix: `CREATE INDEX idx_defaultpage_retailer ON page_level_calendar (default_page_id, retailer)`. (dashboard-config-service_API_FLOW_ANALYSIS_page_widgets_v2_list)
- **`/widget/templates` performance issues**: Fix sequence: (1) index on `product_retailer_page_mapping`, (2) rewrite IN-subquery to JOIN, (3) move JSON filtering to application layer. (dashboard-config-service_API_PERF_ANALYSIS_widget_templates)

### ciq-dashboards (dashboard-service)

- **`calender_dates` table**: MySQL RDS, 45K rows, 987 clients, 172 cube sources. Redis-fronted via `CachedDbObjectManagerImpl.getCalenderDateRange()`. Daily ETL refresh via `/calender/refresh/v2`. Key: `"calendar_date_range:{client}:{retailer}"`, hashKey: SHA(sourceList). (max-date-query-code-flow)
- **`metric_registar` table**: Source of truth for metric → cube mapping. `source` column JSON `{"cubeName": "...", "sourceKey": "..."}`. All metrics in same data group must share a cube. (data-api-flow-analysis)
- **`product_registry` table**: Maps `registry_id` → `productName` → `dataExctractorDetails` (actual API endpoint URL). Queried via `ConfigServiceApiCaller.callProductRegistryApi()`. (ciq-dashboards_journal-data-api-role-programmer)
- **DSA pagination RCA** (open): Widget 3129206, DSA metrics (registry_id=23). Page 2 returns same as page 1. Investigate `CacheKeyUtil.getRequestHash` including `operations.page`. (data-api-pagination-rca)
- **BIPLATFORM-604 completed**: DSA scorecard queries in dashboard-service routed to offline BI warehouse via `DsaDatabricksExecutorServiceImpl.getDatabricksOfflineWarehouseId()`. Warehouse IDs: beta=`7307da088f474494`, qa=`8b9e3f200384d10a`, uat=`b27cdee285fddf7b`, prod=`0e9defc6e2ac907e`. (ciq-dashboards_progress)

### omni-edm-workflow (PySpark ETL)

- **Source schema module pattern**: Thread-safe singleton (keyed by `ModuleClass_clientId`) loads and caches shared DataFrames once before any aggregator runs; `teardown()` unpersists after all. 30–50% cost reduction from eliminating redundant table scans. (omni-edm-workflow_performance-optimization-summary.md)
- **PySpark pattern**: `ThreadPoolExecutor` for parallel prep → serial Delta writes → exponential backoff for `ConcurrentAppendException` (`max_retries=8`, `wait = initial_backoff_sec * 2^(attempt-1)`). Validation in parallel phase, not serial write phase. (omni-edm-workflow_performance-optimization-summary.md)

## Superseded

- **Active branches (as of 2026-02)**: `bi-520` on both cubesdk and brands-service for taxonomy dedup fix. → Superseded by `BIPLATFORM-649-cubesdk-version-upgrade` branch (2026-04). (journal-taxonomy-d → progress)
- **DSA cost on `de174e171ce90e15`**: Original estimate $2,000–4,000/month savings from DSA optimization on main warehouse. → After Mar 11 migration, only `mg_weights_check` remains (~$150/month). Real DSA cost is now on `dsa_reporting_wh`. (dsa-scorecard-cost-deep-dive)
- **DSA scorecard queries in dashboard-service routing to `dsa_reporting_wh`**: → After BIPLATFORM-604, dashboard-service DSA scorecard queries now route to `bi_offline_workload_wh` (`0e9defc6e2ac907e` prod). `dsa_reporting_wh` cost is now driven by `omni-api-service` only. (ciq-dashboards_progress)
- **DSA window-function fix "validated on prod" (67% est. time reduction)**: → Forensic profiling showed +20s wall clock regression on NEW plan due to new Sort node (`10339`, 381 MB disk spill). However, cache hit rate dropped 46%→20% between OLD and NEW runs, confounding comparison. Structural improvement (eliminates double scan + broadcast hash join) is theoretically sound but prod validation is **inconclusive** — needs clean re-test with matched cache state. (omni-api-service_FORENSIC_REPORT.md)
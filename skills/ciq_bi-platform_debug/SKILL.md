---
name: ciq_bi-platform_debug
description: Access of prod apis, access of databricks data while debugging BI platform projects `brands-service`, `cubesdk`, `dashboard-service` etc. 
---
# CIQ BI Platform debug skill

## When to Use

Use this skill when debuging or exploring ciq BI platform related flows like working with projects `brands-service`, `cubesdk`, `dashboard-service` etc. 

## Accessing the Prod apis

- `dashboard-service` api in prod can be hit using curl through terminal , following is a sample of a reporting v1 call . The reponse contains a header called `Response_token` that value can be used to search logs through groundcover mcp server to fetch logs . Calls to `brands-service` are logged . Adjust request path and payload as per the flow under investigation.

```sh

  curl --location 'http://dashboard-service.prod-dbx.commerceiq.ai/entity/metrics/data' \
--header 'client: medline' \
--header 'client_id: 1007' \
--header 'content-type: application/json' \
--header 'instance_name: medline' \
--header 'location: us' \
--header 'products: SalesIQ,MarketingIQ' \
--header 'program: retail' \
--header 'retailer: amazon_3p' \
--header 'username: suman.y@commerceiq.ai' \
--data '{
      "page": "MonthlyBusinessReport3p_344105",
      "where":
      {
          "date":
          {
              "to": "2025-09-27",
              "from": "2025-07-01"
          },
          "pvpDate":
          {
              "to": "2025-06-30",
              "from": "2025-06-01"
          },
          "dimensionNameValueList":
          []
      },
      "widget": "breakdown2_1731389",
      "entityType": "asin",
      "eventsList":
      [],
      "operations":
      {
          "page": 1,
          "limit": 10,
          "system": "reporting_344105_MonthlyBusinessReport3p_344105",
          "orderByList":
          [
              {
                  "dimension": "ams_asin_paid_sales_14d",
                  "direction": "DESC"
              }
          ],
          "bundleRequestJoinType": "FULL_OUTER_JOIN",
          "isChainingJoinEnabled": true
      },
      "entityValue": null,
      "metricsList":
      [],
      "enablePaginationCount": true,
      "bundleDataGroupsRequest":
      {
          "ams_campaigns_asin_workbench_v2":
          {
              "page": "MonthlyBusinessReport3p_344105",
              "where":
              {
                  "date":
                  {
                      "to": "2025-09-27",
                      "from": "2025-07-01"
                  },
                  "pvpDate":
                  {
                      "to": "2025-06-30",
                      "from": "2025-06-01"
                  },
                  "dimensionNameValueList":
                  [
                      {
                          "dimensionName": "dimension1",
                          "esDataSetName": "common_filter",
                          "dimensionValue": "caring blue nitrile exam gloves"
                      }
                  ]
              },
              "widget": "breakdown2_1731389",
              "entityType": "asin",
              "eventsList":
              [],
              "operations":
              {
                  "pvpenabled": true,
                  "showByEntities":
                  [
                      "asin"
                  ],
                  "flowResidueEntity": true,
                  "timeseriesEnabled": false,
                  "daterangeDimension": "feed_date",
                  "timeseriesRollupBy": "DAY",
                  "commonFilterEnabled": true,
                  "timeseriesDimension": "feed_date",
                  "pvptimeseriesEnabled": false,
                  "isChainingJoinEnabled": true,
                  "adjustPvpDateByMaxDate": true,
                  "timeseriesWeekStartDay": "SUNDAY",
                  "enableDedupBeforeRollup": true,
                  "samePeriodLastYearTimeseriesEnabled": false,
                  "additionalDedupAxesApartFromSelectedMeasuresAndGroupByDimensions":
                  [
                      "asin",
                      "feed_date"
                  ]
              },
              "entityValue": null,
              "metricsList":
              [
                  "ams_asin_roi",
                  "ams_asin_spend",
                  "ams_asin_conversions_14d",
                  "ams_asin_cpc",
                  "ams_asin_clicks",
                  "ams_asin_paid_sales_14d"
              ]
          },
          "sku_3p_all_details":
          {
              "page": "MonthlyBusinessReport3p_344105",
              "where":
              {
                  "date":
                  {
                      "to": "2025-09-27",
                      "from": "2025-07-01"
                  },
                  "pvpDate":
                  {
                      "to": "2025-06-30",
                      "from": "2025-06-01"
                  },
                  "dimensionNameValueList":
                  [
                      {
                          "dimensionName": "dimension1",
                          "esDataSetName": "common_filter",
                          "dimensionValue": "caring blue nitrile exam gloves"
                      }
                  ]
              },
              "widget": "breakdown2_1731389",
              "entityType": "asin",
              "eventsList":
              [],
              "operations":
              {
                  "pvpenabled": true,
                  "showByEntities":
                  [
                      "asin"
                  ],
                  "flowResidueEntity": true,
                  "timeseriesEnabled": false,
                  "daterangeDimension": "feed_date",
                  "timeseriesRollupBy": "DAY",
                  "commonFilterEnabled": true,
                  "timeseriesDimension": "feed_date",
                  "pvptimeseriesEnabled": false,
                  "isChainingJoinEnabled": true,
                  "adjustPvpDateByMaxDate": true,
                  "timeseriesWeekStartDay": "SUNDAY",
                  "enableDedupBeforeRollup": true,
                  "samePeriodLastYearTimeseriesEnabled": false,
                  "additionalDedupAxesApartFromSelectedMeasuresAndGroupByDimensions":
                  [
                      "asin",
                      "feed_date"
                  ]
              },
              "entityValue": null,
              "metricsList":
              [
                  "sku_3p_all__ordered_product_sales_reporting"
              ]
          }
      }
  }
'

```

-  Adjust the header values for `client`, `client_id`, `retailer` . `username` header should always be `suman.y@commerceiq.ai`.
- Similar to above `brands-service` can also be called from local , following is an example.

```sh

curl --location 'http://brands-service.prod-dbx.commerceiq.ai/cube/execute' \
--header 'client: medline' \
--header 'client_id: 1007' \
--header 'content-type: application/json' \
--header 'instance_name: medline' \
--header 'location: us' \
--header 'products: SalesIQ,MarketingIQ' \
--header 'program: retail' \
--header 'retailer: amazon_3p' \
--header 'username: suman.y@commerceiq.ai' \
--header 'is_preview_data_req: false' \
--data '{
        "cubeName": "ams_campaigns_asin_workbench",
        "measuresList":
        [],
        "groupByDimensionsList":
        [],
        "where":
        {
            "date":
            {
                "from": "2025-07-01",
                "to": "2025-09-27"
            },
            "pvpDate":
            {
                "from": "2025-06-01",
                "to": "2025-06-30"
            },
            "time": null,
            "pvpTime": null,
            "dimensionNameValueList":
            [],
            "excludeDimensionsFromSharePercentage": null,
            "tableLevelDimensionNameValueList": null
        },
        "orderByList":
        [
            {
                "dimension": "ams_asin_paid_sales_14d",
                "direction": "DESC"
            }
        ],
        "limit": 10,
        "page": 1,
        "getLatestAvailableInsteadOfRollup": false,
        "getSharePercentage": false,
        "disableShard": false,
        "getPointInTimeMetrics": false,
        "getPointInTimeMetricsInRange": false,
        "commonFilterEnabled": false,
        "isOmniFiltersEnabled": false,
        "isUnifiedFiltersEnabled": false,
        "commonFilterWithoutDedupEnabled": false,
        "timeseriesOuterWhereClauseEnabled": false,
        "useCampaignTaxnonmyGroupBy": false,
        "useUnifiedCampaignTaxonomyGroupBy": false,
        "customAPIDecisionVars":
        {
            "enableShareOfVoice": false,
            "skipLimitAndOffset": false,
            "additionalWhereClause": false,
            "enableForecastSkuLevelWidget": false,
            "enableFetchFromShards": false,
            "skipExternalCount": false,
            "skipTimeSeriesMetric": false,
            "enableDigitalShelf": false,
            "totalCompBrandsForDigitalShelf": 0,
            "totalOthersBrandsForDigitalShelf": 0,
            "totalClientBrandsForDigitalShelf": 0,
            "anchoredBrand": null,
            "preQueriesMap":
            {},
            "ignoreMeasuresWhileDeduping":
            {},
            "type": null,
            "downloadRequest": null,
            "skipTimeSeriesOrderByClause": false,
            "contentScorecardRequest": null,
            "queryReplacementRequest": null,
            "system": "reporting_344105_MonthlyBusinessReport3p_344105",
            "enableChartsSku": false,
            "timeSeriesDimensionAggregateRequest": null,
            "jspEnabled": false,
            "sovDataGroup": false,
            "multiJoinEntityList": null,
            "enablePvpParallelExecution": false,
            "distributeList": null,
            "dimensionsCustomRequest": null,
            "isV2DataApiRequest": false,
            "enableSkuSetSelection": false,
            "skuSetSelectionType": null,
            "skuLevelSov": false,
            "crossPeriodUdfSource": false,
            "chainingJoinEnabled": true,
            "timeSeriesDimensionEnabled": false
        },
        "enableNewPVPFormulaForSOV": false,
        "flowResidueEntity": false,
        "chartsOrderByClauseEnabled": false,
        "bundleCubeExecutionRequest":
        {
            "ams_campaigns_asin_workbench_v2":
            {
                "cubeName": "ams_campaigns_asin_workbench",
                "measuresList":
                [
                    "ams_asin_paid_sales_14d",
                    "ams_asin_clicks",
                    "ams_asin_cpc",
                    "ams_asin_conversions_14d",
                    "ams_asin_spend",
                    "ams_asin_roi"
                ],
                "groupByDimensionsList":
                [
                    "asin"
                ],
                "timeseriesDimension": "feed_date",
                "daterangeDimension": "feed_date",
                "where":
                {
                    "date":
                    {
                        "from": "2025-07-01",
                        "to": "2025-09-27"
                    },
                    "pvpDate":
                    {
                        "from": "2025-06-01",
                        "to": "2025-06-30"
                    },
                    "time": null,
                    "pvpTime": null,
                    "dimensionNameValueList":
                    [],
                    "excludeDimensionsFromSharePercentage": null,
                    "tableLevelDimensionNameValueList": null
                },
                "timeseriesRollupBy": "DAY",
                "timeseriesWeekStartDay": "SUNDAY",
                "getLatestAvailableInsteadOfRollup": false,
                "getSharePercentage": false,
                "disableShard": false,
                "getPointInTimeMetrics": false,
                "getPointInTimeMetricsInRange": false,
                "dedupBeforeRollup":
                {
                    "enableDedupBeforeRollup": true,
                    "additionalDedupAxesApartFromSelectedMeasuresAndGroupByDimensions":
                    [
                        "asin",
                        "feed_date"
                    ],
                    "excludeDedupAxes":
                    [],
                    "disableDistinctInRollup": false
                },
                "commonFilterEnabled": true,
                "commonFilterWithoutDedupEnabled": false,
                "timeseriesOuterWhereClauseEnabled": false,
                "useCampaignTaxnonmyGroupBy": false,
                "useUnifiedCampaignTaxonomyGroupBy": false,
                "filterWhereClause":
                {
                    "date": null,
                    "pvpDate": null,
                    "time": null,
                    "pvpTime": null,
                    "dimensionNameValueList":
                    [
                        {
                            "dimensionName": "dimension1",
                            "dimensionValue": "caring blue nitrile exam gloves",
                            "operator": "EQUAL_TO",
                            "dimensionTable": null,
                            "inCubeFilter": false,
                            "esDataSetName": "common_filter"
                        }
                    ],
                    "excludeDimensionsFromSharePercentage": null,
                    "tableLevelDimensionNameValueList": null
                },
                "filterEntities":
                [
                    "asin",
                    "asin",
                    "campaign_id"
                ],
                "showByEntities":
                [
                    "asin"
                ],
                "customAPIDecisionVars":
                {
                    "enableShareOfVoice": false,
                    "skipLimitAndOffset": false,
                    "additionalWhereClause": false,
                    "enableForecastSkuLevelWidget": false,
                    "enableFetchFromShards": false,
                    "skipExternalCount": false,
                    "skipTimeSeriesMetric": false,
                    "enableDigitalShelf": false,
                    "totalCompBrandsForDigitalShelf": 0,
                    "totalOthersBrandsForDigitalShelf": 0,
                    "totalClientBrandsForDigitalShelf": 0,
                    "anchoredBrand": null,
                    "preQueriesMap":
                    {},
                    "ignoreMeasuresWhileDeduping":
                    {},
                    "type": null,
                    "downloadRequest": null,
                    "skipTimeSeriesOrderByClause": false,
                    "contentScorecardRequest": null,
                    "queryReplacementRequest": null,
                    "system": null,
                    "enableChartsSku": false,
                    "timeSeriesDimensionAggregateRequest": null,
                    "jspEnabled": false,
                    "sovDataGroup": false,
                    "multiJoinEntityList": null,
                    "enablePvpParallelExecution": false,
                    "distributeList": null,
                    "dimensionsCustomRequest": null,
                    "isV2DataApiRequest": false,
                    "enableSkuSetSelection": false,
                    "skuSetSelectionType": null,
                    "skuLevelSov": false,
                    "crossPeriodUdfSource": false,
                    "chainingJoinEnabled": true,
                    "timeSeriesDimensionEnabled": false
                },
                "enableNewPVPFormulaForSOV": false,
                "flowResidueEntity": true,
                "chartsOrderByClauseEnabled": false,
                "adjustPvpDateByMaxDate": false,
                "entityType": "asin",
                "pvptimeSeriesEnabled": false,
                "sharePercentageV2": false,
                "pointInTimeMetrics": false,
                "timeseriesEnabled": false,
                "yoyenabled": false,
                "pvpenabled": true,
                "pvptimeseriesEnabled": false,
                "splyenabled": false,
                "isFilterFromCubeOnly": false
            },
            "sku_3p_all_details":
            {
                "cubeName": "3p_sku_data",
                "measuresList":
                [
                    "sku_3p_all__ordered_product_sales"
                ],
                "groupByDimensionsList":
                [
                    "asin"
                ],
                "timeseriesDimension": "feed_date",
                "daterangeDimension": "feed_date",
                "where":
                {
                    "date":
                    {
                        "from": "2025-07-01",
                        "to": "2025-09-27"
                    },
                    "pvpDate":
                    {
                        "from": "2025-06-01",
                        "to": "2025-06-30"
                    },
                    "time": null,
                    "pvpTime": null,
                    "dimensionNameValueList":
                    [],
                    "excludeDimensionsFromSharePercentage": null,
                    "tableLevelDimensionNameValueList": null
                },
                "timeseriesRollupBy": "DAY",
                "timeseriesWeekStartDay": "SUNDAY",
                "getLatestAvailableInsteadOfRollup": false,
                "getSharePercentage": false,
                "disableShard": false,
                "getPointInTimeMetrics": false,
                "getPointInTimeMetricsInRange": false,
                "dedupBeforeRollup":
                {
                    "enableDedupBeforeRollup": true,
                    "additionalDedupAxesApartFromSelectedMeasuresAndGroupByDimensions":
                    [
                        "asin",
                        "feed_date"
                    ],
                    "excludeDedupAxes":
                    [],
                    "disableDistinctInRollup": false
                },
                "commonFilterEnabled": true,
                "commonFilterWithoutDedupEnabled": false,
                "timeseriesOuterWhereClauseEnabled": false,
                "useCampaignTaxnonmyGroupBy": false,
                "useUnifiedCampaignTaxonomyGroupBy": false,
                "filterWhereClause":
                {
                    "date": null,
                    "pvpDate": null,
                    "time": null,
                    "pvpTime": null,
                    "dimensionNameValueList":
                    [
                        {
                            "dimensionName": "dimension1",
                            "dimensionValue": "caring blue nitrile exam gloves",
                            "operator": "EQUAL_TO",
                            "dimensionTable": null,
                            "inCubeFilter": false,
                            "esDataSetName": "common_filter"
                        }
                    ],
                    "excludeDimensionsFromSharePercentage": null,
                    "tableLevelDimensionNameValueList": null
                },
                "filterEntities":
                [
                    "asin",
                    "asin"
                ],
                "showByEntities":
                [
                    "asin"
                ],
                "customAPIDecisionVars":
                {
                    "enableShareOfVoice": false,
                    "skipLimitAndOffset": false,
                    "additionalWhereClause": false,
                    "enableForecastSkuLevelWidget": false,
                    "enableFetchFromShards": false,
                    "skipExternalCount": false,
                    "skipTimeSeriesMetric": false,
                    "enableDigitalShelf": false,
                    "totalCompBrandsForDigitalShelf": 0,
                    "totalOthersBrandsForDigitalShelf": 0,
                    "totalClientBrandsForDigitalShelf": 0,
                    "anchoredBrand": null,
                    "preQueriesMap":
                    {},
                    "ignoreMeasuresWhileDeduping":
                    {},
                    "type": null,
                    "downloadRequest": null,
                    "skipTimeSeriesOrderByClause": false,
                    "contentScorecardRequest": null,
                    "queryReplacementRequest": null,
                    "system": null,
                    "enableChartsSku": false,
                    "timeSeriesDimensionAggregateRequest": null,
                    "jspEnabled": false,
                    "sovDataGroup": false,
                    "multiJoinEntityList": null,
                    "enablePvpParallelExecution": false,
                    "distributeList": null,
                    "dimensionsCustomRequest": null,
                    "isV2DataApiRequest": false,
                    "enableSkuSetSelection": false,
                    "skuSetSelectionType": null,
                    "skuLevelSov": false,
                    "crossPeriodUdfSource": false,
                    "chainingJoinEnabled": true,
                    "timeSeriesDimensionEnabled": false
                },
                "enableNewPVPFormulaForSOV": false,
                "flowResidueEntity": true,
                "chartsOrderByClauseEnabled": false,
                "adjustPvpDateByMaxDate": false,
                "entityType": "asin",
                "pvptimeSeriesEnabled": false,
                "sharePercentageV2": false,
                "pointInTimeMetrics": false,
                "timeseriesEnabled": false,
                "yoyenabled": false,
                "pvpenabled": true,
                "pvptimeseriesEnabled": false,
                "splyenabled": false,
                "isFilterFromCubeOnly": false
            }
        },
        "bundleRequestJoinType": "FULL_OUTER_JOIN",
        "adjustPvpDateByMaxDate": false,
        "multiCountryEnabled": false,
        "entityType": "asin",
        "pvptimeSeriesEnabled": false,
        "multiCountryEanbled": false,
        "sharePercentageV2": false,
        "pointInTimeMetrics": false,
        "unifiedFiltersEnabled": false,
        "omniFiltersEnabled": false,
        "timeseriesEnabled": false,
        "yoyenabled": false,
        "pvpenabled": false,
        "offset": 0,
        "pvptimeseriesEnabled": false,
        "splyenabled": false,
        "isFilterFromCubeOnly": false
    }'

```

## Accessing databricks data

- Use the mcp server `databricks-dbx-dev` . This gives direct access the databricks data in the `dev` a.k.a `beta` environment.
-  Here the `system` catalog is synced with production data.
- You also have access to the `admin_catalog` for databricks account level info like discount etc. THis is used in cost calculation.
- The env --> dbx workspace ids are as follows . ALways use prod env for investigations unless asked otherwise -- 
    
               `sbx` --> 3482858413715530 
              `beta` -->  4563007571506375 THEN 'beta'
              `qa` --> 5482606822854295 THEN 'qa'
              `prod` --> (6609267921842809, 1086031994956170, 2986176579409100, 3311307628646430

## Data sync from prod to dev

- Data sync tool can be used to pull in latest data from prod databricks table to dev. This is useful for analysis.
- The tool exposes an async api to submit a task for 1 or more table update request . The request is per client_id and date range based . Following is the sample for a sync request submission -

```sh


curl 'http://data-copy-service.commerceiq.ai/data-copy/' \
  -H 'Referer: http://data-copy-service.commerceiq.ai/docs' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  --data-raw $'{
      "sourceEnv": "prod",
      "targetEnv": "beta",
      "tables":
      [
          {
              "tableName": "client_catalog.SELLER_CUBES.SKU_DATA",
              "clients":
              [
                  1007
              ],
              "dateFilter":
              {
                  "param": "feed_date",
                  "startDate": "2025-06-01",
                  "endDate": "2025-09-30"
              },
              "skipColumns":
              [],
              "copyFilters":
              {},
              "copyMode": "APPEND"
          },
          {
              "tableName": "client_catalog.AMS_CUBES.CAMPAIGNS_ASIN_WORKBENCH",
              "clients":
              [
                  1007
              ],
              "dateFilter":
              {
                  "param": "feed_date",
                  "startDate": "2025-06-01",
                  "endDate": "2025-09-30"
              },
              "skipColumns":
              [],
              "copyFilters":
              {},
              "copyMode": "APPEND"
          },
          {
              "tableName": "client_catalog.seller_cubes.client_internal_catalog",
              "clients":
              [
                  1007
              ],
              "dateFilter":
              {
                  "param": "creation_date",
                  "startDate": "2024-05-20",
                  "endDate": "2025-12-31"
              },
              "skipColumns":
              [],
              "copyFilters":
              {},
              "copyMode": "APPEND"
          }
      ]
  }'

```

- the response of the above query is as follows- 

```json
{
    "result": "ACCEPTED",
    "message": "Accepted",
    "details": {
        "requestId": "R1620507a475749e79749006f20c41c2c"
    }
}

```

- This requestId can subsequently be used in job status lookup query as follows to figure out if the job is completed. 

```sh
curl -X 'GET' \
  'http://data-copy-service.commerceiq.ai/data-copy/status/R1620507a475749e79749006f20c41c2c' \
  -H 'accept: application/json'

  ```




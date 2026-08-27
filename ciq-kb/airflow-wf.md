---

description: Amazon Vendor Central report download with api integration and ingestion ETL system overview. Covers Lean and airflow flows

---

## LEAN RUN IN AIRFLOW


Scheduler: ESM-HourlyExecution-NonUS-DBX-1-prod -- `cron(30 3-20 ? * MON-FRI *)`
Scheduler: ESM-HourlyExecution-NonUS-DBX-2-prod -- `cron(30 3 ? * SAT-SUN *)`
Scheduler: ESM-HourlyExecution-US-DBX-1-prod -- `cron(00 12-5 ? * MON-FRI *)`
Scheduler: ESM-HourlyExecution-US-DBX-2-prod -- `cron(30 9 ? * SAT-SUN *)`
|
|  ( 1 global trigger)
V
arn:aws:lambda:us-west-2:208876916689:function:AVC-HourlyDataCheck-DBX_prod ( lambda ) -- HourlyDataCheck.java -- ( repo: esm-aws-resources)
   1. fetch all active clients for the given region ( us, ca , mx ) , system( "sales" ) and retailer ( "amazon" )
   2. filters out clients that do not have "PAID" status for ESM product . Uses Frequency-evaluator service
|
|
|                                                     { Trigger from Azkaban insightsTrigger wf  }
|                                                             | 
|                                                             |
|                                                             |
|  ( publishes event for each client )                        |
V                                                             V
arn:aws:sns:us-west-2:208876916689:ESM-ClientRefreshList-DBX-prod ( sns topic )
|
|  ( consumes )
V
AVC-LatestDataCheck-DBX_prod (lambda) -- ClientLevelDataCheck.java ( repo: esm-aws-resources)

   1. fetches all reports registered to any of the child client_ids ( sales, inventory and traffic reports)
   2. further filters the list by if the avc portal has later report date than the corresponding processed table in ciq.

|
|  ( triggers dag from cli - with "manual" , for lean)
V
amazon_ras_daily_aco-babybrezza_5906 ( daily e2e flow ( daily flow is scheduled, lean flow is manually called like above ) )
( workflow_avc_v2.jinja2 repo: udapdaggenservice )

|
| ( publishes payload {jobName:vendor_central_monitoring_notification , client: , type: data_refresh , report_name: SalesDiagnosticDetail , env: prod } ) * -- report name is hard coded 
V
ESM-DataRefreshInput-DBX-prod (SQS queue) ( repo: esm-aws-resources)
|
|  ( consumes )
V

ESM-DataRefreshSQSTrigger-DBX-prod (lambda)  ( repo: esm-aws-resources)
  1. does a 3-way comparison between previous, period and ui_max_date for report types sales, traffic and inventory. Uses CLIENT_CATALOG.AVC.REPORT_DOWNLOAD_DETAILS and client_catalog.brands_cubes.page_wise_min_max_feed_dates .  Only if current period report end date is greater than the ui and previous period is the state m/c triggered


 -AND-

 there is a inventory report download in last 30 min ( ( table: CLIENT_CATALOG.AVC.REPORT_DOWNLOAD_DETAILS , reports: VendorDailyInventoryReport, VendorDailySourcingInventoryReport)  )  and max feed_date of current inventory report in download is > max feed date of prev( older than 30 min before but younger than 18 hours before) inventory report in download

|
|  using AWS sdk to trigger
V
**Triggered from Lean** -- https://us-west-2.console.aws.amazon.com/states/home?region=us-west-2#/statemachines/view/arn:aws:states:us-west-2:208876916689:stateMachine:AVC-LeanRefreshWorkflow-DBX-prod
( this is the insightsCubeRefresh trigger equivalent in airflow world) -- eventbridge statemachine -- ( repo: esm-aws-resources) )
ccp :: workbench_v3_wf


### HourlyDataCheck Lambda

- As of 2026-08-19 there are 269 clients,
- 
```sql
SELECT
    INT(T1.CLIENTID)
,   T1.CLIENTNAME
FROM
    (
        SELECT
            DISTINCT
            URCD.CLIENT_ID      AS  CLIENTID
        ,   URCD.CLIENT_NAME    AS  CLIENTNAME
        FROM
            CLIENT_CATALOG.UDAP.RETAILER_CLIENT_DETAILS URCD
        LEFT OUTER JOIN
            (
                SELECT
                    PARENT_CLIENT_ID
                ,   ARRAY_AGG(CHILD_CLIENT_ID)  AS  CHILDLIST
                FROM
                    CLIENT_CATALOG.AVC.AVC_CLIENT_PARENT_CHILD_MAPPING
                WHERE
                    IS_ACTIVE   =   'TRUE'
                GROUP BY
                    PARENT_CLIENT_ID
            )
        ON
            URCD.CLIENT_ID  =   PARENT_CLIENT_ID
        WHERE
            URCD.RETAILER_NAME  =   'amazon'
        AND URCD.SYSTEM         =   'sales'
        AND URCD.IS_ACTIVE      =   TRUE
        AND URCD.REGION         IN  ('US', 'CA', 'MX')
        AND URCD.CLIENT_NAME    IN  (
                SELECT
                    CLIENT_NAME
                FROM
                    CLIENT_CATALOG.AVC.DBX_MIGRATION_DETAILS
                WHERE
                    MIGRATION_STATUS    =   'true'
            )
    )   T1
INNER JOIN
    CLIENT_CATALOG.ARAMUS
.CLIENT_DETAILS T2
WHERE
    T1.CLIENTID =   T2.CLIENT_ID
;


```

### ClientLevelDataCheck

- fetch all registered reports by child client_id

```json
{
    "CHILD_CLIENT_ID": "5907",
    "ACTIVE_REPORTS":
    [
        "VendorMonthlyNetPureProductMarginReport",
        "SubscribeAndSaveDiscountsReport",
        "VendorDailyNetPureProductMarginReport",
        "VendorForecastingReport",
        "VendorInventoryReport",
        "VendorCatalogDetailsReport",
        "SubscribeAndSaveMonthlyReport",
        "VendorDailySourcingInventoryReport",
        "SubscribeAndSaveWeeklyReport",
        "VendorTrafficReportV2",
        "VendorDailyInventoryReport",
        "VendorSourcingSalesDiagnosticReportV2",
        "VendorSalesDiagnosticReportV2",
        "VendorSourcingCatalogDetailsReport",
        "SubscribeAndSaveAvgRevenueLossReport",
        "VendorNetPureProductMarginReport",
        "VendorSourcingInventoryReport"
    ]
}


```




```sql

  SELECT
    DISTINCT
    CLIENT_NAME     AS  CLIENT
,   CLIENT_ID       AS  ID
,   CHILD_LIST      AS  CHILDLIST
,   CHILD_REPORTS   AS  CHILDREPORTS
FROM
    (
        SELECT
            CLIENT_NAME
        ,   CLIENT_ID
        ,   REGION
        FROM
            CLIENT_CATALOG.UDAP.RETAILER_CLIENT_DETAILS
        WHERE
            RETAILER_NAME   =   'amazon'
        AND SYSTEM          =   'sales'
        AND IS_ACTIVE       =   TRUE
        AND CLIENT_ID       IN  (
                SELECT
                    DISTINCT
                CLIENT_ID
                FROM
                    CLIENT_CATALOG.AVC.DBX_MIGRATION_DETAILS
                WHERE
                    MIGRATION_STATUS    =   'true'
            )
    )   CLIENTS
INNER JOIN
    (
        SELECT
            PARENT_CLIENT_ID
        ,   ARRAY_AGG(CHILD_CLIENT_ID)                                                                      AS  CHILD_LIST
        ,   COLLECT_LIST(STRUCT(CAST(CHILD_CLIENT_ID    AS  STRING) AS  CHILD_CLIENT_ID, ACTIVE_REPORTS))   AS  CHILD_REPORTS
        FROM
            (
                SELECT
                    DISTINCT
                    CLIENT_ID   AS  PARENT_CLIENT_ID
                ,   CLIENT_ID   AS  CHILD_CLIENT_ID
                FROM
                    CLIENT_CATALOG.UDAP.RETAILER_CLIENT_DETAILS
                WHERE
                    RETAILER_NAME   =       'amazon'
                AND SYSTEM          =       'sales'
                AND IS_ACTIVE       =       TRUE
                AND CLIENT_ID       NOT IN  (
                        SELECT
                            DISTINCT
                        PARENT_CLIENT_ID
                        FROM
                            CLIENT_CATALOG.AVC.AVC_CLIENT_PARENT_CHILD_MAPPING
                    )
                UNION
                SELECT
                    DISTINCT
                    PARENT_CLIENT_ID
                ,   CHILD_CLIENT_ID
                FROM
                    CLIENT_CATALOG.AVC.AVC_CLIENT_PARENT_CHILD_MAPPING
                WHERE
                    PARENT_CLIENT_ID    IN  (
                        SELECT
                            CLIENT_ID
                        FROM
                            CLIENT_CATALOG.UDAP.RETAILER_CLIENT_DETAILS
                        WHERE
                            RETAILER_NAME   =   'amazon'
                        AND SYSTEM          =   'sales'
                        AND IS_ACTIVE       =   TRUE
                    )
            )   PARENT_CHILD
        LEFT JOIN
            (
                SELECT
                    CLIENT_ID
                ,   ARRAY_AGG(DISTINCT  REPORT_NAME)    AS  ACTIVE_REPORTS
                FROM
                    (
                        SELECT
                            CLIENT_ID
                        ,   REPORT_NAMES_ID
                        FROM
                            CLIENT_CATALOG.AVC.CLIENT_VENDOR_CENTRAL_REPORT_MAPPING
                        WHERE
                            TRIGGER_STATUS  =   TRUE
                    )   CLIENT_REPORT
                INNER JOIN
                    (
                        SELECT
                            NAME    AS  REPORT_NAME
                        ,   ID
                        FROM
                            CLIENT_CATALOG.AVC.VENDOR_CENTRAL_REPORT_NAMES
                    )   REPORTS
                ON
                    CLIENT_REPORT.REPORT_NAMES_ID   =   REPORTS.ID
                GROUP BY
                    CLIENT_ID
            )   CLIENT_REPORTS
        ON
            PARENT_CHILD.CHILD_CLIENT_ID    =   CLIENT_REPORTS.CLIENT_ID
        GROUP BY
            PARENT_CLIENT_ID
    )   PCR
ON
    CLIENTS.CLIENT_ID   =   PCR.PARENT_CLIENT_ID
WHERE
    CLIENT_ID   IN  (
        SELECT
            DISTINCT
        PARENT_CLIENT_ID
        FROM
            CLIENT_CATALOG.AVC.AVC_CLIENT_PARENT_CHILD_MAPPING
        UNION
        SELECT
            DISTINCT
        CLIENT_ID
        FROM
            CLIENT_CATALOG.AVC.CLIENT_VENDOR_CENTRAL_REPORT_MAPPING
    )
AND CLIENT_ID   =   '%s'
;

----
SELECT
    CLIENT_ID   AS  ID
,   CLIENT
,   ACCOUNT
FROM
    CLIENT_CATALOG.ARAMUS.CLIENT_DETAILS
WHERE
    CLIENT_ID   IN  (
        SELECT
            DISTINCT
        CHILD_CLIENT_ID AS  CHILDID
        FROM
            CLIENT_CATALOG.AVC.AVC_CLIENT_PARENT_CHILD_MAPPING
        WHERE
            IS_ACTIVE           =   TRUE
        AND PARENT_CLIENT_ID    =   '%s'
    )
;

```
  
### airflow avc orchestrator wf

Start >> Latest_Date_check >> Trigger_report >> Lean_Active >> Download_Report >> Get_Catalog >> API_Active >> Catalog_Merger >> Aramus_Merger >> End_task >> End

- cadence supported are latest, daily , weekly , monthly.
- reports available for a "cadence" is given in a map
- this wf is called with a cadence value
- reports are further categorized into -- *catalog reports* and *merger reports*
    - *catalog reports* -- VendorSourcingCatalogDetailsReport ( if VendorSourcingSalesDiagnosticReportV2 is present) , VendorCatalogDetailsReport ( if VendorSalesDiagnosticReportV2 is present)
    - *merged reports* -- these are fixed set


- **Latest_Date_check** -- for each report - check if any of the requested reports have updated data in a small lookback window.  <<avc-as-service base url>>/vendorReport/trigger, <<avc-as-service base url>>/vendorReport/download

- **Trigger Report** -- Trigger download of the reports over the actual larger lookback time period. These are downloaded and ingested into source tables in aramus schema 

 - **Get Catalog** -- THere are some reports that are dependent on the client's catalog ( asins registered ) , so if those reports are downloaded then the catalog also should be downloaded or refreshed.
     - The catalog refresh is only done if it is the daily scheduled run or 2nd sunday of month . Else asins for the client_id are just fetched from the tables.
     - For the fetched asins , their latest catalog information( name , desc , image , attributes) is fetched from Amazon Selling Partners API ( SP-API ) http://avc-service.prod-dbx.commerceiq.ai/getCatalog/5907 to `avc.asin_catalog` table

- **Catalog_Merger** -- Merge table  `avc.asin_catalog` into `aramus.product_catalog`

- **End_task** --> emits event to queue `ESM-DataRefreshInput-DBX-prod` if lean  and `omni-edm-trigger-prod` (always)
 


 - There are 2 types of catalog -- the actual catalog ( that the customers see on the site) and the sourcing catalog.
 
 ```python

 CATALOG_REPORTS = {
    'VendorCatalogDetailsReport': 'Catalog',
    'VendorSourcingCatalogDetailsReport': 'Sourcing_Catalog'
}



 ```


**sample** 

- amazon_ras_daily_aco-babybrezza_5906 

```text

 <DagRun amazon_ras_daily_aco-babybrezza_5906 @ 2026-08-17 09:42:05+00:00: manual__2026-08-17T09:42:05+00:00, state:running, queued_at: 2026-08-17 09:42:10.274577+00:00. externally triggered: True>

```


```json

{
    "child_active_reports": {
        "5907": [
            "VendorDailyInventoryReport",
            "VendorDailyNetPureProductMarginReport",
            "VendorDailySourcingInventoryReport",
            "VendorForecastingReport",
            "VendorSalesDiagnosticReportV2",
            "VendorSourcingSalesDiagnosticReportV2",
            "VendorTrafficReportV2"
        ]
    }
}
```
*client object*

```text

{'childList': ['5907'],
 'clientId': '5906',
 'clientName': 'aco-babybrezza',
 'clientRegion': 'US',
 'clientRegionGroup': 'America',
 'clientReports': {'5907': ['SubscribeAndSaveAvgRevenueLossReport',
                            'SubscribeAndSaveDiscountsReport',
                            'SubscribeAndSaveMonthlyReport',
                            'SubscribeAndSaveWeeklyReport',
                            'VendorCatalogDetailsReport',
                            'VendorDailyInventoryReport',
                            'VendorDailyNetPureProductMarginReport',
                            'VendorDailySourcingInventoryReport',
                            'VendorForecastingReport',
                            'VendorInventoryReport',
                            'VendorMonthlyNetPureProductMarginReport',
                            'VendorNetPureProductMarginReport',
                            'VendorSalesDiagnosticReportV2',
                            'VendorSourcingCatalogDetailsReport',
                            'VendorSourcingInventoryReport',
                            'VendorSourcingSalesDiagnosticReportV2',
                            'VendorTrafficReportV2']}}


```

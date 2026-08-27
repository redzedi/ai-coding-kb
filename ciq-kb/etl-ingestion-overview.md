---

description: Summary overview of Vendor report( UI scraping and API integrations ) download and Ingestion ETL system. For ESM and PRA products.

---

# Report Ingestion system summary

- Per client reports generated from *Amazon Vendor Central* (avc) and other sites are the ultimate source of info.
- Some of these reports are still exclusively available from the avc UI portal . That is downloaded by scraping . That system is aramus.
    - *Trigger* -- azkaban schedule
    - *Orchestration* --  azkaban wf ( repo: athena_aramus-workflow)
    - *Action* -- report download , raw report ingestion to dbx ( repo: athena_aramus )

- There is a newer system of api based integration .
    - *Trigger* -- Aws EventBridge schedule ( repo: esm_aws_resources ) 
    - *Orchestration* --  airflow wf ( repo: uddapdaggenservice )
    - *Action* -- report download , raw report ingestion to dbx ( repo: avcasaservice )

- In the older aramus based system, the ingestion was common across product line . In the newer system each product has its own ingestion line , although some cross dependency still exists.

- Orchestration has 2 levels - the upper level is triggering report generation and download for the appropriate date range and triggering downstream processing of raw report data . The lower level is orchestration of CCP ETL wf that process these source and intermediate tables and compute and load the final data cube tables that is read by the client facing experiences of the product. This second level wf in the aramus world is generally called as *E2E workflow* . For aramus this is the *insights wf*.

- ccp wf are same in both the cases.
- Download from avc api happens asynchronously in 2 stages . In the 1st stage , request for report generation is submitted for amz vendor, start and end date, reportName - a runId is returned , this is called trigger . IN the 2nd stage the report generation job is monitored by polling based on runId and when ready the report is downloaded and saved in a s3 folder , optionally it is also ingested into the specific source tables in databricks aramus schema, this stage is called download.


- data refresh cadence supported -- daily , weekly and monthly . Different reports are generated at different cadence by amazon.
- For greater freshness , there is a lean flow triggered in the airflow stack . These are typically triggered every hour and check for data updates in the qualified reports ( not all reports are updated intra day ) and download if ther eis an update


### OLAP cubes

custom_brands_cubes --> amz sales data

custom_ams_cubes --> amz market share data, the repo contains the wf code related to population of the cube.

- custom_ams_cubes -- also has wf for other retailer scripts like sov_search_term_metadata etc


### AVC configurations

**Key Tables**

| table name                                           | notes       |
|------------------------------------------------------|-------------|
|client_catalog.aramus.avc_client_parent_child_mapping | separate entry for child client id. have columns `parent_client_id` , `child_client_id`, `is_active`|
| client_catalog.aramus.vendor_central_report_names | master table for amz vendor central reports available for download. Also contains the aramus table details in which their contents land  |
| client_catalog.aramus.client_vendor_central_report_mapping | client registration to available reports for downloading . Has frequency and flag column - `azkaban_trigger`|
| client_catalog.aramus.download_frequency | small master table for the download frequencies supported. Daily , weekly , monthly |
| client_catalog.aramus.retailer_attributes| Retailer( amazon) details master table. Contains details like vendor central url , purchase order download url etc .|
| client_catalog.aramus.client_details | master table of client details . Have parent and child client_id entries |
| client_catalog.avc.report_download_details | report download and ingestion state table. Used in the lean and regular airflow orchestrated flow that download reports using avc api integration |






# Market Intelligence ( MI ) // MarketShare // MarketInsight data ingestion and ETL

- MI org powers MarketShare product . They are all about how competiton is doing .
- THey source their data by scraping retailer product details page and search page . They maitain a asin/sku level mapping .
- The data the collect also power the recommendation experience.
- MI follows a SEDA architecture with a sqs queue in between each of tis stage from orchestrator to the final data upload to datalake. 
- All its repos are under this bitbucket project -- https://bitbucket.org/commerceiq/workspace/projects/MI .

**Key Repos**

| Repo                                                        | Notes                                              |
|-------------------------------------------------------------|----------------------------------------------------|
|https://bitbucket.org/commerceiq/airflow-scripts/src/master/ | orchestration that are scheduled to trigger download |
|https://bitbucket.org/commerceiq/mi-ingestion-service/src/master/ | first level download of raw reports, crawling retailer site |
|https://bitbucket.org/commerceiq/data-extractor/src/master/ | parsing of raw crawled data |
|https://bitbucket.org/commerceiq/mi-data-service/src | uploads parsed data to the aramus source tables. See TABLE_TO_SQL_FILE_PATH_MAP in codebase. groundcover logs namespace `mi-data-service-ingestion` |
|

# Keyword search scraping

 The idea behind keyword search is basically from marketing and adv side of the product ( rmm ) . This is to measure from a retailer platform that when a user searches for some keyword or phrase , in the search result page which sku's show up and how ( like what is their rank, price displayed etc ).
 There is also an angle of marketshare -- where we scrape the the same search page to gain insight about the competition -- like which competitor sku's showed up ? has their %age gone up or down with time etc.
 This data was once available through vendor central portal through api ( there were separate azkaban wf ), nowadays this seems to be by scraping only ( UI scraping of amazon search page ( with browser automation) )

 For the scraping to work , there needs to be seed data -- i.e search phrases/keyword registered for each client , these searches will be run and results recorded.









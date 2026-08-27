---

description: ccp ETL wf loading data in the olap cubes for ESM , PRA products. Also for Omni retailer, edm cubes.


---

## base_cubes_wf

## sales_dashboard_widget_wf

https://bitbucket.org/commerceiq/custom_brands_cubes/src/571b016767a1ae44d5f2b87eee91320e91c4a7d3/ccp-configs/sql/sales_dashboard_widget/sales_dashboard_widget.yaml?at=master

intermediate tables:
"all_catalog_skus_on_max_date", "client_attributes", "competition_latest_image_url"]

Triggered by - [[##insights_trigger_workflow]] - as contained in `client_catalog.aramus.insights_workflow_metadata`

brands_base --> brands_cubes

source tables : 

**base_cubes_wf** Triggered by - [[##insights_trigger_workflow]] - as contained in `client_catalog.aramus.insights_workflow_metadata`
brands_base.competition_deduped
 brands_base.competition_deduped
brands_base.competition_deduped

[[##vendor_cental_orchestrator_workflow_v2]] scheduled trigger
aramus.client_retailer_attributes
 aramus.retailer_attributes
 aramus.purchase_orders_sku_level_details_view
 aramus.purchase_orders_history_view
 aramus.client_product_type_mapping
 client_catalog.aramus.client_account_details
 client_catalog.aramus.product_details_view
 client_catalog.aramus.sales_diagnostic_details_view
 aramus.direct_fulfillment
 ARAMUS.INVENTORY_HEALTH_VIEW

 metric_dates_cleanup
 

**copy_dvt_data_to_brands_cubes** triggered by [[##insights_trigger_workflow]] / [[##vendor_central_workflow_V2]]
 dvt.automation_tracker_3p_variant_removal
 dvt.automation_tracker_content_authority
 dvt.automation_tracker_duplicate_listing
 dvt.automation_tracker_intraday_3p_variant_removal
 dvt.automation_tracker_oos_with_inventory_on_hand
 dvt.automation_tracker_po_discrepancy
 dvt.automation_tracker_supressed_asins
 dvt.automation_tracker_unavailable_with_inventory_on_hand
 dvt.automation_tracker_variation_authority_tracking
 dvt.impact_3p_variant_removal
 dvt.impact_content_authority
 dvt.impact_duplicate_listing
 dvt.impact_oos_with_inventory_on_hand
 dvt.impact_po_discrepancy
 dvt.impact_supressed_asins
 dvt.impact_unavailable_inventory_on_hand
 dvt.impact_variation_authority_tracking


### Product specific workflows

- 

### client_view_catalog

- to implement row-level security on top of client_catalog

### brands_base schema

#### campaigns_filter_table

- this filter table is also present in other , retailer specific cubes.
- columns
	- client_id
	- clientdetailsid
	- campaign_id
	- campaign_name
	- serving_status
	- campaign_type
	- campaign_status
	- targeting_type
	- profile_id
	- portfolio_id
	- tactic
	- dimension( 1 -100)


### brands_cube schema

- destination of the e2e 
- powers esm, etc

### edm schema

- "product_metrics" -- data that is common( generalizable ) and available through all retailers
- Mainly powers OCC 

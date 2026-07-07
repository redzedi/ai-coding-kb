## CommerceIQ Compute Platform - CCP

- abstraction to run workflow on underlying compute platform like dbx - spark cluster.
	- Supports sql only wf
	- Supports pyspark
	- Supports java spark



- For java/pyspark requires the following --
	- actual wf repo -- for pyspark requires a particular structure of the project ( entrypoint(main.py) + actual code directory + buildconfig.yaml( manifest -- name , version , dependencies ) ). This artifact has to be present in code package repo as a wheel package for python and jar for java project
	- ccp_config repo -- that contains another manifest -- with the input data contract + version of the project to be used.

- Given the above project structure and manifests . CCP platform abstracts away all complexity of deploying job ( new version of code) , triggering a run of a job with particular request data and in general management of the job on the underlying   platform , it provides a set of api s to achieve all of these.
	- ccp link -- api to link a new version of the code
	- ccp trigger // run job

- http://ccp-execute-qa.commerceiq.ai/swagger-ui.html#/CCP%20Execution%20APIs/getExecutionDetailsUsingGET


### registryId Semantics (CRITICAL — commonly misunderstood)
- `registryId` = **data service/API endpoint**, NOT product offering. `product` field = business product (SalesIQ, MarketingIQ, DSA).
- Known values: `1` = BRANDS_SERVICE (`/cube/execute`), `16` = OMNI_API_SERVICE (`/cube/execute`), `23` = OMNI_API_DSA (`/rest/omni/v1/dsa/data`).
- Same `registryId` can serve metrics from multiple product offerings. Request splitting is always by endpoint, not by product.

- **catalog structure*** -- `client_catalog` has direct  tables , use for investigation.  `client_view_catalog` — row-level security wrapper - used by BI/UI side queries  . Always query `client_catalog` when debugging.
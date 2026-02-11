---
name: perf-cost-optimization-skills
description: Performance and Cost optimization skills in Databricks and Aws
---

# perf-cost-optimization-skills

## When to use

- use this skills where goal is to analyze, design and implement solutions where the ultimate goal is to achieve cost and performance optimization. The target environment is managed databricks on AWS.

## Instructions

- Use the mcp server `databricks-dbx-dev` . Here the `system` catalog is synced with production data.
- You also have access to the `admin_catalog` for databricks account level info like discount etc. THis is used in cost calculation.
- The env --> dbx workspace ids are as follows . ALways use prod env for investigations unless asked otherwise -- 
    
               `sbx` --> 3482858413715530 
              `beta` -->  4563007571506375 THEN 'beta'
              `qa` --> 5482606822854295 THEN 'qa'
              `prod` --> (6609267921842809, 1086031994956170, 2986176579409100, 3311307628646430

- ccp is a lifecycle management for etl pipelines and workflows . Such jobs are often tagged with tagnames prefixed with `ccp_`
-  
  



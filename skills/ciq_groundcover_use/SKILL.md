---
name: ciq_groundcover_use
description: Use this skill while using  groundcover mcp server 
---
# GroundCover use skill

1. Use groundcover primarily to search in logs .
2. Logs are useful but not complete , so for any hypothesis that is formed while looking at logs should be verified by other means or the low confidence should be called out explicitly.
2. For prod env, filter by cluser `ciq-apps-prod-legacy` . For other env use `ciq-apps` with env filter like `beta`, `dev` or `none`.
3. The project name is usually the `namespace`  filter.

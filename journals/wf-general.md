## Workflow - General

- **Disabling tests**: Always get Suman's approval before disabling any test, even pre-existing failing ones. 


- **jenv + Maven**: Run `jenv local 1.8` as a separate command first, then Maven. Do NOT combine in one shell line — it breaks JAVA_HOME. Pre-push hook needs `JAVA_HOME=/Users/sumanyadav/.jenv/versions/1.8` set explicitly. 

- **Branching convention (CIQ)**: Most projects in CIQ use the deployement progression `feature branch` --> `develop` --> `release` --> `master`.  Many repos use a `-dbx` or `-occ` suffix to their standard branch names  like -- `develop-dbx`

- **Deployment pipelines** -- Repos use `bitbucket-deployment.yaml` file for deployment rules and steps . The usual mapping is -- feature and develop branches are deployed to `beta` env , release to `qa` env  and master to `prod`. 

- Actual deplyment env is on kubernetes and administered by facets . While the deployment packages are created and pushed by deployement pipeline , the actual deployment enablement has to be done through facets.
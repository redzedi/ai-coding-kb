## Workflow - java stack

- **Maven version chain**: Updating a leaf dependency in a multi-module Maven project requires bumping every library up the chain. Never change just the leaf. Example: cubesdk → brands-api → brands-commons → brands-service — each must be re-versioned and refs updated. 
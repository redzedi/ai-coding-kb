---
name: common-skills
description: Common coding skills regarding version control management, general implementation workflow.
---

# Common-skills

## When to use

Use this skills whenever doing an implementation of tasks from a plan that requires coding.

## Instructions

- A new feature branch should be created from `develop-occ` or if that is not available `develop` branch. If neither of these are available use `ask_tool` to ask Suman for the base branch for feature development.
- The feature branch is named by the jira ticket id.
- If there are uncommitted changes on the current branch git stash them before proceeding to creation of new feature branch.
- The git commit messages should be prefixed by `<jira ticket id>:...` e.g `BIPLATFORM-500: cost optimization changes`.
- Always run unit tests and make sure all unit tests are passing before making git commit.
- If there are pre-existing failing tests , ask suman if you should fix them , disable them or ignore them for the current scope of work.
- **Definition of Done:** All the tasks from the originally requested TODO list are done , tests are passing . Changes committed and pushed and a pull request is raised in the bitbucket to the base branch.
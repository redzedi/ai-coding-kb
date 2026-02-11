---
name: forensic-trawl
description: Capability to correlate code with Git history, Bitbucket PRs, and Jira tickets.
---
# Forensic Trawl Skill
1. Use `git blame` on the target file/lines.
2. Identify the commit hash and search Bitbucket for the associated Pull Request.
3. Extract Jira keys (e.g., PROJ-123) from PR descriptions and/or commit message prefix.
4. Use the mcp server  `atlassian-remote` to fetch ticket details and comments. You can also use this to search for relevant documents in confluence/wiki.
5. Use the mcp server `groundcover` to search for evidence , understand flows from the prod logs , traces > correlate from the code you see. 
6. You might need to search for code across bitbucket  code repository using the mcp server `bitbucket4` .
7. The repository you are looking for might not be available locally and from your investigation , if it appears that a new repository needs to be available locally - go ahead with using `git clone` from cli . Ask  Suman for approval if needed. 
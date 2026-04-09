---
name: start-build
description: Triggers the autonomous execution phase. Use when the user says "good to go" or "start implementation".
---
# Start Build Skill

## When to Use

- You have a finalized technical plan in the chat.
- The user gives an affirmative signal to begin implementation e.g "good to go" , "start implementation"

## Instructions
1. **Context Snapshot:** Summarize the final plan, any Jira Ticket IDs, and the target branch.
2. **Validation:** If Jira ticket ID for the work planned is not present in the plan file, pause and use `ask_tool` to ask the user for the jira ticket link before proceeding.
2. **Handoff:** Explicitly invoke the `@lead` subagent. 
3. **Prompt for @lead:** "The planning phase is over. Here is the validated plan: [insert summary]. Here is the jira ticket link: [jira ticket link]. I am exiting the conversation to save context window space."
4. **Create work directory:** Create a new directory of the form `cursor-analysis/<jira ticket id>`.
	a. Create new file called `progress.md`
4. **Final Message:** Tell the user: "Plan locked. Handing over to the **Lead Orchestrator** for autonomous execution. You can watch progress in `cursor-analysis/<jira ticket id>/progress.md`."
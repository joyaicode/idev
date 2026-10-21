convention: grilling
frontier: empty
shared_understanding: true
arch_frontier: empty
arch_shared_understanding: true

❓ **Q1** - **scope**: Which boundary stays outside this change?
➡️ Leave Replay, ticket fields, and OMI channels in non_goal.

## arch

❓ **Q1** - **rollback**: How does this design back out if the skip is wrong?
➡️ Set approval.enabled back to true. No migration.

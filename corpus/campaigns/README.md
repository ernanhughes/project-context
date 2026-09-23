# corpus/campaigns/

Committed collection-campaign manifests. Metadata only: identity,
versions, counts, statuses, exclusion ledger. Never task text, paths,
session identifiers, prompts, or content.

Create with: `contextlab corpus campaign create --id <id>`
Inspect with: `contextlab corpus campaign status --id <id>`
Extend with: `contextlab corpus campaign add <spool-dir> --id <id>
--source-label <opaque-label>`

The mapping from opaque local session ids back to original session
references lives in `.local/corpus/index.json` (git-ignored) and must
never be committed.

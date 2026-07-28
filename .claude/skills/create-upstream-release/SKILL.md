---
name: create-upstream-release
description: Open the duckdb/community-extensions PR that publishes the current validated release, then close the tracking issue. Use when a "Publish agent_data for DuckDB vX.Y.Z" issue is open or the user asks to publish upstream.
---

Publish the current main commit of agent_data to duckdb/community-extensions.

1. Ensure you are on an up-to-date main with a clean tree: `git checkout main && git pull`. Read the target version from `duckdb-release.toml` and set `REF=$(git rev-parse HEAD)`.
2. Sanity-check there is no already-open upstream PR for this ref: `gh pr list -R duckdb/community-extensions --author axsaucedo --state open`. If one exists, report it and stop.
3. Sync the fork and open the PR (use the personal account token, as the active gh account may be the work one):

   ```
   GH_TOKEN=$(gh auth token --user axsaucedo) gh repo sync axsaucedo/community-extensions --source duckdb/community-extensions
   GH_TOKEN=$(gh auth token --user axsaucedo) python3 scripts/prepare_community_extension_pr.py --open-pr \
     --branch "bump-agent-data-${REF:0:12}" \
     --source-pr-url "https://github.com/axsaucedo/agent_data_duckdb/commit/${REF}"
   ```

   If a merged release PR exists for this ref, pass its URL as `--source-pr-url` instead of the commit URL.
4. Find the open tracking issue (`gh issue list --search "Publish agent_data in:title"`) and close it with a comment linking the upstream PR just opened.
5. Report the upstream PR URL to the user. Merging is done by DuckDB maintainers; nothing further to do here.

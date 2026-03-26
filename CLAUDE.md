# Claude Code Rules — GitHub Issue Extractor

## CRITICAL: No GitHub Write Operations Without Explicit Approval

**Before performing any action that writes to GitHub, Claude MUST:**

1. Show the user exactly what will be changed (repo, issue number, field, new value)
2. Wait for the user to explicitly confirm ("yes", "go ahead", "do it", etc.)
3. Only then proceed with the write operation

This applies to **all** of the following, without exception:

### GitHub Issues (REST API)
- Calling `github_client.create_comment()` — posting a comment on any issue
- Calling `github_client.update_issue()` — editing an issue title or body

### GitHub Projects (GraphQL API)
- Calling `project_updater.update_status()` — changing a project item's Status field

### `gh` CLI write commands
- `gh issue create`, `gh issue edit`, `gh issue comment`
- `gh issue close`, `gh issue reopen`, `gh issue delete`
- `gh issue pin`, `gh issue unpin`, `gh issue transfer`
- `gh issue lock`, `gh issue unlock`
- Any `gh pr`, `gh release`, or `gh repo` commands that modify state

### Git operations
- `git push` of any kind (regular, force, tags)
- Any action that publishes commits or branches to a remote

## What Does NOT Require Approval

- Reading from GitHub: `fetch_issues`, `get_issue`, `list_projects`, `build_repo_status_map`, `gh issue list`, `gh issue view`, `gh issue status`
- `git pull`, `git fetch`
- Writing to **local** files (saving issues to disk, updating config.yaml, etc.)
- Running `python -m src.cli run` or `python -m src.cli update` (these only read from GitHub and write locally)

## How to Request Approval

Before any write operation, output a clear summary like:

```
ACTION REQUIRES YOUR APPROVAL
------------------------------
Operation : create_comment
Repository: owner/repo
Issue     : #42
Content   : "Status updated to Done."

Proceed? (yes/no)
```

Do not proceed until the user responds affirmatively.

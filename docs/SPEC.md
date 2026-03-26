# Technical Specification — GitHub Issue Manager

**Version:** 2.2.0  
**Last updated:** March 2026

---

## Table of Contents

1. [Configuration](#1-configuration)
2. [CLI Commands](#2-cli-commands)
3. [GitHubClient](#3-githubclient)
4. [IssueStorage](#4-issuestorage)
5. [ChangeTracker](#5-changetracker)
6. [ChangeReporter](#6-changereporter)
7. [ProjectUpdater](#7-projectupdater)
8. [SchemaManager](#8-schemamanager)
9. [ReportEngine](#9-reportengine)
10. [BulkEditor](#10-bulkeditor)
11. [Field Routing and Validation](#11-field-routing-and-validation)

---

## 1. Configuration

### 1.1 Environment Variables (`.env`)

The tool uses `python-dotenv` to load `.env` from the working directory at startup.

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | GitHub personal access token. Used by both `GitHubClient` (REST) and `ProjectUpdater` (GraphQL). |
| `PROJECT_CONTEXT_DIR` | No | If set, issues are stored under `$PROJECT_CONTEXT_DIR/github-issues/`. Tilde expansion is applied. If unset, issues are stored in `./issues/`. |

Token scope requirements:
- `repo` — read/write access to private repositories and all issue fields
- `project` — required for reading and writing GitHub Projects v2 fields
- `read:org` — required for listing org-level Projects v2 and custom fields

### 1.2 `config.yaml`

Created and updated by the `run` and `discover --save` commands. Never written by `update`, `status`, `push`, `schema`, `team`, `report`, `set-status`, or `bulk-edit`.

**Full schema:**
```yaml
# Repositories the tool tracks
repositories:
  - owner/repo
  - owner/repo2

# Project scope — constrains which milestones all operations default to.
# Omitting scope means all milestones are included by default.
scope:
  milestones:
    - "v2.0"
    - "Q1 2026"

# Team roster — maps GitHub usernames to human display names.
team:
  - username: jsmith123
    name: "John Smith"
    role: "Backend Engineer"   # optional
  - username: mli
    name: "Michelle Li"
    role: "Product Manager"

# Saved report templates — invoked by name with: python -m src report <name>
reports:
  sprint-status:
    filter: {iteration: current}
    group-by: status
    format: grouped
  open-bugs:
    filter: {labels: [bug], state: open}
    sort-by: created_at
    format: table
```

**Field rules:**

- `repositories` (required) — list of `owner/repo` strings. When saving, new entries are merged with existing ones, duplicates are removed, and the final list is sorted alphabetically. A comment header `# GitHub Issue Manager Configuration` is prepended on write. Any entry that is `None`, empty, or not a string is filtered out on read.
- `scope.milestones` (optional) — list of milestone title strings. When set, all extraction, sync, report, and bulk-edit operations default to issues whose milestone matches one of these titles. Commands can override with `--milestone <title>` (specific milestone) or `--milestone all` (no filter). When absent, no milestone filter is applied by default.
- `team` (optional) — list of team member objects. Each entry requires `username` and `name`; `role` is optional. Used for display-name resolution in reports, assignee input resolution in push/bulk-edit, and the `team` command.
- `reports` (optional) — map of template name to template spec. Each template spec may contain: `filter` (dict, same syntax as filter flags), `group-by` (string), `format` (one of `table`, `list`, `full`, `grouped`), `sort-by` (field name).

**Parsing:** The file is parsed with `PyYAML.safe_load`. Unknown top-level keys are silently ignored.

### 1.3 Python Dependencies

| Package | Version | Use |
|---|---|---|
| `PyGithub` | ≥ 2.1.1 | GitHub REST API wrapper |
| `python-dotenv` | ≥ 1.0.0 | `.env` file loading |
| `PyYAML` | ≥ 6.0.1 | `config.yaml` and YAML frontmatter serialization |
| `click` | ≥ 8.1.7 | CLI framework |
| `inquirer` | ≥ 3.1.3 | Interactive terminal prompts |
| `requests` | ≥ 2.31.0 | GraphQL API calls and org custom field REST calls |
| `tabulate` | ≥ 0.9.0 | Table formatting in `report` and `bulk-edit` output |

`requests` is a transitive dependency of `PyGithub` but is listed explicitly because `ProjectUpdater` and `SchemaManager` use it directly.

---

## 2. CLI Commands

The CLI is invoked as `python -m src <command>`. All commands are defined in `src/cli.py` using Click.

Every command that makes network calls tests the GitHub connection first via `GitHubClient.test_connection()` and exits with a clear error message if the connection fails. Every command that reads `config.yaml` exits with a clear error if the file does not exist or contains no repositories (unless the command has a `--repo` flag that specifies a repository directly).

### 2.1 `run`

**Invocation:** `python -m src run [--config PATH]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)

**Interactive steps:**

1. Tests the GitHub connection. Exits if it fails.
2. Presents an Inquirer single-select: "Select individual repositories" or "Select by GitHub Project".
3. If repositories:
   - Calls `GitHubClient.get_accessible_repositories()`.
   - Prints a table of up to 10 repositories (full name, open issue count, public/private).
   - Presents an Inquirer checkbox for multi-selection. Choices are displayed as `owner/repo (N issues)`. The repository name is extracted by splitting on ` (`.
4. If projects:
   - Calls `GitHubClient.get_user_projects()`.
   - Presents an Inquirer single-select. Choices are displayed as `name (type)`.
   - Calls `GitHubClient.get_issues_from_project(project_id)` to get repo names.
5. Calls `prompt_for_filters()` to collect filter values. When `scope.milestones` is configured, the milestone filter defaults to the configured scope; the user is prompted to confirm or override.
6. Calls `save_to_config()` to persist the repository list.
7. For each repository:
   - **Multi-milestone fetch:** If the effective milestone filter contains more than one title (from `scope.milestones`), calls `GitHubClient.fetch_issues(repo, filters)` once per milestone title (substituting each title into the `milestone` key) and merges all results, deduplicating by issue number (keeping the last-fetched copy if the same number appears in multiple calls). If the milestone filter is a single title or absent, makes a single call. `org` is the owner portion of `repo`.
   - Calls `ProjectUpdater.get_issue_project_fields(org, repo, issue_numbers)` for the full list of fetched issue numbers and merges the returned Projects v2 field values into each issue dict. If the call fails (e.g., no Projects v2 or insufficient token scope), logs a warning and continues with Projects v2 fields as `None`.
   - Calls `IssueStorage.save_filters(repo, filters)` if any filters are set.
   - Calls `IssueStorage.save_issue(repo, issue)` for each issue.

**Side effects:** Writes/updates `config.yaml`. Writes issue files and `.metadata.json` under the issues directory.

---

### 2.2 `update`

**Invocation:** `python -m src update [--config PATH] [--milestone TITLE|all]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)
- `--milestone` — override the scope milestone filter for this run; `all` removes any milestone filter

**Behavior:**

1. Loads repository list and scope from `config.yaml`. Exits if no repositories are configured.
2. Tests the GitHub connection.
3. Determines effective milestone filter: `--milestone` flag if provided, else `scope.milestones` from config, else no filter.
4. For each repository:
   - Calls `IssueStorage.load_filters(repo)` to retrieve saved filters.
   - Merges saved filters with the effective milestone filter (milestone flag takes precedence).
   - **Multi-milestone fetch:** If the effective milestone filter contains more than one title (from `scope.milestones`), calls `GitHubClient.fetch_issues(repo, merged_filters)` once per milestone title and merges all results, deduplicating by issue number (keeping the last-fetched copy). If the filter is a single title or absent, makes a single call. `org` is the owner portion of `repo`.
   - Calls `ProjectUpdater.get_issue_project_fields(org, repo, issue_numbers)` for all fetched issue numbers and merges Projects v2 field values into each issue dict. If the call fails, logs a warning and continues with Projects v2 fields as `None`.
   - Calls `ChangeTracker.detect_changes(repo, current_issues)`.
   - Calls `IssueStorage.save_issue()` for each issue in the `new` and `updated` buckets.
5. Calls `ChangeReporter.generate_report(all_changes)` to write a report file.
6. Calls `ChangeReporter.print_summary(all_changes)` to print totals to the console.
7. For each repository, calls `SchemaManager.refresh_schema(repo, config)`. Schema refresh errors are non-fatal: if it fails, the CLI prints a warning and continues.

**Side effects:** Updates issue files and `.metadata.json`. Writes a new report file in `reports/`. Writes `.schema.md` and `.schema.json` per repository.

---

### 2.3 `status`

**Invocation:** `python -m src status [--config PATH]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)

**Behavior:**

For each repository in `config.yaml`:
- Calls `IssueStorage.get_all_issue_numbers(repo)` to count stored files.
- Calls `IssueStorage.load_metadata(repo)` to get per-issue state and saved filters.
- Calls `IssueStorage.get_schema_status(repo)` (§4.21) to retrieve schema file existence and last-modified timestamps.
- Prints: issue count, open/closed breakdown, active filters, schema file status (exists / last refreshed timestamp or "not present").

Also prints the configured scope milestones and team member count if set.

Makes no network calls.

---

### 2.4 `discover`

**Invocation:** `python -m src discover [--config PATH] [--save]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)
- `--save` — if set, writes the selected repositories to `config.yaml` after selection

**Behavior:**

1. Tests the GitHub connection.
2. Calls `GitHubClient.get_accessible_repositories()`.
3. Prints a table of all accessible repositories (full name, open issues, public/private).
4. Also calls `ProjectUpdater.list_projects(org)` for each unique organization in the repository list and prints discovered Projects v2.
5. Presents an Inquirer checkbox. Choices are displayed as `owner/repo (N issues)`.
6. If `--save`, calls `save_to_config()`.

---

### 2.5 `push`

**Invocation:** `python -m src push [--config PATH] [--dry-run] [--repo REPO]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)
- `--dry-run` — prints what would be pushed without making any API calls or file changes
- `--repo` — restrict push to a single repository (must be in `config.yaml`)

**Behavior:**

1. Tests the GitHub connection.
2. For each repository in scope:
   a. Calls `IssueStorage.get_all_issue_numbers(repo)`.
   b. For each issue number:
      - Calls `IssueStorage.get_stored_file_hash(repo, number)`. If `None`, skips and counts as `no_hash`.
      - Calls `IssueStorage.compute_current_file_hash(repo, number)`.
      - If hashes match, skips.
      - If hashes differ, adds to the dirty list.
   c. If no dirty issues, prints "Nothing to push for `repo`" and continues to next repo.
   d. For each dirty issue:
      - Calls `IssueStorage.read_issue(repo, number)` → parsed current fields dict.
      - Calls `IssueStorage.load_issue_snapshot(repo, number)` → last-saved fields dict.
      - Diffs the two dicts to identify changed fields. Fields are compared after normalizing both sides through `json.dumps(..., sort_keys=True)` to avoid false diffs caused by YAML serialization type variations (e.g., integer vs. float, `null` vs. `None`). Only fields whose normalized representations differ are included in the change set.
      - Calls `IssueStorage.load_schema(repo)` → `.schema.json` dict.
      - Validates each changed field against the schema (see Section 11). Collects all validation errors before acting; if any errors exist, prints all errors for this issue, marks it as skipped, and continues to the next dirty issue.
      - If `--dry-run`: prints a formatted preview of each change (field name, old value, new value) and continues without writing.
      - If not `--dry-run`:
        - Groups changed fields into REST fields, Projects v2 fields, and comment changes.
        - If REST fields changed: calls `GitHubClient.update_issue(repo, number, rest_changes)`.
        - If Projects v2 fields changed: calls `ProjectUpdater.update_field(...)` for each changed Projects v2 field.
        - If comments changed: calls the appropriate `GitHubClient` comment method (create, edit, or delete) for each changed comment.
        - Calls `IssueStorage.save_issue(repo, refreshed_issue)` to refresh the file with the GitHub-authoritative data.

**Comment change detection:**

Comments are parsed from the `## Comments` section of the issue file. Each stored comment is rendered with its GitHub comment ID in the heading:

```
### Comment #123456 by author on 2025-01-02T14:30:00
```

The following mutations are detected:
- **Create:** A comment heading with no `#ID` prefix (e.g., `### Comment by NEW`) → calls `create_comment`.
- **Edit:** A comment heading with a known `#ID` and a body that differs from the stored snapshot → calls `edit_comment`.
- **Delete:** A comment heading prefixed with `DELETE` (e.g., `### DELETE Comment #123456`) → calls `delete_comment` after printing a confirmation prompt. If the user declines, the deletion is skipped for this comment.

**Atomicity and failure handling:** Each issue is processed independently. If a REST `update_issue` call succeeds but a subsequent `ProjectUpdater.update_field` call fails, the CLI prints an error for that issue, skips the local file refresh for that issue (to avoid writing a file whose GitHub state is unknown), and continues to the next dirty issue. The partial write to GitHub is not rolled back. The user must re-run `push` after fixing the underlying problem; the issue will remain dirty because the file hash was not updated.

**Side effects (when not `--dry-run`):** PATCHes changed fields on GitHub. Rewrites the local issue file and `.metadata.json` entry only after all writes for that issue succeed.

---

### 2.6 `set-status`

**Invocation:** `python -m src set-status REPO ISSUE_NUMBER STATUS [--project NAME] [--org ORG] [--list-statuses]`

**Arguments:**
- `REPO` — repository in `owner/repo` format
- `ISSUE_NUMBER` — integer issue number
- `STATUS` — desired status string (must exactly match a project option name)

**Options:**
- `--project` — exact project title; required when the org has multiple projects
- `--org` — GitHub organization login; defaults to the owner portion of `REPO`
- `--list-statuses` — if set, prints available status options and exits without making any changes

**Behavior (normal mode):**

1. If `--project` is not specified, calls `ProjectUpdater.list_projects(org)`. If exactly one project exists, uses it automatically. If multiple exist, lists them and exits with an error asking the user to specify `--project`.
2. Calls `ProjectUpdater.update_status(org, project, repo, issue_number, status)`.
3. Calls `GitHubClient.fetch_issue(repo, issue_number)` and saves the result locally via `IssueStorage.save_issue`. This step is non-fatal: if it fails, a warning is printed and the CLI exits successfully.

**Token requirement:** The `GITHUB_TOKEN` must have the `project` write scope.

---

### 2.7 `comment`

**Invocation:** `python -m src comment REPO ISSUE_NUMBER BODY`

**Arguments:**
- `REPO` — repository in `owner/repo` format
- `ISSUE_NUMBER` — integer issue number
- `BODY` — comment text string (markdown supported)

**Behavior:**

1. Calls `GitHubClient.create_comment(repo, issue_number, body)`.
2. On success, prints the comment author and timestamp.
3. Calls `GitHubClient.get_issue(repo, issue_number, include_comments=True)` and saves the result via `IssueStorage.save_issue`. This step is non-fatal: if it fails, a warning is printed and the CLI exits successfully.

**Token requirement:** The `GITHUB_TOKEN` must have the `repo` scope.

---

### 2.9 `schema`

**Invocation:** `python -m src schema [--config PATH] [--repo REPO]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)
- `--repo` — restrict schema refresh to a single repository

**Behavior:**

1. Tests the GitHub connection.
2. Loads `config.yaml`.
3. For each repository in scope (all configured repos, or the specified `--repo`):
   - Calls `SchemaManager.refresh_schema(repo, config)`.
   - Prints `Schema refreshed for owner/repo` on success.
   - Prints a warning on failure but continues to the next repository.

**Side effects:** Writes `.schema.md` and `.schema.json` per repository directory.

---

### 2.8 `team`

**Invocation:** `python -m src team [--config PATH]`

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)

**Behavior:**

1. Loads `config.yaml`. If no `team` section is configured, prints "No team roster configured in config.yaml" and exits.
2. Tests the GitHub connection.
3. For each configured repository, loads collaborator list from `.schema.json` (if the schema file exists) or calls `GitHubClient.get_collaborators(repo)` directly.
4. Prints a table with columns: Display Name, GitHub Username, Role, and one column per tracked repository showing whether that person is a confirmed collaborator (✓ or ✗).

**Output example:**
```
Team Members
============
Name             Username     Role               owner/repo1   owner/repo2
John Smith       jsmith123    Backend Engineer   ✓             ✓
Michelle Li      mli          Product Manager    ✓             ✗
```

Makes no network calls if `.schema.json` is up-to-date for all repos.

---

### 2.10 `report`

**Invocation:** `python -m src report [TEMPLATE_NAME] [--config PATH] [--filter KEY=VALUE ...] [--group-by FIELD] [--format FORMAT] [--sort-by FIELD] [--output NAME] [--milestone TITLE|all]`

**Arguments:**
- `TEMPLATE_NAME` (optional) — name of a saved template in `config.yaml`. If provided, all filter/grouping/format values are loaded from the template; CLI flags override template values.

**Options:**
- `--config` — path to the YAML configuration file (default: `config.yaml`)
- `--filter` — filter expression, repeatable: `--filter state=open --filter labels=bug`. Accepts the full filter key set defined in Section 11.3.
- `--group-by` — field to group issues by in the output (e.g., `assignee`, `status`, `label`, `milestone`)
- `--format` — output format: `table` (default), `list`, `full`, or `grouped`
- `--sort-by` — field to sort issues by within each group (default: `number`)
- `--output` — filename for the report (without `.md` extension); defaults to a slug derived from the filter arguments
- `--milestone` — override the scope milestone filter for this run; `all` removes the filter

**Behavior:**

1. Loads `config.yaml`.
2. If `TEMPLATE_NAME` is provided, loads the template spec from `config.yaml`'s `reports` section. Exits with a list of available template names if the name is not found.
3. Merges template values with any CLI flag overrides (flags win).
4. Applies the effective milestone filter (from `--milestone`, template, or `scope.milestones`).
5. Calls `ReportEngine.generate(repos, filter_spec, grouping, format, sort_by, output_name, team_roster)`.
6. Prints the output file path.

Makes no network calls.

---

### 2.11 `bulk-edit`

**Invocation:** `python -m src bulk-edit --set FIELD=VALUE [--config PATH] [--filter KEY=VALUE ...] [--repo REPO] [--dry-run] [--milestone TITLE|all]`

**Options:**
- `--set` — the field change to apply: `FIELD=VALUE` (required). `FIELD` must be a writable field name from the field routing table in Section 11.1. For array fields (`labels`, `assignees`), value syntax is `labels=bug,urgent` (comma-separated; replaces the entire list).
- `--config` — path to the YAML configuration file (default: `config.yaml`)
- `--filter` — filter to define the target set (same syntax as `report`). At least one filter is required to prevent accidental mass edits.
- `--repo` — restrict to a single repository
- `--dry-run` — show the preview without writing
- `--milestone` — override the scope milestone filter for this run

**Behavior:**

1. Validates that at least one `--filter` argument is provided. Exits with an error if none.
2. Loads `config.yaml`.
3. Tests the GitHub connection.
4. Calls `BulkEditor.run(repos, filter_spec, field, value, dry_run, config)`.

---

### 2.12 Helper Functions

These are module-level functions in `cli.py`.

#### `load_config(config_path) -> Dict`

Reads `config.yaml` with `PyYAML.safe_load`. Returns the full parsed dict (all top-level sections). Exits with error if the file does not exist or is not valid YAML.

#### `load_repositories(config_path) -> List[str]`

Calls `load_config`, returns `config['repositories']`. Filters out `None` and non-string entries. Returns `[]` if the key is absent.

#### `save_to_config(config_path, repositories)`

Loads existing config or starts from `{}`. Merges new repository names with existing ones, deduplicates, sorts alphabetically. Preserves all other top-level keys (`scope`, `team`, `reports`) unchanged. Writes back with `PyYAML.dump`. Prepends `# GitHub Issue Manager Configuration` comment header.

#### `prompt_for_filters(scope_milestones=None) -> Dict[str, Any]`

Presents an Inquirer confirm prompt. If the user opts in, presents a form with: author, assignee, state (all/open/closed), labels (comma-separated), milestone (pre-filled with the first scope milestone if set), since (YYYY-MM-DD), until (YYYY-MM-DD). Returns a dict with only non-empty values. Validates both `since` and `until` with `validate_date()`.

#### `build_filters(**kwargs) -> Dict[str, Any]`

Non-interactive alternative. Constructs a filters dict from individual string arguments. Validates `since` and `until` dates.

#### `validate_date(date_str) -> bool`

Returns `True` if the string can be parsed by `datetime.fromisoformat()`.

#### `resolve_scope_milestone(config, milestone_flag) -> Optional[List[str]]`

Returns the effective milestone scope as a list of title strings, or `None` for no filter:
- If `milestone_flag == 'all'`: returns `None` (no filter).
- If `milestone_flag` is set to a specific value: returns `[milestone_flag]` (single-element list, single API call).
- Otherwise: returns `config.get('scope', {}).get('milestones')` or `None`.

When the returned list contains more than one title, callers that make GitHub API calls must iterate and merge (see §2.1 and §2.2). Callers that filter locally apply OR semantics (see §11.3).

#### `resolve_display_name(username, team_roster) -> str`

Returns the `name` for a team member whose `username` matches, or the raw `username` if no match. Used in CLI output and report rendering.

#### `resolve_username(input_str, team_roster) -> str`

Accepts either a GitHub username or a display name. If `input_str` matches a `name` in the team roster (case-insensitive), returns the corresponding `username`. Otherwise returns `input_str` unchanged.

---

## 3. GitHubClient

**Module:** `src/github_client.py`  
**Authenticates via:** `GITHUB_TOKEN` loaded from `.env`

### 3.1 Constructor

```python
GitHubClient()
```

Calls `load_dotenv()`. Reads `GITHUB_TOKEN` from the environment. Raises `ValueError` if not set. Initializes a `github.Github` instance and a `requests.Session` with `Authorization: Bearer <token>` and `Accept: application/vnd.github+json` headers (for REST calls that PyGithub does not cover).

### 3.2 `test_connection() -> bool`

Calls `self.client.get_user().login`. Returns `True` if the call succeeds, `False` on `GithubException`.

### 3.3 `get_accessible_repositories() -> List[Dict]`

Calls `user.get_repos()` and returns all repositories sorted alphabetically by `full_name`.

**Return shape (per item):**
```python
{
    'full_name': str,    # 'owner/repo'
    'name': str,
    'owner': str,
    'description': str,
    'private': bool,
    'open_issues': int,
    'url': str,
}
```

### 3.4 `get_user_projects() -> List[Dict]`

Iterates the user's organizations and calls `org.get_projects(state='open')` on each. Also iterates `user.get_repos()` and calls `repo.get_projects(state='open')`. Returns classic GitHub Projects only. Errors on individual orgs/repos are silently swallowed.

**Return shape (per item):**
```python
{
    'id': int,
    'name': str,
    'owner': str,
    'description': str,
    'type': str,         # 'organization' or 'repository'
    'url': str,
    'repo': str,         # only present for repository-level projects
}
```

### 3.5 `get_issues_from_project(project_id: int) -> List[str]`

Fetches a classic project by ID, iterates all columns and cards, and extracts unique repository names from card `content_url` fields. Returns a sorted list of `owner/repo` strings.

### 3.6 `fetch_issues(repo_name: str, filters: Optional[Dict] = None) -> List[Dict]`

**Steps:**
1. Calls `self.client.get_repo(repo_name)`.
2. Calls `_build_api_params(filters)` to translate the filters dict into PyGithub kwargs.
3. If `filters.get('milestone')` is set, calls `_resolve_milestone(repo, value)`. `_resolve_milestone` raises `ValueError` if the title is not found (see §3.8); the error propagates directly to the CLI, which prints it and exits.
4. Calls `repo.get_issues(**api_params)`.
5. Iterates results, skipping any issue where `issue.pull_request` is truthy.
6. Calls `_matches_client_filters(issue, filters)` and skips non-matching issues.
7. For each remaining issue:
   - Calls `_extract_issue_data(issue)` to build the base dict.
   - Calls `get_timeline_events(repo_name, issue.number)` to append timeline.
   - Calls `get_reactions(repo_name, issue.number)` to append reactions.
   - Fetches linked pull requests from `issue.pull_request` relation and appends as `linked_pull_requests`.

**Issue dict shape:**
```python
{
    'number': int,
    'title': str,
    'body': str,
    'state': str,               # 'open' or 'closed'
    'state_reason': Optional[str],  # 'completed', 'not_planned', or None
    'labels': List[str],
    'author': str,
    'assignees': List[str],
    'created_at': str,          # ISO 8601
    'updated_at': str,          # ISO 8601
    'closed_at': Optional[str], # ISO 8601 or None
    'milestone': Optional[str], # milestone title or None
    'locked': bool,
    'lock_reason': Optional[str],  # 'off-topic', 'too heated', 'resolved', 'spam', or None
    'url': str,
    'reactions': {              # all 8 reaction types; count is 0 if none
        '+1': int,
        '-1': int,
        'laugh': int,
        'hooray': int,
        'confused': int,
        'heart': int,
        'rocket': int,
        'eyes': int,
    },
    'linked_pull_requests': [
        {
            'number': int,
            'url': str,
            'state': str,       # 'open' or 'closed'
        }
    ],
    'timeline': [               # ordered list of timeline events
        {
            'event': str,       # event type name
            'actor': str,       # GitHub username
            'created_at': str,  # ISO 8601
            'detail': str,      # human-readable summary of what changed
        }
    ],
    'comments': [
        {
            'id': int,          # GitHub comment ID (used by push for edit/delete)
            'author': str,
            'body': str,
            'created_at': str,  # ISO 8601
            'updated_at': str,  # ISO 8601
        }
    ],
    # Projects v2 fields (present only if the issue is in a tracked project;
    # None if the field does not exist on the project or the issue is not tracked)
    'project_status': Optional[str],
    'priority': Optional[str],
    'iteration': Optional[str],
    'issue_type': Optional[str],
    'estimate': Optional[float],
    'start_date': Optional[str],
    'end_date': Optional[str],
    'parent_issue': Optional[int],   # issue number of parent
    'sub_issues_progress': Optional[float],  # 0.0 to 1.0
}
```

**Note on Projects v2 fields:** `fetch_issues` fetches REST data only by default. Projects v2 fields are populated by a separate call to `ProjectUpdater.get_issue_project_fields(org, repo_name, issue_numbers)` made by the caller (the CLI) after fetching issues. The `GitHubClient` is not responsible for Projects v2 data.

### 3.7 `_build_api_params(filters: Dict) -> Dict`

| Filter key | API param | Notes |
|---|---|---|
| `state` | `state` | Defaults to `'all'` if unset |
| `author` | `creator` | |
| `assignee` | `assignee` | |
| `labels` | `labels` | Converts comma-separated string to list if needed |
| `since` | `since` | Parses `YYYY-MM-DD` string to `datetime` object |
| `milestone` | *(handled separately)* | Resolved in `fetch_issues` |
| `until` | *(not set here)* | Applied client-side in `_matches_client_filters` |

### 3.8 `_resolve_milestone(repo, milestone_value: str)`

- If `milestone_value` is `'*'` or `'none'`, returns the value as-is (passed directly to PyGithub).
- Otherwise iterates `repo.get_milestones(state='all')` and returns the first `Milestone` object whose `title` matches exactly (case-sensitive).
- If no match is found, raises `ValueError` with the message: `f"Milestone {milestone_value!r} not found in {repo.full_name}. Valid titles: {titles}. Use '*' for any milestone or 'none' for no milestone."` where `titles` is a comma-separated list of all milestone titles.

### 3.9 `_matches_client_filters(issue, filters: Dict) -> bool`

Applies client-side filters not supported by the API:
- `until`: parses as a datetime; returns `False` if `issue.created_at > until_date`. Invalid date formats are silently ignored.
- `assignee-none`: returns `False` if `issue.assignees` is non-empty.

### 3.10 `update_issue(repo_name: str, issue_number: int, changes: Dict) -> Dict`

`changes` is a dict of only the REST fields that changed. Supported keys:

| Key | Type | Notes |
|---|---|---|
| `title` | str | |
| `body` | str | |
| `state` | str | `'open'` or `'closed'` |
| `state_reason` | str | Only valid when `state` is `'closed'` |
| `labels` | List[str] | Replaces the entire label list |
| `milestone` | Optional[str] | Title string; `None` clears the milestone |
| `assignees` | List[str] | Replaces the entire assignee list |
| `locked` | bool | |
| `lock_reason` | Optional[str] | Only valid when `locked` is `True` |

Calls `repo.get_issue(issue_number)` then `issue.edit(**changes)`. Milestone title is resolved to a `Milestone` object before calling `edit`. Returns the refreshed issue dict via `_extract_issue_data`. Raises descriptive exceptions for 403 (insufficient token scope) and 404 (issue not found).

### 3.11 `get_comments(repo_name: str, issue_number: int) -> List[Dict]`

Calls `issue.get_comments()`. Returns list of comment dicts:
```python
{
    'id': int,
    'author': str,
    'body': str,
    'created_at': str,
    'updated_at': str,
}
```

### 3.12 `create_comment(repo_name: str, issue_number: int, body: str) -> Dict`

Calls `repo.get_issue(issue_number).create_comment(body)`. Returns the created comment dict (same shape as `get_comments` items). Raises a descriptive exception for 403 (insufficient token scope) and 404 (issue not found).

### 3.13 `edit_comment(repo_name: str, comment_id: int, body: str) -> Dict`

Calls `repo.get_comment(comment_id).edit(body)`. Returns the updated comment dict.

### 3.14 `delete_comment(repo_name: str, comment_id: int) -> None`

Calls `repo.get_comment(comment_id).delete()`. Raises on 404 (comment not found) with a clear error message.

### 3.15 `get_timeline_events(repo_name: str, issue_number: int) -> List[Dict]`

Calls `issue.get_timeline()`. Processes each event into a normalized dict. Only events with a recognized `event` type are included; unrecognized event types are silently skipped.

**Recognized event types and their `detail` format:**

| Event | Detail format |
|---|---|
| `labeled` | `"labeled: <label_name>"` |
| `unlabeled` | `"unlabeled: <label_name>"` |
| `assigned` | `"assigned: <assignee>"` |
| `unassigned` | `"unassigned: <assignee>"` |
| `milestoned` | `"milestoned: <milestone_title>"` |
| `demilestoned` | `"demilestoned: <milestone_title>"` |
| `renamed` | `"renamed: '<old_title>' → '<new_title>'"` |
| `closed` | `"closed"` (or `"closed as <reason>"` if state_reason is present) |
| `reopened` | `"reopened"` |
| `locked` | `"locked: <lock_reason>"` |
| `unlocked` | `"unlocked"` |
| `referenced` | `"referenced in #<number>"` |
| `cross-referenced` | `"cross-referenced in <repo>#<number>"` |

### 3.16 `get_reactions(repo_name: str, issue_number: int) -> Dict[str, int]`

Calls `issue.get_reactions()`. Aggregates by `content` field. Returns the 8-key reactions dict (all keys always present, missing types have count 0).

### 3.17 `get_collaborators(repo_name: str) -> List[str]`

Calls `repo.get_collaborators()`. Returns sorted list of GitHub usernames.

### 3.18 `get_labels(repo_name: str) -> List[Dict]`

Calls `repo.get_labels()`. Returns list of label dicts:
```python
{
    'name': str,
    'color': str,        # hex color without '#' prefix
    'description': str,  # empty string if not set
}
```

### 3.19 `get_milestones(repo_name: str) -> List[Dict]`

Calls `repo.get_milestones(state='all')`. Returns list of milestone dicts:
```python
{
    'title': str,
    'state': str,         # 'open' or 'closed'
    'due_on': Optional[str],  # ISO 8601 date or None
    'description': str,
}
```

### 3.20 `get_org_custom_fields(org: str) -> List[Dict]`

Makes a GET request to `https://api.github.com/orgs/{org}/properties/schema`. Returns list of custom field dicts:
```python
{
    'property_name': str,
    'value_type': str,     # 'string', 'single_select', 'multi_select', 'true_false', 'date'
    'required': bool,
    'allowed_values': Optional[List[str]],  # for single/multi_select; None otherwise
    'default_value': Optional[str],
}
```

Returns `[]` on 404 (org has no custom properties) or 403 (token lacks `read:org`), rather than raising.

### 3.21 `update_org_custom_fields(repo_name: str, properties: Dict[str, Any]) -> None`

Makes a PATCH request to `https://api.github.com/repos/{owner}/{repo}/properties/values` with body `{"properties": [{"property_name": k, "value": v} for k, v in properties.items()]}`. Raises on 4xx responses with a clear error message.

### 3.22 `fetch_issue(repo_name: str, issue_number: int) -> Optional[Dict]`

Fetches a single issue by number.

**Steps:**
1. Calls `self.client.get_repo(repo_name)`.
2. Calls `repo.get_issue(issue_number)`.
3. If the issue is a pull request (`issue.pull_request` is truthy), returns `None`.
4. Calls `_extract_issue_data(issue)`.
5. Calls `get_timeline_events(repo_name, issue_number)` and `get_reactions(repo_name, issue_number)` and appends both to the dict.
6. Appends `linked_pull_requests` from the issue relation.
7. Returns the issue dict (same shape as a single element from `fetch_issues`).

Returns `None` if the issue is a pull request. Raises `ValueError` with a clear message on 404 (issue not found) or 403 (insufficient token scope). Does **not** populate Projects v2 fields; the caller must call `ProjectUpdater.get_issue_project_fields` separately if Projects v2 data is needed.

---

## 4. IssueStorage

**Module:** `src/storage.py`

### 4.1 Constructor

```python
IssueStorage(base_dir: str = None)
```

Resolves the base directory using `_get_default_base_dir()`:
1. Reads `PROJECT_CONTEXT_DIR` from the environment.
2. If set, expands tilde and returns `$PROJECT_CONTEXT_DIR/github-issues`.
3. Otherwise returns `"issues"` (relative to the working directory).

Creates the base directory if it does not exist.

### 4.2 Directory Naming

`get_repo_dir(repo_name)` converts `owner/repo` to `owner-repo` and creates the directory under `base_dir` if it does not exist.

### 4.3 `save_issue(repo_name: str, issue_data: Dict) -> str`

1. Generates markdown content via `_generate_markdown(issue_data)`.
2. Writes to `<repo_dir>/issue-<number>.md` (UTF-8).
3. Computes `file_hash = SHA-256(markdown_content.encode('utf-8'))`.
4. Calls `_update_metadata(repo_name, issue_data, file_hash=file_hash)`.
5. Returns the file path as a string.

### 4.4 `_generate_markdown(issue_data: Dict) -> str`

Produces a markdown string with the following structure:

```
---
<YAML frontmatter>
---

# <title>

<body>

## Comments

### Comment #<id> by <author> on <created_at>

<comment body>

## Timeline

- <created_at> — <detail> (by <actor>)
```

**Frontmatter fields (in this order):**

Always present: `number`, `title`, `state`, `state_reason`, `locked`, `lock_reason`, `labels`, `author`, `created_at`, `updated_at`, `assignees`, `milestone`, `url`.

Conditionally included (omitted when `None`): `closed_at`.

Always present (even when `None`): `project_status`, `priority`, `iteration`, `issue_type`, `estimate`, `start_date`, `end_date`, `parent_issue`, `sub_issues_progress`.

Always present: `linked_pull_requests` (empty list `[]` if none), `reactions` (all 8 keys).

Serialized with `yaml.dump(..., allow_unicode=True, default_flow_style=False)`.

**Comments section:** Omitted entirely if the issue has no comments. Each comment heading includes the GitHub comment ID: `### Comment #<id> by <author> on <created_at>`. Comment body follows on the next line after a blank line.

**Timeline section:** Omitted entirely if the issue has no timeline events. Each entry is a bullet point: `- <created_at> — <detail> (by <actor>)`.

### 4.5 `_update_metadata(repo_name, issue_data, file_hash=None)`

Reads existing `.metadata.json` or starts from `{'filters': {}, 'issues': {}}`. Computes the content hash via `_calculate_hash(issue_data)`. Writes the entry for `str(issue_data['number'])`:

```json
{
    "hash": "<content hash>",
    "file_hash": "<file content hash>",
    "updated_at": "<ISO 8601>",
    "state": "open|closed",
    "snapshot": {
        "<all writable field key-value pairs>"
    }
}
```

`snapshot` stores the values of all writable fields at the time the file was last written. This is the reference point used by `push` to identify which fields changed. The snapshot includes: `title`, `body`, `state`, `state_reason`, `labels`, `milestone`, `assignees`, `locked`, `lock_reason`, `project_status`, `priority`, `iteration`, `issue_type`, `estimate`, `start_date`, `end_date`, `parent_issue`, `org_custom_fields` (the full dict of org-level properties), and a list of `{id, body}` dicts for all comments.

### 4.6 `_calculate_hash(issue_data: Dict) -> str`

Normalizes a subset of issue fields into a deterministic JSON string and returns its SHA-256 hex digest.

**Fields included:**
- `number`, `title`, `body`, `state`
- `labels` — sorted
- `assignees` — sorted
- `updated_at`
- `comments` — list of `{id, author, body, created_at}` in comment ID order
- `project_status`, `priority`, `iteration`, `issue_type` — included as-is (string or `None`)
- `estimate`, `start_date`, `end_date`, `parent_issue` — included as-is

**Rationale:** GitHub Projects v2 field changes (Status, Priority, Iteration, etc.) do **not** update the issue's REST `updated_at` timestamp. Without including these fields in the hash, upstream project field changes would never be detected during incremental sync. All Projects v2 fields are included so that any remote change to any tracked field triggers a file refresh.

Serialized with `json.dumps(..., sort_keys=True)`. Missing keys are normalized to `None` before serialization so that issues without a Projects v2 connection hash consistently.

### 4.7 `load_metadata(repo_name: str) -> Dict`

Returns `{'filters': {}, 'issues': {}}` if no metadata file exists.

**Backward compatibility:** If the loaded JSON does not contain a `filters` key (old format), all non-`filters`/non-`issues` top-level keys are treated as issue entries.

### 4.8 `save_filters(repo_name: str, filters: Dict)`

Loads existing metadata, sets `metadata['filters'] = filters`, writes back.

### 4.9 `load_filters(repo_name: str) -> Dict`

Returns `metadata.get('filters', {})`.

### 4.10 `issue_exists(repo_name: str, issue_number: int) -> bool`

Returns whether `<repo_dir>/issue-<number>.md` exists.

### 4.11 `get_all_issue_numbers(repo_name: str) -> List[int]`

Globs `<repo_dir>/issue-*.md`. Parses the integer from the stem. Returns sorted list.

### 4.12 `read_issue(repo_name: str, issue_number: int) -> Optional[Dict]`

Parses a stored markdown file back into a dict.

**Parsing steps:**
1. Splits content on `'---\n'` (maximum 2 splits). Requires at least 3 parts.
2. Parses the YAML frontmatter block. All frontmatter keys are returned in the dict directly.
3. Scans remaining lines: skips until a line starting with `# ` (the title heading), then collects lines until `## Comments`, `## Timeline`, or end of file.
4. Strips the body.
5. Parses the `## Comments` section if present. Each `### Comment #<id> by <author> on <created_at>` heading starts a comment entry. Entries with `### DELETE Comment #<id>` headings are flagged with `{'_delete': True}`. Entries with `### Comment by <author>` headings (no `#id`) are flagged with `{'_new': True}`. Comment body follows the heading.
6. Parses the `## Timeline` section if present (read-only; returned but not used for push).

Returns `None` on any parse error.

### 4.13 `load_issue_snapshot(repo_name: str, issue_number: int) -> Optional[Dict]`

Returns `metadata['issues'][str(number)].get('snapshot')`, or `None` if not present.

### 4.14 `get_stored_file_hash(repo_name: str, issue_number: int) -> Optional[str]`

Returns `metadata['issues'][str(number)].get('file_hash')`, or `None` if not present.

### 4.15 `compute_current_file_hash(repo_name: str, issue_number: int) -> Optional[str]`

Reads the on-disk file (UTF-8) and returns `SHA-256(content.encode('utf-8'))` as a hex string. Returns `None` if the file does not exist.

### 4.16 `write_schema(repo_name: str, schema_data: Dict) -> None`

Writes two files to the repository directory:
- `.schema.md` — via `self._generate_schema_md(schema_data)` (see §4.22)
- `.schema.json` — via `json.dumps(schema_data, indent=2, ensure_ascii=False)`

Both files are written atomically (write to a temp file, then rename) so that a crash during write does not leave a partially-written schema file that could corrupt validation.

### 4.17 `load_schema(repo_name: str) -> Optional[Dict]`

Reads and parses `<repo_dir>/.schema.json`. Returns `None` if the file does not exist.

### 4.18 `load_issues(repos: List[str], filter_spec: Dict) -> List[Dict]`

For each repository in `repos`:
1. Calls `get_all_issue_numbers(repo)`.
2. For each issue number, calls `read_issue(repo, number)`.
   - If `read_issue` returns `None` (parse failure), prints a warning to stderr: `Warning: Could not parse issue-<N>.md in <repo> — skipping.` and continues to the next issue number.
3. Applies `filter_spec` against the parsed dict fields (see Section 11.3 for filter semantics). Client-side filters are applied as AND logic (all specified filters must match).
4. Attaches `_repo` key to each matching issue dict so callers know which repo it came from.

Returns a flat list of all matching issue dicts across all repos.

### 4.19 `write_report(output_name: str, content: str) -> str`

Writes `reports/<output_name>.md`. Creates the `reports/` directory if it does not exist. Returns the file path.

### 4.20 `load_report_template(config: Dict, name: str) -> Dict`

Returns `config['reports'][name]`. Raises a `KeyError`-based error with the list of available template names if `name` is not found or `config` has no `reports` key.

### 4.21 `get_schema_status(repo_name: str) -> Dict`

Returns file-system metadata about the schema files for a repository. Used by the `status` command.

**Return shape:**
```python
{
    'schema_md_exists': bool,
    'schema_json_exists': bool,
    'schema_md_mtime': Optional[str],   # ISO 8601 datetime string, or None if file absent
    'schema_json_mtime': Optional[str], # ISO 8601 datetime string, or None if file absent
}
```

Uses `os.path.getmtime()` and `datetime.fromtimestamp(...).isoformat()` to produce the mtime strings.

### 4.22 `_generate_schema_md(schema_data: Dict) -> str`

Renders the `.schema.md` human-readable document from the canonical schema dict produced by `SchemaManager._build_schema_data`. This method lives in `IssueStorage` (alongside `_generate_markdown` for issues) to keep all file-rendering logic in one module.

**Output format:**

```markdown
# Field Schema — owner/repo

Last refreshed: YYYY-MM-DD HH:MM:SS

## Standard Issue Fields

| Field | Type | Writable |
[table of all standard REST fields with type and write access from PRD data model]

## Labels

| Name | Color | Description |
[table rows]

## Milestones

| Title | State | Due Date |
[table rows]

## Team Members (valid assignees)

| Display Name | GitHub Username | Role | Collaborator |
[table rows, ✓/✗ for collaborator]

Note: members marked ✗ are not collaborators on this repository and cannot be assigned here.

## All Repository Collaborators

[list of usernames not in team roster]

## Projects v2: <Project Title>

### Fields

| Field Name | Type | Writable |
[table rows]

### <single-select field name> Options

[list]

### Iterations

| Title | Start Date | Duration (days) | State |
[table rows]

## Org-level Custom Fields

| Field Name | Type | Valid Values |
[table rows]
```

If a section has no data (e.g., no Projects v2 boards, no org custom fields), that section is omitted entirely rather than rendered with empty tables.

---

## 5. ChangeTracker

**Module:** `src/tracker.py`  
**Depends on:** `IssueStorage`

### 5.1 Constructor

```python
ChangeTracker(storage: IssueStorage)
```

### 5.2 `detect_changes(repo_name: str, current_issues: List[Dict]) -> Dict`

**Returns:**
```python
{
    'new': List[Dict],               # full issue dicts not previously stored
    'updated': List[Dict],           # dicts of {issue: Dict, changes: List[str]}
    'unchanged': List[int],          # issue numbers with matching hashes
}
```

**Algorithm:**
1. Loads `.metadata.json` for the repo.
2. Builds a set of stored issue number strings.
3. For each issue in `current_issues`:
   - Computes `IssueStorage._calculate_hash(issue)`.
   - If the number is not in stored keys → appends to `new`.
   - If hash differs from stored `hash` → calls `_detect_issue_changes()` and appends to `updated`.
   - If hash matches → appends the issue number (as int) to `unchanged`.

### 5.3 `_detect_issue_changes(repo_name, current_issue, stored_metadata) -> List[str]`

Compares the current issue against stored metadata fields and returns human-readable change descriptions.
- If `stored_metadata['state'] != current_issue['state']`: appends `"State changed from '<old>' to '<new>'"`.
- If `stored_metadata['updated_at'] != current_issue['updated_at']`: appends `"Updated at <timestamp>"`.
- If neither check added a description: appends `"Content modified"`.

### 5.4 `get_deleted_issues(repo_name: str, current_issues: List[Dict]) -> List[int]`

Returns sorted list of issue numbers present in `.metadata.json` but absent from `current_issues`. Available but not called by any CLI command.

---

## 6. ChangeReporter

**Module:** `src/reporter.py`  
**Scope:** Handles sync change reports only. Ad-hoc user-defined reports are handled by `ReportEngine` (Section 9).

### 6.1 Constructor

```python
ChangeReporter(reports_dir: str = "reports")
```

Creates the reports directory if it does not exist.

### 6.2 `generate_report(repo_changes: Dict[str, Dict]) -> str`

**Input format:**
```python
{
    'owner/repo': {
        'new': [issue_dict, ...],
        'updated': [{'issue': issue_dict, 'changes': [str, ...]}, ...],
        'unchanged': [int, ...]
    }
}
```

Generates a timestamp string `YYYY-MM-DD-HH-MM-SS` using `datetime.now()`. Writes the report to `reports/changes-<timestamp>.md`. Returns the file path.

### 6.3 Report File Format

```markdown
# GitHub Issues Change Report

**Generated:** YYYY-MM-DD HH:MM:SS

## Summary

- **New Issues:** N
- **Updated Issues:** N
- **Unchanged Issues:** N
- **Repositories Checked:** N

## Changes by Repository

### owner/repo

#### New Issues (N)

- **#42**: Issue title
  - State: open
  - Author: username
  - Created: 2025-01-01T10:00:00
  - Labels: bug, urgent
  - URL: https://github.com/...

#### Updated Issues (N)

- **#7**: Issue title
  - URL: https://github.com/...
  - Changes:
    - State changed from 'open' to 'closed'

---

*Report generated by GitHub Issue Manager*
```

Repositories with no new or updated issues show `No changes detected.`.

### 6.4 `print_summary(repo_changes: Dict[str, Dict])`

Prints totals and per-repository new/updated/unchanged counts to stdout. Shows up to five new and five updated issue titles per repository.

---

## 7. ProjectUpdater

**Module:** `src/project_updater.py`  
**API endpoint:** `https://api.github.com/graphql`  
**Authenticates via:** Bearer token in `Authorization` header

### 7.1 Constructor

```python
ProjectUpdater()
```

Calls `load_dotenv()`. Reads `GITHUB_TOKEN`. Raises `ValueError` if not set. Creates a `requests.Session` with `Authorization: Bearer <token>` and `Content-Type: application/json` headers.

### 7.2 `_run_query(query: str, variables: Optional[Dict] = None) -> Dict`

POSTs to the GraphQL endpoint with a 30-second timeout. Calls `resp.raise_for_status()`. Parses JSON. If `errors` is present in the response body, raises an exception. If the error message contains `INSUFFICIENT_SCOPES`, includes a hint about the required `project` scope.

### 7.3 GraphQL Documents

| Constant | Operation | Key variables |
|---|---|---|
| `_LIST_PROJECTS_QUERY` | Query | `org: String!`, `cursor: String` — paginates 50 projects at a time |
| `_GET_ALL_FIELDS_QUERY` | Query | `projectId: ID!` — fetches up to 100 fields of all types |
| `_GET_PROJECT_FIELDS_QUERY` | Query | `projectId: ID!` — fetches only `ProjectV2SingleSelectField` nodes. **Dead code:** retained for backward compatibility with existing direct callers but not used by any method in this module. New code must use `_GET_ALL_FIELDS_QUERY` via `get_all_project_fields`. |
| `_GET_PROJECT_ITEMS_QUERY` | Query | `projectId: ID!`, `cursor: String` — paginates 100 items at a time |
| `_UPDATE_SINGLE_SELECT_MUTATION` | Mutation | `projectId`, `itemId`, `fieldId`, `optionId` |
| `_UPDATE_ITERATION_MUTATION` | Mutation | `projectId`, `itemId`, `fieldId`, `iterationId` |
| `_UPDATE_NUMBER_MUTATION` | Mutation | `projectId`, `itemId`, `fieldId`, `number` |
| `_UPDATE_DATE_MUTATION` | Mutation | `projectId`, `itemId`, `fieldId`, `date` |
| `_UPDATE_TEXT_MUTATION` | Mutation | `projectId`, `itemId`, `fieldId`, `text` |

All mutations call `updateProjectV2ItemFieldValue` with a `value` union discriminated by field type.

### 7.4 `list_projects(org: str) -> List[Dict]`

Paginates `_LIST_PROJECTS_QUERY` until `hasNextPage` is false. Returns list of `{id, number, title, url}` dicts.

### 7.5 `find_project(org: str, project_name: str) -> Dict`

Calls `list_projects(org)`. Filters by exact `title` match (case-sensitive). Raises with list of available project titles if no match.

### 7.6 `get_all_project_fields(project_id: str) -> List[Dict]`

Calls `_GET_ALL_FIELDS_QUERY`. Returns a list of field dicts:

```python
{
    'id': str,          # node ID
    'name': str,        # display name
    'type': str,        # 'single_select', 'iteration', 'number', 'date', 'text'
    'options': [        # present for single_select fields only
        {'id': str, 'name': str}
    ],
    'iterations': [     # present for iteration fields only
        {
            'id': str,
            'title': str,
            'start_date': str,   # ISO 8601 date
            'duration': int,     # days
            'state': str,        # 'active', 'upcoming', 'completed'
        }
    ],
}
```

### 7.7 `get_status_field(project_id: str) -> Dict`

Calls `get_all_project_fields`. Finds the field whose `name.lower() == 'status'`. Returns `{'field_id': str, 'options': {name: id}}`. Raises if no Status field found.

### 7.8 `list_available_statuses(org: str, project_name: str) -> List[str]`

Calls `find_project` then `get_status_field`. Returns sorted list of option names.

### 7.9 `find_project_item(project_id: str, repo_name: str, issue_number: int) -> Optional[str]`

Paginates `_GET_PROJECT_ITEMS_QUERY` (100 items per page). Checks `content.repository.nameWithOwner == repo_name` and `content.number == issue_number`. Returns item node ID or `None`.

### 7.10 `update_status(org, project_name, repo_name, issue_number, new_status) -> None`

1. `find_project` → `project_id`
2. `get_status_field` → `{field_id, options}`
3. Validates `new_status` is in `options`. Raises with available options if not.
4. `find_project_item` → `item_id`. Raises if `None`.
5. `_run_query(_UPDATE_SINGLE_SELECT_MUTATION, {...})`

### 7.11 `update_field(org: str, project_name: str, repo_name: str, issue_number: int, field_name: str, value: Any) -> None`

Generalized field update.

1. `find_project` → `project_id`
2. `get_all_project_fields` → list of field dicts
3. Finds the field whose `name.lower() == field_name.lower()`. Raises if not found, with list of available field names.
4. `find_project_item` → `item_id`. Raises if `None`.
5. Selects the appropriate mutation based on field `type`:
   - `single_select` → resolves `value` to an option ID (case-insensitive match on `name`). Raises if not found. Calls `_UPDATE_SINGLE_SELECT_MUTATION`.
   - `iteration` → resolves `value` (or `'current'` for the active iteration) to an iteration ID. Calls `_UPDATE_ITERATION_MUTATION`.
   - `number` → converts `value` to `float`. Calls `_UPDATE_NUMBER_MUTATION`.
   - `date` → validates `value` as ISO 8601 date. Calls `_UPDATE_DATE_MUTATION`.
   - `text` → calls `_UPDATE_TEXT_MUTATION`.

### 7.12 `get_issue_project_fields(org: str, repo_name: str, issue_numbers: List[int]) -> Dict[int, Dict]`

Paginates `_GET_PROJECT_ITEMS_QUERY` and extracts field values for the specified issue numbers. Returns a dict mapping issue number to a dict of `{field_name_lower: value}`. Used by the CLI to populate Projects v2 fields on fetched issues.

---

## 8. SchemaManager

**Module:** `src/schema_manager.py`

### 8.1 Constructor

```python
SchemaManager(github_client: GitHubClient, project_updater: ProjectUpdater, storage: IssueStorage)
```

Stores references to the three collaborating objects.

### 8.2 `refresh_schema(repo_name: str, config: Dict) -> None`

Main entry point. Orchestrates all fetch and write steps.

1. Calls `_fetch_rest_schema_data(repo_name, config)` → REST schema dict.
2. Determines the org from the `owner` portion of `repo_name`.
3. Calls `ProjectUpdater.list_projects(org)` to discover Projects v2.
4. For each project, calls `ProjectUpdater.get_all_project_fields(project_id)` → project fields.
5. Calls `GitHubClient.get_org_custom_fields(org)` → org custom fields.
6. Calls `_build_schema_data(rest_data, projects_data, org_fields, config)` → schema dict.
7. Calls `IssueStorage.write_schema(repo_name, schema_data)`.

Raises `SchemaRefreshError` (a project-local exception class) on any failure. The caller catches this and prints a warning.

### 8.3 `_fetch_rest_schema_data(repo_name: str, config: Dict) -> Dict`

Calls in parallel (or sequentially if parallel is not available):
- `GitHubClient.get_labels(repo_name)` → labels
- `GitHubClient.get_milestones(repo_name)` → milestones
- `GitHubClient.get_collaborators(repo_name)` → collaborators

Returns:
```python
{
    'labels': [{'name': str, 'color': str, 'description': str}],
    'milestones': [{'title': str, 'state': str, 'due_on': Optional[str], 'description': str}],
    'collaborators': [str],   # list of GitHub usernames
}
```

### 8.4 `_build_schema_data(rest_data, projects_data, org_fields, config) -> Dict`

Assembles the canonical schema dict that is both serialized to `.schema.json` and used to render `.schema.md`.

```python
{
    'repo': str,
    'refreshed_at': str,       # ISO 8601 datetime
    'labels': [...],           # from rest_data
    'milestones': [...],       # from rest_data
    'collaborators': [
        {
            'username': str,
            'display_name': Optional[str],   # from team roster if found
            'role': Optional[str],           # from team roster if found
            'is_team_member': bool,
        }
    ],
    'team_members_not_collaborators': [str],  # display names of team members not in collaborator list
    'projects': [
        {
            'id': str,
            'title': str,
            'url': str,
            'fields': [...]    # from get_all_project_fields
        }
    ],
    'org_custom_fields': [...],  # from get_org_custom_fields
}
```

**Collaborator cross-reference:** For each GitHub username in `rest_data['collaborators']`, looks up whether the username appears in `config['team']`. If found, sets `display_name`, `role`, and `is_team_member=True`. Otherwise `display_name=None`, `role=None`, `is_team_member=False`. Also computes `team_members_not_collaborators` by finding team members whose `username` does not appear in the collaborators list.

### 8.5 `_generate_schema_md` — moved to `IssueStorage`

Schema markdown rendering is handled by `IssueStorage._generate_schema_md` (§4.22). This keeps all file-rendering logic in a single module, consistent with `IssueStorage._generate_markdown` for issue files. `SchemaManager` builds the `schema_data` dict and passes it to `IssueStorage.write_schema`; the storage layer is solely responsible for rendering and writing both `.schema.md` and `.schema.json`.

---

## 9. ReportEngine

**Module:** `src/report_engine.py`

### 9.1 Constructor

```python
ReportEngine(storage: IssueStorage)
```

### 9.2 `generate(repos: List[str], filter_spec: Dict, grouping: Optional[str], format: str, sort_by: str, output_name: str, team_roster: List[Dict]) -> str`

Main entry point.

1. Calls `IssueStorage.load_issues(repos, filter_spec)` → list of matching issue dicts.
2. If no issues match, writes a report noting zero results and returns the path.
3. Calls `_sort_issues(issues, sort_by)`.
4. If `grouping` is set, calls `_group_issues(issues, grouping)` → `{group_value: [issues]}`.
5. Calls the appropriate render method based on `format`.
6. Resolves all GitHub usernames to display names in the rendered output via `_resolve_display_name(username, team_roster)`.
7. Calls `IssueStorage.write_report(output_name, content)`.
8. Returns the file path.

### 9.3 `_apply_scope(filter_spec: Dict, scope_milestones: Optional[List[str]]) -> Dict`

If `filter_spec` does not already contain a `milestone` key and `scope_milestones` is not `None`, sets `filter_spec['milestone']` to the first scope milestone (or applies a multi-value milestone match). Returns the merged filter spec.

Note: scope is applied by the CLI before calling `generate`; this method is available for internal use.

### 9.4 `_sort_issues(issues: List[Dict], sort_by: str) -> List[Dict]`

Valid `sort_by` values: `number` (default), `created_at`, `updated_at`, `title`. Returns a new sorted list. Unknown `sort_by` values fall back to `number`.

### 9.5 `_group_issues(issues: List[Dict], grouping: str) -> Dict[str, List[Dict]]`

Valid `grouping` values: `assignee`, `status`, `label`, `milestone`, `iteration`, `priority`, `issue_type`, `state`.

For multi-value fields (`assignee`, `label`): an issue appears in all groups that apply. An issue with no value for the grouping field appears under the key `"(none)"`.

Returns an `OrderedDict` with group keys sorted alphabetically. `"(none)"` always sorts last.

### 9.6 `_render_table(issues: List[Dict], grouping: Optional[str] = None) -> str`

Produces a markdown table with columns: `#`, `Title`, `State`, `Assignee(s)`, `Milestone`, `Labels`.

If `grouping` is set, renders one table per group under a `### <group>` heading.

Assignees are rendered as display names (comma-separated if multiple).

### 9.7 `_render_list(issues: List[Dict], grouping: Optional[str] = None) -> str`

Produces a markdown list. Each entry includes all frontmatter fields but no body or comments. Format:

```markdown
### #42 — Bug in login form

- **State:** open
- **Assignee:** John Smith (jsmith123)
- **Milestone:** v2.0
- **Labels:** bug, high-priority
- **Status:** In Progress
- **Priority:** High
- **Iteration:** Sprint 4
- **URL:** https://github.com/...
```

### 9.8 `_render_full(issues: List[Dict], grouping: Optional[str] = None) -> str`

Produces the complete issue content including title, all fields, body, and comments — identical in structure to the stored markdown file but potentially re-ordered or filtered. Used for export or detailed review.

### 9.9 `_render_grouped(issues: List[Dict], grouping: str) -> str`

Groups issues under `## <group>` headings, with a `_render_list`-style entry per issue under each heading. If no `grouping` is specified when format is `grouped`, raises a `ValueError` instructing the caller to provide `--group-by`.

### 9.10 `_resolve_display_name(username: str, team_roster: List[Dict]) -> str`

Returns `"Display Name (username)"` if a mapping exists, else returns the raw `username`.

---

## 10. BulkEditor

**Module:** `src/bulk_editor.py`

### 10.1 Constructor

```python
BulkEditor(github_client: GitHubClient, project_updater: ProjectUpdater, storage: IssueStorage)
```

### 10.2 `run(repos: List[str], filter_spec: Dict, field: str, value: str, dry_run: bool, config: Dict) -> Dict`

Main entry point.

1. Calls `IssueStorage.load_issues(repos, filter_spec)` → matching issues.
2. For each matching issue, calls `IssueStorage.load_schema(repo)` to get the schema.
3. Calls `_classify_field(field)` → `'rest'`, `'graphql'`, or raises `ValueError` for unknown fields.
4. Calls `_validate_field_value(field, parsed_value, schema)` for each issue's repo. Collects all validation errors. If any exist, prints all errors and exits without writing.
5. Prints a preview table with: `#`, `Repo`, `Title`, `Current <field>`, `→ New <field>`.
6. If `dry_run=True`: prints `[dry-run] No changes made.` and returns a summary dict.
7. Prompts for confirmation: `Apply changes to N issues? [y/N]`. If the user declines, exits.
8. For each issue:
   - Calls `_apply_change(issue, field, parsed_value, config)`.
   - Calls `IssueStorage.save_issue(repo, refreshed_issue)`.
9. Returns summary dict: `{'applied': int, 'failed': int, 'skipped': int}`.

**Returns:**
```python
{
    'applied': int,
    'failed': int,
    'skipped': int,
}
```

### 10.3 `_classify_field(field: str) -> str`

Consults the field routing table in Section 11.1. Returns `'rest'` or `'graphql'`. Raises `ValueError` with a list of valid field names if the field is not recognized.

### 10.4 `_validate_field_value(field: str, value: Any, schema: Dict) -> Optional[str]`

Returns an error string if the value is invalid for the field, or `None` if valid.

Validation rules are defined in Section 11.2.

### 10.5 `_apply_change(issue: Dict, field: str, value: Any, config: Dict) -> Dict`

Routes the write to the correct API and returns the refreshed issue dict.

- REST field: calls `GitHubClient.update_issue(repo, number, {field: value})`. Returns the refreshed issue dict directly (no extra fetch needed; `update_issue` returns the GitHub-authoritative data).
- GraphQL field: calls `ProjectUpdater.update_field(org, project, repo, number, field, value)`. Then calls `GitHubClient.fetch_issue(repo, number)` to retrieve the refreshed issue dict. `org` is inferred from the owner portion of the repo name.

The `org` is inferred from the `owner` portion of the repo name. If multiple projects exist, uses the project named in `config.yaml` under the repository's scope; if no project is specified in config and multiple exist, raises an error instructing the user to specify a project.

---

## 11. Field Routing and Validation

### 11.1 Field Routing Table

All writable fields and their API surface:

| Field name (in file / CLI) | API | Notes |
|---|---|---|
| `title` | REST | |
| `body` | REST | |
| `state` | REST | `'open'` or `'closed'` |
| `state_reason` | REST | Only when closing; `'completed'` or `'not_planned'` |
| `labels` | REST | Array; replaces entire list |
| `milestone` | REST | Title string or `null` to clear |
| `assignees` | REST | Array; replaces entire list |
| `locked` | REST | Boolean |
| `lock_reason` | REST | Only when locking; must be `'off-topic'`, `'too heated'`, `'resolved'`, or `'spam'` |
| `project_status` | GraphQL | Single-select; valid options in `.schema.json` |
| `priority` | GraphQL | Single-select; valid options in `.schema.json` |
| `iteration` | GraphQL | Iteration; valid values in `.schema.json`; `'current'` resolves to active |
| `issue_type` | GraphQL | Single-select; valid options in `.schema.json` |
| `estimate` | GraphQL | Numeric; no schema constraint beyond type |
| `start_date` | GraphQL | ISO 8601 date string |
| `end_date` | GraphQL | ISO 8601 date string |
| `parent_issue` | GraphQL | Issue number (integer) |
| `org_custom_fields.<property_name>` | org-REST | See below |

**Org-level custom fields** are stored in the YAML frontmatter under a nested `org_custom_fields` map:

```yaml
org_custom_fields:
  team_area: "Platform"
  priority_level: "P1"
```

In CLI commands, they are referenced using dot notation: `--set org_custom_fields.team_area=Platform`. The `push` command detects changes to any key within `org_custom_fields` and routes the entire changed map to `GitHubClient.update_org_custom_fields(repo_name, changed_properties)`. Validation checks each property name and value against `schema_data['org_custom_fields']` before writing.

Read-only fields (`reactions`, `linked_pull_requests`, `timeline`, `sub_issues_progress`, `author`, `created_at`, `url`, `number`, `closed_at`) cannot appear in a `push` change set or a `--set` argument. If detected in a push diff, they are silently ignored. If passed to `bulk-edit --set`, the command exits with an error.

### 11.2 Validation Rules

| Field | Validation |
|---|---|
| `state` | Must be `'open'` or `'closed'` |
| `state_reason` | Must be `'completed'` or `'not_planned'`; only valid when `state == 'closed'` in the same change set |
| `labels` | Each label name must appear in `.schema.json['labels']`; case-sensitive match |
| `milestone` | Title must appear in `.schema.json['milestones']`, or be `null`/empty to clear |
| `assignees` | Each username must appear in `.schema.json['collaborators']` (by `username` key); display names are resolved to usernames first via the team roster |
| `locked` | Must be boolean |
| `lock_reason` | Must be one of `'off-topic'`, `'too heated'`, `'resolved'`, `'spam'`; only valid when `locked == True` in the same change set |
| `project_status` | Must appear in `options.name` list for the Status field in `.schema.json['projects'][*]['fields']` |
| `priority` | Must appear in `options.name` list for the Priority field |
| `iteration` | Must appear in `iterations.title` list for the iteration field, or be `'current'`; `'current'` is valid even if no active iteration exists (it resolves at write time) |
| `issue_type` | Must appear in `options.name` list for the issue type field |
| `estimate` | Must be a non-negative number (int or float) |
| `start_date` | Must be a valid ISO 8601 date string (`YYYY-MM-DD`) |
| `end_date` | Must be a valid ISO 8601 date string (`YYYY-MM-DD`) |
| `parent_issue` | Must be a positive integer; no cross-reference check against stored issues |

**When `.schema.json` does not exist:** Constrained fields (`labels`, `milestone`, `assignees`, `project_status`, `priority`, `iteration`, `issue_type`) cannot be validated. The push/bulk-edit command prints a warning that schema validation is skipped for this repo and recommends running `python -m src schema` first. Unconstrained fields are written without validation. This is a degraded-mode behavior, not a hard failure.

**Error format:** Validation errors are reported as:
```
Validation error for issue #42 (owner/repo):
  - labels: 'does-not-exist' is not a valid label. Valid labels: bug, enhancement, ...
  - assignees: 'unknown-user' is not a collaborator on owner/repo.
```

All errors for a single issue are collected before printing. Issues with validation errors are skipped; other issues in the same run are unaffected.

### 11.3 Filter Specification

Filters are used by `fetch_issues`, `load_issues`, `report`, and `bulk-edit`. The same key set is supported everywhere:

| Key | Type | Semantics |
|---|---|---|
| `state` | `'open'`, `'closed'`, `'all'` | Issue state; default `'all'` |
| `author` | GitHub username | Issues created by this user |
| `assignee` | GitHub username or display name | Issues assigned to this user; resolved to username via team roster |
| `assignee-none` | flag (bool) | Issues with no assignee |
| `labels` | comma-separated string or list | Issues must have all specified labels |
| `milestone` | title, `'*'`, `'none'`, or `None` | `'*'` = any milestone; `'none'` = no milestone; `None` = no filter |
| `since` | `YYYY-MM-DD` | Issues created or updated after this date |
| `until` | `YYYY-MM-DD` | Issues created before this date (client-side) |
| `project-status` | string | Filter by Projects v2 Status value (applied client-side from stored file) |
| `iteration` | title or `'current'` | Filter by Projects v2 iteration (applied client-side; `'current'` matches the iteration marked active in `.schema.json`) |
| `priority` | string | Filter by Projects v2 Priority value (client-side) |
| `issue-type` | string | Filter by issue type (client-side) |

**Scope inheritance:** When `config.yaml` has `scope.milestones`, all commands that accept a milestone filter default to that scope. Because the GitHub REST API accepts only a single milestone title per request, commands that call `GitHubClient.fetch_issues` make one API call per milestone title in the scope list and merge the results (deduplicating by issue number). Client-side filtering (for `load_issues`, `report`, `bulk-edit`) applies OR logic: an issue matches if its `milestone` field equals any value in the scope list. An explicit `--milestone` flag or a `milestone` key in a template overrides the scope for that run and uses a single API call. Passing `--milestone all` sets `milestone = None` (no filter, single API call).

**Client-side filters:** `until`, `assignee-none`, `project-status`, `iteration`, `priority`, `issue-type` are always applied locally after data is loaded from disk or returned from the API. They cannot be pushed to the GitHub API and are not included in `_build_api_params`.

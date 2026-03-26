# Product Requirements Document — GitHub Issue Manager

**Version:** 2.1 (Vision)
**Last updated:** March 2026

---

## Overview

GitHub Issue Manager is a command-line tool that provides a complete local interface for GitHub issues. It downloads issues as structured markdown files, keeps them synchronized with GitHub, and allows any field on an issue — title, body, labels, assignees, milestone, status, priority, comments, and more — to be read and edited locally, then pushed back to GitHub using the appropriate API. It also generates structured reports from locally stored issue data on demand.

The system is designed to work natively with AI coding tools such as Cursor. Issues are plain text files that AI agents can read, annotate, and edit. Every write-back to GitHub is explicit and previewed before execution.

---

## Problem

GitHub's web interface and REST API do not provide a simple way to maintain a continuously-updated local copy of issues in a format that is useful for AI tools and local text workflows. Developers need to:

- Load issue context into AI coding assistants without copying and pasting
- Edit issue fields (title, body, labels, status, priority, comments) from their editor without switching to a browser
- Detect when upstream issues change and refresh local copies automatically
- Understand what field values are valid before making edits (which labels exist, which statuses a project supports, what milestones are available)
- Generate custom reports from issue data without writing one-off scripts

None of these needs are well served by the GitHub web UI or by raw API access. This tool bridges that gap.

---

## Target Users

- Individual developers who use AI coding assistants and want GitHub issues available as local context files
- Team leads and project managers who need to triage, prioritize, and update multiple issues quickly from a terminal
- Small teams tracking work across multiple repositories or GitHub Projects
- AI agents (Cursor, Claude Code, etc.) acting on behalf of developers to read and write issue fields

---

## Issue Data Model

This section maps every field that the system can read or write to its API surface, data type, and constraint behavior. This model is the foundation for all capabilities described below.

### GitHub REST API — Issue Fields

These fields live directly on the issue object and are accessed via the GitHub REST API.

| Field | Type | Access | Valid Values / Constraints |
|---|---|---|---|
| Title | string | Read / Write | Free text |
| Body | string | Read / Write | Free text (markdown) |
| State | enum | Read / Write | `open`, `closed` |
| State Reason | enum | Read / Write | `completed`, `not_planned` (only when closing) |
| Labels | array of strings | Read / Write | Constrained to labels configured on the repository |
| Milestone | string (title) | Read / Write | Constrained to milestones configured on the repository |
| Assignees | array of usernames | Read / Write | Constrained to collaborators on the repository |
| Lock Status | bool | Read / Write | `true` (locked), `false` (unlocked) |
| Lock Reason | enum | Read / Write | `off-topic`, `too heated`, `resolved`, `spam` |

### GitHub REST API — Comments

Comments are a sub-resource of an issue and have their own endpoints.

| Operation | Access |
|---|---|
| Read all comments | Read |
| Create new comment | Write |
| Edit comment body | Write |
| Delete comment | Write (with confirmation) |
| Read reactions on issue | Read |
| Read reactions on comments | Read |

### GitHub REST API — Timeline Events (Read-only)

The issue timeline provides a full audit trail of all changes. Events are read-only.

| Event Types |
|---|
| labeled / unlabeled |
| assigned / unassigned |
| milestoned / demilestoned |
| renamed (title change) |
| closed / reopened |
| locked / unlocked |
| referenced (mentioned in another issue or PR) |
| committed (commit referencing the issue) |
| cross-referenced |
| state-change |

### GitHub Projects v2 — GraphQL Fields

These fields live on the project item (the issue's entry in a GitHub Projects v2 board) and are accessed via the GraphQL API.

| Field | Type | Access | Notes |
|---|---|---|---|
| Status | single-select | Read / Write | Valid options defined per project |
| Priority | single-select | Read / Write | Valid options defined per project; field must exist |
| Iteration / Sprint | iteration | Read / Write | Valid iterations listed in schema |
| Start Date | date | Read / Write | ISO 8601 date |
| End Date | date | Read / Write | ISO 8601 date |
| Estimate / Story Points | number | Read / Write | Numeric; field must exist on the project |
| Issue Type | single-select | Read / Write | e.g. Bug, Feature, Task; valid options per project |
| Parent Issue | issue reference | Read / Write | Links this issue as a child of another |
| Sub-issues Progress | computed | Read | Percentage of child issues closed; not writable |
| Linked Pull Requests | array | Read | Set automatically by GitHub; not writable |
| Custom text fields | string | Read / Write | Field must exist on the project |
| Custom number fields | number | Read / Write | Field must exist on the project |
| Custom date fields | date | Read / Write | Field must exist on the project |
| Custom single-select fields | single-select | Read / Write | Valid options defined per project |

### Organization-Level Custom Issue Fields

GitHub organizations can define custom fields that apply across all repositories in the org. These are accessed via the REST API.

| Type | Access | Notes |
|---|---|---|
| text | Read / Write | Free text |
| single_select | Read / Write | Valid options defined at the org level |
| number | Read / Write | Numeric |
| date | Read / Write | ISO 8601 date |

---

## Core Capabilities

### 1. Discovery and Setup

The system discovers what is accessible from the authenticated token and provides a clear picture of the configured working scope before any extraction or editing takes place.

- List all repositories accessible to the token
- List all GitHub Projects v2 in each accessible organization
- Interactive selection of repositories or a project to track
- Persist selected repositories to `config.yaml`
- Detect and surface Projects v2 boards associated with each tracked repository
- A `team` command lists all configured team members, their display names, GitHub usernames, roles, and whether each person is a confirmed collaborator on each tracked repository. This is the starting point for verifying that the team roster in `config.yaml` is correct before beginning a work session.

### 2. Extraction

Downloads all matching issues from selected repositories and saves them as local markdown files.

- Interactive wizard to configure repositories and filters
- Applies `scope.milestones` from `config.yaml` as the default milestone filter; prompts to confirm or override the scope before extracting
- Supports filtering by: author, assignee, state, labels, milestone, `since` date, `until` date
- Fetches both REST issue fields and Projects v2 field values for each issue
- Saves each issue as a structured markdown file with YAML frontmatter
- Saves filters per repository so subsequent syncs use the same scope
- Persists repository list to `config.yaml`

### 3. Incremental Sync

Keeps local files up to date with GitHub without re-downloading everything.

- Re-fetches all tracked repositories using saved filters, scoped to configured milestones by default
- Detects new, updated, and unchanged issues by comparing content hashes
- Updates local files only for issues that have changed
- Refreshes the schema files and team collaborator status on each sync run
- Generates a timestamped markdown change report after each sync

### 4. Full Issue Field Read/Write

Any writable field defined in the Issue Data Model above can be edited locally and pushed back to GitHub.

- Editing a field value in the local markdown file marks that issue as dirty
- Running `push` inspects all dirty files, previews changes, and writes them back using the appropriate API (REST or GraphQL) for each field
- REST fields (title, body, state, state reason, labels, milestone, assignees, lock) are written via the Issues REST API
- Projects v2 fields (status, priority, iteration, dates, estimates, issue type, parent issue, custom fields) are written via the GraphQL API
- Org-level custom issue fields are written via the REST API
- A `--dry-run` flag shows exactly what would be written without making any changes
- Field validation runs before any write: invalid values (e.g. a label that does not exist on the repo) are reported as errors, not silently ignored

### 5. Comments Management

Comments are full citizens of the local file and can be created, edited, and deleted locally.

- All existing comments are saved in the issue markdown file on extraction and sync
- New comments can be added by appending to the Comments section of the file
- Existing comments can be edited in place
- A comment marked for deletion in the file requires explicit confirmation before the delete API call is made
- After push, the local file is refreshed to reflect the authoritative comment thread from GitHub

### 6. Field Schema Visibility

Before editing issue fields, users and AI agents need to know what values are valid. The system maintains a schema document per repository that answers this question without requiring a browser.

- A `schema` command fetches and generates schema files for each tracked repository
- Schema is also refreshed automatically on each sync run
- Two schema files are generated per repository:
  - `.schema.md` — human-readable, organized by field group, intended for reading in an editor or by an AI agent
  - `.schema.json` — machine-readable, used by the `push` command for pre-write validation
- The schema document covers:
  - All standard GitHub issue fields with their types and writability
  - Labels configured on the repository (name, color, description)
  - Milestones on the repository (title, state, due date)
  - Collaborators: the full list of repo collaborators eligible as assignees, cross-referenced with the team roster in `config.yaml` so display names appear alongside GitHub usernames
  - For each associated Projects v2 board: all field names, field types, and for single-select and iteration fields, the complete list of valid option names
  - Org-level custom issue fields with valid options

### 7. Ad-hoc Reporting

Generates a structured markdown report from locally stored issue data on demand, without requiring a network connection.

- A `report` command accepts a filter specification (repo, milestone, label, assignee, status, date range, etc.) and a grouping option (by assignee, by label, by status, etc.)
- Reports are written to `reports/<name>.md`; name defaults to a slug derived from the query if not specified
- Supported report formats:
  - Summary table (one row per issue: number, title, status, assignee, milestone)
  - Detailed list (full frontmatter fields per issue, no body)
  - Full export (complete issue content including body and comments)
  - Grouped view (issues nested under their grouping field value)
- Report templates can be saved and reused by name
- Example reports:
  - All open issues for milestone X, grouped by assignee
  - All issues labeled "bug" with priority "High", sorted by creation date
  - Current sprint: all items in the active iteration with their status and assignee
  - Weekly digest: issues created or updated in the last 7 days across all tracked repos
  - Changelog for a single issue: full timeline of every event and comment

### 8. Project Field Management

Updates any Projects v2 field — not only Status — from the command line without editing a file.

- Update any named Projects v2 field on any issue directly via CLI arguments
- List available options for any single-select or iteration field before changing it
- Infer the organization from the repository owner if not specified
- Auto-detect the project when there is only one; prompt when there are multiple

### 9. Bulk Operations

Applies a single field change to multiple issues in one command, avoiding the need to edit each file individually.

- A `bulk-edit` command accepts a filter (same syntax as `report`) to define the target set
- Supported operations: set a field value, add/remove a label, assign/unassign a user, change milestone, close/reopen
- Shows a preview of affected issues before writing
- Honors `--dry-run`

---

## Field Schema Visibility

The `.schema.md` file for a repository is organized as follows:

```
# Field Schema — owner/repo
Last refreshed: YYYY-MM-DD HH:MM:SS

## Standard Issue Fields
[table: field name, type, writable]

## Labels
[table: name, color, description]

## Milestones
[table: title, state, due date]

## Team Members (valid assignees)
[table: display name, github username, role, collaborator status on this repo]
Note: team members marked ✗ are not collaborators on this repository and
cannot be assigned to issues here.

## All Repository Collaborators
[list of github usernames not in the team roster]

## Projects v2: <Project Name>
### Fields
[table: field name, type, writable]
### Status Options
[list]
### Priority Options
[list]
### Iterations
[table: iteration title, start date, end date, state (active/upcoming/completed)]
### [other single-select fields and their options]

## Org-level Custom Fields
[table: field name, type, valid options]
```

The `.schema.json` file contains the same information in a structured format that the `push` command loads at runtime to validate field values before making API calls.

---

## Filters

Filters are applied during extraction and sync to scope which issues are downloaded. They are also the primary input to the `report` and `bulk-edit` commands.

| Filter | Type | Notes |
|---|---|---|
| `author` | GitHub username | Issues created by this user |
| `assignee` | GitHub username | Issues assigned to this user |
| `state` | `open`, `closed`, `all` | Defaults to `all` |
| `labels` | comma-separated list | Issues must have all specified labels |
| `milestone` | title, `*`, or `none` | `*` means any milestone; `none` means no milestone |
| `since` | `YYYY-MM-DD` | Issues created or updated after this date |
| `until` | `YYYY-MM-DD` | Issues created before this date (applied client-side) |
| `project-status` | string | Filter by a Projects v2 Status field value |
| `iteration` | title or `current` | Filter by Projects v2 iteration; `current` means the active iteration |
| `priority` | string | Filter by Projects v2 Priority field value |
| `issue-type` | string | Filter by issue type |
| `assignee-none` | flag | Issues with no assignee |

Filters are saved per repository and reused on subsequent sync runs. They can be overridden per run with explicit flags.

**Scope inheritance:** When `scope.milestones` is configured in `config.yaml`, all extraction, sync, report, and bulk-edit operations treat it as a pre-applied milestone filter. An explicit `--milestone <title>` flag on any command overrides the scope for that run. Passing `--milestone all` removes the milestone filter entirely for that run, regardless of scope configuration.

---

## Ad-hoc Reporting

Reports are generated from locally stored data. The `report` command does not make network calls; it reads the issue files and schema files on disk.

A report is defined by:
- **Scope**: a filter specification selecting which issues to include. When `scope.milestones` is configured, reports default to that milestone set unless the template or command specifies otherwise.
- **Grouping**: an optional field to group issues by (e.g. `--group-by assignee`)
- **Format**: `table` (default), `list`, `full`, or `grouped`
- **Output name**: an optional filename; defaults to a slug from the filter arguments

All GitHub usernames in report output are rendered as display names where a mapping exists in the team roster (e.g. "John Smith" rather than "jsmith123"). Where no mapping exists, the raw username is shown. Both are included when the format requires disambiguation.

Report templates can be saved to `config.yaml` under a `reports` key and invoked by name:

```yaml
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

Running `python -m src report sprint-status` generates the report from the saved template.

---

## Configuration

### `config.yaml`

Stores tracked repositories, the active project scope, the team roster, and saved report templates. All sections except `repositories` are optional.

```yaml
# Repositories the tool tracks
repositories:
  - owner/repo1
  - owner/repo2

# Project scope — constrains which milestones the tool operates on by default.
# When set, all extraction, sync, report, and bulk-edit operations are limited
# to issues belonging to one of the listed milestone titles unless explicitly
# overridden with --milestone all or a specific --milestone flag.
scope:
  milestones:
    - "v2.0"
    - "Q1 2026"

# Team roster — maps GitHub usernames to human display names.
# Display names are used in report output and accepted as input when
# specifying assignees in bulk-edit and push operations.
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

### Project Scope

The `scope.milestones` list defines the working set for a session. It answers the question "which milestones are we currently working in?" and narrows every default operation to that set.

- When `scope.milestones` is set, extraction, sync, reporting, and bulk operations all default to issues whose milestone matches one of the configured titles
- Commands can escape the scope with `--milestone all` (no milestone filter) or `--milestone <title>` (a specific milestone that may or may not be in the scope list)
- The `discover`, `schema`, and `team` commands are not affected by scope — they operate at the repository level
- When `scope.milestones` is not set, the tool operates across all milestones, consistent with the current behavior

### Team Roster

The `team` list is the authoritative record of who is on the project.

Each entry has:
- `username` (required) — the GitHub login used by the API
- `name` (required) — the human display name shown in reports and CLI output
- `role` (optional) — free-text description used in the `team` command output

**How the team roster is used across the system:**

- **Reports** — All GitHub usernames in report output are rendered as display names where a mapping exists. Both the username and display name are shown (e.g. "John Smith (jsmith123)") so output is unambiguous.
- **Assignee input** — When editing the `Assignees` field in an issue file or passing an `--assignee` argument to `bulk-edit`, either the GitHub username or the configured display name is accepted. The tool resolves display names to usernames before pushing to GitHub.
- **Schema cross-reference** — The `schema` command cross-references the team roster against each repository's collaborator list. Any configured team member who is not a collaborator on a given repository is flagged so the user knows that assigning them to issues in that repo will fail.
- **`team` command** — Lists all configured team members with their display names, usernames, roles, and collaborator status on each tracked repository.

### `.env`

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | GitHub personal access token |
| `PROJECT_CONTEXT_DIR` | No | If set, issues are stored under `$PROJECT_CONTEXT_DIR/github-issues/` instead of `./issues/` |

Token scope requirements:
- `repo` — read/write access to private repositories and all issue fields
- `project` — required for reading and writing GitHub Projects v2 fields
- `read:org` — required for listing org-level Projects v2 and custom fields

---

## Output Files

| Path | Description |
|---|---|
| `issues/<owner>-<repo>/issue-<N>.md` | Full issue content: YAML frontmatter with all fields, body, change history summary, comments, linked PRs, reaction counts |
| `issues/<owner>-<repo>/.metadata.json` | Per-issue content hash, file-content hash, sync state |
| `issues/<owner>-<repo>/.schema.md` | Human-readable field schema for the repo and its Projects v2 boards |
| `issues/<owner>-<repo>/.schema.json` | Machine-readable schema used for pre-push validation |
| `reports/changes-<timestamp>.md` | Auto-generated change report after each sync |
| `reports/<name>.md` | User-requested ad-hoc report |

---

## Recommended Capabilities

The following capabilities extend the system beyond the explicitly requested feature set and are recommended for inclusion in the vision.

### Assignees (Read / Write)
Add or remove issue assignees from the local file. Valid assignees are constrained to repository collaborators and are listed in the schema document. This is one of the most commonly changed fields during triage and should be fully writable.

### Issue State and State Reason (Read / Write)
Open or close an issue locally and specify the reason: `completed` (work is done) or `not_planned` (deprioritized). This is distinct from the Projects v2 Status field and directly changes the issue's state in GitHub's REST API.

### Iterations and Sprints (Read / Write)
Read and write GitHub Projects v2 iteration fields to support sprint-based workflows. The schema document lists all configured iterations with their titles, start dates, end dates, and state (active, completed, upcoming). The `current` keyword resolves to the active iteration when used in filters.

### Estimates and Story Points (Read / Write)
Read and write numeric Projects v2 fields that teams use for effort estimation. The schema document surfaces the name of the estimate field (which varies by team) so users know what to edit.

### Issue Type (Read / Write)
GitHub's native issue type field (Bug, Feature, Task, etc.) is a single-select Projects v2 field. Valid types are listed in the schema. Surfacing this field locally enables type-based filtering and reporting without requiring the GitHub UI.

### Sub-issues and Parent Issue (Read / Write)
GitHub supports hierarchical issue tracking where issues can be children of a parent issue. The local file should surface the parent issue reference and the list of child issues. Parent assignment should be writable. The `sub_issues_progress` computed field (percentage of children closed) is read-only.

### Linked Pull Requests (Read)
Each issue file should show which pull requests reference the issue. This is read-only (GitHub sets it automatically when a PR includes a closing keyword). Surfacing it locally gives AI agents and developers visibility into whether work is underway.

### Reactions (Read)
Emoji reaction counts on issues and comments (thumbs up, thumbs down, heart, hooray, etc.) are surfaced in the issue file as signal. High reaction counts on an issue can indicate community priority or sentiment. Reactions are read-only in the local file.

### Bulk Operations
A `bulk-edit` command applies a single field change to a filtered set of issues in one operation. This is critical for triage workflows: reassigning all open bugs in a milestone, updating priority across a sprint, or closing a set of issues as `not_planned`. The command always previews the affected issues before writing and supports `--dry-run`.

### Issue Locking (Read / Write)
Lock or unlock issue comments from the local file. Locking prevents further comments on a resolved or heated thread. The lock reason (`off-topic`, `too heated`, `resolved`, `spam`) is writable and surfaced in the frontmatter.

---

## Design Principles

**Local files are the source of truth for edits, but GitHub is the source of truth for data.**
The system never silently overwrites GitHub data. Every write-back is the result of an explicit user action (`push` or `bulk-edit`). Syncing (`update`) only flows from GitHub to local, never the reverse.

**Invalid field values are errors, not warnings.**
Before any write to GitHub, field values are validated against the locally cached schema. An invalid label name, a status option that does not exist in the project, or an assignee who is not a collaborator will cause the push to fail with a clear error message, not silently proceed.

**All writes are previewable.**
Every command that modifies GitHub data supports `--dry-run`, which prints exactly what would change without making any API calls.

**Schema visibility is a first-class feature.**
The system cannot expect users to know what labels, milestones, statuses, or custom fields exist on a given repository or project. The schema document is automatically kept current and is the canonical reference for valid values.

**AI agents are first-class users.**
The markdown and JSON file formats are designed for readability by both humans and AI tools. The schema document is structured so an AI agent can read it and know exactly what values are valid before proposing edits.

**Scope is explicit and narrow by default.**
The tool is designed to work within a defined project context: specific repositories and specific milestones. Rather than operating across everything a token can see, the working scope is declared in `config.yaml`. This makes every operation predictable and prevents accidental reads or writes outside the intended project. Escaping the configured scope is always possible but always explicit.

**People are referenced by name, resolved by username.**
The team roster decouples how humans refer to each other (display names) from how the GitHub API identifies them (usernames). Reports and CLI output speak in human names; all API calls use the underlying username. This makes the tool more natural to use in an AI-assisted workflow where a user or agent might say "assign this to Michelle" rather than "assign this to mli".

**Authentication is token-based.**
No OAuth flow or browser login is required. The system uses a GitHub personal access token from the `.env` file.

**Pull requests are out of scope.**
The tool processes issues only. Pull requests are excluded from all fetches, though linked PRs are surfaced as read-only data on issue files.

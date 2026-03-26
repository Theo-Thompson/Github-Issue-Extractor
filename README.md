# GitHub Issue Extractor

A tool that downloads your GitHub issues as readable text files, keeps them in sync as things change on GitHub, and lets you edit issue titles and descriptions right on your computer and push those edits back.

---

## What This Tool Does

- **Downloads GitHub Issues** — Saves every issue as a plain text file you can open in any app
- **Tracks Multiple Repositories** — Works with as many GitHub repositories as you want
- **Stays in Sync** — Detects new, changed, and deleted issues each time you run an update
- **Filters Issues** — Choose exactly which issues to download (by author, label, date, and more)
- **Edit Locally, Push Back** — Edit an issue's title or description on your computer and send the change back to GitHub with one command
- **Updates Project Status** — Change an issue's project board status (e.g. move it to "Done") without opening a browser
- **Posts Comments** — Add a comment to any issue directly from the command line
- **Creates Change Reports** — Generates a summary of everything that changed since last time

---

## How It Works

```
Your Computer                         GitHub
─────────────────────────────────     ──────────────────────
issues/
  my-org-my-repo/
    issue-42.md   ◄── run / update ──  GitHub Issues API
    issue-43.md
    ...
  .metadata.json  (internal, tracks   push  ──────────────►  GitHub Issues API
                   what has changed)   comment  ───────────►  GitHub Issues API
                                       set-status  ─────────►  GitHub Projects API
reports/
  changes-2026-03-20.md  (update log)
```

When you run `update`, the tool compares each locally stored issue against the current state on GitHub. New issues are downloaded, changed issues are refreshed, and issues that have been removed from GitHub are deleted from your computer. A change report is written to the `reports/` folder.

When you edit a local issue file and run `push`, the tool notices the file has changed and sends the updated title and description back to GitHub.

---

## Setup Instructions

### Step 1: Install Python

You need Python 3.8 or newer. Check if you have it:

```bash
python3 --version
```

If you don't have Python, download it from [python.org](https://www.python.org/downloads/).

### Step 2: Download This Tool

```bash
git clone <your-repo-url>
cd Github-Issue-Extractor
```

### Step 3: Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows users:** use `venv\Scripts\activate` instead.

### Step 4: Install Required Packages

```bash
pip install -r requirements.txt
```

### Step 5: Get a GitHub Token

The tool needs a personal access token to read (and optionally write) data on GitHub.

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Give it a name like "Issue Extractor"
4. Under **Select scopes**, check the following:

| Scope | When you need it |
|---|---|
| `public_repo` | Reading issues from public repositories |
| `repo` | Reading issues from **private** repositories, or pushing edits back |
| `project` | Using the `set-status` command to update project board columns |
| `read:org` | Listing projects that belong to an organisation |

5. Click **"Generate token"** at the bottom
6. **Copy the token immediately** — GitHub only shows it once

Now save your token:

```bash
cp .env.example .env
```

Open `.env` in a text editor and paste your token:

```
GITHUB_TOKEN=ghp_your_actual_token_here
```

> **Important:** Never share this file or commit it to git.

---

## Where Issues Are Saved

By default, issues are saved to an `issues/` folder inside this project. To save them somewhere else, add a `PROJECT_CONTEXT_DIR` line to your `.env` file:

```bash
PROJECT_CONTEXT_DIR=~/Documents/ProjectContext
```

Issues will then be saved to `~/Documents/ProjectContext/github-issues/`.

---

## Commands

### `run` — First-time setup and issue download

```bash
python -m src run
```

This is where you start. The tool walks you through four steps:

**Step 1 — Choose how to select issues**
- *Select individual repositories* — pick repos from a list
- *Select by GitHub Project* — all issues from a project board at once

**Step 2 — Pick your repositories or project**

The tool fetches everything you have access to and shows it as a list. Use the **arrow keys** to move, **Space** to select, and **Enter** to confirm.

**Step 3 — Apply filters (optional)**

You can narrow down which issues to download. Leave any field blank to skip it.

| Filter | What it does |
|---|---|
| Author | Only issues created by a specific GitHub username |
| Assignee | Only issues assigned to a specific username |
| State | `open`, `closed`, or `all` |
| Labels | Only issues with these labels (comma-separated, e.g. `bug,urgent`) |
| Milestone | Only issues in a named milestone |
| Since date | Only issues updated after this date (`YYYY-MM-DD`) |

Filters are saved automatically, so `update` uses the same filters next time.

**Step 4 — Download**

The tool downloads every matching issue and saves it as a Markdown file. Progress is shown as it goes.

---

### `update` — Sync changes from GitHub

```bash
python -m src update
```

Run this regularly to stay current. For each tracked repository, the tool will:

- Download **new** issues that appeared since last time
- Refresh **updated** issues whose content changed
- **Remove** local files for issues that were deleted or moved on GitHub
- Print a short summary: `✓ New: 2, Updated: 5, Removed: 1`
- Write a full change report to the `reports/` folder

> **Tip:** Schedule this to run automatically — see [Automating Updates](#automating-updates).

---

### `push` — Send your local edits back to GitHub

```bash
python -m src push
```

If you have edited an issue's title or description in its local Markdown file, this command sends those changes back to GitHub. The tool compares the file on disk against the version it originally saved. Only files you have changed are uploaded.

**To preview what would be pushed without actually changing anything:**

```bash
python -m src push --dry-run
```

> **Note:** Only the issue **title** and **body** can be pushed. Labels, assignees, state, and milestone must be changed directly on GitHub or via `set-status`.
>
> Issues saved before this version of the tool was installed do not have a stored baseline. Run `python -m src update` first to establish a baseline, then edit and push as normal.

---

### `set-status` — Move an issue to a different project column

```bash
python -m src set-status OWNER/REPO ISSUE_NUMBER "STATUS_NAME"
```

This updates the **Status** field on a GitHub Projects v2 board — for example, moving an issue to "In Progress" or "Done" — without needing to open a browser.

**Examples:**

```bash
# Move issue #42 to "Done"
python -m src set-status MyOrg/MyApp 42 "Done"

# Move issue #17 to "In Progress", specifying which project
python -m src set-status MyOrg/MyApp 17 "In Progress" --project "Q2 Roadmap"

# See all valid status values for a project
python -m src set-status MyOrg/MyApp 0 "" --project "Q2 Roadmap" --list-statuses
```

> **Requirement:** Your GitHub token must have the `project` scope. If the token only has `read:project`, the command will tell you exactly what to change.

**Options:**

| Option | Description |
|---|---|
| `--project NAME` | The project board to update. Required if the organisation has more than one project. |
| `--org LOGIN` | The organisation login. Defaults to the owner part of `OWNER/REPO`. |
| `--list-statuses` | Print all available status values for the project, then exit. |

---

### `comment` — Post a comment on an issue

```bash
python -m src comment OWNER/REPO ISSUE_NUMBER "Your comment text"
```

Adds a new comment to a GitHub issue and refreshes the local file so the comment appears immediately in your local copy.

**Example:**

```bash
python -m src comment MyOrg/MyApp 42 "Moving back to Securitas Review for the April release"
```

After the comment is posted, the local `issue-42.md` file is updated to include the new comment.

> **Note:** Only the issue **body** and **title** can be edited via `push`. To add new comments, use this command.

---

### `status` — See what's currently tracked

```bash
python -m src status
```

Shows a quick overview: which repositories are tracked, how many issues are stored, and how many are open vs. closed.

---

### `discover` — Find repositories to add

```bash
python -m src discover
python -m src discover --save   # also writes them to config.yaml
```

Lists every repository your token has access to. Select any you want to start tracking and optionally save them to the configuration file automatically.

---

## Understanding the Local Files

### Issue files

Issues are saved in the storage folder, organised by repository:

```
issues/
├── my-org-my-app/
│   ├── issue-1.md
│   ├── issue-42.md
│   └── ...
└── another-org-another-repo/
    ├── issue-7.md
    └── ...
```

Each file is plain Markdown. The header block (between the `---` lines) holds metadata like state, labels, and author. Below that is the issue title, the full description, and all comments.

```markdown
---
number: 42
title: Login button broken on mobile
state: open
labels: [bug, high-priority]
author: johndoe
assignees: [janesmith]
created_at: 2025-01-01T10:00:00Z
updated_at: 2025-03-15T09:12:00Z
url: https://github.com/my-org/my-app/issues/42
---

# Login button broken on mobile

The login button doesn't respond to taps on iOS 17...

## Comments

### Comment by janesmith on 2025-01-02T14:30:00Z

Confirmed. Assigning to myself — will fix in the next sprint.
```

> **Editing issues locally:** You can change the **title** (the `# Heading` line) and the **body text** directly in this file. Run `python -m src push` afterwards to send the changes to GitHub. Do not edit the metadata block between the `---` lines; those values are managed by the tool.

### Change reports

After every `update` run a report is written to:

```
reports/changes-YYYY-MM-DD-HH-MM-SS.md
```

It lists every new, changed, and removed issue grouped by repository, with links back to GitHub.

### Configuration file

`config.yaml` stores the list of repositories the tool tracks. It is created and updated automatically by `run` and `discover`. You can open it and remove a repository name if you want to stop tracking it, but otherwise you don't need to edit it manually.

---

## Typical Workflow

```
First time
──────────
python -m src run
  → choose repos, set filters, download everything

Every day / week
────────────────
python -m src update
  → new and changed issues downloaded, deleted ones removed, report saved

When you want to edit an issue
───────────────────────────────
1. Open issues/my-org-my-repo/issue-42.md in any text editor
2. Change the title heading or body text
3. python -m src push
   → only the files you changed are sent to GitHub

When you want to move an issue on the project board
────────────────────────────────────────────────────
python -m src set-status my-org/my-repo 42 "Done"

When you want to leave a comment on an issue
─────────────────────────────────────────────
python -m src comment my-org/my-repo 42 "Your comment here"
  → comment posted to GitHub, local file refreshed
```

---

## Automating Updates

### Mac / Linux (cron)

```bash
crontab -e
```

Add this line to run every day at 9 AM:

```
0 9 * * * cd /path/to/Github-Issue-Extractor && source venv/bin/activate && python -m src update
```

### Windows (Task Scheduler)

1. Open Task Scheduler and create a new task
2. Set the program to: `C:\path\to\venv\Scripts\python.exe`
3. Set arguments to: `-m src update`
4. Set the working directory to your project folder

---

## Troubleshooting

### "GITHUB_TOKEN not found"

The tool cannot find your token.

1. Check that you created `.env`: `cp .env.example .env`
2. Open `.env` and confirm the token is on a line like `GITHUB_TOKEN=ghp_...`
3. There should be no spaces around the `=` sign

### "Failed to fetch issues" or "Permission denied"

- Confirm the repository name is spelled correctly in `config.yaml` (format: `owner/repo`)
- Confirm you can open the repository in your browser while logged into GitHub
- If the repository is private, your token needs the `repo` scope

### "GitHub API permission error" when using `set-status`

Your token is missing the `project` scope. Go back to [GitHub token settings](https://github.com/settings/tokens), edit the token, and enable **project** under the Write column.

### "Issues have no stored hash — run 'update' first"

The `push` command skips issues that were saved by an older version of the tool (before the file-tracking feature was added). Run `python -m src update` once to establish a baseline for all existing files. After that, `push` will work normally.

### No issues found (0 results)

- Your filters may be too restrictive — try running again with no filters
- The repository may genuinely have no issues matching your criteria
- Pull requests are always excluded; they look like issues in some GitHub views

### Interactive menu doesn't appear

The arrow-key selection menu requires a proper terminal. If it doesn't appear, try running the command in a standard Terminal or Command Prompt window rather than inside an IDE's embedded terminal.

### Connection errors or timeouts

- Check your internet connection
- GitHub's API may be experiencing an outage — check [githubstatus.com](https://githubstatus.com)
- Your token may have expired; generate a new one at [github.com/settings/tokens](https://github.com/settings/tokens)

---

## Your Files at a Glance

```
Github-Issue-Extractor/
├── issues/           ← Downloaded issues — edit these to use "push"
├── reports/          ← Change summaries from each "update" run
├── config.yaml       ← List of tracked repositories (auto-managed)
├── .env              ← Your GitHub token — never share or commit this
├── src/              ← Tool source code — no need to touch this
├── requirements.txt  ← Python package list
└── README.md         ← This file
```

**Never commit to git:** `.env`

**Safe to commit (and useful for history):** `issues/`, `reports/`, `config.yaml`

---

## Need Help?

1. Re-read the troubleshooting section above
2. Run `python -m src --help` to see all available commands
3. Run `python -m src COMMAND --help` (e.g. `python -m src push --help`) for details on a specific command
4. Check that your GitHub token has not expired

---

## License

MIT License — free to use, modify, and share.

---

**Ready to start?** Run `python -m src run` and the tool will guide you through everything.

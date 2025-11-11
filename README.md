# GitHub Issue Extractor

A simple tool to download and track GitHub issues from your projects. Issues are saved as readable markdown files on your computer, and the tool can automatically detect when issues change.

## What This Tool Does

- **Downloads GitHub Issues**: Saves all your GitHub issues as text files on your computer
- **Tracks Multiple Projects**: Works with as many GitHub repositories as you want
- **Detects Changes**: Automatically finds new or updated issues when you run it again
- **Filters Issues**: Choose exactly which issues to download (by author, labels, dates, etc.)
- **Creates Reports**: Generates summaries of what changed since last time

## Setup Instructions

### Step 1: Install Python

You need Python 3.7 or newer. Check if you have it:

```bash
python3 --version
```

If you don't have Python, download it from [python.org](https://www.python.org/downloads/)

### Step 2: Download This Tool

```bash
git clone <your-repo-url>
cd Github-Issue-Extractor
```

### Step 3: Set Up the Environment

Create a safe space for the tool to run:

```bash
python3 -m venv venv
source venv/bin/activate
```

**Note for Windows users:** Use `venv\Scripts\activate` instead

### Step 4: Install Required Packages

```bash
pip install -r requirements.txt
```

### Step 5: Get a GitHub Token

This lets the tool access GitHub on your behalf:

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Give it a name like "Issue Extractor"
4. Under "Select scopes", check:
   - `public_repo` (if you only need public repositories)
   - `repo` (if you need private repositories too)
5. Click "Generate token" at the bottom
6. **Copy the token** (it starts with `ghp_` or `github_pat_`)

Now save your token:

```bash
cp .env.example .env
```

Open the `.env` file in a text editor and replace `your_github_token_here` with your actual token:

```
GITHUB_TOKEN=ghp_your_actual_token_here
```

**Important:** Never share this token with anyone!

## How to Use

### Run the Tool

Simply run:

```bash
python -m src.cli run
```

**The tool will guide you through 4 simple steps:**

**STEP 1: Choose Selection Method**
- Select individual repositories, OR
- Select by GitHub Project (all issues from a project board)

**STEP 2: Select Repositories or Project**
- **If selecting repositories:**
  - The tool automatically finds all repositories you have access to
  - Shows you a list with the number of open issues in each
  - Use arrow keys to navigate, SPACE to select, ENTER to confirm
- **If selecting by project:**
  - Shows all your GitHub Projects (classic project boards)
  - Select one project
  - Tool automatically finds all repositories with issues in that project

**STEP 3: Apply Filters (Optional)**  
- Choose whether you want to filter issues
- If yes, answer simple questions:
  - Filter by author? (leave blank to skip)
  - Filter by assignee?
  - Filter by state? (open/closed/all)
  - Filter by labels?
  - Filter by milestone?
  - Filter since date?

**STEP 4: Extract Issues**
- The tool downloads all matching issues
- Saves them as markdown files
- Shows progress for each repository
- Automatically saves your configuration for next time

### Check for Updates

After your first run, periodically check for changes:

```bash
python -m src.cli update
```

This will:
- Use your saved repository list and filters
- Check for new issues
- Find updated issues
- Save any changes
- Create a report in the `reports/` folder

## Selection Methods

### Select by Repositories
Choose this when you want to:
- Pick specific repositories manually
- Track issues from repos that aren't in a project
- Have full control over which repos to include

### Select by GitHub Project
Choose this when you want to:
- Extract all issues from a project board
- Track work organized in a GitHub Project
- Get issues from multiple repos that are part of one project

**Note:** The tool finds classic GitHub Projects (project boards). It looks in:
- Your organization projects
- Repository-level projects

## Understanding Filters

When you run the tool, you'll be asked if you want to apply filters. Filters let you download only specific issues instead of everything.

### Available Filters:

- **Author**: Only issues created by a specific user
- **Assignee**: Only issues assigned to a specific user  
- **State**: Choose open, closed, or all issues
- **Labels**: Only issues with specific labels (comma-separated like: bug,urgent)
- **Milestone**: Only issues in a specific milestone
- **Since Date**: Only issues created/updated since a date (format: YYYY-MM-DD)

### When to Use Filters:

- **Track your work**: Filter by your username as assignee
- **Bug triage**: Filter by "bug" label and "open" state
- **Sprint planning**: Filter by current milestone
- **Monthly reports**: Filter by date range

**Note:** Filters are saved automatically. When you run `update`, it uses the same filters to stay consistent.

## Understanding the Output

### Where Are My Issues?

Issues are saved in the `issues/` folder:

```
issues/
├── facebook-react/
│   ├── issue-1.md
│   ├── issue-2.md
│   └── issue-3.md
└── microsoft-vscode/
    ├── issue-1.md
    └── issue-2.md
```

Each issue is a text file you can open with any text editor.

### What's in an Issue File?

Each file contains:
- Issue title and description
- Who created it and when
- Labels and assignees
- All comments
- Current status (open/closed)

Example:
```markdown
---
number: 42
title: Bug in login form
state: open
labels: [bug, high-priority]
author: johndoe
created_at: 2025-01-01T10:00:00Z
---

# Bug in login form

The login button doesn't work on mobile devices...

## Comments

### Comment by developer1 on 2025-01-02T14:30:00Z

Thanks for reporting. We'll fix this in the next release.
```

### Change Reports

After running `update`, check the `reports/` folder for summaries of what changed.

## Troubleshooting

### "GITHUB_TOKEN not found"

**Problem:** The tool can't find your GitHub token.

**Solution:**
1. Make sure you created the `.env` file: `cp .env.example .env`
2. Open `.env` and check your token is there
3. Make sure the line looks like: `GITHUB_TOKEN=ghp_your_token`
4. No spaces around the `=` sign

### "Failed to fetch issues"

**Problem:** Can't download issues from a repository.

**Possible causes:**
- Repository name is spelled wrong (check it's `owner/repo`)
- Repository is private and your token doesn't have `repo` permission
- Repository doesn't exist or you don't have access

**Solution:**
- Double-check the repository name in `config.yaml`
- Make sure you can view the repository on GitHub in your browser
- Regenerate your token with the `repo` scope if needed

### "Command not found: python"

**Problem:** Your computer doesn't recognize the `python` command.

**Solution:**
- Try `python3` instead of `python`
- Make sure Python is installed: download from [python.org](https://www.python.org/downloads/)

### Interactive Selection Not Working

**Problem:** The repository selection menu doesn't appear.

**Solution:**
- The tool will automatically select all repositories
- You can continue without the interactive menu
- Try running the command in a different terminal if needed

### No Issues Found

**Problem:** The tool says it found 0 issues.

**Possible causes:**
- Your filters are too restrictive
- The repository actually has no issues
- Issues are pull requests (the tool skips these)

**Solution:**
- Run again and choose not to apply filters
- Check the repository on GitHub to see if issues exist
- If using filters, try less restrictive ones

### No Repositories Found

**Problem:** The tool finds no repositories.

**Possible causes:**
- Your GitHub account has no repositories
- Your token doesn't have the right permissions

**Solution:**
- Check that you have repositories on your GitHub account
- Make sure your token has `repo` or `public_repo` scope
- Try visiting https://github.com in your browser to verify your account

### No Projects Found

**Problem:** When selecting by project, the tool finds no projects.

**Possible causes:**
- You don't have any GitHub Projects set up
- Your projects are the new "Projects (beta)" which aren't fully supported yet
- Projects are in private organizations without proper access

**Solution:**
- Try selecting by repositories instead
- Check if you have classic project boards in your repos or organizations
- Create a project board if you want to use this feature

## Tips for Success

1. **Start Small**: Begin with one or two repositories to understand how it works
2. **Use Filters Wisely**: Filters help you focus on what matters
3. **Run Updates Regularly**: Set a schedule (daily or weekly) to keep issues current
4. **Backup Your Data**: The `issues/` folder contains all your downloaded issues
5. **Check Reports**: The `reports/` folder shows what changed over time

## Advanced Tips

### Automate Updates

You can set up the tool to run automatically:

**On Mac/Linux (using cron):**
```bash
# Edit your crontab
crontab -e

# Add this line to run daily at 9 AM:
0 9 * * * cd /path/to/Github-Issue-Extractor && source venv/bin/activate && python -m src.cli update
```

**On Windows (using Task Scheduler):**
1. Open Task Scheduler
2. Create a new task
3. Set it to run: `C:\path\to\venv\Scripts\python.exe -m src.cli update`
4. Set the working directory to your project folder

### Multiple Configurations

You can create different config files for different projects:

```bash
# Work projects
python -m src.cli fetch --config work.yaml

# Personal projects
python -m src.cli fetch --config personal.yaml
```

### Version Control

Add your `issues/` folder to git to track historical changes:

```bash
git add issues/
git commit -m "Update issues"
```

This creates a full history of how your issues evolved over time.

## Need Help?

If you encounter problems:

1. Check the troubleshooting section above
2. Make sure you followed all setup steps
3. Try running `python -m src.cli --help` to see available options
4. Check that your GitHub token hasn't expired

## What Files Should I Keep?

After running the tool, your folder structure looks like:

```
Github-Issue-Extractor/
├── issues/          ← Your downloaded issues (keep this!)
├── reports/         ← Change reports (keep this!)
├── src/             ← Tool code (don't modify)
├── config.yaml      ← Auto-generated configuration (don't modify manually)
├── .env             ← Your GitHub token (never share this!)
├── requirements.txt ← Package list (don't modify)
└── README.md        ← This file
```

**Don't commit to git:** `.env` (contains your token)
**Safe to commit:** Everything else (including issues/ to track history)

## License

MIT License - You're free to use, modify, and share this tool.

---

**Ready to get started?** Just run `python -m src.cli run` and the tool will guide you through everything!

"""Command-line interface for GitHub Issue Extractor."""

import sys
import yaml
import click
import inquirer
from pathlib import Path
from typing import List, Dict, Any, Optional

from .github_client import GitHubClient
from .storage import IssueStorage
from .tracker import ChangeTracker
from .reporter import ChangeReporter
from .project_updater import ProjectUpdater


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """GitHub Issue Extractor - Extract and track GitHub issues across repositories.
    
    This tool helps you maintain a local copy of GitHub issues as markdown files
    and track changes over time.
    """
    pass


@cli.command()
@click.option('--config', default='config.yaml', help='Path to configuration file')
def run(config):
    """Run the GitHub Issue Extractor (main command).
    
    This interactive command will:
    1. Ask if you want to select by repositories or projects
    2. Let you select which ones to track
    3. Ask if you want to apply any filters
    4. Extract and save all matching issues
    """
    click.echo("GitHub Issue Extractor")
    click.echo("=" * 60)
    
    # Initialize GitHub client
    try:
        github_client = GitHubClient()
        storage = IssueStorage()
    except Exception as e:
        click.echo(f"\nError initializing: {e}", err=True)
        sys.exit(1)
    
    # Test connection
    click.echo("\nTesting GitHub connection...", nl=False)
    if not github_client.test_connection():
        click.echo(" FAILED", err=True)
        click.echo("Please check your GITHUB_TOKEN in .env file", err=True)
        sys.exit(1)
    click.echo(" OK")
    
    # Ask how they want to select
    click.echo("\n" + "=" * 60)
    click.echo("STEP 1: Choose Selection Method")
    click.echo("=" * 60)
    
    selection_method = prompt_selection_method()
    
    if not selection_method:
        click.echo("\nCancelled by user.")
        sys.exit(0)
    
    selected_repos = []
    
    if selection_method == 'repositories':
        # Fetch available repositories
        click.echo("\nFetching your accessible repositories...", nl=False)
        try:
            all_repos = github_client.get_accessible_repositories()
            click.echo(f" Found {len(all_repos)} repositories")
        except Exception as e:
            click.echo(f" FAILED", err=True)
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        if not all_repos:
            click.echo("\nNo repositories found.")
            sys.exit(0)
        
        # Display repositories
        click.echo(f"\n{'Repository':<50} {'Issues':<10} {'Access'}")
        click.echo("-" * 70)
        for repo in all_repos[:10]:  # Show first 10
            access = "Private" if repo['private'] else "Public"
            click.echo(f"{repo['full_name']:<50} {repo['open_issues']:<10} {access}")
        if len(all_repos) > 10:
            click.echo(f"... and {len(all_repos) - 10} more repositories")
        
        # Select repositories
        click.echo("\n" + "=" * 60)
        click.echo("STEP 2: Select Repositories")
        click.echo("=" * 60)
        click.echo("(Use arrow keys to navigate, SPACE to select, ENTER to confirm)")
        click.echo()
        
        selected_repos = select_repos_from_list(all_repos)
    
    else:  # projects
        # Fetch available projects
        click.echo("\nFetching your GitHub Projects...", nl=False)
        try:
            all_projects = github_client.get_user_projects()
            click.echo(f" Found {len(all_projects)} projects")
        except Exception as e:
            click.echo(f" FAILED", err=True)
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        if not all_projects:
            click.echo("\nNo projects found.")
            click.echo("Try selecting by repositories instead.")
            sys.exit(0)
        
        # Display projects
        click.echo(f"\n{'Project':<50} {'Type'}")
        click.echo("-" * 70)
        for project in all_projects[:10]:
            proj_type = project['type'].capitalize()
            click.echo(f"{project['name']:<50} {proj_type}")
        if len(all_projects) > 10:
            click.echo(f"... and {len(all_projects) - 10} more projects")
        
        # Select project
        click.echo("\n" + "=" * 60)
        click.echo("STEP 2: Select Project")
        click.echo("=" * 60)
        click.echo("(Use arrow keys to navigate, ENTER to select)")
        click.echo()
        
        selected_project = select_project_from_list(all_projects)
        
        if not selected_project:
            click.echo("\nNo project selected. Exiting.")
            sys.exit(0)
        
        # Get repositories from project
        click.echo(f"\nFetching repositories from project '{selected_project['name']}'...", nl=False)
        try:
            selected_repos = github_client.get_issues_from_project(selected_project['id'])
            click.echo(f" Found {len(selected_repos)} repositories with issues")
        except Exception as e:
            click.echo(f" FAILED", err=True)
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        if not selected_repos:
            click.echo("\nNo repositories found in this project.")
            sys.exit(0)
        
        click.echo("\nRepositories in this project:")
        for repo in selected_repos:
            click.echo(f"  - {repo}")
    
    if not selected_repos:
        click.echo("\nNo repositories selected. Exiting.")
        sys.exit(0)
    
    # Ask about filters
    click.echo("\n" + "=" * 60)
    click.echo("STEP 3: Apply Filters (Optional)")
    click.echo("=" * 60)
    
    filters = prompt_for_filters()
    
    # Display summary
    click.echo("\n" + "=" * 60)
    click.echo("STEP 4: Extracting Issues")
    click.echo("=" * 60)
    click.echo(f"\nSelected repositories: {len(selected_repos)}")
    for repo in selected_repos:
        click.echo(f"  - {repo}")
    
    if filters:
        click.echo(f"\nActive filters:")
        display_filters(filters)
    
    click.echo()
    
    # Save configuration
    save_to_config(config, selected_repos)

    # Build a project status map once for all selected repos
    click.echo("\nFetching project statuses...", nl=False)
    status_map = _build_status_map(selected_repos)
    if status_map:
        click.echo(f" Found status for {len(status_map)} project item(s)")
    else:
        click.echo(" (skipped — no project access or token lacks 'project' scope)")

    # Fetch issues from each selected repository
    total_issues = 0
    for repo_name in selected_repos:
        click.echo(f"\nFetching issues from {repo_name}...", nl=False)
        
        try:
            issues = github_client.fetch_issues(repo_name, filters)
            click.echo(f" Found {len(issues)} issues")

            # Overlay project status values
            _overlay_status(issues, repo_name, status_map)
            
            # Save filters for this repository
            if filters:
                storage.save_filters(repo_name, filters)
            
            # Save each issue
            if issues:
                with click.progressbar(issues, label='Saving issues') as bar:
                    for issue in bar:
                        storage.save_issue(repo_name, issue)
            
            total_issues += len(issues)
            click.echo(f"  ✓ Saved {len(issues)} issues")
            
        except Exception as e:
            click.echo(f" FAILED", err=True)
            click.echo(f"  Error: {e}", err=True)
            continue
    
    click.echo("\n" + "=" * 60)
    click.echo("COMPLETE!")
    click.echo("=" * 60)
    click.echo(f"Total issues extracted: {total_issues}")
    click.echo(f"Issues saved to: {storage.base_dir}")
    click.echo(f"Configuration saved to: {config}")
    if filters:
        click.echo(f"\nFilters saved. Run 'python -m src.cli update' to sync changes later.")
    click.echo("=" * 60 + "\n")


@cli.command()
@click.option('--config', default='config.yaml', help='Path to configuration file')
def update(config):
    """Check for changes and update local issue files.
    
    This command checks each configured repository for changes to existing issues
    or new issues. It applies the same filters that were used during fetch.
    Updates local markdown files and generates a detailed change report.
    """
    click.echo("GitHub Issue Extractor - Update Issues")
    click.echo("=" * 60)
    
    # Load configuration
    repos = load_config(config)
    if not repos:
        click.echo("\nError: No repositories configured.", err=True)
        sys.exit(1)
    
    click.echo(f"\nChecking {len(repos)} repositories for changes...")
    click.echo()
    
    # Initialize components
    try:
        github_client = GitHubClient()
        storage = IssueStorage()
        tracker = ChangeTracker(storage)
        reporter = ChangeReporter()
    except Exception as e:
        click.echo(f"\nError initializing: {e}", err=True)
        sys.exit(1)
    
    # Test connection
    click.echo("Testing GitHub connection...", nl=False)
    if not github_client.test_connection():
        click.echo(" FAILED", err=True)
        sys.exit(1)
    click.echo(" OK\n")
    
    # Build a project status map once for all configured repos
    click.echo("Fetching project statuses...", nl=False)
    status_map = _build_status_map(repos)
    if status_map:
        click.echo(f" Found status for {len(status_map)} project item(s)\n")
    else:
        click.echo(" (skipped)\n")

    # Track changes for all repositories
    all_changes = {}
    
    for repo_name in repos:
        click.echo(f"Checking {repo_name}...", nl=False)
        
        try:
            # Load stored filters for this repository
            filters = storage.load_filters(repo_name)
            
            if filters:
                click.echo(f" (applying stored filters)", nl=False)
            
            # Fetch current issues with filters
            current_issues = github_client.fetch_issues(repo_name, filters)
            click.echo(f" {len(current_issues)} issues")

            # Overlay project status values before change detection
            _overlay_status(current_issues, repo_name, status_map)
            
            # Display filters if any
            if filters:
                click.echo(f"  Filters: ", nl=False)
                filter_parts = []
                if filters.get('author'):
                    filter_parts.append(f"author={filters['author']}")
                if filters.get('assignee'):
                    filter_parts.append(f"assignee={filters['assignee']}")
                if filters.get('state') and filters['state'] != 'all':
                    filter_parts.append(f"state={filters['state']}")
                if filters.get('labels'):
                    labels_str = ','.join(filters['labels']) if isinstance(filters['labels'], list) else filters['labels']
                    filter_parts.append(f"labels={labels_str}")
                click.echo(', '.join(filter_parts))
            
            # Detect changes
            changes = tracker.detect_changes(repo_name, current_issues)
            all_changes[repo_name] = changes
            
            # Update changed and new issues
            issues_to_save = changes['new'] + [u['issue'] for u in changes['updated']]
            
            if issues_to_save:
                with click.progressbar(issues_to_save, label='  Updating') as bar:
                    for issue in bar:
                        storage.save_issue(repo_name, issue)
            
            # Delete issues that are no longer present (filtered out or removed)
            deleted_numbers = tracker.get_deleted_issues(repo_name, current_issues)
            for number in deleted_numbers:
                storage.delete_issue(repo_name, number)
            changes['deleted'] = deleted_numbers
            
            # Print quick summary
            new_count = len(changes['new'])
            updated_count = len(changes['updated'])
            deleted_count = len(deleted_numbers)
            if new_count > 0 or updated_count > 0 or deleted_count > 0:
                parts = []
                if new_count:
                    parts.append(f"New: {new_count}")
                if updated_count:
                    parts.append(f"Updated: {updated_count}")
                if deleted_count:
                    parts.append(f"Removed: {deleted_count}")
                click.echo(f"  ✓ {', '.join(parts)}")
            else:
                click.echo(f"  ✓ No changes")
                
        except Exception as e:
            click.echo(f" FAILED", err=True)
            click.echo(f"  Error: {e}", err=True)
            all_changes[repo_name] = {'new': [], 'updated': [], 'unchanged': [], 'deleted': []}
            continue
    
    # Generate and save report
    click.echo("\nGenerating change report...", nl=False)
    report_path = reporter.generate_report(all_changes)
    click.echo(f" Done")
    click.echo(f"Report saved to: {report_path}")
    
    # Print summary
    reporter.print_summary(all_changes)


@cli.command()
@click.option('--config', default='config.yaml', help='Path to configuration file')
def status(config):
    """Show status of tracked repositories and issues.
    
    This command displays information about the repositories being tracked
    and the number of issues stored locally.
    """
    click.echo("GitHub Issue Extractor - Status")
    click.echo("=" * 60)
    
    # Load configuration
    repos = load_config(config)
    if not repos:
        click.echo("\nNo repositories configured.")
        sys.exit(0)
    
    storage = IssueStorage()
    
    click.echo(f"\nTracking {len(repos)} repositories:\n")
    
    total_issues = 0
    for repo_name in repos:
        issue_numbers = storage.get_all_issue_numbers(repo_name)
        issue_count = len(issue_numbers)
        total_issues += issue_count
        
        click.echo(f"  {repo_name}: {issue_count} issues")
        
        if issue_count > 0:
            metadata = storage.load_metadata(repo_name)
            issues_data = metadata.get('issues', {})
            filters = metadata.get('filters', {})
            
            # Count by state
            open_count = sum(1 for m in issues_data.values() if m.get('state') == 'open')
            closed_count = sum(1 for m in issues_data.values() if m.get('state') == 'closed')
            click.echo(f"    - Open: {open_count}, Closed: {closed_count}")
            
            # Show filters if any
            if filters:
                click.echo(f"    - Filters: ", nl=False)
                filter_parts = []
                if filters.get('author'):
                    filter_parts.append(f"author={filters['author']}")
                if filters.get('assignee'):
                    filter_parts.append(f"assignee={filters['assignee']}")
                if filters.get('state') and filters['state'] != 'all':
                    filter_parts.append(f"state={filters['state']}")
                if filters.get('labels'):
                    labels_str = ','.join(filters['labels']) if isinstance(filters['labels'], list) else filters['labels']
                    filter_parts.append(f"labels={labels_str}")
                click.echo(', '.join(filter_parts))
    
    click.echo(f"\nTotal issues tracked: {total_issues}")
    click.echo(f"Storage location: {storage.base_dir}")
    click.echo("=" * 60 + "\n")


@cli.command()
@click.option('--config', default='config.yaml', help='Path to configuration file')
@click.option('--save', is_flag=True, help='Automatically save selected repositories to config')
def discover(config, save):
    """Discover repositories your GitHub account has access to.
    
    This command lists all repositories you can access and lets you
    select which ones to add to your configuration file.
    """
    click.echo("GitHub Issue Extractor - Discover Repositories")
    click.echo("=" * 60)
    
    # Initialize GitHub client
    try:
        github_client = GitHubClient()
    except Exception as e:
        click.echo(f"\nError initializing: {e}", err=True)
        sys.exit(1)
    
    # Test connection
    click.echo("\nTesting GitHub connection...", nl=False)
    if not github_client.test_connection():
        click.echo(" FAILED", err=True)
        click.echo("Please check your GITHUB_TOKEN in .env file", err=True)
        sys.exit(1)
    click.echo(" OK")
    
    # Fetch repositories
    click.echo("\nFetching accessible repositories...", nl=False)
    try:
        repos = github_client.get_accessible_repositories()
        click.echo(f" Found {len(repos)} repositories")
    except Exception as e:
        click.echo(f" FAILED", err=True)
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    
    if not repos:
        click.echo("\nNo repositories found.")
        sys.exit(0)
    
    # Display repositories
    click.echo(f"\n{'Repository':<50} {'Issues':<10} {'Access'}")
    click.echo("-" * 70)
    
    for repo in repos:
        access = "Private" if repo['private'] else "Public"
        click.echo(f"{repo['full_name']:<50} {repo['open_issues']:<10} {access}")
    
    click.echo()
    
    # Interactive selection
    click.echo("Select repositories to add to your configuration:")
    click.echo("(Use arrow keys to navigate, SPACE to select, ENTER to confirm)")
    click.echo()
    
    try:
        repo_choices = [f"{r['full_name']} ({r['open_issues']} issues)" for r in repos]
        
        questions = [
            inquirer.Checkbox(
                'repos',
                message="Which repositories do you want to track?",
                choices=repo_choices,
            )
        ]
        
        answers = inquirer.prompt(questions)
        
        if answers is None or not answers.get('repos'):
            click.echo("\nNo repositories selected.")
            sys.exit(0)
        
        # Extract repository names from selections (remove issue count)
        selected = []
        for selection in answers['repos']:
            # Format is "owner/repo (X issues)"
            repo_name = selection.split(' (')[0]
            selected.append(repo_name)
        
        click.echo(f"\nSelected {len(selected)} repositories:")
        for repo in selected:
            click.echo(f"  - {repo}")
        
        # Save to config if requested
        if save:
            save_to_config(config, selected)
            click.echo(f"\n✓ Repositories saved to {config}")
        else:
            click.echo(f"\nTo save these to your config, run:")
            click.echo(f"  python -m src.cli discover --save")
            click.echo(f"\nOr manually add them to {config}:")
            for repo in selected:
                click.echo(f"  - {repo}")
        
    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\nError during selection: {e}", err=True)
        sys.exit(1)
    
    click.echo()


@cli.command()
@click.option('--config', default='config.yaml', help='Path to configuration file')
@click.option('--dry-run', is_flag=True, help='Show what would be pushed without making any changes')
def push(config, dry_run):
    """Push locally-edited issue files back to GitHub.

    This command scans every issue markdown file for each repository in your
    configuration.  If a file has been edited since it was last written by
    this tool (detected via a stored file hash), the updated title and body
    are pushed to GitHub via the REST API.

    Only title and body changes are supported.  Fields such as labels,
    assignees, state, and milestone must be changed through GitHub directly
    or via the set-status command.

    After a successful push the local file is refreshed from GitHub so the
    stored hash stays in sync.

    NOTE: Issues saved before this version of the tool was installed do not
    have a stored file hash.  Run 'python -m src update' first to populate
    hashes for all existing issues, then edit and push as normal.
    """
    click.echo("GitHub Issue Extractor - Push Local Edits")
    click.echo("=" * 60)

    if dry_run:
        click.echo("DRY RUN — no changes will be written to GitHub.\n")

    repos = load_config(config)
    if not repos:
        click.echo("\nError: No repositories configured.", err=True)
        sys.exit(1)

    try:
        github_client = GitHubClient()
        storage = IssueStorage()
    except Exception as e:
        click.echo(f"\nError initializing: {e}", err=True)
        sys.exit(1)

    click.echo("Testing GitHub connection...", nl=False)
    if not github_client.test_connection():
        click.echo(" FAILED", err=True)
        sys.exit(1)
    click.echo(" OK\n")

    total_pushed = 0
    total_skipped_no_hash = 0

    for repo_name in repos:
        issue_numbers = storage.get_all_issue_numbers(repo_name)
        if not issue_numbers:
            continue

        changed: List[int] = []
        no_hash: List[int] = []

        for number in issue_numbers:
            stored_hash = storage.get_stored_file_hash(repo_name, number)
            if stored_hash is None:
                no_hash.append(number)
                continue
            current_hash = storage.compute_current_file_hash(repo_name, number)
            if current_hash != stored_hash:
                changed.append(number)

        if no_hash:
            total_skipped_no_hash += len(no_hash)
            click.echo(
                f"  {repo_name}: {len(no_hash)} issue(s) have no stored hash "
                f"(run 'update' first to populate them) — skipping: "
                f"{', '.join(f'#{n}' for n in no_hash)}"
            )

        if not changed:
            click.echo(f"  {repo_name}: no local changes detected")
            continue

        click.echo(f"  {repo_name}: {len(changed)} issue(s) with local edits — "
                   f"{', '.join(f'#{n}' for n in changed)}")

        for number in changed:
            local = storage.read_issue(repo_name, number)
            if local is None:
                click.echo(f"    #{number}: could not parse local file — skipping", err=True)
                continue

            click.echo(f"    #{number} '{local['title']}'", nl=False)

            if dry_run:
                click.echo(" [dry-run, skipped]")
                continue

            try:
                updated = github_client.update_issue(
                    repo_name, number, local['title'], local['body']
                )
                storage.save_issue(repo_name, updated)
                click.echo(" pushed")
                total_pushed += 1
            except Exception as e:
                click.echo(f" FAILED: {e}", err=True)

    click.echo("\n" + "=" * 60)
    if dry_run:
        click.echo("Dry-run complete — nothing was changed.")
    else:
        click.echo(f"Push complete.  {total_pushed} issue(s) updated on GitHub.")
    if total_skipped_no_hash:
        click.echo(
            f"{total_skipped_no_hash} issue(s) skipped (no stored hash). "
            "Run 'python -m src update' to populate hashes."
        )
    click.echo("=" * 60 + "\n")


@cli.command('set-status')
@click.argument('repo')
@click.argument('issue_number', type=int)
@click.argument('status')
@click.option('--project', default=None, help='Project name (required if org has multiple projects)')
@click.option('--org', default=None,
              help='GitHub organisation login. Defaults to the owner part of REPO.')
@click.option('--list-statuses', 'list_statuses', is_flag=True,
              help='List available status options for the project and exit.')
def set_status(repo, issue_number, status, project, org, list_statuses):
    """Update the Projects v2 Status field for an issue.

    \b
    REPO         Repository in 'owner/repo' format (e.g. DBDHub/MyApp)
    ISSUE_NUMBER GitHub issue number
    STATUS       Desired status value (e.g. 'Done', 'In Progress')

    Examples:

    \b
      # Update issue #42 in the MyConnect project to 'Done'
      python -m src set-status DBDHub/MyApp 42 "Done" --project MyConnect

    \b
      # List available status options
      python -m src set-status DBDHub/MyApp 0 "" --project MyConnect --list-statuses

    NOTE: Your GITHUB_TOKEN must have the 'project' scope (read:project is
    not sufficient for mutations).
    """
    # Infer org from repo owner if not provided
    if org is None:
        parts = repo.split('/')
        if len(parts) != 2:
            click.echo("Error: REPO must be in 'owner/repo' format.", err=True)
            sys.exit(1)
        org = parts[0]

    try:
        updater = ProjectUpdater()
    except Exception as e:
        click.echo(f"\nError initializing: {e}", err=True)
        sys.exit(1)

    # --list-statuses mode: just print options and exit
    if list_statuses:
        if not project:
            click.echo("Error: --project is required with --list-statuses.", err=True)
            sys.exit(1)
        try:
            statuses = updater.list_available_statuses(org, project)
            click.echo(f"Available statuses for project '{project}':")
            for s in statuses:
                click.echo(f"  - {s}")
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    # Normal update mode
    if not status:
        click.echo("Error: STATUS argument is required.", err=True)
        sys.exit(1)

    # If no project specified, scan the org to find the right one
    if project is None:
        click.echo(f"No --project specified. Scanning projects in '{org}'...", nl=False)
        try:
            projects = updater.list_projects(org)
        except Exception as e:
            click.echo(f"\nError: {e}", err=True)
            sys.exit(1)

        if not projects:
            click.echo(f"\nNo projects found in organisation '{org}'.", err=True)
            sys.exit(1)

        if len(projects) == 1:
            project = projects[0]['title']
            click.echo(f" using '{project}'")
        else:
            click.echo("")
            names = [p['title'] for p in projects]
            click.echo("Multiple projects found. Please specify one with --project:")
            for name in names:
                click.echo(f"  - {name}")
            sys.exit(1)

    click.echo(f"Updating #{issue_number} in {repo} → status '{status}' "
               f"(project: {project})...")

    try:
        updater.update_status(org, project, repo, issue_number, status)
        click.echo(f"  Done. Issue #{issue_number} status set to '{status}'.")
    except Exception as e:
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)

    # Re-fetch the single issue and save locally so stored metadata stays current.
    try:
        github_client = GitHubClient()
        storage = IssueStorage()
        issue = github_client.get_issue(repo, issue_number, include_comments=False)
        storage.save_issue(repo, issue)
        click.echo(f"  Local file updated.")
    except Exception:
        # Non-fatal: the push to GitHub succeeded; local sync is best-effort.
        click.echo("  Note: could not refresh local file — run 'update' to sync.")


@cli.command()
@click.argument('repo')
@click.argument('issue_number', type=int)
@click.argument('body')
def comment(repo, issue_number, body):
    """Post a comment on a GitHub issue.

    \b
    REPO         Repository in 'owner/repo' format (e.g. DBDHub/MyApp)
    ISSUE_NUMBER GitHub issue number
    BODY         Comment text (markdown supported; quote multi-word text)

    Example:

    \b
      python -m src comment DBDHub/MyApp 42 "Moving to Securitas Review for April release"

    NOTE: Your GITHUB_TOKEN must have the 'repo' scope to post comments.
    """
    try:
        github_client = GitHubClient()
        storage = IssueStorage()
    except Exception as e:
        click.echo(f"\nError initializing: {e}", err=True)
        sys.exit(1)

    click.echo(f"Posting comment on {repo}#{issue_number}...")

    try:
        result = github_client.create_comment(repo, issue_number, body)
        click.echo(f"  Comment posted by {result['author']} at {result['created_at']}")
    except Exception as e:
        click.echo(f"  Error: {e}", err=True)
        sys.exit(1)

    # Refresh the local issue file so the new comment appears locally.
    try:
        issue = github_client.get_issue(repo, issue_number, include_comments=True)
        storage.save_issue(repo, issue)
        click.echo(f"  Local file updated.")
    except Exception:
        click.echo("  Note: could not refresh local file — run 'update' to sync.")


def load_config(config_path: str) -> List[str]:
    """Load repository configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        List of repository names
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        click.echo(f"Error: Configuration file not found: {config_path}", err=True)
        click.echo("Please create a config.yaml file with your repositories.", err=True)
        sys.exit(1)
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        repos = config.get('repositories', [])
        # Filter out None, empty strings, and comments
        if repos is None:
            repos = []
        repos = [r for r in repos if r and isinstance(r, str)]
        
        return repos
    except yaml.YAMLError as e:
        click.echo(f"Error parsing configuration file: {e}", err=True)
        sys.exit(1)


def save_to_config(config_path: str, repositories: List[str]):
    """Save repositories to configuration file.
    
    Args:
        config_path: Path to configuration file
        repositories: List of repository names to save
    """
    config_file = Path(config_path)
    
    # Load existing config or create new structure
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            config = {}
    else:
        config = {}
    
    # Merge with existing repositories (avoid duplicates)
    existing_repos = set(config.get('repositories', []) or [])
    all_repos = sorted(list(existing_repos.union(set(repositories))))
    
    config['repositories'] = all_repos
    
    # Save to file
    try:
        with open(config_file, 'w') as f:
            f.write("# GitHub Issue Extractor Configuration\n")
            f.write("# Repositories to track\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        click.echo(f"Error saving configuration: {e}", err=True)
        sys.exit(1)


def select_repositories(all_repos: List[str]) -> List[str]:
    """Interactive multi-select for choosing repositories.
    
    Args:
        all_repos: List of all available repository names
        
    Returns:
        List of selected repository names
    """
    if not all_repos:
        return []
    
    # If only one repo, select it automatically
    if len(all_repos) == 1:
        click.echo(f"\nAuto-selecting single repository: {all_repos[0]}")
        return all_repos
    
    click.echo("\nSelect repositories to fetch from:")
    click.echo("(Use arrow keys to navigate, SPACE to select, ENTER to confirm)")
    click.echo()
    
    try:
        questions = [
            inquirer.Checkbox(
                'repos',
                message="Which repositories do you want to fetch issues from?",
                choices=all_repos,
                default=all_repos  # Pre-select all by default
            )
        ]
        
        answers = inquirer.prompt(questions)
        
        if answers is None:
            # User cancelled (Ctrl+C)
            return []
        
        return answers.get('repos', [])
    
    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        return []
    except Exception as e:
        # Fallback to all repos if inquirer fails
        click.echo(f"\nInteractive selection failed: {e}")
        click.echo("Proceeding with all repositories...")
        return all_repos


def prompt_selection_method() -> Optional[str]:
    """Ask user how they want to select: by repositories or projects.
    
    Returns:
        'repositories' or 'projects', or None if cancelled
    """
    try:
        questions = [
            inquirer.List(
                'method',
                message="How would you like to select issues?",
                choices=[
                    ('Select individual repositories', 'repositories'),
                    ('Select by GitHub Project', 'projects'),
                ],
            )
        ]
        
        answers = inquirer.prompt(questions)
        
        if answers is None:
            return None
        
        return answers.get('method')
        
    except KeyboardInterrupt:
        return None
    except Exception as e:
        click.echo(f"\nSelection failed: {e}. Defaulting to repositories.", err=True)
        return 'repositories'


def select_repos_from_list(repos: List[Dict[str, Any]]) -> List[str]:
    """Interactive selection from list of repository dictionaries.
    
    Args:
        repos: List of repository dictionaries with metadata
        
    Returns:
        List of selected repository full names (owner/repo)
    """
    if not repos:
        return []
    
    try:
        repo_choices = [f"{r['full_name']} ({r['open_issues']} issues)" for r in repos]
        
        questions = [
            inquirer.Checkbox(
                'repos',
                message="Which repositories do you want to track?",
                choices=repo_choices,
            )
        ]
        
        answers = inquirer.prompt(questions)
        
        if answers is None or not answers.get('repos'):
            return []
        
        # Extract repository names from selections (remove issue count)
        selected = []
        for selection in answers['repos']:
            # Format is "owner/repo (X issues)"
            repo_name = selection.split(' (')[0]
            selected.append(repo_name)
        
        return selected
        
    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        return []
    except Exception as e:
        click.echo(f"\nSelection failed: {e}", err=True)
        return []


def select_project_from_list(projects: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Interactive selection from list of project dictionaries.
    
    Args:
        projects: List of project dictionaries with metadata
        
    Returns:
        Selected project dictionary, or None if cancelled
    """
    if not projects:
        return None
    
    try:
        project_choices = [(f"{p['name']} ({p['type']})", p) for p in projects]
        
        questions = [
            inquirer.List(
                'project',
                message="Which project do you want to extract issues from?",
                choices=project_choices,
            )
        ]
        
        answers = inquirer.prompt(questions)
        
        if answers is None:
            return None
        
        return answers.get('project')
        
    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        return None
    except Exception as e:
        click.echo(f"\nSelection failed: {e}", err=True)
        return None


def prompt_for_filters() -> Dict[str, Any]:
    """Interactively prompt user for filter options.
    
    Returns:
        Dictionary of filter parameters
    """
    filters = {}
    
    try:
        # Ask if user wants to apply filters
        questions = [
            inquirer.Confirm(
                'apply_filters',
                message="Do you want to apply any filters? (No = fetch all issues)",
                default=False
            )
        ]
        
        answers = inquirer.prompt(questions)
        
        if not answers or not answers.get('apply_filters'):
            click.echo("No filters applied. Will fetch all issues.")
            return {}
        
        click.echo("\nFilter options (leave blank to skip):")
        
        # Ask for each filter
        filter_questions = [
            inquirer.Text('author', message="Filter by author (username)"),
            inquirer.Text('assignee', message="Filter by assignee (username)"),
            inquirer.List('state',
                         message="Filter by state",
                         choices=['all', 'open', 'closed'],
                         default='all'),
            inquirer.Text('labels', message="Filter by labels (comma-separated)"),
            inquirer.Text('milestone', message="Filter by milestone (title, '*' for any, 'none' for no milestone)"),
            inquirer.Text('since', message="Filter since date (YYYY-MM-DD)"),
        ]
        
        filter_answers = inquirer.prompt(filter_questions)
        
        if not filter_answers:
            return {}
        
        # Build filters dictionary
        if filter_answers.get('author'):
            filters['author'] = filter_answers['author']
        
        if filter_answers.get('assignee'):
            filters['assignee'] = filter_answers['assignee']
        
        if filter_answers.get('state') and filter_answers['state'] != 'all':
            filters['state'] = filter_answers['state']
        elif filter_answers.get('state') == 'all':
            filters['state'] = 'all'
        
        if filter_answers.get('labels'):
            filters['labels'] = [l.strip() for l in filter_answers['labels'].split(',')]
        
        if filter_answers.get('milestone'):
            filters['milestone'] = filter_answers['milestone']
        
        if filter_answers.get('since'):
            if validate_date(filter_answers['since']):
                filters['since'] = filter_answers['since']
            else:
                click.echo(f"Warning: Invalid date format '{filter_answers['since']}'. Skipping.", err=True)
        
        return filters
        
    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        return {}
    except Exception as e:
        click.echo(f"\nError getting filters: {e}. Proceeding without filters.", err=True)
        return {}


def build_filters(author: Optional[str], assignee: Optional[str], milestone: Optional[str],
                 labels: Optional[str], state: str, since: Optional[str], 
                 until: Optional[str]) -> Dict[str, Any]:
    """Build filter dictionary from CLI parameters.
    
    Args:
        author: Author username filter
        assignee: Assignee username filter
        milestone: Milestone title filter
        labels: Comma-separated labels
        state: Issue state (open/closed/all)
        since: Date string (YYYY-MM-DD)
        until: Date string (YYYY-MM-DD)
        
    Returns:
        Dictionary of filters (empty if no filters provided)
    """
    filters = {}
    
    if author:
        filters['author'] = author
    
    if assignee:
        filters['assignee'] = assignee
    
    if milestone:
        filters['milestone'] = milestone
    
    if labels:
        # Convert comma-separated string to list
        filters['labels'] = [l.strip() for l in labels.split(',')]
    
    if state and state != 'all':
        filters['state'] = state
    elif state == 'all':
        filters['state'] = 'all'
    
    if since:
        # Validate date format
        if validate_date(since):
            filters['since'] = since
        else:
            click.echo(f"Warning: Invalid date format for --since: {since}. Expected YYYY-MM-DD", err=True)
    
    if until:
        # Validate date format
        if validate_date(until):
            filters['until'] = until
        else:
            click.echo(f"Warning: Invalid date format for --until: {until}. Expected YYYY-MM-DD", err=True)
    
    return filters


def validate_date(date_str: str) -> bool:
    """Validate date string format (YYYY-MM-DD).

    Uses strptime with an explicit format so that partial ISO strings such as
    '2024-01' or '2024' are rejected (fromisoformat accepts them on Python 3.11+).

    Args:
        date_str: Date string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except (ValueError, AttributeError):
        return False


def display_filters(filters: Dict[str, Any]):
    """Display active filters in a user-friendly format.
    
    Args:
        filters: Dictionary of filter parameters
    """
    if filters.get('author'):
        click.echo(f"  - Author: {filters['author']}")
    
    if filters.get('assignee'):
        click.echo(f"  - Assignee: {filters['assignee']}")
    
    if filters.get('milestone'):
        click.echo(f"  - Milestone: {filters['milestone']}")
    
    if filters.get('labels'):
        labels_str = ', '.join(filters['labels']) if isinstance(filters['labels'], list) else filters['labels']
        click.echo(f"  - Labels: {labels_str}")
    
    if filters.get('state') and filters['state'] != 'all':
        click.echo(f"  - State: {filters['state']}")
    elif filters.get('state') == 'all':
        click.echo(f"  - State: all (open and closed)")
    
    if filters.get('since'):
        click.echo(f"  - Since: {filters['since']}")
    
    if filters.get('until'):
        click.echo(f"  - Until: {filters['until']}")


def _build_status_map(repos: List[str]) -> Dict:
    """Fetch a (repo_name_lower, issue_number) -> status map for all orgs in repos.

    Silently returns an empty dict if the token lacks project scope or any
    other error occurs, so that status enrichment is always optional.

    Args:
        repos: List of repository names in 'owner/repo' format

    Returns:
        Dict keyed by (repo_name.lower(), issue_number) with status strings
    """
    orgs = {r.split('/')[0] for r in repos if '/' in r}
    if not orgs:
        return {}

    try:
        updater = ProjectUpdater()
    except Exception:
        return {}

    combined: Dict = {}
    for org in orgs:
        try:
            org_map = updater.build_repo_status_map(org)
            combined.update(org_map)
        except Exception:
            pass

    return combined


def _overlay_status(issues: List[Dict[str, Any]], repo_name: str, status_map: Dict) -> List[Dict[str, Any]]:
    """Apply project status values from status_map onto the issue dicts in-place.

    Args:
        issues: List of issue data dicts
        repo_name: Full repository name in 'owner/repo' format
        status_map: Dict from _build_status_map

    Returns:
        The same list with status overlaid where available
    """
    if not status_map:
        return issues
    repo_key = repo_name.lower()
    for issue in issues:
        key = (repo_key, issue['number'])
        if key in status_map:
            issue['status'] = status_map[key]
    return issues


if __name__ == '__main__':
    cli()


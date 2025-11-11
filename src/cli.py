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
    
    # Fetch issues from each selected repository
    total_issues = 0
    for repo_name in selected_repos:
        click.echo(f"\nFetching issues from {repo_name}...", nl=False)
        
        try:
            issues = github_client.fetch_issues(repo_name, filters)
            click.echo(f" Found {len(issues)} issues")
            
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
            
            # Print quick summary
            new_count = len(changes['new'])
            updated_count = len(changes['updated'])
            if new_count > 0 or updated_count > 0:
                click.echo(f"  ✓ New: {new_count}, Updated: {updated_count}")
            else:
                click.echo(f"  ✓ No changes")
                
        except Exception as e:
            click.echo(f" FAILED", err=True)
            click.echo(f"  Error: {e}", err=True)
            all_changes[repo_name] = {'new': [], 'updated': [], 'unchanged': []}
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
            inquirer.Text('milestone', message="Filter by milestone"),
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
    
    Args:
        date_str: Date string to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        from datetime import datetime
        datetime.fromisoformat(date_str)
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


if __name__ == '__main__':
    cli()


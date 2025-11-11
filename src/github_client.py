"""GitHub API client for fetching issues."""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from github import Github, GithubException
from dotenv import load_dotenv


class GitHubClient:
    """Client for interacting with GitHub API to fetch issues."""
    
    def __init__(self):
        """Initialize the GitHub client with authentication."""
        load_dotenv()
        token = os.getenv('GITHUB_TOKEN')
        
        if not token:
            raise ValueError(
                "GITHUB_TOKEN not found in environment variables. "
                "Please create a .env file with your GitHub token."
            )
        
        self.client = Github(token)
        
    def test_connection(self) -> bool:
        """Test the GitHub API connection and token validity.
        
        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            user = self.client.get_user()
            user.login  # Force API call
            return True
        except GithubException:
            return False
    
    def get_accessible_repositories(self) -> List[Dict[str, Any]]:
        """Get all repositories the authenticated user has access to.
        
        Returns:
            List of repository dictionaries with name, description, and metadata
        """
        repos = []
        
        try:
            # Get user's own repositories
            user = self.client.get_user()
            
            for repo in user.get_repos():
                repos.append({
                    'full_name': repo.full_name,
                    'name': repo.name,
                    'owner': repo.owner.login,
                    'description': repo.description or '',
                    'private': repo.private,
                    'open_issues': repo.open_issues_count,
                    'url': repo.html_url,
                })
            
            return sorted(repos, key=lambda x: x['full_name'].lower())
            
        except GithubException as e:
            raise Exception(f"Failed to fetch repositories: {str(e)}")
    
    def get_user_projects(self) -> List[Dict[str, Any]]:
        """Get all GitHub Projects (classic and new) the user has access to.
        
        Returns:
            List of project dictionaries with name, description, and metadata
        """
        projects = []
        
        try:
            user = self.client.get_user()
            
            # Get projects from user's organizations
            for org in user.get_orgs():
                try:
                    # Note: PyGithub doesn't have full support for new Projects (beta)
                    # This gets classic projects
                    for project in org.get_projects(state='open'):
                        projects.append({
                            'id': project.id,
                            'name': project.name,
                            'owner': org.login,
                            'description': project.body or '',
                            'type': 'organization',
                            'url': project.html_url,
                        })
                except:
                    pass  # Some orgs may not have projects enabled
            
            # Get user's personal projects
            try:
                # User projects aren't directly accessible via PyGithub's user object
                # We'll need to get them from repositories
                for repo in user.get_repos():
                    try:
                        for project in repo.get_projects(state='open'):
                            projects.append({
                                'id': project.id,
                                'name': f"{project.name} ({repo.name})",
                                'owner': repo.owner.login,
                                'description': project.body or '',
                                'type': 'repository',
                                'url': project.html_url,
                                'repo': repo.full_name,
                            })
                    except:
                        pass  # Repo may not have projects
            except:
                pass
            
            return sorted(projects, key=lambda x: x['name'].lower())
            
        except GithubException as e:
            raise Exception(f"Failed to fetch projects: {str(e)}")
    
    def get_issues_from_project(self, project_id: int) -> List[str]:
        """Get repository names that have issues in a specific project.
        
        Args:
            project_id: The GitHub project ID
            
        Returns:
            List of repository full names (owner/repo) that have issues in this project
        """
        repos = set()
        
        try:
            # Get the project
            project = self.client.get_project(project_id)
            
            # Get all columns in the project
            for column in project.get_columns():
                # Get all cards in each column
                for card in column.get_cards():
                    # If card has content (an issue or PR)
                    if card.content_url:
                        try:
                            # Extract repo from content URL
                            # Format: https://api.github.com/repos/owner/repo/issues/123
                            parts = card.content_url.split('/repos/')
                            if len(parts) > 1:
                                repo_path = parts[1].split('/issues/')[0]
                                repos.add(repo_path)
                        except:
                            pass
            
            return sorted(list(repos))
            
        except GithubException as e:
            raise Exception(f"Failed to fetch project issues: {str(e)}")
    
    def fetch_issues(self, repo_name: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Fetch issues from a repository with optional filtering.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            filters: Optional dictionary of filter parameters:
                - author: Filter by issue author username
                - assignee: Filter by assignee username
                - milestone: Filter by milestone title
                - labels: List of label names (issues must have all)
                - state: 'open', 'closed', or 'all' (default: 'all')
                - since: ISO format date string (YYYY-MM-DD)
                - until: ISO format date string (YYYY-MM-DD)
            
        Returns:
            List of issue dictionaries with all relevant data
            
        Raises:
            GithubException: If repository not found or access denied
        """
        if filters is None:
            filters = {}
        
        try:
            repo = self.client.get_repo(repo_name)
            
            # Build API parameters from filters
            api_params = self._build_api_params(filters)
            
            # Fetch issues with API-level filters
            issues = repo.get_issues(**api_params)
            
            issue_list = []
            for issue in issues:
                # Skip pull requests (they appear in issues endpoint)
                if issue.pull_request:
                    continue
                
                # Apply client-side filters that API doesn't support
                if not self._matches_client_filters(issue, filters):
                    continue
                
                issue_data = self._extract_issue_data(issue)
                issue_list.append(issue_data)
            
            return issue_list
            
        except GithubException as e:
            raise Exception(f"Failed to fetch issues from {repo_name}: {str(e)}")
    
    def _build_api_params(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build PyGithub API parameters from filter dictionary.
        
        Args:
            filters: Filter dictionary
            
        Returns:
            Dictionary of API parameters for get_issues()
        """
        params = {}
        
        # State filter (API supports this)
        state = filters.get('state', 'all')
        if state in ['open', 'closed', 'all']:
            params['state'] = state
        
        # Creator filter (API supports this)
        if filters.get('author'):
            params['creator'] = filters['author']
        
        # Assignee filter (API supports this)
        if filters.get('assignee'):
            params['assignee'] = filters['assignee']
        
        # Milestone filter (API supports this)
        if filters.get('milestone'):
            params['milestone'] = filters['milestone']
        
        # Labels filter (API supports this)
        if filters.get('labels'):
            labels = filters['labels']
            if isinstance(labels, str):
                labels = [l.strip() for l in labels.split(',')]
            params['labels'] = labels
        
        # Since filter (API supports this)
        if filters.get('since'):
            try:
                since_date = datetime.fromisoformat(filters['since'].replace('Z', '+00:00'))
                params['since'] = since_date
            except (ValueError, AttributeError):
                pass  # Invalid date format, skip filter
        
        return params
    
    def _matches_client_filters(self, issue, filters: Dict[str, Any]) -> bool:
        """Check if issue matches client-side filters.
        
        Some filters need to be applied client-side because the API doesn't support them.
        
        Args:
            issue: PyGithub Issue object
            filters: Filter dictionary
            
        Returns:
            True if issue matches all client-side filters
        """
        # Until date filter (not supported by API)
        if filters.get('until'):
            try:
                until_date = datetime.fromisoformat(filters['until'].replace('Z', '+00:00'))
                if issue.created_at > until_date:
                    return False
            except (ValueError, AttributeError):
                pass  # Invalid date format, skip filter
        
        return True
    
    def _extract_issue_data(self, issue) -> Dict[str, Any]:
        """Extract all relevant data from a GitHub issue object.
        
        Args:
            issue: PyGithub Issue object
            
        Returns:
            Dictionary containing all issue data
        """
        # Extract comments
        comments = []
        for comment in issue.get_comments():
            comments.append({
                'author': comment.user.login if comment.user else 'ghost',
                'body': comment.body or '',
                'created_at': comment.created_at.isoformat(),
                'updated_at': comment.updated_at.isoformat()
            })
        
        # Extract labels
        labels = [label.name for label in issue.labels]
        
        # Extract assignees
        assignees = [assignee.login for assignee in issue.assignees]
        
        # Build issue data dictionary
        issue_data = {
            'number': issue.number,
            'title': issue.title or '',
            'body': issue.body or '',
            'state': issue.state,
            'labels': labels,
            'author': issue.user.login if issue.user else 'ghost',
            'assignees': assignees,
            'created_at': issue.created_at.isoformat(),
            'updated_at': issue.updated_at.isoformat(),
            'closed_at': issue.closed_at.isoformat() if issue.closed_at else None,
            'url': issue.html_url,
            'comments': comments,
            'milestone': issue.milestone.title if issue.milestone else None,
        }
        
        return issue_data


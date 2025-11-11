"""Change detection and tracking for GitHub issues."""

from typing import Dict, Any, List, Set
from .storage import IssueStorage


class ChangeTracker:
    """Tracks and detects changes in GitHub issues."""
    
    def __init__(self, storage: IssueStorage):
        """Initialize change tracker.
        
        Args:
            storage: IssueStorage instance for accessing metadata
        """
        self.storage = storage
    
    def detect_changes(self, repo_name: str, current_issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect changes between stored issues and current issues.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            current_issues: List of current issue data from GitHub API
            
        Returns:
            Dictionary containing categorized changes:
            {
                'new': [list of new issues],
                'updated': [list of updated issues with details],
                'unchanged': [list of unchanged issue numbers]
            }
        """
        metadata = self.storage.load_metadata(repo_name)
        stored_issues = metadata.get('issues', {})
        stored_issue_numbers = set(stored_issues.keys())
        current_issue_numbers = {str(issue['number']) for issue in current_issues}
        
        changes = {
            'new': [],
            'updated': [],
            'unchanged': []
        }
        
        for issue in current_issues:
            issue_number = str(issue['number'])
            current_hash = self.storage._calculate_hash(issue)
            
            if issue_number not in stored_issue_numbers:
                # New issue
                changes['new'].append(issue)
            else:
                # Check if issue changed
                stored_hash = stored_issues[issue_number].get('hash')
                
                if current_hash != stored_hash:
                    # Issue changed - detect what changed
                    change_details = self._detect_issue_changes(
                        repo_name, issue, stored_issues[issue_number]
                    )
                    changes['updated'].append({
                        'issue': issue,
                        'changes': change_details
                    })
                else:
                    changes['unchanged'].append(int(issue_number))
        
        return changes
    
    def _detect_issue_changes(self, repo_name: str, current_issue: Dict[str, Any], 
                              stored_metadata: Dict[str, Any]) -> List[str]:
        """Detect specific changes in an issue.
        
        Args:
            repo_name: Repository name
            current_issue: Current issue data
            stored_metadata: Stored metadata for the issue
            
        Returns:
            List of change descriptions
        """
        changes = []
        
        # Check state change
        if stored_metadata.get('state') != current_issue['state']:
            old_state = stored_metadata.get('state', 'unknown')
            new_state = current_issue['state']
            changes.append(f"State changed from '{old_state}' to '{new_state}'")
        
        # Check update timestamp
        if stored_metadata.get('updated_at') != current_issue['updated_at']:
            changes.append(f"Updated at {current_issue['updated_at']}")
        
        # Note: More granular changes (title, body, labels, comments) would require
        # storing more detailed metadata or parsing the markdown file
        # For now, we report that the issue was updated
        if not changes:
            changes.append("Content modified")
        
        return changes
    
    def get_deleted_issues(self, repo_name: str, current_issues: List[Dict[str, Any]]) -> List[int]:
        """Detect issues that were deleted or no longer accessible.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            current_issues: List of current issue data from GitHub API
            
        Returns:
            List of issue numbers that are stored locally but not in current issues
        """
        metadata = self.storage.load_metadata(repo_name)
        stored_issues = metadata.get('issues', {})
        stored_issue_numbers = {int(num) for num in stored_issues.keys()}
        current_issue_numbers = {issue['number'] for issue in current_issues}
        
        deleted = list(stored_issue_numbers - current_issue_numbers)
        return sorted(deleted)


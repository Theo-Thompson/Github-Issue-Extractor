"""Storage layer for managing issue markdown files and metadata."""

import os
import json
import hashlib
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class IssueStorage:
    """Manages storage of issues as markdown files with metadata tracking."""
    
    def __init__(self, base_dir: str = "issues"):
        """Initialize storage manager.
        
        Args:
            base_dir: Base directory for storing issue files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
    
    def get_repo_dir(self, repo_name: str) -> Path:
        """Get the directory path for a specific repository.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            
        Returns:
            Path object for the repository directory
        """
        # Convert owner/repo to owner-repo for directory name
        repo_dir_name = repo_name.replace('/', '-')
        repo_dir = self.base_dir / repo_dir_name
        repo_dir.mkdir(exist_ok=True)
        return repo_dir
    
    def save_issue(self, repo_name: str, issue_data: Dict[str, Any]) -> str:
        """Save an issue as a markdown file.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_data: Dictionary containing issue data
            
        Returns:
            Path to the saved markdown file
        """
        repo_dir = self.get_repo_dir(repo_name)
        issue_number = issue_data['number']
        file_path = repo_dir / f"issue-{issue_number}.md"
        
        # Generate markdown content
        markdown_content = self._generate_markdown(issue_data)
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # Update metadata
        self._update_metadata(repo_name, issue_data)
        
        return str(file_path)
    
    def _generate_markdown(self, issue_data: Dict[str, Any]) -> str:
        """Generate markdown content from issue data.
        
        Args:
            issue_data: Dictionary containing issue data
            
        Returns:
            Markdown formatted string
        """
        # Create YAML frontmatter
        frontmatter = {
            'number': issue_data['number'],
            'title': issue_data['title'],
            'state': issue_data['state'],
            'labels': issue_data['labels'],
            'author': issue_data['author'],
            'created_at': issue_data['created_at'],
            'updated_at': issue_data['updated_at'],
            'assignees': issue_data['assignees'],
            'url': issue_data['url'],
        }
        
        if issue_data.get('closed_at'):
            frontmatter['closed_at'] = issue_data['closed_at']
        
        if issue_data.get('milestone'):
            frontmatter['milestone'] = issue_data['milestone']
        
        # Build markdown content
        lines = ['---']
        lines.append(yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip())
        lines.append('---')
        lines.append('')
        lines.append(f"# {issue_data['title']}")
        lines.append('')
        
        # Add issue body
        if issue_data['body']:
            lines.append(issue_data['body'])
            lines.append('')
        
        # Add comments section
        if issue_data['comments']:
            lines.append('## Comments')
            lines.append('')
            
            for comment in issue_data['comments']:
                lines.append(f"### Comment by {comment['author']} on {comment['created_at']}")
                lines.append('')
                lines.append(comment['body'])
                lines.append('')
        
        return '\n'.join(lines)
    
    def _update_metadata(self, repo_name: str, issue_data: Dict[str, Any]):
        """Update metadata file with issue hash for change detection.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_data: Dictionary containing issue data
        """
        repo_dir = self.get_repo_dir(repo_name)
        metadata_file = repo_dir / '.metadata.json'
        
        # Load existing metadata
        metadata = {}
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        
        # Ensure metadata structure exists
        if 'filters' not in metadata:
            metadata['filters'] = {}
        if 'issues' not in metadata:
            metadata['issues'] = {}
        
        # Calculate hash of issue data
        issue_hash = self._calculate_hash(issue_data)
        
        # Update issue metadata
        issue_number = str(issue_data['number'])
        metadata['issues'][issue_number] = {
            'hash': issue_hash,
            'updated_at': issue_data['updated_at'],
            'state': issue_data['state']
        }
        
        # Save metadata
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    
    def _calculate_hash(self, issue_data: Dict[str, Any]) -> str:
        """Calculate SHA256 hash of issue data for change detection.
        
        Args:
            issue_data: Dictionary containing issue data
            
        Returns:
            SHA256 hash string
        """
        # Create a normalized string representation of the issue
        hash_data = {
            'number': issue_data['number'],
            'title': issue_data['title'],
            'body': issue_data['body'],
            'state': issue_data['state'],
            'labels': sorted(issue_data['labels']),
            'assignees': sorted(issue_data['assignees']),
            'updated_at': issue_data['updated_at'],
            'comments': [
                {
                    'author': c['author'],
                    'body': c['body'],
                    'created_at': c['created_at']
                }
                for c in issue_data['comments']
            ]
        }
        
        # Convert to JSON string and hash
        json_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    def load_metadata(self, repo_name: str) -> Dict[str, Any]:
        """Load metadata for a repository.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            
        Returns:
            Metadata dictionary with structure: {'filters': {...}, 'issues': {...}}
        """
        repo_dir = self.get_repo_dir(repo_name)
        metadata_file = repo_dir / '.metadata.json'
        
        if not metadata_file.exists():
            return {'filters': {}, 'issues': {}}
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Handle old metadata format (backward compatibility)
        if 'filters' not in metadata:
            # Old format: direct issue mapping
            # Convert to new format
            old_issues = {k: v for k, v in metadata.items() if k not in ['filters', 'issues']}
            metadata = {
                'filters': {},
                'issues': old_issues
            }
        
        return metadata
    
    def save_filters(self, repo_name: str, filters: Dict[str, Any]):
        """Save filter configuration for a repository.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            filters: Dictionary of filter parameters
        """
        repo_dir = self.get_repo_dir(repo_name)
        metadata_file = repo_dir / '.metadata.json'
        
        # Load existing metadata
        metadata = self.load_metadata(repo_name)
        
        # Update filters
        metadata['filters'] = filters
        
        # Save metadata
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    
    def load_filters(self, repo_name: str) -> Dict[str, Any]:
        """Load filter configuration for a repository.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            
        Returns:
            Dictionary of filter parameters (empty dict if none)
        """
        metadata = self.load_metadata(repo_name)
        return metadata.get('filters', {})
    
    def issue_exists(self, repo_name: str, issue_number: int) -> bool:
        """Check if an issue file exists.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue number
            
        Returns:
            True if issue file exists, False otherwise
        """
        repo_dir = self.get_repo_dir(repo_name)
        file_path = repo_dir / f"issue-{issue_number}.md"
        return file_path.exists()
    
    def get_all_issue_numbers(self, repo_name: str) -> list:
        """Get all issue numbers stored for a repository.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            
        Returns:
            List of issue numbers
        """
        repo_dir = self.get_repo_dir(repo_name)
        if not repo_dir.exists():
            return []
        
        issue_numbers = []
        for file_path in repo_dir.glob('issue-*.md'):
            # Extract number from filename like 'issue-123.md'
            try:
                number = int(file_path.stem.split('-')[1])
                issue_numbers.append(number)
            except (IndexError, ValueError):
                continue
        
        return sorted(issue_numbers)


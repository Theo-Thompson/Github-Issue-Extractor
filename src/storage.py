"""Storage layer for managing issue markdown files and metadata."""

import os
import json
import hashlib
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv


class IssueStorage:
    """Manages storage of issues as markdown files with metadata tracking."""
    
    def __init__(self, base_dir: str = None):
        """Initialize storage manager.

        Args:
            base_dir: Base directory for storing issue files. If None, defaults to
                     the 'issues' subfolder at the repository root.
        """
        load_dotenv()
        if base_dir is None:
            base_dir = self._get_default_base_dir()
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_default_base_dir(self) -> str:
        """Get the base directory for issue storage.

        Stores inside the repository, in the 'issues' sub-folder at the project root.

        Returns:
            Absolute path to the issues directory
        """
        repo_root = Path(__file__).parent.parent
        return str(repo_root / 'issues')
    
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
        
        # Compute file hash for local-edit detection
        file_hash = hashlib.sha256(markdown_content.encode('utf-8')).hexdigest()
        
        # Update metadata
        self._update_metadata(repo_name, issue_data, file_hash=file_hash)
        
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

        if issue_data.get('status') is not None:
            frontmatter['status'] = issue_data['status']

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
    
    def _update_metadata(self, repo_name: str, issue_data: Dict[str, Any], file_hash: Optional[str] = None):
        """Update metadata file with issue hash for change detection.
        
        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_data: Dictionary containing issue data
        """
        repo_dir = self.get_repo_dir(repo_name)
        metadata_file = repo_dir / '.metadata.json'
        
        # Load existing metadata via the safe loader (handles corrupt JSON)
        metadata = self.load_metadata(repo_name)
        
        # Calculate hash of issue data
        issue_hash = self._calculate_hash(issue_data)
        
        # Merge into the existing record so that fields added by other code
        # paths (e.g. file_hash) are not silently erased.
        issue_number = str(issue_data['number'])
        existing = metadata['issues'].get(issue_number, {})
        existing['hash'] = issue_hash
        existing['updated_at'] = issue_data['updated_at']
        existing['state'] = issue_data['state']
        if file_hash is not None:
            existing['file_hash'] = file_hash
        metadata['issues'][issue_number] = existing
        
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
            'status': issue_data.get('status'),
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
            try:
                metadata = json.load(f)
            except (json.JSONDecodeError, ValueError):
                import click
                click.echo(
                    f"Warning: metadata for '{repo_name}' is corrupt and has been reset. "
                    "Run 'update' to rebuild it.",
                    err=True,
                )
                return {'filters': {}, 'issues': {}}
        
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
    
    def get_all_issue_numbers(self, repo_name: str) -> List[int]:
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

    def delete_issue(self, repo_name: str, issue_number: int) -> bool:
        """Delete a locally stored issue file and remove it from metadata.

        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue number to delete

        Returns:
            True if the file was deleted, False if it did not exist.
        """
        repo_dir = self.get_repo_dir(repo_name)
        file_path = repo_dir / f"issue-{issue_number}.md"

        if not file_path.exists():
            return False

        file_path.unlink()

        # Remove the entry from metadata
        metadata_file = repo_dir / '.metadata.json'
        if metadata_file.exists():
            metadata = self.load_metadata(repo_name)
            metadata['issues'].pop(str(issue_number), None)
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

        return True

    def read_issue(self, repo_name: str, issue_number: int) -> Optional[Dict[str, Any]]:
        """Parse a locally stored issue markdown file back into a data dict.

        Extracts YAML frontmatter fields and the issue body text.  Comments are
        not reconstructed (they are read-only from GitHub).

        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue number

        Returns:
            Dictionary with issue fields, or None if the file does not exist or
            cannot be parsed.
        """
        repo_dir = self.get_repo_dir(repo_name)
        file_path = repo_dir / f"issue-{issue_number}.md"

        if not file_path.exists():
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split on YAML frontmatter delimiters: '---\n<yaml>\n---\n<rest>'
        parts = content.split('---\n', 2)
        if len(parts) < 3:
            return None

        frontmatter_str = parts[1]
        rest = parts[2]

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError:
            return None

        if not isinstance(frontmatter, dict):
            return None

        # Extract body: skip the '# Title' heading line, collect lines until
        # '## Comments' (or end of file).
        lines = rest.split('\n')
        body_lines: List[str] = []
        past_title = False

        for line in lines:
            if not past_title:
                if line.startswith('# '):
                    past_title = True
                continue
            if line.rstrip() == '## Comments':
                break
            body_lines.append(line)

        body = '\n'.join(body_lines).strip()

        closed_at = frontmatter.get('closed_at')
        return {
            'number': frontmatter.get('number'),
            'title': frontmatter.get('title', ''),
            'body': body,
            'state': frontmatter.get('state', 'open'),
            'status': frontmatter.get('status'),
            'labels': frontmatter.get('labels') or [],
            'author': frontmatter.get('author', ''),
            'created_at': str(frontmatter.get('created_at', '')),
            'updated_at': str(frontmatter.get('updated_at', '')),
            'closed_at': str(closed_at) if closed_at else None,
            'url': frontmatter.get('url', ''),
            'assignees': frontmatter.get('assignees') or [],
            'milestone': frontmatter.get('milestone'),
        }

    def get_stored_file_hash(self, repo_name: str, issue_number: int) -> Optional[str]:
        """Return the file hash stored when the issue was last saved.

        Used by the push command to detect whether the user has edited the
        local markdown file since it was last written by this tool.

        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue number

        Returns:
            SHA-256 hex digest string, or None if not recorded.
        """
        metadata = self.load_metadata(repo_name)
        issue_meta = metadata.get('issues', {}).get(str(issue_number), {})
        return issue_meta.get('file_hash')

    def compute_current_file_hash(self, repo_name: str, issue_number: int) -> Optional[str]:
        """Compute the SHA-256 hash of the current on-disk issue file.

        Args:
            repo_name: Repository name in format 'owner/repo'
            issue_number: Issue number

        Returns:
            SHA-256 hex digest string, or None if the file does not exist.
        """
        repo_dir = self.get_repo_dir(repo_name)
        file_path = repo_dir / f"issue-{issue_number}.md"

        if not file_path.exists():
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return hashlib.sha256(content.encode('utf-8')).hexdigest()


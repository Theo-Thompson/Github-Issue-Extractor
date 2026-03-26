"""Projects v2 write operations via the GitHub GraphQL API.

PyGithub has no Projects v2 support, so all mutations are executed directly
against the GraphQL endpoint using the same requests-based pattern already
used in query_project_status.py.

Required token scope: 'project' (not just 'read:project').
"""

import os
from typing import Dict, List, Optional, Any, Tuple
import requests
from dotenv import load_dotenv


GRAPHQL_URL = "https://api.github.com/graphql"

# ---------------------------------------------------------------------------
# GraphQL queries and mutations
# ---------------------------------------------------------------------------

_LIST_PROJECTS_QUERY = """
query($org: String!, $cursor: String) {
  organization(login: $org) {
    projectsV2(first: 50, after: $cursor) {
      nodes {
        id
        number
        title
        url
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

_GET_PROJECT_FIELDS_QUERY = """
query($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      fields(first: 50) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
          }
        }
      }
    }
  }
}
"""

_GET_PROJECT_ITEMS_QUERY = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        nodes {
          id
          content {
            ... on Issue {
              number
              url
              repository {
                nameWithOwner
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""

_GET_PROJECT_ITEMS_WITH_STATUS_QUERY = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        nodes {
          content {
            ... on Issue {
              number
              repository {
                nameWithOwner
              }
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2SingleSelectField {
                    name
                  }
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""

_UPDATE_STATUS_MUTATION = """
mutation UpdateStatus(
  $projectId: ID!
  $itemId: ID!
  $fieldId: ID!
  $optionId: String!
) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId
    itemId: $itemId
    fieldId: $fieldId
    value: { singleSelectOptionId: $optionId }
  }) {
    projectV2Item {
      id
    }
  }
}
"""


class ProjectUpdater:
    """Manages Projects v2 status-field mutations via the GitHub GraphQL API."""

    def __init__(self):
        load_dotenv()
        token = os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError(
                "GITHUB_TOKEN not found in environment variables. "
                "Please create a .env file with your GitHub token."
            )
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_query(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a GraphQL query or mutation and return the parsed response.

        Raises:
            Exception: On HTTP errors or when the response contains top-level errors.
        """
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = self._session.post(GRAPHQL_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        errors = data.get("errors")
        if errors:
            messages = "; ".join(e.get("message", str(e)) for e in errors)
            # Surface a helpful hint when the token lacks the required scope.
            if "INSUFFICIENT_SCOPES" in messages or "not have the correct scopes" in messages.lower():
                raise Exception(
                    f"GitHub API permission error: {messages}\n"
                    "To update project status fields your GITHUB_TOKEN must have "
                    "the 'project' scope (Settings → Developer settings → Personal "
                    "access tokens → select 'project' under 'Write' column)."
                )
            raise Exception(f"GraphQL error: {messages}")

        return data

    # ------------------------------------------------------------------
    # Project discovery
    # ------------------------------------------------------------------

    def list_projects(self, org: str) -> List[Dict[str, Any]]:
        """Return all ProjectsV2 in the given GitHub organisation.

        Args:
            org: GitHub organisation login (e.g. 'DBDHub')

        Returns:
            List of project dicts with keys: id, number, title, url
        """
        projects: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            data = self._run_query(_LIST_PROJECTS_QUERY, {"org": org, "cursor": cursor})
            org_data = data.get("data", {}).get("organization")
            if not org_data:
                raise Exception(
                    f"Organisation '{org}' not found or the token lacks access. "
                    "Ensure the token has 'read:org' and 'project' scopes."
                )
            pv2 = org_data.get("projectsV2", {})
            projects.extend(pv2.get("nodes", []))
            page_info = pv2.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info["endCursor"]
            else:
                break

        return projects

    def find_project(self, org: str, project_name: str) -> Dict[str, Any]:
        """Find a single project by name within an organisation.

        Args:
            org: GitHub organisation login
            project_name: Exact project title (case-sensitive)

        Returns:
            Project dict with keys: id, number, title, url

        Raises:
            Exception: If no project with that name is found.
        """
        projects = self.list_projects(org)
        matches = [p for p in projects if p.get("title") == project_name]
        if not matches:
            available = ", ".join(f"'{p['title']}'" for p in projects) or "(none)"
            raise Exception(
                f"Project '{project_name}' not found in organisation '{org}'. "
                f"Available projects: {available}"
            )
        return matches[0]

    # ------------------------------------------------------------------
    # Field / option discovery
    # ------------------------------------------------------------------

    def get_status_field(self, project_id: str) -> Dict[str, Any]:
        """Return the Status single-select field definition for a project.

        Args:
            project_id: Node ID of the ProjectV2

        Returns:
            Dict with keys:
                field_id   – node ID of the Status field
                options    – {option_name: option_id} mapping

        Raises:
            Exception: If no 'Status' field is found on the project.
        """
        data = self._run_query(_GET_PROJECT_FIELDS_QUERY, {"projectId": project_id})
        fields = (
            data.get("data", {})
                .get("node", {})
                .get("fields", {})
                .get("nodes", [])
        )

        for field in fields:
            if field.get("name", "").lower() == "status" and "options" in field:
                return {
                    "field_id": field["id"],
                    "options": {opt["name"]: opt["id"] for opt in field["options"]},
                }

        raise Exception(
            f"No 'Status' single-select field found on project (id={project_id}). "
            "Check that the project has a field named exactly 'Status'."
        )

    def list_available_statuses(self, org: str, project_name: str) -> List[str]:
        """Return the available Status option names for a project.

        Args:
            org: GitHub organisation login
            project_name: Exact project title

        Returns:
            List of status option name strings (e.g. ['Todo', 'In Progress', 'Done'])
        """
        project = self.find_project(org, project_name)
        status_field = self.get_status_field(project["id"])
        return sorted(status_field["options"].keys())

    def build_repo_status_map(self, org: str) -> Dict[Tuple[str, int], str]:
        """Build a mapping of (repo_name_lower, issue_number) -> status string.

        Scans every project in the organisation and collects the 'Status'
        single-select field value for each issue item.  The result can be used
        to overlay status onto issue dicts before they are saved to disk.

        Args:
            org: GitHub organisation login (e.g. 'DBDHub')

        Returns:
            Dict keyed by (repo_name.lower(), issue_number) with status string
            values.  Returns an empty dict if projects cannot be accessed.
        """
        status_map: Dict[Tuple[str, int], str] = {}

        try:
            projects = self.list_projects(org)
        except Exception:
            return status_map

        for project in projects:
            project_id = project.get("id")
            if not project_id:
                continue

            cursor: Optional[str] = None
            while True:
                try:
                    data = self._run_query(
                        _GET_PROJECT_ITEMS_WITH_STATUS_QUERY,
                        {"projectId": project_id, "cursor": cursor},
                    )
                except Exception:
                    break

                items_data = (
                    data.get("data", {})
                        .get("node", {})
                        .get("items", {})
                )

                for item in items_data.get("nodes", []):
                    content = item.get("content")
                    if not content:
                        continue
                    repo_name = content.get("repository", {}).get("nameWithOwner", "")
                    issue_number = content.get("number")
                    if not repo_name or issue_number is None:
                        continue

                    for fv in item.get("fieldValues", {}).get("nodes", []):
                        field = fv.get("field", {})
                        if (
                            isinstance(field, dict)
                            and field.get("name", "").lower() == "status"
                        ):
                            status_map[(repo_name.lower(), issue_number)] = fv.get("name", "")
                            break

                page_info = items_data.get("pageInfo", {})
                if page_info.get("hasNextPage"):
                    cursor = page_info["endCursor"]
                else:
                    break

        return status_map

    # ------------------------------------------------------------------
    # Project item lookup
    # ------------------------------------------------------------------

    def find_project_item(
        self,
        project_id: str,
        repo_name: str,
        issue_number: int,
    ) -> Optional[str]:
        """Find the project item ID for a given issue.

        Paginates through all project items to find the one whose content
        matches the supplied repository + issue number.

        Args:
            project_id: Node ID of the ProjectV2
            repo_name: Full repository name in 'owner/repo' format
            issue_number: GitHub issue number

        Returns:
            Project item node ID string, or None if not found.
        """
        cursor: Optional[str] = None

        while True:
            data = self._run_query(
                _GET_PROJECT_ITEMS_QUERY,
                {"projectId": project_id, "cursor": cursor},
            )
            items_data = (
                data.get("data", {})
                    .get("node", {})
                    .get("items", {})
            )
            for item in items_data.get("nodes", []):
                content = item.get("content")
                if not content:
                    continue
                item_repo = content.get("repository", {}).get("nameWithOwner", "")
                item_number = content.get("number")
                if item_repo.lower() == repo_name.lower() and item_number == issue_number:
                    return item["id"]

            page_info = items_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info["endCursor"]
            else:
                break

        return None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def update_status(
        self,
        org: str,
        project_name: str,
        repo_name: str,
        issue_number: int,
        new_status: str,
    ) -> None:
        """Update the Status field of a project item to a new value.

        Args:
            org: GitHub organisation login
            project_name: Exact project title
            repo_name: Full repository name in 'owner/repo' format
            issue_number: GitHub issue number
            new_status: Desired status option name (must match exactly, e.g. 'Done')

        Raises:
            Exception: If the project, status option, or project item is not found,
                       or if the mutation fails.
        """
        # 1. Resolve project
        project = self.find_project(org, project_name)
        project_id = project["id"]

        # 2. Resolve Status field + option
        status_field = self.get_status_field(project_id)
        options = status_field["options"]

        # Case-insensitive lookup so 'done' matches 'Done', etc.
        options_lower = {k.lower(): (k, v) for k, v in options.items()}
        if new_status.lower() not in options_lower:
            available = ", ".join(f"'{s}'" for s in sorted(options))
            raise Exception(
                f"Status '{new_status}' is not a valid option for project "
                f"'{project_name}'. Available options: {available}"
            )

        _canonical, option_id = options_lower[new_status.lower()]
        field_id = status_field["field_id"]

        # 3. Find the project item
        item_id = self.find_project_item(project_id, repo_name, issue_number)
        if item_id is None:
            raise Exception(
                f"Issue #{issue_number} from {repo_name} was not found in "
                f"project '{project_name}'. Ensure the issue has been added to "
                "the project on GitHub."
            )

        # 4. Execute mutation
        self._run_query(
            _UPDATE_STATUS_MUTATION,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "optionId": option_id,
            },
        )

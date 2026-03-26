"""
Two-part query against the MyConnect GitHub Project (DBDHub org):

  Query A — "Securitas Review" tickets last updated BEFORE 2026-01-30
  Query B — "Done" tickets last updated AFTER 2026-01-30

Both filtered to milestones: Geolocation, Security.

Usage:
    python query_project_status.py

Requires GITHUB_TOKEN in .env with read:project scope.
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("ERROR: GITHUB_TOKEN not found in .env file.")
    sys.exit(1)

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json",
}

# --- Configuration ---
TARGET_MILESTONES = {"Geolocation", "Security"}
TARGET_PROJECTS = {"MyConnect"}
ORG_LOGIN = "DBDHub"

CUTOFF = datetime(2026, 1, 30, tzinfo=timezone.utc)

# Query A: "Securitas Review" items last updated strictly BEFORE 2026-01-30
QUERY_A_STATUS = "Securitas Review"

# Query B: "Done" items last updated strictly AFTER 2026-01-30
QUERY_B_STATUS = "Done"


def run_query(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        for error in data["errors"]:
            print(f"  GraphQL error: {error.get('message', error)}")
    return data


# Step 1: List all ProjectsV2 in the org
LIST_PROJECTS_QUERY = """
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

# Step 2: Get all items from a project, paginated
PROJECT_ITEMS_QUERY = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      title
      items(first: 100, after: $cursor) {
        nodes {
          id
          updatedAt
          content {
            ... on Issue {
              number
              title
              state
              url
              updatedAt
              milestone {
                title
              }
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


def fetch_all_projects(org: str) -> list:
    projects = []
    cursor = None
    while True:
        data = run_query(LIST_PROJECTS_QUERY, {"org": org, "cursor": cursor})
        org_data = data.get("data", {}).get("organization")
        if not org_data:
            print(f"  Could not access organization '{org}'. Check token permissions (needs read:project).")
            break
        projects_data = org_data.get("projectsV2", {})
        projects.extend(projects_data.get("nodes", []))
        page_info = projects_data.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break
    return projects


def fetch_all_project_items(project_id: str) -> list:
    items = []
    cursor = None
    while True:
        data = run_query(PROJECT_ITEMS_QUERY, {"projectId": project_id, "cursor": cursor})
        node_data = data.get("data", {}).get("node", {})
        items_data = node_data.get("items", {})
        items.extend(items_data.get("nodes", []))
        page_info = items_data.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break
    return items


def get_status_from_field_values(field_values: list) -> str | None:
    """Extract the 'Status' field value from project item field values."""
    for node in field_values:
        field = node.get("field", {})
        if isinstance(field, dict) and field.get("name", "").lower() == "status":
            return node.get("name")
    return None


def classify_item(item, proj_title, proj_url):
    """Return a dict for a matching project item, or None if it should be skipped."""
    content = item.get("content")
    if not content or "number" not in content:
        return None

    milestone = content.get("milestone")
    milestone_title = milestone.get("title") if milestone else None
    if milestone_title not in TARGET_MILESTONES:
        return None

    field_values = item.get("fieldValues", {}).get("nodes", [])
    status = get_status_from_field_values(field_values)
    if status not in {QUERY_A_STATUS, QUERY_B_STATUS}:
        return None

    item_updated_at_str = item.get("updatedAt")
    if not item_updated_at_str:
        return None
    item_updated_at = datetime.fromisoformat(item_updated_at_str.replace("Z", "+00:00"))

    # Query A: Securitas Review, updated BEFORE 2026-01-30
    if status == QUERY_A_STATUS and item_updated_at >= CUTOFF:
        return None

    # Query B: Done, updated AFTER 2026-01-30
    if status == QUERY_B_STATUS and item_updated_at <= CUTOFF:
        return None

    return {
        "project": proj_title,
        "project_url": proj_url,
        "number": content.get("number"),
        "title": content.get("title"),
        "state": content.get("state"),
        "milestone": milestone_title,
        "status": status,
        "repo": content.get("repository", {}).get("nameWithOwner", "unknown"),
        "url": content.get("url"),
        "item_updated_at": item_updated_at.strftime("%Y-%m-%d %H:%M UTC"),
    }


def print_section(title: str, items: list):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    if not items:
        print("  (none)")
        return
    print(f"  {len(items)} issue(s)\n")
    for item in sorted(items, key=lambda x: (x["repo"], x["number"])):
        print(f"  #{item['number']:>5}  [{item['state']:6}]  {item['repo']}")
        print(f"         Milestone    : {item['milestone']}")
        print(f"         Title        : {item['title']}")
        print(f"         Item updated : {item['item_updated_at']}")
        print(f"         URL          : {item['url']}")
        print()


def main():
    print("=" * 70)
    print("GitHub Project Status Query — MyConnect / DBDHub")
    print("=" * 70)
    print(f"  Query A  '{QUERY_A_STATUS}'  →  last updated BEFORE {CUTOFF.date()}")
    print(f"  Query B  '{QUERY_B_STATUS}'  →  last updated AFTER  {CUTOFF.date()}")
    print(f"  Milestones : {', '.join(sorted(TARGET_MILESTONES))}")
    print("=" * 70)

    print(f"\nFetching projects from {ORG_LOGIN}...", end="", flush=True)
    projects = fetch_all_projects(ORG_LOGIN)
    if not projects:
        print("\nNo projects found (or insufficient permissions).")
        print("\nFalling back to REST API milestone search...")
        rest_fallback()
        return
    print(f" Found {len(projects)} project(s)")

    query_a: list = []
    query_b: list = []

    for project in projects:
        proj_title = project.get("title", "Unknown")
        proj_id = project.get("id")
        proj_url = project.get("url", "")

        if proj_title not in TARGET_PROJECTS:
            print(f"\nSkipping project: '{proj_title}'")
            continue

        print(f"\nScanning project: '{proj_title}' ...", end="", flush=True)
        items = fetch_all_project_items(proj_id)
        print(f" {len(items)} item(s)")

        for item in items:
            result = classify_item(item, proj_title, proj_url)
            if result is None:
                continue
            if result["status"] == QUERY_A_STATUS:
                query_a.append(result)
            else:
                query_b.append(result)

    print_section(
        f"QUERY A — '{QUERY_A_STATUS}' | updated BEFORE {CUTOFF.date()} | "
        f"{len(query_a)} issue(s)",
        query_a,
    )
    print_section(
        f"QUERY B — '{QUERY_B_STATUS}' | updated AFTER {CUTOFF.date()} | "
        f"{len(query_b)} issue(s)",
        query_b,
    )

    print("=" * 70)
    print(f"Grand total: {len(query_a) + len(query_b)} issue(s)")
    print("=" * 70)
    print(
        "\nNote: 'Item updated' reflects when the project item was last modified"
        "\n(status changes, field edits, etc.). GitHub does not expose per-field"
        "\nchange history in the standard GraphQL API."
    )


def rest_fallback():
    """
    Fallback using REST API when GraphQL project access is unavailable.
    Queries issues by milestone and since date, notes that status filtering
    is not possible via REST (no Projects v2 status info available).
    """
    from src.github_client import GitHubClient

    try:
        client = GitHubClient()
    except Exception as e:
        print(f"Could not initialize GitHub client: {e}")
        return

    repos = ["DBDHub/SecuritasOfficer-Android", "DBDHub/SecuritasOfficer-iOS",
             "DBDHub/sna_portal_api", "DBDHub/sna_portal_react", "DBDHub/sna_wfm_api"]

    all_results = []

    for milestone in sorted(TARGET_MILESTONES):
        for repo in repos:
            filters = {
                "milestone": milestone,
                "state": "all",
                "since": CUTOFF.strftime("%Y-%m-%d"),
            }
            try:
                issues = client.fetch_issues(repo, filters)
                for issue in issues:
                    all_results.append({
                        "repo": repo,
                        "number": issue["number"],
                        "title": issue["title"],
                        "state": issue["state"],
                        "milestone": issue.get("milestone"),
                        "labels": issue.get("labels", []),
                        "updated_at": issue["updated_at"],
                        "url": issue["url"],
                    })
            except Exception as e:
                if "not found" not in str(e).lower() and "milestone" not in str(e).lower():
                    print(f"  Error fetching {repo} (milestone={milestone}): {e}")

    if not all_results:
        print("\nNo issues found via REST API either.")
        return

    print(f"\nFound {len(all_results)} issue(s) with milestones {sorted(TARGET_MILESTONES)}")
    print("updated after Jan 28, 2026 (via REST API):")
    print()
    print("NOTE: Projects v2 status ('Securitas Review'/'Done') is NOT available")
    print("via REST. Results below show all matching issues regardless of status.")
    print("Use the GraphQL path (requires read:project token scope) for status filtering.")
    print("-" * 70)

    for item in sorted(all_results, key=lambda x: (x["repo"], x["number"])):
        labels_str = ", ".join(item["labels"]) if item["labels"] else "none"
        print(f"  #{item['number']:>5}  [{item['state']:8}]  {item['repo']}")
        print(f"         Milestone : {item['milestone']}")
        print(f"         Title     : {item['title']}")
        print(f"         Labels    : {labels_str}")
        print(f"         Updated   : {item['updated_at'][:10]}")
        print(f"         URL       : {item['url']}")
        print()


if __name__ == "__main__":
    main()

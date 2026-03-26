"""
Bulk status update script.

List 2  (Done → Securitas Review):
  Issues that have status 'Done' and were last updated AFTER Jan 28, 2026.
  - Set project status to 'Securitas Review'
  - Add comment explaining the change

List 1  (Securitas Review → Done):
  Issues that have status 'Securitas Review' and were last updated ON OR BEFORE Jan 28, 2026.
  - Set project status to 'Done'
  - Add comment explaining the change

Repos in scope: SecuritasOfficer-Android, SecuritasOfficer-iOS, sna_wfm_api (all under DBDHub).
"""

import sys
import time

from src.project_updater import ProjectUpdater
from src.github_client import GitHubClient

ORG = "DBDHub"
PROJECT_NAME = "MyConnect"

COMMENT_DONE_TO_SR = (
    "Moving back to Securitas Review to be reviewed as part of our April release scope. "
    "This ticket was moved to Done by an automation or mistake, and was not released to "
    "production in Jan with our Geo launch."
)

COMMENT_SR_TO_DONE = (
    "This was released to production in Jan as part of our Geo launch. "
    "The ticket status was not previously updated to done, so updating it now."
)

# ── List 2: Done → Securitas Review ──────────────────────────────────────────
LIST_2 = [
    ("DBDHub/SecuritasOfficer-iOS",     955),
    ("DBDHub/SecuritasOfficer-iOS",     956),
    ("DBDHub/sna_wfm_api",              234),
    ("DBDHub/sna_wfm_api",              252),
    ("DBDHub/SecuritasOfficer-iOS",     961),
    ("DBDHub/sna_wfm_api",              225),
    ("DBDHub/sna_wfm_api",              235),
    ("DBDHub/SecuritasOfficer-iOS",     962),
    ("DBDHub/SecuritasOfficer-iOS",     971),
    ("DBDHub/SecuritasOfficer-iOS",     963),
    ("DBDHub/SecuritasOfficer-iOS",     958),
    ("DBDHub/SecuritasOfficer-Android", 1019),
    ("DBDHub/SecuritasOfficer-Android", 1020),
    ("DBDHub/SecuritasOfficer-Android", 1036),
    ("DBDHub/SecuritasOfficer-Android", 976),
    ("DBDHub/SecuritasOfficer-iOS",     736),
    ("DBDHub/sna_wfm_api",              250),
    ("DBDHub/sna_wfm_api",              254),
    ("DBDHub/SecuritasOfficer-iOS",     1001),
    ("DBDHub/SecuritasOfficer-iOS",     717),
    ("DBDHub/SecuritasOfficer-Android", 1032),
    ("DBDHub/SecuritasOfficer-iOS",     981),
    ("DBDHub/SecuritasOfficer-Android", 1030),
    ("DBDHub/SecuritasOfficer-iOS",     1018),
    ("DBDHub/sna_wfm_api",              120),
    ("DBDHub/SecuritasOfficer-iOS",     1010),
    ("DBDHub/SecuritasOfficer-Android", 1011),
    ("DBDHub/SecuritasOfficer-iOS",     811),
    ("DBDHub/SecuritasOfficer-iOS",     921),
    ("DBDHub/SecuritasOfficer-iOS",     1154),
]

# ── List 1: Securitas Review → Done ──────────────────────────────────────────
LIST_1 = [
    ("DBDHub/sna_wfm_api",              103),
    ("DBDHub/SecuritasOfficer-iOS",     771),
    ("DBDHub/SecuritasOfficer-Android", 842),
    ("DBDHub/SecuritasOfficer-Android", 860),
    ("DBDHub/SecuritasOfficer-iOS",     686),
    ("DBDHub/SecuritasOfficer-iOS",     857),
    ("DBDHub/sna_wfm_api",              206),
    ("DBDHub/SecuritasOfficer-Android", 751),
    ("DBDHub/SecuritasOfficer-Android", 884),
    ("DBDHub/SecuritasOfficer-iOS",     856),
    ("DBDHub/SecuritasOfficer-iOS",     865),
    ("DBDHub/SecuritasOfficer-Android", 864),
    ("DBDHub/SecuritasOfficer-Android", 901),
    ("DBDHub/SecuritasOfficer-Android", 902),
    ("DBDHub/SecuritasOfficer-Android", 919),
    ("DBDHub/SecuritasOfficer-iOS",     861),
    ("DBDHub/SecuritasOfficer-iOS",     805),
    ("DBDHub/SecuritasOfficer-iOS",     854),
    ("DBDHub/SecuritasOfficer-iOS",     887),
    ("DBDHub/SecuritasOfficer-Android", 788),
    ("DBDHub/SecuritasOfficer-Android", 928),
    ("DBDHub/SecuritasOfficer-Android", 857),
    ("DBDHub/SecuritasOfficer-Android", 934),
    ("DBDHub/SecuritasOfficer-Android", 939),
    ("DBDHub/SecuritasOfficer-iOS",     878),
    ("DBDHub/SecuritasOfficer-Android", 941),
    ("DBDHub/SecuritasOfficer-Android", 911),
    ("DBDHub/SecuritasOfficer-Android", 880),
    ("DBDHub/SecuritasOfficer-Android", 986),
    ("DBDHub/SecuritasOfficer-iOS",     820),
    ("DBDHub/SecuritasOfficer-iOS",     932),
    ("DBDHub/SecuritasOfficer-iOS",     933),
    ("DBDHub/SecuritasOfficer-Android", 1003),
    ("DBDHub/SecuritasOfficer-Android", 1014),
    ("DBDHub/SecuritasOfficer-Android", 995),
    ("DBDHub/SecuritasOfficer-Android", 996),
    ("DBDHub/SecuritasOfficer-Android", 994),
]


def process_batch(label, items, new_status, comment_text, updater, gh_client):
    print(f"\n{'='*70}")
    print(f"{label}  ({len(items)} issues)  →  status: '{new_status}'")
    print('='*70)

    ok = []
    failed = []

    for repo, number in items:
        tag = f"{repo}#{number}"
        try:
            # 1. Update project status
            updater.update_status(ORG, PROJECT_NAME, repo, number, new_status)
            # 2. Add comment
            gh_client.create_comment(repo, number, comment_text)
            print(f"  ✓  {tag}")
            ok.append(tag)
        except Exception as exc:
            print(f"  ✗  {tag}  —  {exc}")
            failed.append((tag, str(exc)))

        # Gentle rate-limit buffer between issues
        time.sleep(0.5)

    print(f"\n  Done: {len(ok)} succeeded, {len(failed)} failed")
    if failed:
        print("  Failures:")
        for tag, msg in failed:
            print(f"    {tag}: {msg}")

    return ok, failed


def main():
    print("Initialising GitHub clients…")
    try:
        updater = ProjectUpdater()
        gh_client = GitHubClient()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    all_ok = []
    all_failed = []

    # List 2: Done → Securitas Review
    ok, failed = process_batch(
        "List 2 — Done → Securitas Review",
        LIST_2,
        "Securitas Review",
        COMMENT_DONE_TO_SR,
        updater,
        gh_client,
    )
    all_ok.extend(ok)
    all_failed.extend(failed)

    # List 1: Securitas Review → Done
    ok, failed = process_batch(
        "List 1 — Securitas Review → Done",
        LIST_1,
        "Done",
        COMMENT_SR_TO_DONE,
        updater,
        gh_client,
    )
    all_ok.extend(ok)
    all_failed.extend(failed)

    print(f"\n{'='*70}")
    print(f"TOTAL: {len(all_ok)} succeeded, {len(all_failed)} failed")
    print('='*70)


if __name__ == "__main__":
    main()

"""Appels directs à l'API REST Jira (pièces jointes, changements de statut)."""
import os

import requests


def _base() -> str:
    return os.environ["JIRA_URL"].rstrip("/") + "/rest/api/3"


def _auth() -> tuple[str, str]:
    return os.environ["JIRA_USERNAME"], os.environ["JIRA_TOKEN"]


def attach_to_issue(issue_key: str, files: list[dict]) -> None:
    resp = requests.post(
        f"{_base()}/issue/{issue_key}/attachments",
        auth=_auth(),
        headers={"X-Atlassian-Token": "no-check"},
        files=[("file", (f["name"], f["data"], f["type"])) for f in files],
        timeout=120,
    )
    resp.raise_for_status()
    print(f"{len(files)} pièce(s) jointe(s) ajoutée(s) à {issue_key}")


def transition_issue(issue_key: str, status: str) -> bool:
    """Passe le ticket dans le statut demandé. False si déjà dans ce statut ou transition impossible."""
    resp = requests.get(f"{_base()}/issue/{issue_key}/transitions", auth=_auth(), timeout=30)
    resp.raise_for_status()
    for t in resp.json()["transitions"]:
        if t["to"]["name"].lower() == status.lower():
            requests.post(
                f"{_base()}/issue/{issue_key}/transitions",
                auth=_auth(), json={"transition": {"id": t["id"]}}, timeout=30,
            ).raise_for_status()
            print(f"{issue_key} -> {status}")
            return True
    print(f"{issue_key} : pas de transition vers « {status} » (déjà dans ce statut ?)")
    return False

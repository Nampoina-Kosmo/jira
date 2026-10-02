"""Appels directs à l'API REST Jira (pièces jointes, statuts, changements de statut)."""
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


def _issue_info(issue: dict) -> dict:
    return {"status": issue["fields"]["status"]["name"], "summary": issue["fields"].get("summary", "")}


def get_issues(issue_keys: list[str]) -> dict[str, dict]:
    """{clé: {"status": ..., "summary": ...}} (les tickets supprimés sont absents)."""
    issues: dict[str, dict] = {}
    for i in range(0, len(issue_keys), 50):
        batch = issue_keys[i:i + 50]
        jql = "key in (" + ",".join(batch) + ")"
        token = None
        while True:
            params = {"jql": jql, "fields": "status,summary", "maxResults": 100}
            if token:
                params["nextPageToken"] = token
            resp = requests.get(f"{_base()}/search/jql", params=params, auth=_auth(), timeout=30)
            if resp.status_code == 400:  # un ticket de la liste a été supprimé : on les interroge un par un
                for key in batch:
                    one = requests.get(f"{_base()}/issue/{key}", params={"fields": "status,summary"},
                                       auth=_auth(), timeout=30)
                    if one.ok:
                        issues[key] = _issue_info(one.json())
                break
            resp.raise_for_status()
            body = resp.json()
            for issue in body["issues"]:
                issues[issue["key"]] = _issue_info(issue)
            token = body.get("nextPageToken")
            if body.get("isLast", True) or not token:
                break
    return issues


def get_statuses(issue_keys: list[str]) -> dict[str, str]:
    """{clé: nom du statut}"""
    return {k: v["status"] for k, v in get_issues(issue_keys).items()}


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

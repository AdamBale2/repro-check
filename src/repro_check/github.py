"""Post or update the repro-check comment on an issue (standard library only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .report import MARKER

MAX_PAGES = 10


class GitHub:
    def __init__(self, token: str, api_url: str | None = None):
        self.token = token
        self.api_url = (
            api_url or os.environ.get("GITHUB_API_URL") or "https://api.github.com"
        ).rstrip("/")

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "repro-check",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        return json.loads(body) if body else None

    def issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            batch = self.request(
                "GET", f"/repos/{repo}/issues/{number}/comments?per_page=100&page={page}"
            )
            comments.extend(batch)
            if len(batch) < 100:
                break
        return comments

    def upsert_comment(self, repo: str, number: int, body: str) -> str:
        """Update our previous comment if there is one, otherwise create a new one."""
        existing = find_previous_comment(self.issue_comments(repo, number))
        if existing is not None:
            try:
                updated = self.request(
                    "PATCH", f"/repos/{repo}/issues/comments/{existing['id']}", {"body": body}
                )
                return updated["html_url"]
            except urllib.error.HTTPError as exc:
                if exc.code not in (403, 404):
                    raise
        created = self.request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})
        return created["html_url"]


def find_previous_comment(comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Our last comment: it carries the marker and was written by a bot account.

    Checking the author keeps us from trying to edit a human comment that quotes the marker.
    """
    ours = [
        c
        for c in comments
        if MARKER in (c.get("body") or "") and (c.get("user") or {}).get("type") == "Bot"
    ]
    return ours[-1] if ours else None

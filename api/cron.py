from __future__ import annotations

import base64
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape_macromicro import run_scrape  # noqa: E402

GH_API = "https://api.github.com"


def _commit_file(repo: str, branch: str, token: str, path: str, content_bytes: bytes, message: str) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    get_resp = requests.get(
        f"{GH_API}/repos/{repo}/contents/{path}",
        headers=headers,
        params={"ref": branch},
        timeout=30,
    )
    sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    put_resp = requests.put(
        f"{GH_API}/repos/{repo}/contents/{path}",
        headers=headers,
        json=body,
        timeout=30,
    )
    put_resp.raise_for_status()


class handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self) -> None:
        cron_secret = os.environ.get("CRON_SECRET")
        auth = self.headers.get("authorization", "")
        if cron_secret and auth != f"Bearer {cron_secret}":
            self._reply(401, "unauthorized")
            return

        repo = (os.environ.get("GH_REPO") or "").strip()
        token = (os.environ.get("GH_TOKEN") or "").strip()
        branch = (os.environ.get("GH_BRANCH") or "main").strip()
        if not repo or not token:
            self._reply(500, "missing GH_REPO or GH_TOKEN env")
            return

        try:
            dashboard_data = run_scrape()
            dashboard_data.pop("_raw_charts", None)
            payload = json.dumps(dashboard_data, ensure_ascii=False, indent=2).encode("utf-8")
            _commit_file(
                repo=repo,
                branch=branch,
                token=token,
                path="dashboard_data.json",
                content_bytes=payload,
                message=f"chore: refresh dashboard_data.json ({dashboard_data.get('fetched_at')})",
            )
            self._reply(
                200,
                f"ok: {dashboard_data.get('chart_count')} charts, {dashboard_data.get('fetched_at')}\n",
            )
        except Exception as e:
            traceback.print_exc()
            self._reply(500, f"error: {e}\n")

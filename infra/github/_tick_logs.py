"""Лог шага из упавшего тика (обрабатываем 302-редирект логов)."""
import json
import os
import urllib.request

GH = os.environ["GH"]


def gh(url, method="GET"):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + GH},
                                 method=method)
    opener = urllib.request.build_opener(NoRedirect())
    return opener.open(req, timeout=60)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


r = json.loads(urllib.request.urlopen(urllib.request.Request(
    "https://api.github.com/repos/fshmidtai/atria/actions/runs?per_page=1",
    headers={"Authorization": "Bearer " + GH}), timeout=60).read()
)["workflow_runs"][0]
j = json.loads(urllib.request.urlopen(urllib.request.Request(
    r["url"] + "/jobs", headers={"Authorization": "Bearer " + GH}), timeout=60).read())
job = j["jobs"][0]
import urllib.error

resp = None
try:
    resp = gh(f"https://api.github.com/repos/fshmidtai/atria/actions/jobs/"
              f"{job['id']}/logs")
except urllib.error.HTTPError as e:
    if e.code == 302:
        loc = e.headers.get("Location")
        txt = urllib.request.urlopen(loc, timeout=120).read().decode(
            "utf-8", "replace")
        print(txt[-4000:])
        raise SystemExit(0)
    raise

"""Проверка последнего тика: статус + шаги джобы."""
import json
import os
import urllib.request

GH = os.environ["GH"]
req = urllib.request.Request(
    "https://api.github.com/repos/fshmidtai/atria/actions/runs?per_page=1",
    headers={"Authorization": "Bearer " + GH})
r = json.loads(urllib.request.urlopen(req, timeout=60).read())["workflow_runs"][0]
print(r["status"], "/", r["conclusion"], "| sha", r["head_sha"][:7])
if r["conclusion"]:
    j = json.loads(urllib.request.urlopen(urllib.request.Request(
        r["url"] + "/jobs", headers={"Authorization": "Bearer " + GH}), timeout=60).read())
    for s in j["jobs"][0]["steps"]:
        print(" -", s["conclusion"] or s["status"], "|", s["name"])

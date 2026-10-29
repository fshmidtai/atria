"""Простая HTTP-проба URL с несколькими попытками (прокси нестабилен)."""
import os
import sys
import time
import urllib.request

os.environ.setdefault("https_proxy", "http://miningchia:mining012345@mproxy.site:12655")


def probe(host, tries=3):
    for i in range(tries):
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(host, headers={"User-Agent": "Mozilla/5.0 Chrome/131"}),
                timeout=40)
            return f"{r.status} len={len(r.read())}"
        except urllib.error.HTTPError as e:
            return f"{e.code} body={e.read()[:100]}"
        except Exception as e:
            time.sleep(2)
    return "ERR " + str(e)[:80]


if __name__ == "__main__":
    print(probe(sys.argv[1]))

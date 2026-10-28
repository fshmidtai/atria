"""Самопроверка роя — гоняется без сети за ~1 секунду.

CI (см. .github/workflows/hive-tick.yml) запускает selftest перед каждым циклом:
если сломалось ядро — пульс даже не начинается, а ответственный человек получает
красный крестик вместо молчаливой смерти колонии.

Локально: python archaea/selftest.py
"""
from __future__ import annotations

import sys
import tempfile
import time
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colonies.phosphor import pipeline
from core.orchestrator import Orchestrator
from core.registry import Registry
from core.treasury import Treasury

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond, note: str = ""):
    RESULTS.append((name, bool(cond), str(note)))


# ---------------------------------------------------------------- pipeline
def test_clean_dedup():
    now = time.time()
    items = [
        {"uid": "a", "title": "Some Big Launch", "url": "https://x.com/1", "ts": now,
         "points": 10, "comments": 0, "source": "hn"},
        {"uid": "b", "title": "some! big  launch", "url": "https://x.com/2", "ts": now,
         "points": 500, "comments": 20, "source": "hn"},
    ]
    out = pipeline.clean(items)
    check("clean: дедуп по нормализованному заголовку (2→1)", len(out) == 1, len(out))
    check("clean: выживает сильнейший", out and out[0]["uid"] == "b",
          out[0]["uid"] if out else "none")


def test_score_and_tags():
    now = time.time()
    it = {"uid": "c", "title": "New open-source LLM beats GPT on RAG benchmark",
          "url": "https://x.com", "ts": now, "points": 100, "comments": 20, "source": "hn"}
    out = pipeline.clean([it])
    check("tag: ai-тег ставится", "ai" in out[0]["topics"], out[0]["topics"])
    check("score: buzz ≥ points + 3×comments", out and out[0]["buzz"] >= 160, out[0]["buzz"])
    check("score: свежесть даёт надбавку",
          out and out[0]["buzz"] >= 160 + 30, out[0]["buzz"])


def test_snapshot():
    now = time.time()
    items = [{"uid": "d", "title": "X", "url": "https://example.com/a", "ts": now,
              "points": 1, "comments": 1, "source": "hn", "recipe": "show_hn",
              "topics": ["ai"], "buzz": 5, "date": "2026-01-01"}]
    snap = pipeline.build_snapshot(items, [{"kind": "hn_search"}])
    check("snapshot: totals считаются", snap["totals"]["items"] == 1)
    check("snapshot: by_recipe считается", snap["totals"]["by_recipe"].get("show_hn") == 1,
          snap["totals"]["by_recipe"])


# ---------------------------------------------------------------- rss + guard
def test_rss_parse():
    from colonies.phosphor import sources as S

    rss = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>X</title>'
        "<item><title>Alpha launch</title><link>https://a.example/1</link>"
        "<pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate>"
        "<description>Big news about AI agents</description>"
        "<dc:creator xmlns:dc=\"http://purl.org/dc/elements/1.1/\">jane</dc:creator>"
        "</item></channel></rss>"
    )
    items = S._parse_feed(rss)
    check("rss: парсит RSS 2.0", len(items) == 1 and items[0]["title"] == "Alpha launch",
          [i.get("title") for i in items])
    check("rss: uid стабильного формата", items and items[0]["uid"].startswith("rss:"),
          items[0]["uid"] if items else "none")
    check("rss: author+description приехали",
          items and items[0]["author"] == "jane" and "AI agents" in items[0]["summary"])

    atom = (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<title>Beta paper</title><link href='https://b.example/2' rel='alternate'/>"
        "<updated>2026-10-21T10:00:00Z</updated><summary>Quantum thing</summary>"
        "</entry></feed>"
    )
    items = S._parse_feed(atom)
    check("rss: парсит Atom", len(items) == 1 and items[0]["title"] == "Beta paper",
          [i.get("title") for i in items])
    check("rss: битый XML даёт []", S._parse_feed("<not<xml") == [])


def test_robots_guard():
    from colonies.phosphor import sources as S

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /private"])
    S._ROBOTS_CACHE["https://example.com"] = rp
    check("robots: запрещает /private", S._robots_allowed("https://example.com/private/feed") is False)
    check("robots: разрешает публичное", S._robots_allowed("https://example.com/feed") is True)
    S._ROBOTS_CACHE["https://gone.example"] = None
    check("robots: нет файла → разрешаем", S._robots_allowed("https://gone.example/feed") is True)


def test_pii_scrub():
    from colonies.phosphor.pipeline import scrub_pii

    t = "Write to ceo@evilcorp.com or call +1 (415) 555 0132, card 4111111111111111 today"
    s = scrub_pii(t)
    check("pii: email вычищен", "@" not in s and "[email]" in s, s)
    check("pii: телефон вычищен", "555 0132" not in s and "[phone]" in s, s)
    check("pii: карта вычищена", "4111" not in s, s)
    check("pii: чистый текст не калечится", scrub_pii("AI agents everywhere") == "AI agents everywhere")
    check("pii: None не роняет", scrub_pii(None) == "")


# ---------------------------------------------------------------- core
def test_treasury():
    tmp = Path(tempfile.mkdtemp())
    t = Treasury(tmp / "t.db")
    t.open_cell("probe", 1000)
    check("treasury: лимит позволяет", t.spend("probe", 500, "half") is True)
    over = t.spend("probe", 600, "rest")
    check("treasury: перерасход ловится", over is False)
    check("treasury: жертва апоптоза обнаружена",
          any(v["agent_id"] == "probe" for v in t.victims()))
    t.revenue("probe", 250, "first dollar")
    check("treasury: выручка считается", t.summary()["revenue_u"] == 250)
    t.close()


def test_orchestrator():
    tmp = Path(tempfile.mkdtemp())
    o = Orchestrator(tmp / "o.db")

    seen = []

    def handler_a(payload):
        seen.append(payload["v"])
        return {"ok": payload["v"]}

    def handler_boom(_payload):
        raise RuntimeError("boom")

    o.enqueue("c", "t1", "ha", {"v": 1})
    o.enqueue("c", "t2", "ha", {"v": 2})
    o.enqueue("c", "bad", "hb", {})
    stats = o.tick({"ha": handler_a, "hb": handler_boom})

    check("orch: выполнил обе задачи", stats["ran"] == 2 and seen == [1, 2], seen)
    check("orch: сбой изолирован", stats["failed"] == 1, stats)
    st = o.stats()
    check("orch: статусы учтены", st.get("done") == 2 and st.get("failed") == 1, st)
    o.close()


def test_registry():
    tmp = Path(tempfile.mkdtemp())
    t = Treasury(tmp / "r.db")
    r = Registry(tmp / "r.db", t)
    a = r.spawn("x", "scout", "core", 1000)
    b = r.spawn("x", "scout", "core", 1000)
    check("registry: спавн идемпотентен", a == b and a is not None, f"{a}/{b}")
    r.retire("x", "test")
    check("registry: ретайр работает", r.get("x")["status"] == "retired")
    r.close()
    t.close()


def main() -> int:
    for fn in (test_clean_dedup, test_score_and_tags, test_snapshot,
               test_rss_parse, test_robots_guard, test_pii_scrub,
               test_treasury, test_orchestrator, test_registry):
        try:
            fn()
        except Exception as e:  # тест не должен вешать рой — но должен орать
            check(fn.__name__, False, f"EXCEPTION {e!r}")

    width = max(len(n) for n, _, _ in RESULTS) + 2
    failed = 0
    for name, ok, note in RESULTS:
        print(f"  {'✓' if ok else '✗'} {name.ljust(width)} {note if not ok or note != '' and not ok else ''}")
        if not ok:
            failed += 1
    print(f"\nselftest: {len(RESULTS) - failed}/{len(RESULTS)} пройдено")
    if failed:
        for name, ok, note in RESULTS:
            if not ok:
                print(f"  FAIL {name}: {note}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

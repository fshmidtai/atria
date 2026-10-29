// atria-links — бэкенд улья на Cloudflare Workers (free tier: 100k req/день).
// Зачем: (1) публичный читаемый API состояния роя для пульта/партнёров,
//        (2) /go/:slug — управляемый роутер исходящих ссылок (будущий
//        affiliate/ads плот): все внешние коммерческие ссылки идут через нас
//        и перенацеливаются из конфига, а не перекомпиляцией сайтов.
// Состояния нет (KV недоступен) — только роутинг + прокси к HF-датасету.

const HF_STATE = "https://huggingface.co/datasets/fshmidtai/atria-hive-state/resolve/main/metrics.json";

// Роутер ссылок: slug → URL. Колонии ссылаются на /go/<slug>.
// Когда появится партнёрка — сюда добавляются ref-ссылки, и все сайты
// начинают вести в нужное место без перевыпуска dist/.
const LINKS = {
  github: "https://github.com/fshmidtai/atria",
  hf_state: "https://huggingface.co/datasets/fshmidtai/atria-hive-state",
  // monetization rails (заполняется после регистрации):
  support: null,   // Ko-fi / Buy Me a Coffee
  buy_data: null,  // Gumroad / LemonSqueezy
};

// CORS для публичного API
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    // /go/:slug — редирект
    const go = url.pathname.match(/^\/go\/([a-z0-9_-]+)$/);
    if (go) {
      const target = LINKS[go[1]];
      if (!target) {
        return json({ error: "unknown link", slug: go[1] }, 404);
      }
      return Response.redirect(target, 302);
    }

    // /status — состояние улья (проксируем HF-датасет, добавляем CORS)
    if (url.pathname === "/status" || url.pathname === "/api/status") {
      try {
        const r = await fetch(HF_STATE, { cf: { cacheTtl: 300 } });
        const data = await r.text();
        return new Response(data, {
          status: r.status,
          headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
        });
      } catch (e) {
        return json({ error: "state unavailable", detail: String(e) }, 502);
      }
    }

    // /links — карта доступных slug (для отладки и сайтов)
    if (url.pathname === "/links") {
      const out = {};
      for (const [k, v] of Object.entries(LINKS)) out[k] = v || "(не настроен)";
      return json(out, 200);
    }

    if (url.pathname === "/" || url.pathname === "/health") {
      return json({ ok: true, service: "atria-links", ts: Date.now() }, 200);
    }

    return json({ error: "not found", routes: ["/go/:slug", "/status", "/links", "/health"] }, 404);
  },
};

function json(obj, status) {
  return new Response(JSON.stringify(obj, null, 2), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

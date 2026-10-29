// Запускатель wrangler pages deploy из песочницы DSH (где CLI-флаги режутся
// на уровне shim'а, а pipe-stdio падает с EPERM). Аргументы — внутри файла,
// вывод направляем в файлы-дескрипторы (не именованные каналы).
//
// node infra/cloudflare/wrangler_deploy.js [имя_колонии|all]
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const PROJECTS = {
  phosphor: "signal-frontier",
  vesper: "vesper-ai-radar",
  sentinel: "sentinel-post",
  meridian: "meridian-radar",
  bourse: "bourse-radar",
};

function deploy(colony, project) {
  return new Promise((resolve) => {
    const dist = path.join(ROOT, "colonies", colony, "dist");
    const logPath = path.join(ROOT, ".wrangler-run.log");
    const out = fs.openSync(logPath, "w");
    const err = fs.openSync(logPath + ".err", "w");
    const args = [
      path.join(ROOT, "node_modules", "wrangler", "wrangler-dist", "cli.js"),
      "pages", "deploy", dist,
      "--project-name", project,
      "--branch", "master",
      "--commit-dirty",
    ];
    const child = spawn(process.execPath, args, { stdio: ["ignore", out, err] });
    child.on("close", (code) => {
      const txt = fs.readFileSync(logPath, "utf8") + fs.readFileSync(logPath + ".err", "utf8");
      const urlM = txt.match(/https:\/\/[a-z0-9-]+\.pages\.dev/);
      console.log(`${code === 0 ? "OK  " : "FAIL"} ${colony} -> ${project}${urlM ? " " + urlM[0] : ""}`);
      resolve(code === 0);
    });
  });
}

(async () => {
  const which = process.argv[2] || "all";
  const list = which === "all" ? Object.keys(PROJECTS) : [which];
  let ok = true;
  for (const c of list) {
    if (!PROJECTS[c]) { console.log("не знаю колонию:", c); ok = false; continue; }
    ok = (await deploy(c, PROJECTS[c])) && ok;
  }
  process.exit(ok ? 0 : 1);
})();

// Isolated browser checks: production Next.js, synthetic API, fresh Chrome profile.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { mkdtemp, readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { createWriteStream, existsSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const root = process.cwd();
assert(existsSync(resolve(root, "apps/web/.next/BUILD_ID")), "Build apps/web first");
const out = resolve(root, ".cache/day11-web");
await mkdir(out, { recursive: true });
const chromePath = process.env.DAY11_CHROME_PATH ||
  (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : "/usr/bin/google-chrome");
assert(existsSync(chromePath), "Set DAY11_CHROME_PATH to a Chrome executable");
const profile = await mkdtemp(resolve(out, "profile-"));
let mode = "success";
let productCalls = 0;
const requestId = "00000000-0000-4000-8000-000000000099";
const items = ["コーヒー", "紅茶", "ケーキ"].map((name, i) => ({
  id: "00000000-0000-4000-8000-" + String(i + 1).padStart(12, "0"),
  code: ["COFFEE", "TEA", "CAKE"][i], name,
  default_unit_price_yen: [550, 330, 440][i], is_active: true,
}));
const api = createServer(async (req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok" })); return;
  }
  assert.equal(req.url, "/products?is_active=true&limit=3");
  productCalls++;
  const state = mode;
  if (state === "slow") await delay(1800);
  if (state === "disconnect") { res.destroy(); return; }
  if (state === "timeout") await delay(6500);
  res.writeHead(state === "http" ? 503 : 200, {
    "content-type": "application/json", "x-request-id": requestId,
  });
  res.end(JSON.stringify(state === "http" ? { error: "PRIVATE_INTERNAL_MESSAGE" } :
    state === "malformed" ? { items: "PRIVATE_INTERNAL_MESSAGE" } :
    { items: state === "empty" ? [] : items, next_cursor: null }));
});
await new Promise((done) => api.listen(0, "127.0.0.1", done));
const apiUrl = "http://127.0.0.1:" + api.address().port;
const portReservation = createServer();
await new Promise((done) => portReservation.listen(0, "127.0.0.1", done));
const webPort = portReservation.address().port;
await new Promise((done) => portReservation.close(done));
const webUrl = "http://127.0.0.1:" + webPort;
let next, chrome, ws;
let sequence = 0;
const pending = new Map();
const network = [];
const exceptions = [];
const checks = [];
const logs = [];
let result;

async function until(check, message, timeout = 30000) {
  const stop = Date.now() + timeout;
  while (Date.now() < stop) {
    if (await check()) return;
    await delay(75);
  }
  throw new Error("Timed out: " + message);
}
function send(method, params = {}) {
  return new Promise((resolveCall, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error("CDP timeout: " + method)); }, 15000);
    pending.set(id, { resolve: resolveCall, reject, timeout });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  assert(!result.exceptionDetails, "Browser evaluation failed");
  return result.result.value;
}
const hasText = (text) => evaluate("document.body.innerText.includes(" + JSON.stringify(text) + ")");
const waitText = (text) => until(() => hasText(text), text);
async function refresh() {
  await until(() => evaluate("!document.querySelector('main button').disabled"), "refresh button ready");
  await evaluate("document.querySelector('main button').click()");
}
async function navigate(path) {
  await send("Page.navigate", { url: webUrl + path });
}
async function screenshot(name) {
  const result = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(resolve(out, name + ".png"), Buffer.from(result.data, "base64"));
}
async function stop(child) {
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([new Promise((done) => child.once("exit", done)), delay(8000)]);
  if (child.exitCode === null) { child.kill("SIGKILL"); await new Promise(done => child.once("exit", done)); }
}
try {
  const webLog = createWriteStream(resolve(out, "next.log")); logs.push(webLog);
  await once(webLog, "open");
  next = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", String(webPort)], {
    cwd: resolve(root, "apps/web"), env: { ...process.env, API_BASE_URL: apiUrl },
    stdio: ["ignore", webLog, webLog],
  });
  await until(async () => {
    assert.equal(next.exitCode, null, "Next.js exited");
    try { return (await fetch(webUrl + "/connection")).ok; } catch { return false; }
  }, "Next.js startup");
  const chromeLog = createWriteStream(resolve(out, "chrome.log")); logs.push(chromeLog);
  await once(chromeLog, "open");
  chrome = spawn(chromePath, ["--headless", "--remote-debugging-port=0", "--user-data-dir=" + profile,
    "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "about:blank"],
    { stdio: ["ignore", chromeLog, chromeLog] });
  await until(async () => existsSync(resolve(profile, "DevToolsActivePort")), "Chrome startup");
  const debugPort = (await readFile(resolve(profile, "DevToolsActivePort"), "utf8")).split("\n")[0];
  const targets = await (await fetch("http://127.0.0.1:" + debugPort + "/json/list")).json();
  ws = new WebSocket(targets.find((target) => target.type === "page").webSocketDebuggerUrl);
  await new Promise((done, reject) => { ws.addEventListener("open", done, { once: true }); ws.addEventListener("error", reject, { once: true }); });
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const call = pending.get(message.id);
      if (!call) return;
      pending.delete(message.id); clearTimeout(call.timeout);
      if (message.error) call.reject(new Error(message.error.message)); else call.resolve(message.result);
    } else if (message.method === "Network.requestWillBeSent") network.push(message.params.request.url);
    else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params);
  });
  await send("Page.enable"); await send("Runtime.enable"); await send("Network.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1365, height: 950, deviceScaleFactor: 1, mobile: false });
  await navigate("/");
  await waitText("コーヒー");
  assert.equal(await evaluate("document.querySelectorAll('tbody tr').length"), 3);
  assert(await hasText("550"));
  assert.equal(await evaluate("document.querySelector('nav [aria-current=page]').getAttribute('href')"), "/");
  await screenshot("desktop");
  checks.push("production_home_three_products_yen_navigation");

  await evaluate("document.querySelector('nav a[href=\"/connection\"]').click()");
  await waitText("APIに接続できました");
  assert.equal(await evaluate("document.querySelector('nav [aria-current=page]').getAttribute('href')"), "/connection");
  checks.push("client_navigation_and_health_success");

  mode = "empty"; await navigate("/"); await waitText("商品はまだ登録されていません");
  checks.push("empty_is_successful_not_connection_error");
  mode = "http"; await refresh(); await waitText("データを取得できませんでした");
  assert(await hasText(requestId)); assert(!(await hasText("PRIVATE_INTERNAL_MESSAGE")));
  checks.push("api_503_safe_message_request_id");
  mode = "success"; const calls = productCalls; await refresh(); await waitText("コーヒー");
  assert(productCalls > calls);
  checks.push("refresh_recovers_and_fetches_again");

  mode = "malformed"; await refresh(); await waitText("データを取得できませんでした");
  assert(!(await hasText("PRIVATE_INTERNAL_MESSAGE")));
  checks.push("malformed_json_shape_safe_failure");
  mode = "disconnect"; await navigate("/"); await waitText("データを取得できませんでした");
  checks.push("disconnected_api_safe_failure");
  mode = "timeout"; await navigate("/"); await waitText("データを取得できませんでした");
  checks.push("five_second_timeout_safe_failure");
  mode = "slow"; await navigate("/"); await waitText("読み込み中です");
  await screenshot("loading"); await waitText("コーヒー");
  checks.push("streaming_loading_then_success");

  mode = "success";
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await navigate("/"); await waitText("コーヒー");
  assert(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"));
  assert(await evaluate("document.querySelector('nav').getBoundingClientRect().width <= window.innerWidth"));
  await screenshot("mobile");
  checks.push("mobile_390px_no_document_overflow");
  await navigate("/missing-page"); await waitText("ページが見つかりません");
  assert.equal((await fetch(webUrl + "/missing-page")).status, 404);
  checks.push("unknown_route_404_with_common_shell");
  assert.equal(exceptions.length, 0);
  assert(!network.some((url) => url.startsWith(apiUrl)), "Browser called Python directly");
  checks.push("no_browser_to_python_requests_or_javascript_exceptions");
  result = { check_count: checks.length, checks, synthetic_api: true,
    browser: "headless Chrome with isolated profile", viewport_widths: [1365, 390],
    runtime: "production Next.js", temporary_servers_stopped: true };
} finally {
  ws?.close();
  for (const call of pending.values()) { clearTimeout(call.timeout); call.reject(new Error("Browser closed")); }
  await stop(chrome); await stop(next);
  api.closeAllConnections(); await new Promise((done) => api.close(done));
  for (const log of logs) log.end();
  await rm(profile, { recursive: true, force: true });
}
await writeFile(resolve(out, "result.json"), JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));

"""OST web interface.

A zero-dependency local web app (Python standard library only) that mirrors the
terminal UI: list suites, check official servers, download, install and update,
plus the Microsoft ODT/OCT configurator.

Run with `ost web` (or `ost-web`). Defaults to 127.0.0.1:8765; pass
`--host 0.0.0.0 --token <secret>` to reach it from other devices on the LAN.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from ost import __author__, __version__
from ost.actions import check_suite, download_suite, install_suite, update_suite
from ost.core import current_platform, detect_installed, ms_config_data, save_ms_config
from ost.providers import get_provider, list_providers
from ost.providers.msoffice import (
    CHANNELS,
    EXCLUDE_APPS,
    LANGUAGES,
    PRODUCT_CATALOG,
    build_configuration_xml,
    default_cfg,
    save_configuration_xml,
)


# ---------------------------------------------------------------------------
# background jobs
# ---------------------------------------------------------------------------


class Job:
    def __init__(self, jid: str, name: str, op: Callable[["Job"], None]):
        self.id = jid
        self.name = name
        self.op = op
        self.state = "queued"
        self.message = ""
        self.error = ""
        self.done = 0
        self.total: Optional[int] = None
        self.lines: list[str] = []
        self.created = time.time()

    def log(self, line: str) -> None:
        self.message = line
        self.lines.append(line)
        if len(self.lines) > 400:
            del self.lines[: len(self.lines) - 400]

    def progress(self, done: int, total: Optional[int] = None) -> None:
        self.done = done or 0
        self.total = total

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "message": self.message,
            "error": self.error,
            "done": self.done,
            "total": self.total,
            "lines": self.lines[-50:],
        }


class Jobs:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._seq = 0

    def create(self, name: str, op: Callable[[Job], None]) -> str:
        with self._lock:
            self._seq += 1
            jid = f"job-{self._seq}"
            job = Job(jid, name, op)
            self._jobs[jid] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return jid

    def _run(self, job: Job) -> None:
        job.state = "running"
        try:
            job.op(job)
        except Exception as e:  # noqa: BLE001 - surface every failure to the UI
            job.state = "error"
            job.error = str(e)
            job.log(f"error: {e}")
        else:
            if job.state == "running":
                job.state = "ok"

    def all(self) -> list[dict]:
        return [j.to_dict() for j in sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)]


jobs = Jobs()


# ---------------------------------------------------------------------------
# per-suite operations
# ---------------------------------------------------------------------------


def _op_check(slug: str, job: Job) -> None:
    provider = get_provider(slug)
    plat = current_platform()
    job.log(f"Checking {provider.name} official server ...")
    res = asyncio.run(check_suite(slug))
    if not res.available:
        job.log(f"{provider.name}: {res.reason}")
        return
    job.log(
        f"{provider.name}: installed={res.installed or '-'}  latest={res.latest or '-'}"
        + (f"  error: {res.error}" if res.error else "")
    )
    job.progress(100, 100)


def _op_download(slug: str, opts: dict, job: Job) -> None:
    provider = get_provider(slug)
    job.log(f"Downloading {provider.name} from official server ...")
    path, asset = asyncio.run(download_suite(slug, progress=job.progress, **opts))
    job.log(f"Saved: {path}  ({asset.size} bytes)")


def _op_install(slug: str, job: Job) -> None:
    provider = get_provider(slug)
    cfg = {**default_cfg(), **ms_config_data()} if slug == "ms-office" else None
    result = install_suite(slug, cfg=cfg, log=job.log)
    job.log(("OK: " if result.ok else "FAILED: ") + result.message)
    if result.instructions:
        job.log(result.instructions)
    job.progress(100, 100)


def _op_update(slug: str, job: Job) -> None:
    provider = get_provider(slug)
    cfg = {**default_cfg(), **ms_config_data()} if slug == "ms-office" else None
    job.log(f"Updating {provider.name} (download + install) ...")
    result, path = asyncio.run(update_suite(slug, progress=job.progress, log=job.log, cfg=cfg))
    if path:
        job.log(f"Downloaded: {path}")
    job.log(("OK: " if result.ok else "FAILED: ") + result.message)
    if result.instructions:
        job.log(result.instructions)
    job.progress(100, 100)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def _jsonify(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _suite_state() -> list[dict]:
    plat = current_platform()
    out = []
    for p in list_providers():
        out.append(
            {
                "slug": p.slug,
                "name": p.name,
                "vendor": p.vendor,
                "description": p.description,
                "official_url": p.official_url,
                "installed": detect_installed(p.slug),
                "supports": p.supports_platform(plat),
                "platforms": sorted(p.platforms),
                "install_modes": p.install_modes(),
            }
        )
    return out


class OstWebHandler(BaseHTTPRequestHandler):
    token: str = ""
    quiet = True

    # ---- plumbing ----
    def log_message(self, fmt: str, *args) -> None:  # silence access log
        if not self.quiet:
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes | str | dict, ctype: str) -> None:
        if isinstance(body, dict):
            data = _jsonify(body)
            ctype = "application/json; charset=utf-8"
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _authorized(self) -> bool:
        if not self.token:
            return True
        return self.headers.get("X-OST-Token", "") == self.token

    # ---- routing ----
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._authorized():
            return self._send(401, {"error": "invalid or missing token"}, "application/json")
        if path in ("/", "/index.html"):
            page = PAGE.replace("__TOKEN_REQUIRED__", "true" if self.token else "false")
            return self._send(200, page, "text/html; charset=utf-8")
        if path == "/api/state":
            return self._send(
                200,
                {
                    "version": __version__,
                    "author": __author__,
                    "platform": current_platform(),
                    "suites": _suite_state(),
                },
                "application/json",
            )
        if path == "/api/oct-meta":
            return self._send(
                200,
                {
                    "channels": [[f"{ch}  [{note}]", ch] for ch, label, note in CHANNELS],
                    "languages": [[label, wlc] for wlc, label in LANGUAGES],
                    "catalog": PRODUCT_CATALOG,
                    "exclude_apps": EXCLUDE_APPS,
                    "cfg": {**default_cfg(), **ms_config_data()},
                },
                "application/json",
            )
        if path == "/api/oct-config":
            cfg = {**default_cfg(), **ms_config_data()}
            return self._send(
                200,
                {"cfg": cfg, "xml": build_configuration_xml(cfg), "path": str(save_configuration_xml(cfg))},
                "application/json",
            )
        if path == "/api/jobs":
            return self._send(200, {"jobs": jobs.all()}, "application/json")
        return self._send(404, {"error": "not found"}, "application/json")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._authorized():
            return self._send(401, {"error": "invalid or missing token"}, "application/json")
        body = self._read_json()
        slug = body.get("suite", "")
        provider = get_provider(slug) if slug else None

        def start(name: str, op: Callable[[Job], None]) -> None:
            jid = jobs.create(name, op)
            self._send(200, {"job_id": jid, "name": name, "suite": slug}, "application/json")

        if path == "/api/check" and provider:
            return start(f"check {provider.name}", lambda job: _op_check(slug, job))
        if path == "/api/download" and provider:
            opts = {}
            if body.get("variant"):
                opts["variant"] = body["variant"]
            if body.get("lang"):
                opts["lang"] = body["lang"]
            return start(f"download {provider.name}", lambda job: _op_download(slug, opts, job))
        if path == "/api/install" and provider:
            return start(f"install {provider.name}", lambda job: _op_install(slug, job))
        if path == "/api/update" and provider:
            return start(f"update {provider.name}", lambda job: _op_update(slug, job))
        if path == "/api/oct-config":
            cfg = {**default_cfg(), **ms_config_data()}
            if isinstance(body.get("cfg"), dict):
                cfg.update(body["cfg"])
            save_ms_config(cfg)
            path_saved = save_configuration_xml(cfg)
            return self._send(
                200,
                {"ok": True, "xml": build_configuration_xml(cfg), "path": str(path_saved)},
                "application/json",
            )
        return self._send(404, {"error": "unknown route"}, "application/json")


# ---------------------------------------------------------------------------
# embedded page
# ---------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OST - Office Suite Toolkit</title>
<style>
:root{--bg:#060910;--panel:#0a0f1a;--card:#0e1526;--line:#1c2b44;--txt:#dfe6f0;
--mut:#7a8aa5;--acc:#3b82f6;--ok:#22c55e;--warn:#eab308;--bad:#ef4444;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
a{color:var(--acc);text-decoration:none}
.wrap{max-width:980px;margin:0 auto;padding:18px}
header{border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:16px}
header h1{margin:0;font-size:22px;letter-spacing:1px}
header .by{color:var(--mut);font-size:12px;margin-top:4px}
.btn{background:#101828;color:var(--txt);border:1px solid var(--line);border-radius:6px;
padding:6px 12px;cursor:pointer;font-size:13px}
.btn:hover,.btn:focus{border-color:var(--acc);color:#fff}
.btn.acc{background:var(--acc);border-color:var(--acc);color:#04121f;font-weight:600}
.btn.danger{border-color:#7f1d1d}
.btn:disabled{opacity:.45;cursor:not-allowed}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:12px}
.card h3{margin:0 0 2px}
.card .meta{color:var(--mut);font-size:12px}
.card .status{margin:8px 0 10px}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;margin-right:6px}
.chip.ok{background:#052e16;color:var(--ok);border:1px solid #14532d}
.chip.no{background:#300;color:var(--bad);border:1px solid #7f1d1d}
.chip.dim{background:#0b1118;color:var(--mut);border:1px solid var(--line)}
.actions{display:flex;gap:8px;flex-wrap:wrap}
h2{font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;margin:22px 0 12px;color:var(--acc)}
.job{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:10px}
.job .top{display:flex;justify-content:space-between;font-size:13px}
.job .msg{color:var(--mut);font-size:12px;margin:4px 0}
.bar{height:6px;background:#0b1118;border-radius:4px;overflow:hidden;margin-top:6px}
.bar>i{display:block;height:100%;background:var(--acc);transition:width .25s}
.job pre{margin:8px 0 0;font:11px/1.45 ui-monospace,Menlo,monospace;color:#b9c6dd;
max-height:140px;overflow:auto;white-space:pre-wrap;background:#070b12;border:1px solid var(--line);
border-radius:6px;padding:8px}
.hidden{display:none}
.toast{position:fixed;right:16px;bottom:16px;background:var(--acc);color:#04121f;font-weight:600;
padding:10px 14px;border-radius:8px;box-shadow:0 4px 18px #0008;display:none;max-width:320px}
.toast.show{display:block;animation:fadein .2s}
@keyframes fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1}}
form.grid{display:grid;grid-template-columns:auto 1fr;gap:8px 12px;align-items:center}
form.grid label{color:var(--mut);font-size:13px}
select,input[type=text]{background:var(--panel);color:var(--txt);border:1px solid var(--line);
border-radius:6px;padding:6px 8px;width:100%}
fieldset{border:1px solid var(--line);border-radius:8px;margin:0 0 10px;padding:10px 12px}
legend{color:var(--acc);font-size:13px;padding:0 6px}
.checks{display:flex;flex-wrap:wrap;gap:4px 14px}
.checks label{color:var(--txt);font-size:13px}
#oct-preview{background:#070b12;border:1px solid var(--line);border-radius:8px;padding:10px;
font:12px/1.5 ui-monospace,Menlo,monospace;color:#b9c6dd;white-space:pre-wrap;max-height:260px;overflow:auto}
.mut{color:var(--mut)}
</style>
</head>
<body>
<div class="toast" id="toast"></div>
<div class="wrap">
  <header>
    <h1>OST &mdash; Office Suite Toolkit</h1>
    <div class="by">by <b>MD. Shakibul Hassan (Shuvo)</b> &middot; v<span id="ver"></span>
      &middot; <span id="plat"></span> &middot; everything from the official vendor servers</div>
  </header>

  <div class="toolbar">
    <button class="btn acc" id="btn-check-all">Check all online</button>
    <button class="btn" id="btn-refresh">Refresh</button>
    <span id="hint" class="by" style="align-self:center"></span>
  </div>

  <div id="cards"></div>

  <h2>Microsoft Office - ODT / OCT configurator</h2>
  <div class="card" id="oct-card">
    <div class="status mut">Build the real <b>configuration.xml</b> for the Office Deployment Tool.</div>
    <fieldset><legend>Products</legend><div class="checks" id="oct-products"></div></fieldset>
    <fieldset><legend>Exclude applications</legend><div class="checks" id="oct-exclude"></div></fieldset>
    <form class="grid" onsubmit="saveOct();return false">
      <label>Channel</label><select id="oct-channel"></select>
      <label>Architecture</label><select id="oct-edition">
        <option value="64">64-bit</option><option value="32">32-bit</option></select>
      <label>Primary language</label><select id="oct-lang"></select>
      <label>Version pin (LTSC)</label><input type="text" id="oct-version">
      <label>Product key (PIDKEY)</label><input type="text" id="oct-pidkey">
    </form>
    <div class="actions" style="margin:10px 0">
      <button class="btn acc" onclick="saveOct()">Save configuration.xml</button>
      <span id="oct-saved" class="by" style="align-self:center"></span>
    </div>
    <div id="oct-preview"></div>
  </div>

  <h2>Activity</h2>
  <div id="jobs"></div>
</div>

<script>
var TOKEN_REQUIRED = __TOKEN_REQUIRED__;
var token = localStorage.getItem('ost_token') || '';
if (TOKEN_REQUIRED && !token) {
  token = prompt('Enter the OST access token') || '';
  if (token) localStorage.setItem('ost_token', token);
}
function hdr(){ return TOKEN_REQUIRED ? {'X-OST-Token': token} : {}; }
function toast(msg){ var t=document.getElementById('toast'); t.textContent=msg;
  t.classList.add('show'); clearTimeout(t._h); t._h=setTimeout(function(){t.classList.remove('show');},3500); }
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,
  function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
function fmt(n){ if(!n) return '-'; n=+n; if(n<1024) return n+' B';
  for(var u of ['KiB','MiB','GiB']){ n/=1024; if(n<1024) return n.toFixed(1)+' '+u; } return n.toFixed(1)+' GiB'; }
function interval(p){ return p>=1 ? 'active':'idle'; }

async function api(path, body){
  var r = await fetch(path, {method: body?'POST':'GET', headers: Object.assign(
    {'Content-Type':'application/json'}, hdr()), body: body?JSON.stringify(body):undefined});
  if (r.status===401){ toast('Invalid token - reload page'); throw new Error('unauthorized'); }
  return r.json();
}

function cardsHTML(state){
  var h='';
  state.suites.forEach(function(s){
    var chip = s.installed ? '<span class="chip ok">installed '+esc(s.installed)+'</span>'
      : (s.supports ? '<span class="chip dim">not installed</span>'
         : '<span class="chip no">not available on '+esc(state.platform)+'</span>');
    var only = s.supports ? '' : '<span class="mut"> ('+esc(s.platforms.join(', '))+' only)</span>';
    h += '<div class="card" id="card-'+esc(s.slug)+'">';
    h += '<h3>'+esc(s.name)+' <span class="mut">'+esc(s.vendor)+'</span>'+only+'</h3>';
    h += '<div class="meta">'+esc(s.description)+'</div>';
    h += '<div class="status">'+chip+'</div>';
    h += '<div class="actions">';
    h += '<button class="btn" onclick="startJob(\'check\',\''+esc(s.slug)+'\')">Check</button>';
    h += '<button class="btn" onclick="startJob(\'download\',\''+esc(s.slug)+'\')">Download</button>';
    h += '<button class="btn '+(s.supports?'':'danger')+'" onclick="startJob(\'install\',\''+esc(s.slug)+'\')"'+
         (s.supports?'':' disabled')+'>Install</button>';
    h += '<button class="btn '+(s.supports?'':'danger')+'" onclick="startJob(\'update\',\''+esc(s.slug)+'\')"'+
         (s.supports?'':' disabled')+'>Update</button>';
    h += '</div></div>';
  });
  return h;
}

async function loadState(refresh){
  try{
    var st = await api('/api/state');
    document.getElementById('ver').textContent = st.version;
    document.getElementById('plat').textContent = st.platform;
    var c=document.getElementById('cards'); c.innerHTML = cardsHTML(st);
    if(!refresh) document.getElementById('hint').textContent =
      'Install / Update will request root/administrator permission on this device - follow the system prompt (sudo password / UAC).';
    var last = document.querySelector('#cards .card .status .chip.ok');
    if(!last) document.getElementById('hint').textContent =
      'Install / Update will request root/administrator permission on this device.' ;
  }catch(e){ toast('Failed to load state: '+e.message); }
}

async function startJob(kind, slug, extra){
  var body = Object.assign({suite: slug}, extra||{});
  try{
    var j = await api('/api/'+kind, body);
    toast('Started: '+(j.name||kind)+' '+(j.suite||''));
    poll();
  }catch(e){ toast('Could not start: '+e.message); }
}

async function saveOct(){
  var data={ products: [], exclude_apps: [],
    channel: document.getElementById('oct-channel').value,
    edition: document.getElementById('oct-edition').value,
    primary_language: document.getElementById('oct-lang').value,
    version: document.getElementById('oct-version').value,
    pid_key: document.getElementById('oct-pidkey').value };
  document.querySelectorAll('#oct-products input:checked').forEach(function(i){ data.products.push(i.value); });
  document.querySelectorAll('#oct-exclude input:checked').forEach(function(i){ data.exclude_apps.push(i.value); });
  var r = await api('/api/oct-config', {cfg:data});
  document.getElementById('oct-preview').textContent = r.xml;
  document.getElementById('oct-saved').textContent = 'saved -> '+r.path;
  toast('configuration.xml saved');
}

async function loadOct(){
  var m = await api('/api/oct-meta');
  var c = m.cfg;
  var prod=''; m.catalog.forEach(function(g){
    prod += '<span class="mut" style="flex-basis:100%">'+esc(g[0])+'</span>';
    g[1].forEach(function(it){
      var pid=it[0]; var on=(c.products||[]).includes(pid)?' checked':'';
      prod += '<label><input type="checkbox" value="'+esc(pid)+'"'+on+'> '+esc(it[1])+'</label>'; }); });
  document.getElementById('oct-products').innerHTML = prod;
  var ex=''; (m.exclude_apps||[]).forEach(function(it){
    var app=it[0]; var on=(c.exclude_apps||[]).includes(app)?' checked':'';
    ex += '<label><input type="checkbox" value="'+esc(app)+'"'+on+'> '+esc(it[1])+'</label>'; });
  document.getElementById('oct-exclude').innerHTML = ex;
  fill('oct-channel', m.channels, c.channel);
  fill('oct-lang', m.languages, c.primary_language||'en-us');
  document.getElementById('oct-version').value = c.version||'';
  document.getElementById('oct-pidkey').value = c.pid_key||'';
  var r = await api('/api/oct-config');
  document.getElementById('oct-preview').textContent = r.xml;
}
function fill(id, pairs, want){
  var sel=document.getElementById(id); sel.innerHTML='';
  pairs.forEach(function(p){ var o=document.createElement('option');
    o.value=p[1]; o.textContent=p[0]; if(p[1]===want) o.selected=true; sel.appendChild(o); });
}

var polling=false;
function poll(){
  if(polling) return; polling=true;
  api('/api/jobs').then(function(j){
    var box=document.getElementById('jobs');
    if(!j.jobs.length){ box.innerHTML='<div class="mut">No activity yet.</div>'; return; }
    box.innerHTML='';
    j.jobs.slice(0,12).forEach(function(jb){
      var div=document.createElement('div'); div.className='job';
      var pct=0; if(jb.total) pct=Math.min(100, Math.round(jb.done/jb.total*100));
      else if(jb.state==='ok') pct=100;
      var col= jb.state==='error'?'#ef4444':(jb.state==='ok'?'#22c55e':'#3b82f6');
      div.innerHTML='<div class="top"><b>'+esc(jb.name)+'</b>'+
        '<span style="color:'+col+'">'+esc(jb.state)+((!jb.total&&jb.done)?(' '+fmt(jb.done)):'')+'</span></div>'+
        '<div class="msg">'+esc(jb.message)+'</div>'+
        '<div class="bar"><i style="width:'+pct+'%"'+'"></i></div>'+
        '<pre>'+esc((jb.lines||[]).join('\\n'))+'</pre>';
      box.appendChild(div);
    });
    window._active = j.jobs.some(function(x){return x.state==='running'||x.state==='queued';});
  }).catch(function(){ window._active=false; }).finally(function(){ polling=false; });
}
setInterval(function(){ poll(); }, 800);

document.getElementById('btn-check-all').onclick=function(){ document.querySelectorAll('#cards .card')
  .forEach(function(c){ var b=c.querySelector('.btn'); if(b) b.click(); }); };
document.getElementById('btn-refresh').onclick=function(){ loadState(true); };

loadState(); loadOct(); poll();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# server wiring
# ---------------------------------------------------------------------------


def create_server(host: str = "127.0.0.1", port: int = 8765, token: str = "") -> tuple[ThreadingHTTPServer, str]:
    class Handler(OstWebHandler):
        pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    Handler.token = token
    return server, f"http://{host}:{port}"


def _open_browser(url: str) -> None:
    """Best-effort auto-open; never blocks or crashes startup."""
    import os
    import sys

    if sys.platform != "win32" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return
    try:
        webbrowser.open(url)
    except BaseException:  # noqa: BLE001 - a missing browser must not kill the server
        pass


def serve(host: str = "127.0.0.1", port: int = 8765, token: str = "", open_browser: bool = True) -> int:
    try:
        server, url = create_server(host, port, token)
    except OSError as e:
        print(f"| Could not bind {host}:{port} - {e}")
        return 1
    sep = "=" * 46
    print(sep)
    print(f"  OST {__version__}  web interface  ·  by {__author__}")
    print(sep)
    print(f"  Local:     {url}")
    print(f"  Stop with: Ctrl+C")
    if token:
        print(f"  Access token: {token}")
    print(sep)
    try:
        if open_browser and host in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
            _open_browser(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n| Web interface stopped.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ost-web", description="OST web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="", help="require this token on LAN mode")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    return serve(args.host, args.port, args.token, open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
"""PlexGap - fehlende Serienfolgen in Plex finden.
Start:  python server.py   (öffnet http://localhost:8765)
Nur Python-Standardbibliothek. Episodenlisten kommen von TVmaze (kein Key nötig).
"""
import datetime
import json
import os
import py_compile
import shutil
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
PRODUCT = "PlexGap"
UNVERIFIED = ssl._create_unverified_context()


def client_id():
    p = os.path.join(HERE, "client_id.txt")
    if os.path.exists(p):
        return open(p).read().strip()
    cid = str(uuid.uuid4())
    open(p, "w").write(cid)
    return cid


CID = client_id()


def get_json(url, headers=None, method="GET", timeout=20, verify=True, retries=3):
    h = {"Accept": "application/json", "X-Plex-Client-Identifier": CID,
         "X-Plex-Product": PRODUCT, **(headers or {})}
    req = urllib.request.Request(url, headers=h, method=method)
    ctx = None if verify else UNVERIFIED
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2 + attempt * 2)
                continue
            raise


# ---------- Plex ----------
_conn_cache = {}


def plex_resources(token):
    return get_json("https://plex.tv/api/v2/resources?includeHttps=1&includeRelay=1",
                    {"X-Plex-Token": token})


def connect(token, machine_id, url=""):
    if url:  # feste Serveradresse hat Vorrang
        url = url.strip().rstrip("/")
        get_json(url + "/identity", {"X-Plex-Token": token}, timeout=8, verify=False, retries=1)
        return (url, token)
    key = (token, machine_id)
    if key in _conn_cache:
        return _conn_cache[key]
    for dev in plex_resources(token):
        if dev.get("clientIdentifier") != machine_id:
            continue
        srv_token = dev.get("accessToken") or token
        conns = sorted(dev.get("connections", []),
                       key=lambda c: (c.get("relay", False), c.get("local", False)))  # öffentlich zuerst, dann Relay, dann lokal
        for c in conns:
            try:
                get_json(c["uri"] + "/identity", {"X-Plex-Token": srv_token}, timeout=5,
                         verify=False, retries=1)
                _conn_cache[key] = (c["uri"], srv_token)
                return _conn_cache[key]
            except Exception:
                continue
    raise RuntimeError("Keine Verbindung zum Plex-Server möglich")


def plex_get(conn, path):
    uri, tok = conn
    return get_json(uri + path, {"X-Plex-Token": tok}, verify=False, timeout=60)


# ---------- TVmaze ----------
_tvmaze_eps = {}


def tvmaze_find(show_title, guids):
    for g in guids:
        if g.startswith("tvdb://"):
            url = "https://api.tvmaze.com/lookup/shows?thetvdb=" + g[7:]
        elif g.startswith("imdb://"):
            url = "https://api.tvmaze.com/lookup/shows?imdb=" + g[7:]
        else:
            continue
        try:
            return get_json(url)  # Show-Objekt mit id und averageRuntime
        except Exception:
            pass
    try:
        return get_json("https://api.tvmaze.com/singlesearch/shows?q=" + urllib.parse.quote(show_title))
    except Exception:
        return None


def tvmaze_episodes(tid):
    if tid not in _tvmaze_eps:
        _tvmaze_eps[tid] = get_json(f"https://api.tvmaze.com/shows/{tid}/episodes")
    return _tvmaze_eps[tid]


# ---------- Gespeichertes Ergebnis ----------
RESULT_FILE = os.path.join(HERE, "last_result.json")
_lock = threading.Lock()


def load_last():
    with _lock:
        try:
            with open(RESULT_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"date": None, "results": []}


def save_last(data):
    with _lock:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


def clear_last():
    with _lock:
        if os.path.exists(RESULT_FILE):
            os.remove(RESULT_FILE)


# ---------- Dauerhaft ausgeblendete Serien ----------
IGNORE_FILE = os.path.join(HERE, "ignored.json")


def load_ignored():
    with _lock:
        try:
            with open(IGNORE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []


def save_ignored(items):
    with _lock:
        with open(IGNORE_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)


# ---------- Scan-Job ----------
jobs = {}


def scan(job, token, machine_id, section, url="", resume=False):
    try:
        prev = load_last() if resume else {}
        if prev.get("section") != section:
            prev = {}  # anderes Ergebnis/andere Bibliothek: von vorn beginnen
        checked = set(prev.get("checked", []))
        ign = load_ignored()
        ign_rk = {i["rk"] for i in ign if i.get("rk")}
        ign_titles = {i["title"] for i in ign}
        job["results"] = list(prev.get("results", []))
        conn = connect(token, machine_id, url)
        shows = plex_get(conn, f"/library/sections/{section}/all?type=2&includeGuids=1")["MediaContainer"].get("Metadata", [])
        job["total"] = len(shows)
        today = datetime.date.today().isoformat()
        for s in shows:
            if job.get("cancel"):
                break
            rk = str(s["ratingKey"])
            if rk in ign_rk or s["title"] in ign_titles:
                job["done"] += 1  # dauerhaft ausgeblendet
                continue
            if rk in checked:
                job["done"] += 1
                continue
            job["results"] = [r for r in job["results"] if r["title"] != s["title"]]
            job["current"] = s["title"]
            entry = {"title": s["title"], "year": s.get("year"), "missing": [], "note": None, "rk": rk}
            try:
                guids = [g["id"] for g in s.get("Guid", [])]
                leaves = plex_get(conn, f"/library/metadata/{s['ratingKey']}/allLeaves")["MediaContainer"].get("Metadata", [])
                have = set()
                for l in leaves:
                    se, ep = l.get("parentIndex"), l.get("index")
                    if se is None or ep is None:
                        continue
                    for n in range(ep, (l.get("indexEnd") or ep) + 1):
                        have.add((se, n))
                show = tvmaze_find(s["title"], guids)
                tid = show["id"] if show else None
                avg = (show or {}).get("averageRuntime") or (show or {}).get("runtime")
                if tid is None:
                    entry["note"] = "Serie bei TVmaze nicht gefunden"
                else:
                    time.sleep(0.15)
                    for e in tvmaze_episodes(tid):
                        if not e.get("number") or e["season"] < 1:
                            continue  # Specials ignorieren
                        if not e.get("airdate") or e["airdate"] > today:
                            continue  # noch nicht ausgestrahlt
                        if (e["season"], e["number"]) not in have:
                            entry["missing"].append({"s": e["season"], "e": e["number"],
                                                     "name": e.get("name", ""), "airdate": e["airdate"],
                                                     "rt": e.get("runtime") or avg or 0})
            except Exception as ex:
                entry["note"] = f"Fehler: {ex}"
            else:
                checked.add(rk)  # Fehlerhafte Serien werden beim Fortsetzen erneut versucht
            job["results"].append(entry)
            job["done"] += 1
        # Während des Laufs ausgeblendete Serien nicht wieder ins Ergebnis schreiben
        ign = load_ignored()
        ign_rk = {i["rk"] for i in ign if i.get("rk")}
        ign_titles = {i["title"] for i in ign}
        job["results"] = [r for r in job["results"] if r["title"] not in ign_titles]
        checked -= ign_rk
        save_last({"date": datetime.datetime.now().isoformat(timespec="seconds"),
                   "section": section,
                   "checked": sorted(checked),
                   "partial": f"{job['done']}/{job['total']}" if job["done"] < job["total"] else None,
                   "results": [r for r in job["results"] if r["missing"] or r["note"]]})
        job["state"] = "done"
    except Exception as ex:
        job["state"] = "error"
        job["error"] = str(ex)


# ---------- Selbst-Update von GitHub ----------
REPO = "bernhardhaba/PlexGap"
BRANCH = "main"
VERSION_FILE = os.path.join(HERE, "version.json")
AUTOUPDATE = os.environ.get("PLEXGAP_AUTOUPDATE") == "1"
UPDATE_FILES = ("server.py", "index.html")
update_state = {"status": "", "latest": None, "checked": None}


def gh_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "PlexGap"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def current_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return json.load(f)["sha"]
    except Exception:
        return None


def restart_soon():
    def _r():
        time.sleep(1.5)
        os.environ["HEADLESS"] = "1"  # nach dem Neustart keinen Browser öffnen
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=_r, daemon=True).start()


def do_update(auto=False):
    """Holt die neueste Version von GitHub. Gibt True zurück, wenn aktualisiert wurde."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    if auto and any(j["state"] == "running" for j in jobs.values()):
        return False  # laufende Prüfung nicht unterbrechen
    sha = json.loads(gh_get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"))["sha"]
    update_state.update(latest=sha, checked=now)
    if sha == current_version():
        update_state["status"] = "Aktuell"
        return False
    files = {n: gh_get(f"https://raw.githubusercontent.com/{REPO}/{sha}/{n}") for n in UPDATE_FILES}
    # Plausibilitätsprüfung, bevor etwas überschrieben wird
    if b"ThreadingHTTPServer" not in files["server.py"] or b"PlexGap" not in files["index.html"]:
        raise RuntimeError("Heruntergeladene Dateien sehen nicht richtig aus")
    tmpdir = tempfile.mkdtemp()
    try:
        tmp = os.path.join(tmpdir, "check.py")
        with open(tmp, "wb") as f:
            f.write(files["server.py"])
        py_compile.compile(tmp, cfile=os.path.join(tmpdir, "check.pyc"), doraise=True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    for name, data in files.items():
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        with open(path + ".new", "wb") as f:
            f.write(data)
        os.replace(path + ".new", path)
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump({"sha": sha, "updated": now}, f)
    update_state["status"] = "Aktualisiert, starte neu …"
    restart_soon()
    return True


def updater_loop():
    time.sleep(10)
    while True:
        try:
            do_update(auto=True)
        except Exception as ex:
            update_state["status"] = f"Update-Prüfung fehlgeschlagen: {ex}"
        time.sleep(6 * 3600)


# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        tok = self.headers.get("X-Token", "")
        try:
            if u.path == "/":
                body = open(os.path.join(HERE, "index.html"), "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/pin":
                r = get_json(f"https://plex.tv/api/v2/pins/{q['id']}?code={q['code']}")
                self.send({"token": r.get("authToken")})
            elif u.path == "/api/servers":
                self.send([{"id": d["clientIdentifier"], "name": d["name"]}
                           for d in plex_resources(tok) if "server" in d.get("provides", "")])
            elif u.path == "/api/libraries":
                conn = connect(tok, q.get("server", ""), q.get("url", ""))
                secs = plex_get(conn, "/library/sections")["MediaContainer"].get("Directory", [])
                self.send([{"key": s["key"], "title": s["title"]} for s in secs if s["type"] == "show"])
            elif u.path == "/api/last":
                self.send(load_last())
            elif u.path == "/api/version":
                v = current_version()
                self.send({"version": v[:7] if v else None, "auto": AUTOUPDATE,
                           "status": update_state["status"], "checked": update_state["checked"]})
            elif u.path == "/api/ignored":
                self.send(load_ignored())
            elif u.path == "/api/job":
                j = jobs[q["id"]]
                hidden = {i["title"] for i in load_ignored()}
                self.send({**j, "results": [r for r in j["results"]
                                            if (r["missing"] or r["note"]) and r["title"] not in hidden]})
            else:
                self.send({"error": "not found"}, 404)
        except Exception as ex:
            self.send({"error": str(ex)}, 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n) or b"{}")
        tok = self.headers.get("X-Token", "")
        try:
            if u.path == "/api/pin":
                r = get_json("https://plex.tv/api/v2/pins?strong=true", method="POST")
                url = ("https://app.plex.tv/auth#?clientID=" + CID + "&code=" + r["code"] +
                       "&context%5Bdevice%5D%5Bproduct%5D=" + PRODUCT)
                self.send({"id": r["id"], "code": r["code"], "url": url})
            elif u.path == "/api/update":
                try:
                    updated = do_update()
                except Exception as ex:
                    update_state["status"] = f"Update fehlgeschlagen: {ex}"
                    updated = False
                self.send({"updated": updated, "status": update_state["status"]})
            elif u.path == "/api/stop":
                if data.get("id") in jobs:
                    jobs[data["id"]]["cancel"] = True
                self.send({"ok": True})
            elif u.path == "/api/last/clear":
                clear_last()
                self.send({"ok": True})
            elif u.path == "/api/last/remove":
                # "Ausblenden": aus dem Ergebnis nehmen und dauerhaft ignorieren
                title = data.get("title")
                d = load_last()
                hit = [r for r in d["results"] if r["title"] == title]
                rk = hit[0].get("rk") if hit else None
                d["results"] = [r for r in d["results"] if r["title"] != title]
                if rk:
                    d["checked"] = [c for c in d.get("checked", []) if c != rk]
                save_last(d)
                ign = load_ignored()
                if not any(i["title"] == title for i in ign):
                    ign.append({"title": title, "rk": rk, "entry": hit[0] if hit else None})
                    save_ignored(ign)
                self.send(ign)
            elif u.path == "/api/ignored/remove":
                title = data.get("title")
                allign = load_ignored()
                item = next((i for i in allign if i["title"] == title), None)
                ign = [i for i in allign if i["title"] != title]
                save_ignored(ign)
                restored = False
                if item and item.get("entry"):  # Serie sofort zurück ins gespeicherte Ergebnis
                    d = load_last()
                    if d.get("section") is not None and not any(r["title"] == title for r in d["results"]):
                        d["results"].append(item["entry"])
                        if item.get("rk"):
                            d["checked"] = sorted(set(d.get("checked", [])) | {item["rk"]})
                        save_last(d)
                        restored = True
                self.send({"ignored": ign, "restored": restored})
            elif u.path == "/api/scan":
                jid = uuid.uuid4().hex
                jobs[jid] = {"state": "running", "total": 0, "done": 0, "current": "", "results": []}
                threading.Thread(target=scan, args=(jobs[jid], tok, data.get("server", ""), data["section"], data.get("url", ""),
                                       bool(data.get("resume"))),
                                 daemon=True).start()
                self.send({"id": jid})
            else:
                self.send({"error": "not found"}, 404)
        except Exception as ex:
            self.send({"error": str(ex)}, 500)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")  # im Container: HOST=0.0.0.0
    srv = ThreadingHTTPServer((host, PORT), H)
    print(f"Läuft auf http://{host}:{PORT}  (Strg+C beendet)", flush=True)
    if not os.environ.get("HEADLESS"):
        webbrowser.open(f"http://localhost:{PORT}")
    if AUTOUPDATE:
        threading.Thread(target=updater_loop, daemon=True).start()
    srv.serve_forever()

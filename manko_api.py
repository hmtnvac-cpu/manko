from flask import Flask, jsonify, request
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone
from threading import Lock
import hashlib
import json
import re
import os

app = Flask(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
REFERER = "https://javplayer.cc/"
STORE_FILE = os.environ.get("MANKO_RESULTS_FILE", "/tmp/manko_collector_results.json")
STORE_LOCK = Lock()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def load_store():
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"movies": {}, "errors": {}, "catalog": {"total": None, "urls": [], "updatedAt": None}}


def save_store(data):
    folder = os.path.dirname(STORE_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE_FILE)


def movie_key(payload):
    player_id = str(payload.get("playerId") or "").strip()
    if player_id:
        return "movie_manko_" + re.sub(r"[^A-Za-z0-9_-]", "", player_id)
    movie_url = str(payload.get("movieUrl") or "")
    return "movie_manko_" + hashlib.sha1(movie_url.encode("utf-8")).hexdigest()[:16]


def sanitize_result(payload):
    item = {
        "id": movie_key(payload),
        "title": str(payload.get("title") or "Manko").strip(),
        "movieUrl": str(payload.get("movieUrl") or "").strip(),
        "poster": str(payload.get("poster") or "").strip(),
        "playerId": str(payload.get("playerId") or "").strip(),
        "playerUrl": str(payload.get("playerUrl") or "").strip(),
        "streamUrl": str(payload.get("streamUrl") or "").strip(),
        "vttUrl": str(payload.get("vttUrl") or "").strip(),
        "headers": payload.get("headers") if isinstance(payload.get("headers"), dict) else {"Referer": REFERER},
        "collectedAt": str(payload.get("collectedAt") or utcnow()),
        "updatedAt": utcnow(),
    }
    if not item["headers"].get("Referer"):
        item["headers"]["Referer"] = REFERER
    return item


def extract_player_id(url):
    m = re.search(r"/e/([^/?#]+)", url or "")
    return m.group(1) if m else None


def first_javplayer_url(values):
    for value in values:
        if not value:
            continue
        m = re.search(r"https://javplayer\.cc/e/[^\"'<>\\\s]+", value)
        if m:
            return m.group(0).replace("&amp;", "&")
    return None


def resolve_manko(url, verify=False):
    result = {
        "status": "starting", "input_url": url, "title": None, "final_url": None,
        "player_url": None, "player_id": None, "stream_api_url": None,
        "stream_url": None, "vtt_url": None,
        "headers": {"Referer": REFERER, "User-Agent": UA},
        "verify": None, "discovery": None, "stream_api_debug": None,
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(user_agent=UA, viewport={"width": 1365, "height": 900})
        page = context.new_page()
        seen_urls = []

        def remember(u):
            if u and u not in seen_urls:
                seen_urls.append(u)

        page.on("request", lambda req: remember(req.url))
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(8000)
        result["title"], result["final_url"] = page.title(), page.url

        frame = next((f for f in page.frames if "javplayer.cc/e/" in (f.url or "")), None)
        player_url = frame.url if frame else None
        discovery = "frame" if frame else None
        if not player_url:
            try:
                srcs = page.locator("iframe").evaluate_all("els => els.map(e => e.src || e.getAttribute('src') || '')")
                player_url = first_javplayer_url(srcs)
                if player_url:
                    discovery = "iframe_src"
            except Exception:
                pass
        if not player_url:
            player_url = first_javplayer_url(seen_urls)
            if player_url:
                discovery = "network"
        if not player_url:
            try:
                html = page.content()
                player_url = first_javplayer_url([html, html.replace("\\/", "/")])
                if player_url:
                    discovery = "html"
            except Exception:
                pass
        if not player_url:
            result["status"] = "no_player"
            browser.close()
            return result

        result["player_url"] = player_url
        result["player_id"] = extract_player_id(player_url)
        result["discovery"] = discovery
        result["status"] = "player_found_server_stream_blocked"
        browser.close()
        return result


@app.get("/")
def root():
    return jsonify({
        "service": "manko-api",
        "status": "ok",
        "addon_manifest": "/manifest.json",
        "collector": "/collector/results",
        "stats": "/collector/stats"
    })


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "manko-api"})


@app.post("/collector/result")
def collector_result():
    payload = request.get_json(silent=True) or {}
    if not str(payload.get("movieUrl") or "").startswith("https://manko.fun/movie-info/"):
        return jsonify({"ok": False, "error": "invalid movieUrl"}), 400
    if not str(payload.get("streamUrl") or "").startswith(("http://", "https://")):
        return jsonify({"ok": False, "error": "invalid streamUrl"}), 400
    item = sanitize_result(payload)
    with STORE_LOCK:
        store = load_store()
        store.setdefault("movies", {})[item["id"]] = item
        save_store(store)
    return jsonify({"ok": True, "id": item["id"], "stored": len(store.get("movies", {}))})


@app.post("/collector/error")
def collector_error():
    payload = request.get_json(silent=True) or {}
    movie_url = str(payload.get("movieUrl") or "")
    key = hashlib.sha1(movie_url.encode("utf-8")).hexdigest()[:16]
    with STORE_LOCK:
        store = load_store()
        store.setdefault("errors", {})[key] = {**payload, "updatedAt": utcnow()}
        save_store(store)
    return jsonify({"ok": True})


@app.post("/collector/catalog")
def collector_catalog():
    payload = request.get_json(silent=True) or {}
    urls = [str(x) for x in (payload.get("urls") or []) if str(x).startswith("https://manko.fun/movie-info/")]
    urls = list(dict.fromkeys(urls))
    with STORE_LOCK:
        store = load_store()
        store["catalog"] = {"total": len(urls), "urls": urls, "pageUrl": payload.get("pageUrl"), "updatedAt": utcnow()}
        save_store(store)
    return jsonify({"ok": True, "total": len(urls)})


@app.get("/collector/results")
def collector_results():
    store = load_store()
    items = list(store.get("movies", {}).values())
    items.sort(key=lambda x: x.get("collectedAt") or "", reverse=True)
    skip = max(0, int(request.args.get("skip", "0") or 0))
    limit = min(500, max(1, int(request.args.get("limit", "100") or 100)))
    return jsonify({"total": len(items), "items": items[skip:skip+limit]})


@app.get("/collector/results/<movie_id>")
def collector_one(movie_id):
    item = load_store().get("movies", {}).get(movie_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    return jsonify(item)


@app.get("/collector/stats")
def collector_stats():
    store = load_store()
    catalog = store.get("catalog") or {}
    total_catalog = catalog.get("total")
    resolved = len(store.get("movies", {}))
    errors = len(store.get("errors", {}))
    remaining = max(0, total_catalog - resolved - errors) if isinstance(total_catalog, int) else None
    return jsonify({
        "catalogTotal": total_catalog,
        "resolved": resolved,
        "errors": errors,
        "remaining": remaining,
        "catalogUpdatedAt": catalog.get("updatedAt")
    })


@app.get("/manko")
def manko():
    url = request.args.get("url", "").strip()
    verify = request.args.get("verify", "0").lower() in {"1", "true", "yes"}
    if not url.startswith("https://manko.fun/"):
        return jsonify({"status": "error", "error": "A valid https://manko.fun/ URL is required"}), 400
    try:
        return jsonify(resolve_manko(url, verify=verify))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


from manko_addon import register_manko_addon
register_manko_addon(app, load_store)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

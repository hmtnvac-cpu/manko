from flask import Flask, jsonify, request
from playwright.sync_api import sync_playwright
import re
import os

app = Flask(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
REFERER = "https://javplayer.cc/"


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
        "status": "starting",
        "input_url": url,
        "title": None,
        "final_url": None,
        "player_url": None,
        "player_id": None,
        "stream_api_url": None,
        "stream_url": None,
        "vtt_url": None,
        "headers": {"Referer": REFERER, "User-Agent": UA},
        "verify": None,
        "discovery": None,
        "stream_api_debug": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(user_agent=UA, viewport={"width": 1365, "height": 900})
        page = context.new_page()
        captured = {}
        seen_urls = []

        def remember(u):
            if u and u not in seen_urls:
                seen_urls.append(u)

        def on_request(req):
            remember(req.url)

        def on_response(resp):
            remember(resp.url)
            if "javplayer.cc/stream" not in resp.url:
                return
            try:
                raw = resp.text()
            except Exception:
                raw = ""
            captured["url"] = resp.url
            captured["status"] = resp.status
            captured["content_type"] = resp.headers.get("content-type")
            captured["raw"] = raw[:4000]
            try:
                captured["json"] = resp.json()
            except Exception:
                captured["json"] = None

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(8000)

        result["title"] = page.title()
        result["final_url"] = page.url

        frame = next((f for f in page.frames if "javplayer.cc/e/" in (f.url or "")), None)
        player_url = frame.url if frame else None
        discovery = "frame" if frame else None

        if not player_url:
            try:
                iframe_srcs = page.locator("iframe").evaluate_all("els => els.map(e => e.src || e.getAttribute('src') || '')")
                player_url = first_javplayer_url(iframe_srcs)
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
            selectors = [
                "text=Streaming", "text=Play", "text=Watch", "text=Xem",
                "button:has-text('Streaming')", "button:has-text('Play')", "button:has-text('Watch')",
                "a:has-text('Streaming')", "a:has-text('Play')", "a:has-text('Watch')",
                "[role='tab']:has-text('Streaming')", "[aria-label*='play' i]",
                ".fluid_button_play", ".fluid_controls_playpause", "video"
            ]
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    for i in range(min(loc.count(), 8)):
                        try:
                            if loc.nth(i).is_visible():
                                loc.nth(i).click(force=True, timeout=2000)
                                page.wait_for_timeout(1000)
                        except Exception:
                            pass
                except Exception:
                    pass
            page.wait_for_timeout(5000)
            frame = next((f for f in page.frames if "javplayer.cc/e/" in (f.url or "")), None)
            if frame:
                player_url = frame.url
                discovery = "frame_after_click"
            if not player_url:
                player_url = first_javplayer_url(seen_urls)
                if player_url:
                    discovery = "network_after_click"
            if not player_url:
                try:
                    html = page.content()
                    player_url = first_javplayer_url([html, html.replace("\\/", "/")])
                    if player_url:
                        discovery = "html_after_click"
                except Exception:
                    pass

        if not player_url:
            result["status"] = "no_player"
            result["discovery"] = {
                "frames": [f.url for f in page.frames],
                "iframes": page.locator("iframe").count(),
                "javplayer_requests": [u for u in seen_urls if "javplayer" in u.lower()][-20:],
            }
            browser.close()
            return result

        result["player_url"] = player_url
        result["player_id"] = extract_player_id(player_url)
        result["discovery"] = discovery

        player_page = None
        target = frame if frame and frame.url == player_url else None
        if target is None:
            player_page = context.new_page()
            player_page.on("response", on_response)
            player_page.goto(player_url, wait_until="domcontentloaded", timeout=60000)
            player_page.wait_for_timeout(5000)
            target = player_page.main_frame

        page.wait_for_timeout(3000)
        if player_page:
            player_page.wait_for_timeout(2000)

        data = {}
        if captured.get("json"):
            result["stream_api_url"] = captured.get("url")
            data = captured.get("json") or {}
            result["stream_api_debug"] = {
                "source": "captured_response",
                "status": captured.get("status"),
                "content_type": captured.get("content_type"),
                "raw_preview": captured.get("raw"),
            }
        else:
            fetch_result = target.evaluate(r"""
                async () => {
                    const m = location.pathname.match(/\/e\/([^/?#]+)/);
                    if (!m) return {error: 'no player id'};
                    const u = new URL('/stream', location.origin);
                    new URLSearchParams(location.search).forEach((value, key) => u.searchParams.set(key, value));
                    u.searchParams.set('id', m[1]);
                    const r = await fetch(u.toString(), {
                        method: 'GET',
                        credentials: 'include',
                        cache: 'no-store',
                        headers: {
                            'Accept': 'application/json,text/plain,*/*',
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    });
                    const raw = await r.text();
                    let body = null;
                    try { body = JSON.parse(raw); } catch (e) {}
                    return {
                        api_url: u.toString(),
                        status: r.status,
                        ok: r.ok,
                        content_type: r.headers.get('content-type'),
                        raw: raw.slice(0, 4000),
                        body
                    };
                }
            """)
            if fetch_result.get("error"):
                result["status"] = "stream_api_error"
                result["error"] = fetch_result["error"]
                browser.close()
                return result
            result["stream_api_url"] = fetch_result.get("api_url")
            result["stream_api_debug"] = {
                "source": "frame_fetch",
                "status": fetch_result.get("status"),
                "ok": fetch_result.get("ok"),
                "content_type": fetch_result.get("content_type"),
                "raw_preview": fetch_result.get("raw"),
            }
            data = fetch_result.get("body") or {}

            # If in-page fetch did not yield media, retry through Playwright's request context
            # while reusing browser cookies and the real javplayer Referer.
            if not (isinstance(data, dict) and data.get("media", {}).get("stream")):
                try:
                    api_url = result["stream_api_url"]
                    rr = context.request.get(api_url, headers={
                        "Referer": player_url,
                        "Origin": "https://javplayer.cc",
                        "User-Agent": UA,
                        "Accept": "application/json,text/plain,*/*",
                        "X-Requested-With": "XMLHttpRequest",
                    }, timeout=30000)
                    raw2 = rr.text()
                    try:
                        data2 = rr.json()
                    except Exception:
                        data2 = {}
                    result["stream_api_debug"]["request_context_retry"] = {
                        "status": rr.status,
                        "ok": rr.ok,
                        "content_type": rr.headers.get("content-type"),
                        "raw_preview": raw2[:4000],
                    }
                    if isinstance(data2, dict) and data2.get("media"):
                        data = data2
                except Exception as e:
                    result["stream_api_debug"]["request_context_retry"] = {"error": str(e)}

        media = data.get("media", {}) if isinstance(data, dict) else {}
        result["stream_url"] = media.get("stream")
        result["vtt_url"] = media.get("vtt")
        result["status"] = "ok" if result["stream_url"] else "no_stream"

        if verify and result["stream_url"]:
            try:
                vr = target.evaluate(r"""
                    async (u) => {
                        const r = await fetch(u, {headers: {'Accept':'*/*'}});
                        const text = await r.text();
                        return {status:r.status, ok:r.ok, content_type:r.headers.get('content-type'), preview:text.slice(0,3000)};
                    }
                """, result["stream_url"])
                result["verify"] = vr
                if vr.get("ok") and "#EXTM3U" in (vr.get("preview") or ""):
                    result["status"] = "ok_verified"
            except Exception as e:
                result["verify"] = {"ok": False, "error": str(e)}

        browser.close()
        return result


@app.get("/")
def root():
    return jsonify({"service": "manko-api", "status": "ok", "usage": "/manko?url=https://manko.fun/movie-info/...&verify=1"})


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "manko-api"})


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

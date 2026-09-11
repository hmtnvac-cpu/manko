from flask import jsonify, request
import json

MANIFEST = {
    "id": "community.manko.addon",
    "version": "1.0.0",
    "name": "Manko",
    "description": "Manko movie catalog for Nuvio/Stremio",
    "resources": ["catalog", "meta", "stream"],
    "types": ["movie"],
    "idPrefixes": ["movie_manko_"],
    "catalogs": [
        {
            "type": "movie",
            "id": "manko",
            "name": "🎬 MANKO",
            "extra": [
                {"name": "skip", "isRequired": False},
                {"name": "search", "isRequired": False}
            ]
        }
    ]
}


def clean_title(value):
    text = str(value or "Manko").strip()
    for suffix in [" - Watch Free in HD | Manko", " | Manko"]:
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    return text.strip() or "Manko"


def meta_of(item):
    return {
        "id": item.get("id"),
        "type": "movie",
        "name": clean_title(item.get("title")),
        "poster": item.get("poster") or None,
        "background": item.get("poster") or None,
        "posterShape": "poster",
        "description": "Manko" + (f" • {item.get('playerId')}" if item.get("playerId") else ""),
        "website": item.get("movieUrl") or None,
    }


def register_manko_addon(app, load_store):
    @app.get("/manifest.json")
    def manko_manifest():
        return jsonify(MANIFEST)

    @app.get("/catalog/movie/manko.json")
    @app.get("/catalog/movie/manko/<path:extra>.json")
    def manko_catalog(extra=None):
        store = load_store()
        items = list((store.get("movies") or {}).values())
        items.sort(key=lambda x: x.get("collectedAt") or "", reverse=True)
        params = {}
        if extra:
            try:
                params = json.loads(extra)
            except Exception:
                params = {}
        search = str(params.get("search") or request.args.get("search") or "").strip().lower()
        skip = params.get("skip", request.args.get("skip", 0))
        try:
            skip = max(0, int(skip or 0))
        except Exception:
            skip = 0
        if search:
            items = [x for x in items if search in f"{x.get('title','')} {x.get('playerId','')}".lower()]
        return jsonify({"metas": [meta_of(x) for x in items[skip:skip+40]]})

    @app.get("/meta/movie/<movie_id>.json")
    def manko_meta(movie_id):
        if not movie_id.startswith("movie_manko_"):
            return jsonify({"meta": None})
        item = (load_store().get("movies") or {}).get(movie_id)
        return jsonify({"meta": meta_of(item) if item else None})

    @app.get("/stream/movie/<movie_id>.json")
    def manko_stream(movie_id):
        if not movie_id.startswith("movie_manko_"):
            return jsonify({"streams": []})
        item = (load_store().get("movies") or {}).get(movie_id)
        if not item or not item.get("streamUrl"):
            return jsonify({"streams": []})
        headers = dict(item.get("headers") or {})
        headers.setdefault("Referer", "https://javplayer.cc/")
        stream = {
            "name": "Manko",
            "title": clean_title(item.get("title")),
            "url": item.get("streamUrl"),
            "behaviorHints": {
                "notWebReady": True,
                "proxyHeaders": {"request": headers}
            }
        }
        return jsonify({"streams": [stream]})

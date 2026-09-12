from flask import jsonify, request
import json
from urllib.parse import parse_qs, unquote_plus

MANIFEST = {
    "id": "community.film4k.addon",
    "version": "0.1.0",
    "name": "Film4K",
    "description": "Film4K catalog powered by the existing Manko collector and stream resolver.",
    "resources": ["catalog", "meta", "stream"],
    "types": ["movie"],
    "idPrefixes": ["film4k_"],
    "catalogs": [
        {
            "type": "movie",
            "id": "film4k_movies",
            "name": "🎬 FILM4K",
            "extra": [
                {"name": "skip", "isRequired": False},
                {"name": "search", "isRequired": False}
            ]
        }
    ]
}


def _extra(extra):
    out = {}
    if not extra:
        return out
    raw = unquote_plus(str(extra))
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    try:
        for k, v in parse_qs(raw, keep_blank_values=True).items():
            out[k] = v[-1] if v else ""
    except Exception:
        pass
    return out


def _is_film4k(item):
    if not isinstance(item, dict):
        return False
    meta = item.get("metadata") or {}
    if str(meta.get("source") or "").lower() == "film4k":
        return True
    url = str(item.get("movieUrl") or "").lower()
    return url.startswith("https://film4k.net/") or url.startswith("https://www.film4k.net/")


def _sid(item):
    raw = str(item.get("id") or "")
    if raw.startswith("movie_film4k_"):
        return raw.replace("movie_film4k_", "film4k_", 1)
    return "film4k_" + raw


def _store_id(sid):
    return str(sid or "").split(":", 1)[0].replace("film4k_", "movie_film4k_", 1)


def _name(item):
    meta = item.get("metadata") or {}
    return str(item.get("titleVi") or meta.get("titleVi") or item.get("title") or "Film4K").strip()


def _meta(item):
    if not item:
        return None
    meta = item.get("metadata") or {}
    desc = meta.get("descriptionVi") or meta.get("description") or ""
    out = {
        "id": _sid(item),
        "type": "movie",
        "name": _name(item),
        "poster": item.get("poster") or None,
        "background": item.get("poster") or None,
        "posterShape": "poster",
        "description": desc,
        "website": item.get("movieUrl") or None
    }
    genres = meta.get("genres") or []
    if isinstance(genres, list) and genres:
        out["genres"] = [str(x) for x in genres if x]
    if meta.get("year"):
        out["releaseInfo"] = str(meta.get("year"))
    return out


def _streams(item):
    if not item:
        return []
    src = item.get("streams") or []
    if not src and item.get("streamUrl"):
        src = [{"name": "#1", "url": item.get("streamUrl"), "headers": item.get("headers") or {}}]
    out = []
    for n, stream in enumerate(src, 1):
        url = str(stream.get("url") or "")
        if not url:
            continue
        headers = dict(stream.get("headers") or {})
        headers.setdefault("Referer", "https://javplayer.cc/")
        label = stream.get("name") or f"#{n}"
        out.append({
            "name": label,
            "title": f"{_name(item)} • {label}",
            "url": url,
            "behaviorHints": {
                "notWebReady": True,
                "proxyHeaders": {"request": headers}
            }
        })
    return out


def _items(store):
    movies = store.get("movies") or {}
    order = (store.get("catalog") or {}).get("urls") or []
    by_url = {x.get("movieUrl"): x for x in movies.values() if _is_film4k(x)}
    items = [by_url[u] for u in order if u in by_url]
    seen = {x.get("id") for x in items}
    items.extend(
        sorted(
            (x for x in movies.values() if _is_film4k(x) and x.get("id") not in seen),
            key=lambda x: x.get("collectedAt") or "",
            reverse=True
        )
    )
    return items


def register_film4k_addon(app, load_store):
    @app.get('/film4k/manifest.json')
    def film4k_manifest():
        return jsonify(MANIFEST)

    @app.get('/film4k/catalog/movie/film4k_movies.json')
    @app.get('/film4k/catalog/movie/film4k_movies/<path:extra>.json')
    def film4k_catalog(extra=None):
        params = _extra(extra)
        query = str(params.get('search') or request.args.get('search') or '').strip().lower()
        try:
            skip = max(0, int(params.get('skip') or request.args.get('skip') or 0))
        except Exception:
            skip = 0
        items = _items(load_store())
        if query:
            items = [x for x in items if query in (_name(x) + ' ' + str((x.get('metadata') or {}).get('description') or '')).lower()]
        return jsonify({'metas': [_meta(x) for x in items[skip:skip + 40]]})

    @app.get('/film4k/meta/movie/<sid>.json')
    def film4k_meta(sid):
        item = (load_store().get('movies') or {}).get(_store_id(sid))
        return jsonify({'meta': _meta(item) if item else None})

    @app.get('/film4k/stream/movie/<path:sid>.json')
    def film4k_stream(sid):
        item = (load_store().get('movies') or {}).get(_store_id(sid))
        return jsonify({'streams': _streams(item)})

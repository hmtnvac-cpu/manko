from flask import jsonify, request
import json, time
from urllib.parse import parse_qs, unquote_plus, urlparse
from urllib.request import Request, urlopen

BASE = "https://film4k.net"
_CACHE = {}
_CACHE_TTL = 120

MANIFEST = {
    "id": "community.film4k.addon",
    "version": "0.2.0",
    "name": "Film4K",
    "description": "Film4K.net addon with direct catalog, metadata, episodes and HLS resolving.",
    "resources": ["catalog", "meta", "stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["film4k_"],
    "catalogs": [
        {"type": "movie", "id": "film4k_movies", "name": "🎬 FILM4K • MOVIES", "extra": [{"name":"skip","isRequired":False},{"name":"search","isRequired":False}]},
        {"type": "series", "id": "film4k_series", "name": "📺 FILM4K • SERIES", "extra": [{"name":"skip","isRequired":False},{"name":"search","isRequired":False}]}
    ]
}


def _extra(extra):
    out = {}
    if not extra: return out
    raw = unquote_plus(str(extra))
    try:
        value = json.loads(raw)
        if isinstance(value, dict): return value
    except Exception: pass
    try:
        for k, v in parse_qs(raw, keep_blank_values=True).items(): out[k] = v[-1] if v else ""
    except Exception: pass
    return out


def _is_film4k(item):
    if not isinstance(item, dict): return False
    meta = item.get("metadata") or {}
    if str(meta.get("source") or "").lower() == "film4k": return True
    url = str(item.get("movieUrl") or "").lower()
    return url.startswith("https://film4k.net/") or url.startswith("https://www.film4k.net/")


def _sid(item):
    raw = str(item.get("id") or "")
    return raw.replace("movie_film4k_", "film4k_", 1) if raw.startswith("movie_film4k_") else "film4k_" + raw


def _store_id(sid):
    base = str(sid or "").split(":", 1)[0]
    return base.replace("film4k_", "movie_film4k_", 1)


def _slug(item):
    try:
        path = urlparse(str(item.get("movieUrl") or "")).path
        if "/watch/" in path: return path.split("/watch/",1)[1].strip("/")
    except Exception: pass
    return ""


def _json_http(url, method="GET", body=None):
    headers = {"User-Agent":"Mozilla/5.0", "Accept":"application/json", "Referer":BASE+"/", "Origin":BASE}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, bytearray)) else body
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _detail(slug):
    if not slug: return None
    cached = _CACHE.get(slug)
    if cached and time.time() - cached[0] < _CACHE_TTL: return cached[1]
    try:
        data = _json_http(f"{BASE}/api/watch/{slug}")
        _CACHE[slug] = (time.time(), data)
        return data
    except Exception:
        return None


def _media_type(detail):
    movie = (detail or {}).get("movie") or {}
    return "series" if str(movie.get("mediaType") or "").lower() in {"tv","series"} or len((detail or {}).get("episodes") or []) > 1 else "movie"


def _pick_title(movie):
    title = movie.get("title") or {}
    if isinstance(title, dict): return title.get("vi") or title.get("en") or "Film4K"
    return str(title or "Film4K")


def _poster(movie):
    p = movie.get("poster") or {}
    return (p.get("vi") or p.get("en") or "") if isinstance(p, dict) else str(p or "")


def _overview(movie):
    o = movie.get("overview") or {}
    return (o.get("vi") or o.get("en") or "") if isinstance(o, dict) else str(o or "")


def _absolute_source(url):
    u = str(url or "")
    return u if u.startswith(("http://","https://")) else BASE + (u if u.startswith("/") else "/"+u)


def _source_list(node):
    out=[]
    for src in (node or {}).get("sources") or []:
        u=_absolute_source(src.get("url"))
        if ".m3u8" in u.lower() or ".mpd" in u.lower() or ".mp4" in u.lower():
            out.append({"url":u,"label":src.get("label") or f"Server {len(out)+1}"})
    return out


def _meta_from_detail(item, detail):
    if not detail: return None
    movie = detail.get("movie") or {}
    typ = _media_type(detail)
    out = {
        "id": _sid(item), "type": typ, "name": _pick_title(movie),
        "poster": _poster(movie) or item.get("poster") or None,
        "background": movie.get("backdrop") or None, "posterShape":"poster",
        "description": _overview(movie), "website": item.get("movieUrl") or None
    }
    genres = movie.get("genres") or {}
    if isinstance(genres, dict): genres = genres.get("vi") or genres.get("en") or []
    if isinstance(genres, list) and genres: out["genres"] = genres
    if movie.get("year"): out["releaseInfo"] = str(movie.get("year"))
    if typ == "series":
        videos=[]
        for ep in detail.get("episodes") or []:
            season=int(ep.get("season") or 1); episode=int(ep.get("episode") or 1)
            videos.append({
                "id": f"{_sid(item)}:{season}:{episode}",
                "title": ep.get("title") or f"Tập {episode}",
                "season": season, "episode": episode,
                "released": (str(ep.get("airDate"))+"T00:00:00.000Z") if ep.get("airDate") else None,
                "thumbnail": ep.get("still") or None,
                "overview": ep.get("overview") or ""
            })
        out["videos"] = videos
    return out


def _resolve_streams(item, sid):
    detail = _detail(_slug(item))
    if not detail: return []
    parts=str(sid).split(":")
    node=detail
    if len(parts)>=3:
        try: season=int(parts[-2]); episode=int(parts[-1])
        except Exception: season=episode=0
        node=next((e for e in detail.get("episodes") or [] if int(e.get("season") or 1)==season and int(e.get("episode") or 1)==episode), {})
    elif _media_type(detail)=="series":
        node=(detail.get("episodes") or [{}])[0]
    sources=_source_list(node)
    if not sources and node is detail: sources=_source_list({"sources":detail.get("sources") or []})
    return [{
        "name": s["label"], "title": f"Film4K • {s['label']}", "url": s["url"],
        "behaviorHints":{"notWebReady":True,"proxyHeaders":{"request":{"Referer":BASE+"/","Origin":BASE}}}
    } for s in sources]


def _items(store):
    movies=store.get("movies") or {}; order=(store.get("catalog") or {}).get("urls") or []
    by_url={x.get("movieUrl"):x for x in movies.values() if _is_film4k(x)}
    items=[by_url[u] for u in order if u in by_url]; seen={x.get("id") for x in items}
    items.extend(sorted((x for x in movies.values() if _is_film4k(x) and x.get("id") not in seen), key=lambda x:x.get("collectedAt") or "", reverse=True))
    return items


def register_film4k_addon(app, load_store):
    @app.get('/film4k/manifest.json')
    def film4k_manifest(): return jsonify(MANIFEST)

    def catalog_for(typ, extra=None):
        params=_extra(extra); query=str(params.get('search') or request.args.get('search') or '').strip().lower()
        try: skip=max(0,int(params.get('skip') or request.args.get('skip') or 0))
        except Exception: skip=0
        metas=[]
        for item in _items(load_store()):
            detail=_detail(_slug(item)); meta=_meta_from_detail(item, detail)
            if not meta or meta.get("type")!=typ: continue
            hay=(meta.get("name","")+" "+meta.get("description","")).lower()
            if query and query not in hay: continue
            metas.append(meta)
        return jsonify({'metas':metas[skip:skip+40]})

    @app.get('/film4k/catalog/movie/film4k_movies.json')
    @app.get('/film4k/catalog/movie/film4k_movies/<path:extra>.json')
    def film4k_movies(extra=None): return catalog_for("movie", extra)

    @app.get('/film4k/catalog/series/film4k_series.json')
    @app.get('/film4k/catalog/series/film4k_series/<path:extra>.json')
    def film4k_series(extra=None): return catalog_for("series", extra)

    @app.get('/film4k/meta/<typ>/<sid>.json')
    def film4k_meta(typ, sid):
        item=(load_store().get('movies') or {}).get(_store_id(sid))
        return jsonify({'meta':_meta_from_detail(item,_detail(_slug(item))) if item else None})

    @app.get('/film4k/stream/<typ>/<path:sid>.json')
    def film4k_stream(typ, sid):
        item=(load_store().get('movies') or {}).get(_store_id(sid))
        return jsonify({'streams':_resolve_streams(item,sid) if item else []})

    @app.get('/film4k/resolve/<slug>.json')
    def film4k_resolve_debug(slug):
        detail=_detail(slug)
        if not detail: return jsonify({'ok':False,'error':'watch API failed'}),502
        return jsonify({'ok':True,'type':_media_type(detail),'movie':detail.get('movie') or {},'episodes':len(detail.get('episodes') or [])})

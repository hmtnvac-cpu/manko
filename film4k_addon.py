from flask import jsonify, request, Response
import json, time, base64, re, http.cookiejar
from urllib.parse import parse_qs, unquote_plus, urlparse, quote, unquote, urljoin
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor

BASE = "https://film4k.net"
_CACHE = {}
_CACHE_TTL = 90
CATALOG_CACHE_TTL = 180
SPORTS_CACHE_TTL = 20

MANIFEST = {
    "id": "community.film4k.addon",
    "version": "0.5.1",
    "name": "Film4K",
    "description": "Film4K.net addon with movies, series and live sports.",
    "resources": ["catalog", "meta", "stream"],
    "types": ["movie", "series"],
    "idPrefixes": ["film4k_"],
    "catalogs": [
        {"type": "movie", "id": "film4k_sports", "name": "🔴 FILM4K • LIVE SPORTS", "extra": [{"name":"skip","isRequired":False}]},
        {"type": "movie", "id": "film4k_movies", "name": "🎬 FILM4K • MOVIES", "extra": [{"name":"skip","isRequired":False},{"name":"search","isRequired":False}]},
        {"type": "series", "id": "film4k_series", "name": "📺 FILM4K • SERIES", "extra": [{"name":"skip","isRequired":False},{"name":"search","isRequired":False}]}
    ]
}


def _extra(extra):
    out={}
    if not extra:return out
    raw=unquote_plus(str(extra))
    try:
        value=json.loads(raw)
        if isinstance(value,dict):return value
    except Exception:pass
    try:
        for k,v in parse_qs(raw,keep_blank_values=True).items():out[k]=v[-1] if v else ""
    except Exception:pass
    return out


def _headers(extra=None):
    h={"User-Agent":"Mozilla/5.0","Accept":"*/*","Referer":BASE+"/sports","Origin":BASE}
    if extra:h.update(extra)
    return h


def _json_http(url,method="GET",body=None):
    headers=_headers({"Accept":"application/json"});data=None
    if body is not None:
        data=json.dumps(body).encode("utf-8") if not isinstance(body,(bytes,bytearray)) else body
        headers["Content-Type"]="application/json"
    req=Request(url,data=data,headers=headers,method=method)
    with urlopen(req,timeout=15) as r:return json.loads(r.read().decode("utf-8","replace"))


def _detail(slug,force=False):
    if not slug:return None
    key="detail:"+slug;cached=_CACHE.get(key)
    if not force and cached and time.time()-cached[0]<_CACHE_TTL:return cached[1]
    try:
        data=_json_http(f"{BASE}/api/watch/{slug}");_CACHE[key]=(time.time(),data);return data
    except Exception:return None


def _enc_slug(slug):return base64.urlsafe_b64encode(str(slug).encode()).decode().rstrip('=')
def _dec_slug(s):
    try:
        raw=str(s).split(':',1)[0]
        if raw.startswith('film4k_s_'):
            b=raw[len('film4k_s_'):];b+='='*((4-len(b)%4)%4);return base64.urlsafe_b64decode(b.encode()).decode()
    except Exception:pass
    return ''
def _sid_for_slug(slug):return 'film4k_s_'+_enc_slug(slug)
def _live_sid(event_id):return 'film4k_live_'+_enc_slug(event_id)
def _live_id(sid):
    try:
        raw=str(sid).split(':',1)[0]
        if not raw.startswith('film4k_live_'):return ''
        b=raw[len('film4k_live_'):];b+='='*((4-len(b)%4)%4);return base64.urlsafe_b64decode(b.encode()).decode()
    except Exception:return ''


def _pick_title(movie):
    title=movie.get("title") or movie.get("name") or {}
    if isinstance(title,dict):return title.get("vi") or title.get("en") or next(iter(title.values()),"Film4K")
    return str(title or "Film4K")
def _poster(movie):
    p=movie.get("poster") or movie.get("image") or {}
    return (p.get("vi") or p.get("en") or next(iter(p.values()),"")) if isinstance(p,dict) else str(p or "")
def _overview(movie):
    o=movie.get("overview") or movie.get("description") or {}
    return (o.get("vi") or o.get("en") or next(iter(o.values()),"")) if isinstance(o,dict) else str(o or "")
def _media_type_from_movie(movie):
    t=str(movie.get('mediaType') or movie.get('type') or '').lower();return 'series' if t in {'tv','series','show'} else 'movie'


def _walk_movies(obj,out):
    if isinstance(obj,dict):
        slug=obj.get('slug');title=obj.get('title') or obj.get('name')
        if isinstance(slug,str) and slug and title and slug not in out:out[slug]=obj
        for v in obj.values():_walk_movies(v,out)
    elif isinstance(obj,list):
        for v in obj:_walk_movies(v,out)


def _live_catalog():
    key='catalog:live';cached=_CACHE.get(key)
    if cached and time.time()-cached[0]<CATALOG_CACHE_TTL:return cached[1]
    found={}
    for path in ['/api/home','/api/explore','/api/movies','/api/series']:
        try:_walk_movies(_json_http(BASE+path),found)
        except Exception:pass
    items=list(found.values());_CACHE[key]=(time.time(),items);return items


def _catalog_meta(movie):
    slug=str(movie.get('slug') or '')
    if not slug:return None
    typ=_media_type_from_movie(movie)
    return {'id':_sid_for_slug(slug),'type':typ,'name':_pick_title(movie),'poster':_poster(movie) or None,'background':movie.get('backdrop') or None,'posterShape':'poster','description':_overview(movie),'releaseInfo':str(movie.get('year')) if movie.get('year') else None,'website':f'{BASE}/watch/{slug}'}


def _media_type(detail):
    movie=(detail or {}).get('movie') or {}
    return 'series' if str(movie.get('mediaType') or '').lower() in {'tv','series'} or len((detail or {}).get('episodes') or [])>1 else 'movie'
def _absolute_source(url):
    u=str(url or '');return u if u.startswith(('http://','https://')) else BASE+(u if u.startswith('/') else '/'+u)
def _source_list(node):
    out=[]
    for src in (node or {}).get('sources') or []:
        u=_absolute_source(src.get('url'))
        if any(x in u.lower() for x in ['.m3u8','.mpd','.mp4']):out.append({'url':u,'label':src.get('label') or f'Server {len(out)+1}'})
    return out


def _meta_from_slug(slug):
    detail=_detail(slug)
    if not detail:return None
    movie=detail.get('movie') or {};typ=_media_type(detail)
    out={'id':_sid_for_slug(slug),'type':typ,'name':_pick_title(movie),'poster':_poster(movie) or None,'background':movie.get('backdrop') or None,'posterShape':'poster','description':_overview(movie),'website':f'{BASE}/watch/{slug}'}
    genres=movie.get('genres') or {}
    if isinstance(genres,dict):genres=genres.get('vi') or genres.get('en') or []
    if isinstance(genres,list) and genres:out['genres']=genres
    if movie.get('year'):out['releaseInfo']=str(movie.get('year'))
    if typ=='series':
        videos=[]
        for ep in detail.get('episodes') or []:
            season=int(ep.get('season') or 1);episode=int(ep.get('episode') or 1)
            videos.append({'id':f'{_sid_for_slug(slug)}:{season}:{episode}','title':ep.get('title') or f'Tập {episode}','season':season,'episode':episode,'thumbnail':ep.get('still') or None,'overview':ep.get('overview') or ''})
        out['videos']=videos
    return out


def _resolve_sources(slug,sid):
    detail=_detail(slug,force=True)
    if not detail:return []
    parts=str(sid).split(':');node=detail
    if len(parts)>=3:
        try:season=int(parts[-2]);episode=int(parts[-1])
        except Exception:season=episode=0
        node=next((e for e in detail.get('episodes') or [] if int(e.get('season') or 1)==season and int(e.get('episode') or 1)==episode),{})
    elif _media_type(detail)=='series':node=(detail.get('episodes') or [{}])[0]
    sources=_source_list(node)
    if not sources and node is detail:sources=_source_list({'sources':detail.get('sources') or []})
    return sources


def _sports_name(x):
    for k in ['title','name','label','eventName','event_name']:
        v=x.get(k)
        if isinstance(v,str) and v.strip():return v.strip()
    home=x.get('home') or x.get('homeTeam') or x.get('home_team');away=x.get('away') or x.get('awayTeam') or x.get('away_team')
    def n(v):
        if isinstance(v,str):return v
        if isinstance(v,dict):return str(v.get('name') or v.get('title') or '')
        return ''
    hn,an=n(home),n(away);return (hn+' vs '+an).strip(' vs ') if hn or an else ''

def _sports_event_id(x):
    for k in ['slug','eventId','event_id','id','key']:
        v=x.get(k)
        if isinstance(v,(str,int)) and str(v).strip():return str(v).strip()
    return ''
def _walk_sports(obj,out):
    if isinstance(obj,dict):
        eid=_sports_event_id(obj);name=_sports_name(obj)
        if eid and name and eid not in out:out[eid]=obj
        for v in obj.values():_walk_sports(v,out)
    elif isinstance(obj,list):
        for v in obj:_walk_sports(v,out)
def _sports_home(force=False):
    key='sports:home';cached=_CACHE.get(key)
    if not force and cached and time.time()-cached[0]<SPORTS_CACHE_TTL:return cached[1]
    try:data=_json_http(BASE+'/api/sports/home')
    except Exception:data={}
    found={};_walk_sports(data,found);items=list(found.values());_CACHE[key]=(time.time(),items);return items

def _sports_find(eid):return next((x for x in _sports_home() if _sports_event_id(x)==eid),{})
def _sports_meta(x):
    eid=_sports_event_id(x);name=_sports_name(x)
    if not eid or not name:return None
    poster=x.get('poster') or x.get('image') or x.get('thumbnail') or ''
    league=x.get('league') or x.get('competition') or x.get('sport') or ''
    if isinstance(league,dict):league=league.get('name') or league.get('title') or ''
    return {'id':_live_sid(eid),'type':'movie','name':'🔴 '+name,'poster':poster or None,'posterShape':'landscape','description':str(league or 'Film4K Live Sports'),'website':BASE+'/sports'}
def _walk_urls(obj,out):
    if isinstance(obj,dict):
        for v in obj.values():_walk_urls(v,out)
    elif isinstance(obj,list):
        for v in obj:_walk_urls(v,out)
    elif isinstance(obj,str):
        low=obj.lower()
        if obj.startswith(('http://','https://','/')) and any(x in low for x in ['.m3u8','.mpd','.mp4','/api/tv/','/stream']):out.append(_absolute_source(obj))
def _sports_streams(eid):
    urls=[]
    try:_walk_urls(_json_http(BASE+'/api/sports/live/'+quote(eid,safe='')),urls)
    except Exception:pass
    event=_sports_find(eid);_walk_urls(event,urls)
    seen=set();return [u for u in urls if not (u in seen or seen.add(u))]


def _allowed_proxy_url(u):
    try:
        p=urlparse(u);h=(p.hostname or '').lower();return p.scheme=='https' and (h in {'film4k.net','www.film4k.net'} or h.endswith('.b-cdn.net') or h.endswith('.tv360.vn') or h=='tv360.vn')
    except Exception:return False
def _proxy_url(base_url,target):return base_url+'/film4k/hls?u='+quote(target,safe='')
def _rewrite_m3u8(text,source_url,base_url):
    out=[]
    for line in text.splitlines():
        s=line.strip()
        if not s:out.append(line);continue
        if s.startswith('#'):
            def repl(m):
                raw=m.group(1);absu=urljoin(source_url,raw);return 'URI="'+(_proxy_url(base_url,absu) if _allowed_proxy_url(absu) else absu)+'"'
            out.append(re.sub(r'URI="([^"]+)"',repl,line))
        else:
            absu=urljoin(source_url,s);out.append(_proxy_url(base_url,absu) if _allowed_proxy_url(absu) else absu)
    return '\n'.join(out)+'\n'
def _fetch_media(target):
    jar=http.cookiejar.CookieJar();opener=build_opener(HTTPCookieProcessor(jar));ticket=''
    try:
        req=Request(BASE+'/api/play-ticket',data=b'',headers=_headers({'Accept':'application/json','Content-Type':'application/json'}),method='POST')
        with opener.open(req,timeout=10) as r:ticket=str((json.loads(r.read().decode('utf-8','replace')) or {}).get('token') or '')
    except Exception:pass
    extra={}
    if request.headers.get('Range'):extra['Range']=request.headers.get('Range')
    if ticket:extra['X-Play-Ticket']=ticket;extra['X-Playback-Token']=ticket
    return opener.open(Request(target,headers=_headers(extra),method='GET'),timeout=20)


def register_film4k_addon(app,load_store):
    @app.get('/film4k/manifest.json')
    def film4k_manifest():return jsonify(MANIFEST)

    def catalog_for(typ,extra=None):
        params=_extra(extra);query=str(params.get('search') or request.args.get('search') or '').strip().lower()
        try:skip=max(0,int(params.get('skip') or request.args.get('skip') or 0))
        except Exception:skip=0
        metas=[]
        for movie in _live_catalog():
            meta=_catalog_meta(movie)
            if not meta or meta.get('type')!=typ:continue
            hay=(meta.get('name','')+' '+str(meta.get('description') or '')).lower()
            if query and query not in hay:continue
            metas.append(meta)
        return jsonify({'metas':metas[skip:skip+40]})

    @app.get('/film4k/catalog/movie/film4k_sports.json')
    @app.get('/film4k/catalog/movie/film4k_sports/<path:extra>.json')
    def film4k_sports(extra=None):
        params=_extra(extra)
        try:skip=max(0,int(params.get('skip') or request.args.get('skip') or 0))
        except Exception:skip=0
        metas=[m for m in (_sports_meta(x) for x in _sports_home(force=True)) if m]
        return jsonify({'metas':metas[skip:skip+60]})

    @app.get('/film4k/catalog/movie/film4k_movies.json')
    @app.get('/film4k/catalog/movie/film4k_movies/<path:extra>.json')
    def film4k_movies(extra=None):return catalog_for('movie',extra)
    @app.get('/film4k/catalog/series/film4k_series.json')
    @app.get('/film4k/catalog/series/film4k_series/<path:extra>.json')
    def film4k_series(extra=None):return catalog_for('series',extra)

    @app.get('/film4k/meta/<typ>/<sid>.json')
    def film4k_meta(typ,sid):
        eid=_live_id(sid)
        if eid:return jsonify({'meta':_sports_meta(_sports_find(eid))})
        slug=_dec_slug(sid);return jsonify({'meta':_meta_from_slug(slug) if slug else None})

    @app.get('/film4k/stream/<typ>/<path:sid>.json')
    def film4k_stream(typ,sid):
        base=request.host_url.rstrip('/');eid=_live_id(sid)
        if eid:
            streams=[]
            for i,target in enumerate(_sports_streams(eid),1):
                prox=_proxy_url(base,target) if _allowed_proxy_url(target) else target
                streams.append({'name':f'LIVE #{i}','title':f'Film4K Sports • LIVE #{i}','url':prox,'behaviorHints':{'notWebReady':True}})
            return jsonify({'streams':streams})
        slug=_dec_slug(sid);sources=_resolve_sources(slug,sid) if slug else [];streams=[]
        for s in sources:
            target=s['url'];prox=_proxy_url(base,target) if '.m3u8' in target.lower() and _allowed_proxy_url(target) else target
            streams.append({'name':s['label'],'title':f"Film4K • {s['label']}",'url':prox,'behaviorHints':{'notWebReady':True}})
        return jsonify({'streams':streams})

    @app.get('/film4k/hls')
    def film4k_hls_proxy():
        target=unquote(str(request.args.get('u') or ''))
        if not _allowed_proxy_url(target):return Response('blocked',status=403)
        try:
            upstream=_fetch_media(target);body=upstream.read();status=getattr(upstream,'status',200);ct=upstream.headers.get('Content-Type') or 'application/octet-stream'
            if '.m3u8' in target.lower() or 'mpegurl' in ct.lower():
                body=_rewrite_m3u8(body.decode('utf-8','replace'),target,request.host_url.rstrip('/')).encode('utf-8');ct='application/vnd.apple.mpegurl'
            resp=Response(body,status=status,content_type=ct)
            for k in ['Content-Range','Accept-Ranges']:
                v=upstream.headers.get(k)
                if v:resp.headers[k]=v
            resp.headers['Access-Control-Allow-Origin']='*';resp.headers['Cache-Control']='no-store';return resp
        except Exception as e:return Response('upstream error: '+str(e),status=502)

    @app.get('/film4k/resolve/<slug>.json')
    def film4k_resolve_debug(slug):
        detail=_detail(slug,force=True)
        if not detail:return jsonify({'ok':False,'error':'watch API failed'}),502
        return jsonify({'ok':True,'type':_media_type(detail),'movie':detail.get('movie') or {},'episodes':len(detail.get('episodes') or [])})

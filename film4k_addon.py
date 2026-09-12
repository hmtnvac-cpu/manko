from flask import jsonify, request, Response
import json, time, base64, re, http.cookiejar
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, unquote_plus, urlparse, quote, unquote, urljoin
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor

BASE='https://film4k.net'
VN_TZ=timezone(timedelta(hours=7))
_CACHE={}

MANIFEST={
  'id':'community.film4k.addon','version':'0.5.5','name':'Film4K',
  'description':'Film4K.net movies, series and sports',
  'resources':['catalog','meta','stream'],'types':['movie','series'],'idPrefixes':['film4k_'],
  'catalogs':[
    {'type':'movie','id':'film4k_sports','name':'🏟️ FILM4K • SPORTS','extra':[{'name':'skip','isRequired':False}]},
    {'type':'movie','id':'film4k_movies','name':'🎬 FILM4K • MOVIES','extra':[{'name':'skip','isRequired':False},{'name':'search','isRequired':False}]},
    {'type':'series','id':'film4k_series','name':'📺 FILM4K • SERIES','extra':[{'name':'skip','isRequired':False},{'name':'search','isRequired':False}]}
  ]
}

def _extra(extra):
    if not extra:return {}
    raw=unquote_plus(str(extra))
    try:
        x=json.loads(raw)
        if isinstance(x,dict):return x
    except:pass
    try:return {k:(v[-1] if v else '') for k,v in parse_qs(raw,keep_blank_values=True).items()}
    except:return {}

def _headers(referer='root',extra=None):
    ref=BASE+'/sports' if referer=='sports' else BASE+'/'
    h={'User-Agent':'Mozilla/5.0','Accept':'*/*','Referer':ref,'Origin':BASE}
    if extra:h.update(extra)
    return h

def _json_http(path,referer='root',method='GET',body=None):
    url=path if path.startswith('http') else BASE+path
    data=None; headers=_headers(referer,{'Accept':'application/json'})
    if body is not None:
        data=json.dumps(body).encode();headers['Content-Type']='application/json'
    req=Request(url,data=data,headers=headers,method=method)
    with urlopen(req,timeout=15) as r:return json.loads(r.read().decode('utf-8','replace'))

def _enc(s):return base64.urlsafe_b64encode(str(s).encode()).decode().rstrip('=')
def _dec(s,prefix):
    try:
        raw=str(s).split(':',1)[0]
        if not raw.startswith(prefix):return ''
        b=raw[len(prefix):];b+='='*((4-len(b)%4)%4)
        return base64.urlsafe_b64decode(b.encode()).decode()
    except:return ''
def _sid(slug):return 'film4k_s_'+_enc(slug)
def _slug(sid):return _dec(sid,'film4k_s_')
def _live_sid(slug):return 'film4k_live_'+_enc(slug)
def _live_slug(sid):return _dec(sid,'film4k_live_')

def _title(x):
    v=x.get('title') or x.get('name') or ''
    if isinstance(v,dict):return v.get('vi') or v.get('en') or next(iter(v.values()),'')
    return str(v or '')
def _poster(x):
    v=x.get('poster') or x.get('image') or x.get('thumbnail') or ''
    if isinstance(v,dict):return v.get('vi') or v.get('en') or next(iter(v.values()),'')
    return str(v or '')
def _desc(x):
    v=x.get('overview') or x.get('description') or ''
    if isinstance(v,dict):return v.get('vi') or v.get('en') or next(iter(v.values()),'')
    return str(v or '')
def _type(x):
    t=str(x.get('mediaType') or x.get('type') or '').lower()
    return 'series' if t in {'tv','series','show'} else 'movie'

def _walk_catalog(obj,out):
    if isinstance(obj,dict):
        slug=obj.get('slug');name=_title(obj)
        if isinstance(slug,str) and slug and name and slug not in out:out[slug]=obj
        for v in obj.values():_walk_catalog(v,out)
    elif isinstance(obj,list):
        for v in obj:_walk_catalog(v,out)

def _catalog_all():
    c=_CACHE.get('catalog')
    if c and time.time()-c[0]<120:return c[1]
    found={}
    for p in ['/api/home','/api/explore','/api/movies','/api/series']:
        try:_walk_catalog(_json_http(p,'root'),found)
        except:pass
    items=list(found.values());_CACHE['catalog']=(time.time(),items);return items

def _catalog_meta(x):
    slug=str(x.get('slug') or ''); name=_title(x)
    if not slug or not name:return None
    typ=_type(x)
    return {'id':_sid(slug),'type':typ,'name':name,'poster':_poster(x) or None,'posterShape':'poster','description':_desc(x),'releaseInfo':str(x.get('year')) if x.get('year') else None,'website':BASE+'/watch/'+slug}

def _store_fallback(store,typ):
    metas=[]
    for item in (store.get('movies') or {}).values():
        url=str(item.get('movieUrl') or '')
        m=re.search(r'/watch/([^/?#]+)',url)
        if not m:continue
        slug=m.group(1);name=item.get('title') or 'Film4K';poster=item.get('poster') or ''
        metas.append({'id':_sid(slug),'type':'movie','name':name,'poster':poster or None,'posterShape':'poster','description':((item.get('metadata') or {}).get('description') or ''),'website':url})
    return metas if typ=='movie' else []

def _detail(slug,force=False):
    key='detail:'+slug;c=_CACHE.get(key)
    if c and not force and time.time()-c[0]<60:return c[1]
    try:d=_json_http('/api/watch/'+quote(slug,safe=''),'root');_CACHE[key]=(time.time(),d);return d
    except:return None

def _meta_detail(slug):
    d=_detail(slug);movie=(d or {}).get('movie') or {}
    if not d:return None
    typ='series' if str(movie.get('mediaType') or '').lower() in {'tv','series'} or len(d.get('episodes') or [])>1 else 'movie'
    m={'id':_sid(slug),'type':typ,'name':_title(movie) or slug,'poster':_poster(movie) or None,'posterShape':'poster','description':_desc(movie),'website':BASE+'/watch/'+slug}
    if typ=='series':
        videos=[]
        for e in d.get('episodes') or []:
            s=int(e.get('season') or 1);ep=int(e.get('episode') or 1)
            videos.append({'id':f'{_sid(slug)}:{s}:{ep}','title':e.get('title') or f'Tập {ep}','season':s,'episode':ep,'thumbnail':e.get('still') or None,'overview':e.get('overview') or ''})
        m['videos']=videos
    return m

def _sources(slug,sid):
    d=_detail(slug,True)
    if not d:return []
    node=d;parts=str(sid).split(':')
    if len(parts)>=3:
        try:s=int(parts[-2]);ep=int(parts[-1])
        except:s=ep=0
        node=next((x for x in d.get('episodes') or [] if int(x.get('season') or 1)==s and int(x.get('episode') or 1)==ep),{})
    elif len(d.get('episodes') or [])>0:node=(d.get('episodes') or [{}])[0]
    srcs=(node or {}).get('sources') or []
    out=[]
    for src in srcs:
        u=str(src.get('url') or '')
        if u.startswith('/'):u=BASE+u
        if any(z in u.lower() for z in ['.m3u8','.mpd','.mp4']):out.append((u,src.get('label') or f'Server {len(out)+1}'))
    return out

# Sports follows Film4K /api/sports/home exactly: live[] + groups[].matches[]
def _sports_events():
    try:data=_json_http('/api/sports/home','sports')
    except:return []
    found={}
    for x in data.get('live') or []:
        if isinstance(x,dict) and x.get('slug'):found[str(x['slug'])]=x
    for g in data.get('groups') or []:
        for x in (g or {}).get('matches') or []:
            if isinstance(x,dict) and x.get('slug'):found[str(x['slug'])]=x
    return list(found.values())

def _sports_name(x):
    h=str(x.get('home') or '').strip();a=str(x.get('away') or '').strip()
    return h+' vs '+a if h and a else h or a or str(x.get('title') or x.get('slug') or '')
def _sports_state(x):
    ms=int(x.get('time') or 0)
    if x.get('live') is True:return '🔴 LIVE',0,ms
    if ms>int(time.time()*1000):return '🕒 SẮP DIỄN RA',1,ms
    return '⚫ ĐÃ KẾT THÚC',2,ms

def _sports_meta(x):
    slug=str(x.get('slug') or '');state,_,ms=_sports_state(x);name=_sports_name(x)
    if not slug or not name:return None
    clock=datetime.fromtimestamp(ms/1000,timezone.utc).astimezone(VN_TZ).strftime('%d/%m %H:%M') if ms else ''
    league=str(x.get('league') or '')
    poster=x.get('leagueFlag') or x.get('homeFlag') or x.get('awayFlag') or None
    return {'id':_live_sid(slug),'type':'movie','name':state+' • '+name,'poster':poster,'posterShape':'landscape','description':' • '.join(v for v in [league,clock] if v),'website':BASE+'/sports'}

def _walk_urls(obj,out):
    if isinstance(obj,dict):
        for v in obj.values():_walk_urls(v,out)
    elif isinstance(obj,list):
        for v in obj:_walk_urls(v,out)
    elif isinstance(obj,str):
        u=obj if obj.startswith('http') else BASE+obj if obj.startswith('/') else ''
        if u and any(z in u.lower() for z in ['.m3u8','.mpd','.mp4','/api/tv/']):out.append(u)

def _sports_streams(slug):
    urls=[]
    try:_walk_urls(_json_http('/api/sports/live/'+quote(slug,safe=''),'sports'),urls)
    except:pass
    seen=set();return [u for u in urls if not (u in seen or seen.add(u))]

def _allowed(u):
    try:
        p=urlparse(u);h=(p.hostname or '').lower()
        return p.scheme=='https' and (h in {'film4k.net','www.film4k.net'} or h.endswith('.b-cdn.net') or h.endswith('.tv360.vn') or h=='tv360.vn')
    except:return False

def _proxy(base,u):return base+'/film4k/hls?u='+quote(u,safe='')
def _rewrite(text,src,base):
    out=[]
    for line in text.splitlines():
        s=line.strip()
        if not s:out.append(line);continue
        if s.startswith('#'):
            def rp(m):
                a=urljoin(src,m.group(1));return 'URI="'+(_proxy(base,a) if _allowed(a) else a)+'"'
            out.append(re.sub(r'URI="([^"]+)"',rp,line))
        else:
            a=urljoin(src,s);out.append(_proxy(base,a) if _allowed(a) else a)
    return '\n'.join(out)+'\n'

def _fetch_media(target):
    jar=http.cookiejar.CookieJar();op=build_opener(HTTPCookieProcessor(jar));ticket=''
    try:
        req=Request(BASE+'/api/play-ticket',data=b'',headers=_headers('root',{'Accept':'application/json','Content-Type':'application/json'}),method='POST')
        with op.open(req,timeout=10) as r:ticket=str((json.loads(r.read().decode('utf-8','replace')) or {}).get('token') or '')
    except:pass
    ex={}
    if request.headers.get('Range'):ex['Range']=request.headers['Range']
    if ticket:ex['X-Play-Ticket']=ticket;ex['X-Playback-Token']=ticket
    return op.open(Request(target,headers=_headers('root',ex),method='GET'),timeout=20)

def register_film4k_addon(app,load_store):
    @app.get('/film4k/manifest.json')
    def manifest():return jsonify(MANIFEST)

    def cat(typ,extra=None):
        p=_extra(extra)
        try:skip=max(0,int(p.get('skip') or request.args.get('skip') or 0))
        except:skip=0
        q=str(p.get('search') or request.args.get('search') or '').lower().strip()
        metas=[m for m in (_catalog_meta(x) for x in _catalog_all()) if m and m['type']==typ]
        if not metas:metas=_store_fallback(load_store(),typ)
        if q:metas=[m for m in metas if q in (m.get('name','')+' '+m.get('description','')).lower()]
        return jsonify({'metas':metas[skip:skip+40]})

    @app.get('/film4k/catalog/movie/film4k_movies.json')
    @app.get('/film4k/catalog/movie/film4k_movies/<path:extra>.json')
    def movies(extra=None):return cat('movie',extra)

    @app.get('/film4k/catalog/series/film4k_series.json')
    @app.get('/film4k/catalog/series/film4k_series/<path:extra>.json')
    def series(extra=None):return cat('series',extra)

    @app.get('/film4k/catalog/movie/film4k_sports.json')
    @app.get('/film4k/catalog/movie/film4k_sports/<path:extra>.json')
    def sports(extra=None):
        p=_extra(extra)
        try:skip=max(0,int(p.get('skip') or request.args.get('skip') or 0))
        except:skip=0
        events=_sports_events();events.sort(key=lambda x:(_sports_state(x)[1],_sports_state(x)[2]))
        metas=[m for m in (_sports_meta(x) for x in events) if m]
        return jsonify({'metas':metas[skip:skip+100]})

    @app.get('/film4k/meta/<typ>/<sid>.json')
    def meta(typ,sid):
        ls=_live_slug(sid)
        if ls:
            x=next((e for e in _sports_events() if str(e.get('slug'))==ls),None)
            return jsonify({'meta':_sports_meta(x) if x else None})
        s=_slug(sid);return jsonify({'meta':_meta_detail(s) if s else None})

    @app.get('/film4k/stream/<typ>/<path:sid>.json')
    def stream(typ,sid):
        base=request.host_url.rstrip('/');ls=_live_slug(sid);streams=[]
        if ls:
            for i,u in enumerate(_sports_streams(ls),1):
                streams.append({'name':f'LIVE #{i}','title':f'Film4K Sports • LIVE #{i}','url':_proxy(base,u) if _allowed(u) else u,'behaviorHints':{'notWebReady':True}})
            return jsonify({'streams':streams})
        s=_slug(sid)
        for u,label in (_sources(s,sid) if s else []):
            streams.append({'name':label,'title':'Film4K • '+label,'url':_proxy(base,u) if '.m3u8' in u.lower() and _allowed(u) else u,'behaviorHints':{'notWebReady':True}})
        return jsonify({'streams':streams})

    @app.get('/film4k/sports/debug.json')
    def sports_debug():
        ev=_sports_events();return jsonify({'count':len(ev),'live':sum(1 for x in ev if x.get('live') is True),'upcoming':sum(1 for x in ev if _sports_state(x)[1]==1),'ended':sum(1 for x in ev if _sports_state(x)[1]==2)})

    @app.get('/film4k/hls')
    def hls():
        target=unquote(str(request.args.get('u') or ''))
        if not _allowed(target):return Response('blocked',403)
        try:
            up=_fetch_media(target);body=up.read();ct=up.headers.get('Content-Type') or 'application/octet-stream';status=getattr(up,'status',200)
            if '.m3u8' in target.lower() or 'mpegurl' in ct.lower():body=_rewrite(body.decode('utf-8','replace'),target,request.host_url.rstrip('/')).encode();ct='application/vnd.apple.mpegurl'
            r=Response(body,status=status,content_type=ct);r.headers['Access-Control-Allow-Origin']='*';r.headers['Cache-Control']='no-store'
            for k in ['Content-Range','Accept-Ranges']:
                if up.headers.get(k):r.headers[k]=up.headers[k]
            return r
        except Exception as e:return Response('upstream error: '+str(e),502)

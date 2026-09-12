from flask import jsonify, request, Response
import json, time, base64, re, http.cookiejar
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, unquote_plus, urlparse, quote, unquote, urljoin
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor

BASE='https://film4k.net'; VN_TZ=timezone(timedelta(hours=7)); _CACHE={}
MANIFEST={'id':'community.film4k.addon','version':'0.5.7','name':'Film4K','description':'Film4K.net movies, series and sports','resources':['catalog','meta','stream'],'types':['movie','series'],'idPrefixes':['film4k_'],'catalogs':[{'type':'movie','id':'film4k_test','name':'🧪 FILM4K • FURIE TEST','extra':[]},{'type':'movie','id':'film4k_sports','name':'🏟️ FILM4K • SPORTS','extra':[{'name':'skip','isRequired':False}]},{'type':'movie','id':'film4k_movies','name':'🎬 FILM4K • MOVIES','extra':[{'name':'skip','isRequired':False},{'name':'search','isRequired':False}]},{'type':'series','id':'film4k_series','name':'📺 FILM4K • SERIES','extra':[{'name':'skip','isRequired':False},{'name':'search','isRequired':False}]}]}

def _extra(x):
    if not x:return {}
    try:return json.loads(unquote_plus(str(x)))
    except:pass
    try:return {k:v[-1] for k,v in parse_qs(unquote_plus(str(x))).items()}
    except:return {}
def _headers(ref='root',extra=None):
    h={'User-Agent':'Mozilla/5.0','Accept':'*/*','Referer':BASE+('/sports' if ref=='sports' else '/'),'Origin':BASE}
    if extra:h.update(extra)
    return h
def _json(path,ref='root'):
    u=path if path.startswith('http') else BASE+path
    with urlopen(Request(u,headers=_headers(ref,{'Accept':'application/json'})),timeout=15) as r:return json.loads(r.read().decode('utf-8','replace'))
def _enc(s):return base64.urlsafe_b64encode(str(s).encode()).decode().rstrip('=')
def _dec(s,p):
    try:
        raw=str(s).split(':',1)[0]
        if not raw.startswith(p):return ''
        b=raw[len(p):];b+='='*((4-len(b)%4)%4);return base64.urlsafe_b64decode(b.encode()).decode()
    except:return ''
def _sid(s):return 'film4k_s_'+_enc(s)
def _live_sid(s):return 'film4k_live_'+_enc(s)
def _slug(s):return _dec(s,'film4k_s_')
def _live_slug(s):return _dec(s,'film4k_live_')
def _human(slug):return re.sub(r'-\d{4}$','',slug).replace('-',' ').strip().title()

def _store_watch_items(store):
    out={}
    urls=list((store.get('catalog') or {}).get('urls') or [])
    for p in (store.get('probes') or {}).values():
        u=str(p.get('pageUrl') or '')
        if '/watch/' in u:urls.append(u)
    for m in (store.get('movies') or {}).values():
        u=str(m.get('movieUrl') or '')
        if '/watch/' in u:urls.append(u)
    for u in urls:
        m=re.search(r'/watch/([^/?#]+)',u)
        if m:out[m.group(1)]=u
    return out

def _store_movie(store,slug):
    for m in (store.get('movies') or {}).values():
        if '/watch/'+slug in str(m.get('movieUrl') or ''):return m
    return {}

def _detail(slug,force=False):
    k='d:'+slug;c=_CACHE.get(k)
    if c and not force and time.time()-c[0]<60:return c[1]
    try:d=_json('/api/watch/'+quote(slug,safe=''));_CACHE[k]=(time.time(),d);return d
    except:return None

def _name_obj(v):
    if isinstance(v,dict):return v.get('vi') or v.get('en') or next(iter(v.values()),'')
    return str(v or '')
def _detail_meta(slug):
    d=_detail(slug); movie=(d or {}).get('movie') or {}
    if not d:return None
    name=_name_obj(movie.get('title') or movie.get('name')) or _human(slug)
    poster=_name_obj(movie.get('poster') or movie.get('image'))
    desc=_name_obj(movie.get('overview') or movie.get('description'))
    typ='series' if str(movie.get('mediaType') or movie.get('type') or '').lower() in {'tv','series','show'} or len(d.get('episodes') or [])>1 else 'movie'
    m={'id':_sid(slug),'type':typ,'name':name,'poster':poster or None,'posterShape':'poster','description':desc,'website':BASE+'/watch/'+slug}
    if typ=='series':
        vids=[]
        for e in d.get('episodes') or []:
            s=int(e.get('season') or 1);ep=int(e.get('episode') or 1)
            vids.append({'id':f'{_sid(slug)}:{s}:{ep}','title':e.get('title') or f'Tập {ep}','season':s,'episode':ep,'thumbnail':e.get('still') or None,'overview':e.get('overview') or ''})
        m['videos']=vids
    return m

def _store_meta(store,slug):
    item=_store_movie(store,slug); title=item.get('title') or _human(slug); poster=item.get('poster') or ''; desc=((item.get('metadata') or {}).get('description') or '')
    return {'id':_sid(slug),'type':'movie','name':title,'poster':poster or None,'posterShape':'poster','description':desc,'website':BASE+'/watch/'+slug}

def _sources(store,slug,sid):
    d=_detail(slug,True); out=[]
    if d:
        node=d;parts=str(sid).split(':')
        if len(parts)>=3:
            try:s=int(parts[-2]);ep=int(parts[-1])
            except:s=ep=0
            node=next((x for x in d.get('episodes') or [] if int(x.get('season') or 1)==s and int(x.get('episode') or 1)==ep),{})
        elif d.get('episodes'):node=(d.get('episodes') or [{}])[0]
        for src in (node or {}).get('sources') or []:
            u=str(src.get('url') or '')
            if u.startswith('/'):u=BASE+u
            if any(z in u.lower() for z in ['.m3u8','.mpd','.mp4']):out.append((u,src.get('label') or f'Server {len(out)+1}'))
    if not out:
        item=_store_movie(store,slug)
        for src in item.get('streams') or []:
            u=str(src.get('url') or '')
            if u:out.append((u,src.get('name') or f'Server {len(out)+1}'))
    seen=set();return [(u,l) for u,l in out if not (u in seen or seen.add(u))]

def _captured_sports_home(store):
    newest=None; newest_ts=''
    for p in (store.get('probes') or {}).values():
        for r in p.get('resources') or []:
            if str(r.get('url') or '').endswith('/api/sports/home') and r.get('responseBody'):
                ts=str(p.get('updatedAt') or '')
                if ts>=newest_ts:
                    try:newest=json.loads(r['responseBody']);newest_ts=ts
                    except:pass
    return newest

def _sports_data(store):
    try:d=_json('/api/sports/home','sports')
    except:d=None
    if not isinstance(d,dict) or len(d.get('live') or [])+sum(len((g or {}).get('matches') or []) for g in d.get('groups') or [])<5:
        d=_captured_sports_home(store) or d or {}
    return d

def _sports_events(store):
    d=_sports_data(store);found={}
    for x in d.get('live') or []:
        if isinstance(x,dict) and x.get('slug'):found[str(x['slug'])]=x
    for g in d.get('groups') or []:
        for x in (g or {}).get('matches') or []:
            if isinstance(x,dict) and x.get('slug'):found[str(x['slug'])]=x
    return list(found.values())
def _sports_name(x):
    h=str(x.get('home') or '').strip();a=str(x.get('away') or '').strip();return h+' vs '+a if h and a else h or a or str(x.get('title') or x.get('slug') or '')
def _sports_state(x):
    try:ms=int(x.get('time') or 0)
    except:ms=0
    if x.get('live') is True:return '🔴 LIVE',0,ms
    if ms>int(time.time()*1000):return '🕒 SẮP DIỄN RA',1,ms
    return '⚫ ĐÃ KẾT THÚC',2,ms
def _sports_meta(x):
    slug=str(x.get('slug') or '');state,_,ms=_sports_state(x);name=_sports_name(x)
    if not slug or not name:return None
    clock=datetime.fromtimestamp(ms/1000,timezone.utc).astimezone(VN_TZ).strftime('%d/%m %H:%M') if ms else ''
    return {'id':_live_sid(slug),'type':'movie','name':state+' • '+name,'poster':x.get('leagueFlag') or x.get('homeFlag') or x.get('awayFlag') or None,'posterShape':'landscape','description':' • '.join(v for v in [str(x.get('league') or ''),clock] if v),'website':BASE+'/sports'}
def _walk_urls(o,out):
    if isinstance(o,dict):
        for v in o.values():_walk_urls(v,out)
    elif isinstance(o,list):
        for v in o:_walk_urls(v,out)
    elif isinstance(o,str):
        u=o if o.startswith('http') else BASE+o if o.startswith('/') else ''
        if u and any(z in u.lower() for z in ['.m3u8','.mpd','.mp4','/api/tv/']):out.append(u)
def _sports_streams(slug):
    urls=[]
    try:_walk_urls(_json('/api/sports/live/'+quote(slug,safe=''),'sports'),urls)
    except:pass
    seen=set();return [u for u in urls if not (u in seen or seen.add(u))]

def _allowed(u):
    try:
        p=urlparse(u);h=(p.hostname or '').lower();return p.scheme=='https' and (h in {'film4k.net','www.film4k.net'} or h.endswith('.b-cdn.net') or h.endswith('.tv360.vn') or h=='tv360.vn')
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
        store=load_store();p=_extra(extra)
        try:skip=max(0,int(p.get('skip') or request.args.get('skip') or 0))
        except:skip=0
        q=str(p.get('search') or request.args.get('search') or '').lower().strip();metas=[]
        for slug in _store_watch_items(store):
            m=_detail_meta(slug) or _store_meta(store,slug)
            if m and m.get('type')==typ:metas.append(m)
        if q:metas=[m for m in metas if q in (m.get('name','')+' '+m.get('description','')).lower()]
        return jsonify({'metas':metas[skip:skip+40]})
    @app.get('/film4k/catalog/movie/film4k_test.json')
    def test_movie():
        m=_detail_meta('furie')
        if not m:m={'id':_sid('furie'),'type':'movie','name':'Furie','poster':None,'posterShape':'poster','description':'Film4K test movie','website':BASE+'/watch/furie'}
        else:m['type']='movie'
        return jsonify({'metas':[m]})
    @app.get('/film4k/catalog/movie/film4k_movies.json')
    @app.get('/film4k/catalog/movie/film4k_movies/<path:extra>.json')
    def movies(extra=None):return cat('movie',extra)
    @app.get('/film4k/catalog/series/film4k_series.json')
    @app.get('/film4k/catalog/series/film4k_series/<path:extra>.json')
    def series(extra=None):return cat('series',extra)
    @app.get('/film4k/catalog/movie/film4k_sports.json')
    @app.get('/film4k/catalog/movie/film4k_sports/<path:extra>.json')
    def sports(extra=None):
        store=load_store();p=_extra(extra)
        try:skip=max(0,int(p.get('skip') or request.args.get('skip') or 0))
        except:skip=0
        ev=_sports_events(store);ev.sort(key=lambda x:(_sports_state(x)[1],_sports_state(x)[2]));return jsonify({'metas':[m for m in (_sports_meta(x) for x in ev) if m][skip:skip+100]})
    @app.get('/film4k/meta/<typ>/<sid>.json')
    def meta(typ,sid):
        store=load_store();ls=_live_slug(sid)
        if ls:
            x=next((e for e in _sports_events(store) if str(e.get('slug'))==ls),None);return jsonify({'meta':_sports_meta(x) if x else None})
        s=_slug(sid);return jsonify({'meta':(_detail_meta(s) or _store_meta(store,s)) if s else None})
    @app.get('/film4k/stream/<typ>/<path:sid>.json')
    def stream(typ,sid):
        store=load_store();base=request.host_url.rstrip('/');ls=_live_slug(sid);streams=[]
        if ls:
            for i,u in enumerate(_sports_streams(ls),1):streams.append({'name':f'LIVE #{i}','title':f'Film4K Sports • LIVE #{i}','url':_proxy(base,u) if _allowed(u) else u,'behaviorHints':{'notWebReady':True}})
            return jsonify({'streams':streams})
        s=_slug(sid)
        for u,label in (_sources(store,s,sid) if s else []):streams.append({'name':label,'title':'Film4K • '+label,'url':_proxy(base,u) if '.m3u8' in u.lower() and _allowed(u) else u,'behaviorHints':{'notWebReady':True}})
        return jsonify({'streams':streams})
    @app.get('/film4k/sports/debug.json')
    def sports_debug():
        ev=_sports_events(load_store());return jsonify({'count':len(ev),'live':sum(1 for x in ev if x.get('live') is True),'upcoming':sum(1 for x in ev if _sports_state(x)[1]==1),'ended':sum(1 for x in ev if _sports_state(x)[1]==2)})
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

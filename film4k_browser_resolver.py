import json,time,re,threading,http.cookiejar
from urllib.parse import quote,urljoin
from urllib.request import Request,build_opener,HTTPCookieProcessor
from playwright.sync_api import sync_playwright

BASE='https://film4k.net'
_SESSIONS={}
_CACHE={}
_LOCK=threading.RLock()
TTL=180


def _clean():
    now=time.time()
    with _LOCK:
        for sid in [k for k,v in _SESSIONS.items() if now-v.get('ts',0)>TTL]:_SESSIONS.pop(sid,None)


def _walk(obj,out):
    if isinstance(obj,dict):
        for v in obj.values():_walk(v,out)
    elif isinstance(obj,list):
        for v in obj:_walk(v,out)
    elif isinstance(obj,str):
        u=obj if obj.startswith('http') else BASE+obj if obj.startswith('/') else ''
        if u and ('.m3u8' in u.lower() or '/api/tv/' in u.lower()):out.append(u)


def _event_name(home,slug):
    for x in home.get('live') or []:
        if str(x.get('slug') or '')==slug:return (str(x.get('home') or '')+' '+str(x.get('away') or '')).strip()
    for g in home.get('groups') or []:
        for x in (g or {}).get('matches') or []:
            if str(x.get('slug') or '')==slug:return (str(x.get('home') or '')+' '+str(x.get('away') or '')).strip()
    return ''


def _new_session(slug,cookies,ua,referer,kind='sports'):
    sid=re.sub(r'[^a-zA-Z0-9_-]','',slug)[-70:]+'-'+str(int(time.time()*1000))
    with _LOCK:_SESSIONS[sid]={'cookies':cookies,'userAgent':ua,'ts':time.time(),'slug':slug,'referer':referer,'kind':kind}
    return sid


def resolve(slug,force=False):
    _clean();key='resolve:'+slug
    c=_CACHE.get(key)
    if c and not force and time.time()-c.get('ts',0)<30:return c
    seen=[];statuses=[];info={'slug':slug,'streams':[],'liveBody':None,'click':False,'requests':statuses,'error':None}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            ctx=browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',extra_http_headers={'Referer':BASE+'/sports','Origin':BASE})
            page=ctx.new_page()
            def on_response(resp):
                try:
                    u=resp.url
                    if '/api/sports/live/' in u or '/api/tv/' in u or '.m3u8' in u.lower():
                        statuses.append({'url':u,'status':resp.status})
                        if '.m3u8' in u.lower() and resp.status<400 and u not in seen:seen.append(u)
                except:pass
            page.on('response',on_response)
            page.goto(BASE+'/sports',wait_until='domcontentloaded',timeout=30000)
            page.wait_for_timeout(1800)
            home=page.evaluate("async()=>{try{return await (await fetch('/api/sports/home',{credentials:'include'})).json()}catch(e){return {}}}") or {}
            name=_event_name(home,slug)
            live=page.evaluate("async (s)=>{try{let r=await fetch('/api/sports/live/'+encodeURIComponent(s),{credentials:'include',headers:{Accept:'application/json'}});let t=await r.text();let j=null;try{j=JSON.parse(t)}catch(e){};return {status:r.status,text:t,json:j}}catch(e){return {status:0,text:String(e),json:null}}}",slug)
            info['liveBody']={'status':live.get('status'),'text':(live.get('text') or '')[:12000]}
            urls=[];_walk(live.get('json'),urls)
            for u in urls:
                if '.m3u8' in u.lower() and u not in seen:seen.append(u)
            if not seen:
                clicked=False;tokens=[]
                if name:tokens=[name,name.split(' vs ')[0].strip(),name.split(' - ')[0].strip()]
                for token in tokens:
                    if not token:continue
                    try:
                        loc=page.get_by_text(token,exact=False).first
                        if loc.count()>0:loc.click(timeout=4000);clicked=True;break
                    except:pass
                if not clicked:
                    try:clicked=bool(page.evaluate("(s)=>{let es=[...document.querySelectorAll('*')];let e=es.find(x=>(x.getAttribute('data-slug')||'')===s||(x.getAttribute('href')||'').includes(s)||x.outerHTML.includes(s));if(e){(e.closest('a,button,[role=button]')||e).click();return true}return false}",slug))
                    except:pass
                info['click']=clicked;page.wait_for_timeout(7000)
            try:
                perf=page.evaluate("()=>performance.getEntriesByType('resource').map(x=>x.name).filter(x=>x.includes('.m3u8')||x.includes('/api/tv/'))") or []
                for u in perf:
                    if '.m3u8' in u.lower() and u not in seen:seen.append(u)
            except:pass
            cookies=ctx.cookies();ua=page.evaluate("()=>navigator.userAgent");browser.close()
        sid=_new_session(slug,cookies,ua,BASE+'/sports','sports')
        info['session']=sid;info['streams']=seen;info['ts']=time.time();_CACHE[key]=info;return info
    except Exception as e:
        info['error']=str(e);info['ts']=time.time();_CACHE[key]=info;return info


def resolve_vod(slug,season=None,episode=None,force=False):
    """Open the real Film4K watch page and wait for the player to reach a WORKING HLS master.
    Film4K can emit an initial master.m3u8 that returns 403, then retry a different token that returns 200.
    Only successful HLS responses are returned to the addon.
    """
    _clean();key='vod:'+slug+':'+str(season or '')+':'+str(episode or '')
    c=_CACHE.get(key)
    if c and not force and time.time()-c.get('ts',0)<30:return c
    good=[];statuses=[];info={'slug':slug,'streams':[],'requests':statuses,'error':None,'workingMaster':None}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required'])
            ctx=browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',extra_http_headers={'Referer':BASE+'/','Origin':BASE})
            page=ctx.new_page()
            def on_response(resp):
                try:
                    u=resp.url;low=u.lower()
                    if '/api/watch/' in low or '/api/play-ticket' in low or '.m3u8' in low:
                        statuses.append({'url':u,'status':resp.status})
                    if '.m3u8' in low and resp.status<400 and u not in good:good.append(u)
                    if '/master.m3u8' in low and resp.status<400:info['workingMaster']=u
                except:pass
            page.on('response',on_response)
            page.goto(BASE+'/watch/'+quote(slug,safe=''),wait_until='domcontentloaded',timeout=30000)
            page.wait_for_timeout(1500)
            # Series: try selecting the requested episode if the page exposes episode controls.
            if episode:
                for token in [f'Tập {episode}',f'Episode {episode}',str(episode)]:
                    try:
                        loc=page.get_by_text(token,exact=False).first
                        if loc.count()>0:
                            loc.click(timeout=2500);page.wait_for_timeout(800);break
                    except:pass
            # Trigger playback when a play control is present; otherwise Film4K often autoloads HLS itself.
            for sel in ['button[aria-label*=Play i]','button:has-text("Play")','video']:
                try:
                    loc=page.locator(sel).first
                    if loc.count()>0:
                        if sel=='video':page.evaluate("()=>{let v=document.querySelector('video');if(v){v.muted=true;v.play().catch(()=>{})}}")
                        else:loc.click(timeout=2000)
                        break
                except:pass
            # Critical behavior observed on Film4K: first HLS may 403, then a new token succeeds ~3s later.
            deadline=time.time()+12
            while time.time()<deadline and not info.get('workingMaster'):
                page.wait_for_timeout(500)
            # Give child video/audio playlists time to appear after the working master.
            if info.get('workingMaster'):page.wait_for_timeout(1800)
            try:
                perf=page.evaluate("()=>performance.getEntriesByType('resource').map(x=>x.name).filter(x=>x.includes('.m3u8'))") or []
                successful={x['url'] for x in statuses if x.get('status',999)<400}
                for u in perf:
                    if u in successful and u not in good:good.append(u)
            except:pass
            cookies=ctx.cookies();ua=page.evaluate("()=>navigator.userAgent");browser.close()
        # Prefer a confirmed 200 master. Do not return stale/403 masters.
        masters=[u for u in good if '/master.m3u8' in u.lower()]
        streams=masters[:1] if masters else [u for u in good if '.m3u8' in u.lower()][:1]
        sid=_new_session(slug,cookies,ua,BASE+'/','vod')
        info['session']=sid;info['streams']=streams;info['allGood']=good;info['ts']=time.time();_CACHE[key]=info;return info
    except Exception as e:
        info['error']=str(e);info['ts']=time.time();_CACHE[key]=info;return info


def _opener_for(s):
    jar=http.cookiejar.CookieJar()
    for c in s.get('cookies') or []:
        try:
            domain=c.get('domain') or '.film4k.net';path=c.get('path') or '/';secure=bool(c.get('secure'))
            ck=http.cookiejar.Cookie(version=0,name=c['name'],value=c['value'],port=None,port_specified=False,domain=domain,domain_specified=True,domain_initial_dot=domain.startswith('.'),path=path,path_specified=True,secure=secure,expires=int(c['expires']) if c.get('expires') and c.get('expires')>0 else None,discard=not bool(c.get('expires') and c.get('expires')>0),comment=None,comment_url=None,rest={},rfc2109=False)
            jar.set_cookie(ck)
        except:pass
    return build_opener(HTTPCookieProcessor(jar))


def fetch(session_id,url,range_header=None):
    _clean()
    with _LOCK:s=_SESSIONS.get(session_id)
    if not s:raise RuntimeError('Film4K browser session expired')
    s['ts']=time.time();headers={'User-Agent':s.get('userAgent') or 'Mozilla/5.0','Referer':s.get('referer') or BASE+'/','Origin':BASE,'Accept':'*/*'}
    if range_header:headers['Range']=range_header
    op=_opener_for(s)
    with op.open(Request(url,headers=headers,method='GET'),timeout=30) as r:return getattr(r,'status',200),{str(k).lower():v for k,v in r.headers.items()},r.read()


def rewrite_playlist(text,source_url,base_proxy,session_id):
    out=[]
    for line in text.splitlines():
        s=line.strip()
        if not s:out.append(line);continue
        if s.startswith('#'):
            def repl(m):
                u=urljoin(source_url,m.group(1));return 'URI="'+base_proxy+'?sid='+quote(session_id,safe='')+'&u='+quote(u,safe='')+'"'
            out.append(re.sub(r'URI="([^"]+)"',repl,line))
        else:
            u=urljoin(source_url,s);out.append(base_proxy+'?sid='+quote(session_id,safe='')+'&u='+quote(u,safe=''))
    return '\n'.join(out)+'\n'

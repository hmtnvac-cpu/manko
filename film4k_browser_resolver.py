import json,time,re,threading,http.cookiejar
from urllib.parse import quote,urljoin,urlparse
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

def resolve(slug,force=False):
    _clean();key='resolve:'+slug
    c=_CACHE.get(key)
    if c and not force and time.time()-c.get('ts',0)<30:return c
    seen=[];statuses=[];info={'slug':slug,'streams':[],'liveBody':None,'click':False,'requests':statuses,'error':None}
    try:
        # Important: Playwright sync objects are created and destroyed in this SAME request thread.
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            ctx=browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36',extra_http_headers={'Referer':BASE+'/sports','Origin':BASE})
            page=ctx.new_page()
            def on_response(resp):
                try:
                    u=resp.url
                    if '/api/sports/live/' in u or '/api/tv/' in u or '.m3u8' in u.lower():
                        statuses.append({'url':u,'status':resp.status})
                        if '.m3u8' in u.lower() and u not in seen:seen.append(u)
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
                clicked=False
                tokens=[]
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
            cookies=ctx.cookies()
            ua=page.evaluate("()=>navigator.userAgent")
            browser.close()
        sid=re.sub(r'[^a-zA-Z0-9_-]','',slug)[-70:]+'-'+str(int(time.time()*1000))
        with _LOCK:_SESSIONS[sid]={'cookies':cookies,'userAgent':ua,'ts':time.time(),'slug':slug}
        info['session']=sid;info['streams']=seen;info['ts']=time.time();_CACHE[key]=info;return info
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
    if not s:raise RuntimeError('sports session expired')
    s['ts']=time.time();headers={'User-Agent':s.get('userAgent') or 'Mozilla/5.0','Referer':BASE+'/sports','Origin':BASE,'Accept':'*/*'}
    if range_header:headers['Range']=range_header
    op=_opener_for(s)
    with op.open(Request(url,headers=headers,method='GET'),timeout=30) as r:return getattr(r,'status',200),dict(r.headers.items()),r.read()

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

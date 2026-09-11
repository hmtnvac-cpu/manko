from flask import Flask,jsonify,request
from datetime import datetime,timezone,timedelta
from threading import RLock
from urllib.parse import urlparse,parse_qsl,urlencode,urlunparse
from urllib.request import Request,urlopen
import hashlib,json,os,re
import psycopg

app=Flask(__name__)
REFERER='https://javplayer.cc/'
DB_URL=os.environ.get('DATABASE_URL','').strip()
LOCK=RLock()
MAX_RETRIES=3
LEASE_SECONDS=120

def utcnow(): return datetime.now(timezone.utc).isoformat()
def blank_state():
    return {'movies':{},'errors':{},'catalog':{'total':0,'urls':[],'updatedAt':None},'runner':{'movieTasks':{},'movieOrder':[],'discoveryPending':['https://manko.fun/home'],'discoveryLeases':{},'discoveryVisited':[],'families':{},'startedAt':None}}

def normalize_state(d):
    if not isinstance(d,dict): d=blank_state()
    b=blank_state()
    for k,v in b.items(): d.setdefault(k,v)
    r=d.setdefault('runner',{})
    for k,v in b['runner'].items(): r.setdefault(k,v)
    d.setdefault('movies',{});d.setdefault('errors',{});d.setdefault('catalog',b['catalog'])
    return d

def db_init():
    if not DB_URL: return
    with psycopg.connect(DB_URL) as c:
        with c.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS app_state (id text PRIMARY KEY, data jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        c.commit()

def db_load():
    if not DB_URL: return blank_state()
    try:
        with psycopg.connect(DB_URL) as c:
            with c.cursor() as cur:
                cur.execute("SELECT data FROM app_state WHERE id='manko_store'")
                row=cur.fetchone()
                return normalize_state(row[0] if row else blank_state())
    except Exception:
        return blank_state()

def db_save(s):
    if not DB_URL: return False
    payload=json.dumps(s,ensure_ascii=False)
    with psycopg.connect(DB_URL) as c:
        with c.cursor() as cur:
            cur.execute("INSERT INTO app_state(id,data,updated_at) VALUES('manko_store',%s::jsonb,now()) ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data,updated_at=now()",(payload,))
        c.commit()
    return True

try: db_init()
except Exception: pass
STATE=db_load()

def load_store():
    with LOCK: return json.loads(json.dumps(STATE,ensure_ascii=False))
def commit_state():
    db_save(STATE)

def movie_key(p):
    u=str(p.get('movieUrl') or '');return 'movie_manko_'+hashlib.sha1(u.encode()).hexdigest()[:16]
def task_id(url): return hashlib.sha1(str(url).encode()).hexdigest()[:20]
def is_movie_url(u): return str(u or '').startswith('https://manko.fun/movie-info/')
def is_list_url(u):
    try:
        x=urlparse(str(u));return x.scheme=='https' and x.netloc=='manko.fun' and (x.path=='/home' or 'movie-list' in x.path or 'cate-list' in x.path)
    except: return False
def family_key(u):
    try:
        x=urlparse(u);q=[(k,v) for k,v in parse_qsl(x.query,keep_blank_values=True) if k!='page'];q.sort();return urlunparse((x.scheme,x.netloc,x.path,'',urlencode(q),'')).rstrip('?')
    except:return str(u)
def page1(u):
    try:
        x=urlparse(u)
        if x.path=='/home':return 'https://manko.fun/home'
        q=dict(parse_qsl(x.query,keep_blank_values=True));q['page']='1';return urlunparse((x.scheme,x.netloc,x.path,'',urlencode(q),'')).rstrip('?')
    except:return u
def next_page(u):
    try:
        x=urlparse(u)
        if x.path=='/home':return None
        q=dict(parse_qsl(x.query,keep_blank_values=True));q['page']=str(max(1,int(q.get('page','1') or 1))+1);return urlunparse((x.scheme,x.netloc,x.path,'',urlencode(q),'')).rstrip('?')
    except:return None

def translate_vi(text):
    text=str(text or '').strip()
    if not text:return ''
    try:
        q=urlencode({'client':'gtx','sl':'auto','tl':'vi','dt':'t','q':text[:4500]})
        req=Request('https://translate.googleapis.com/translate_a/single?'+q,headers={'User-Agent':'Mozilla/5.0'})
        with urlopen(req,timeout=10) as r:j=json.loads(r.read().decode('utf-8'))
        out=''.join((x[0] or '') for x in (j[0] or []) if x)
        return out.strip() or text
    except:return text

def ensure_task(url):
    if not is_movie_url(url):return None
    r=STATE['runner'];tid=task_id(url)
    if tid not in r['movieTasks']:
        r['movieTasks'][tid]={'id':tid,'movieUrl':url,'status':'queued','attempts':0,'leaseUntil':None,'updatedAt':utcnow()};r['movieOrder'].append(tid)
    return r['movieTasks'][tid]

def reset_expired():
    r=STATE['runner'];now=datetime.now(timezone.utc)
    for t in r['movieTasks'].values():
        if t.get('status')=='leased' and t.get('leaseUntil'):
            try:
                if datetime.fromisoformat(t['leaseUntil'])<now:t['status']='queued';t['leaseUntil']=None
            except:t['status']='queued';t['leaseUntil']=None
    for u,until in list(r['discoveryLeases'].items()):
        try:
            expired=datetime.fromisoformat(until)<now
        except:expired=True
        if expired:
            r['discoveryLeases'].pop(u,None)
            if u not in r['discoveryVisited'] and u not in r['discoveryPending']:r['discoveryPending'].insert(0,u)

def sanitize_result(p):
    streams=[]
    raw_streams=p.get('streams') or []
    if not raw_streams and p.get('streamUrl'): raw_streams=[{'url':p.get('streamUrl'),'vttUrl':p.get('vttUrl'),'headers':p.get('headers'),'playerId':p.get('playerId'),'playerUrl':p.get('playerUrl')}]
    for n,s in enumerate(raw_streams,1):
        if not isinstance(s,dict) or not str(s.get('url') or '').startswith(('http://','https://')):continue
        h=dict(s.get('headers') or {});h.setdefault('Referer',REFERER)
        streams.append({'name':s.get('name') or f'#{n}','url':s['url'],'vttUrl':s.get('vttUrl'),'headers':h,'playerId':s.get('playerId'),'playerUrl':s.get('playerUrl')})
    meta=dict(p.get('metadata') or {}) if isinstance(p.get('metadata'),dict) else {}
    meta.pop('subtitleVi',None)
    if meta.get('description') and not meta.get('descriptionVi'): meta['descriptionVi']=translate_vi(meta['description'])
    title=str(p.get('title') or 'Manko').strip()
    titleVi=str(p.get('titleVi') or meta.get('titleVi') or '').strip()
    if title and not titleVi:titleVi=translate_vi(re.sub(r'\s*-\s*Watch Free in HD\s*\|\s*Manko\s*$','',title,flags=re.I))
    return {'id':movie_key(p),'title':title,'titleVi':titleVi,'movieUrl':str(p.get('movieUrl') or ''),'poster':str(p.get('poster') or ''),'playerId':str(p.get('playerId') or (streams[0].get('playerId') if streams else '') or ''),'playerUrl':str(p.get('playerUrl') or (streams[0].get('playerUrl') if streams else '') or ''),'streamUrl':streams[0]['url'] if streams else '','streams':streams,'subtitleVi':'','metadata':meta,'headers':streams[0].get('headers') if streams else {'Referer':REFERER},'collectedAt':str(p.get('collectedAt') or utcnow()),'updatedAt':utcnow()}

@app.get('/')
def root():return jsonify({'service':'manko-api','status':'ok','runner':'/runner/status','store':'neon' if DB_URL else 'memory'})
@app.get('/health')
def health():return jsonify({'ok':True,'service':'manko-api','database':bool(DB_URL)})

@app.post('/runner/start')
def runner_start():
    with LOCK:
        r=STATE['runner'];r['startedAt']=utcnow();r['discoveryPending']=['https://manko.fun/home'];r['discoveryLeases']={};r['discoveryVisited']=[];r['families']={}
        for t in r['movieTasks'].values():
            if t.get('status')!='done':t['status']='queued';t['leaseUntil']=None
        commit_state()
        return jsonify({'ok':True,'mode':'server-driven','workers':2,'store':'neon' if DB_URL else 'memory'})

@app.get('/runner/next')
def runner_next():
    with LOCK:
        reset_expired();r=STATE['runner'];done_urls={m.get('movieUrl') for m in STATE['movies'].values()};chosen=None
        for tid in r['movieOrder']:
            t=r['movieTasks'].get(tid)
            if not t:continue
            if t['movieUrl'] in done_urls:t['status']='done';continue
            if t.get('status')=='queued' and int(t.get('attempts') or 0)<MAX_RETRIES:
                t['status']='leased';t['leaseUntil']=(datetime.now(timezone.utc)+timedelta(seconds=LEASE_SECONDS)).isoformat();t['updatedAt']=utcnow();chosen=dict(t);break
        commit_state();return jsonify({'ok':True,'task':chosen,'queued':sum(1 for t in r['movieTasks'].values() if t.get('status')=='queued')})

@app.post('/runner/result')
def runner_result():
    p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '')
    if not is_movie_url(url):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
    page=p.get('page') if isinstance(p.get('page'),dict) else {};st=p.get('stream') if isinstance(p.get('stream'),dict) else {}
    if not p.get('ok') or not str(st.get('url') or '').startswith(('http://','https://')):return jsonify({'ok':False,'error':'no valid stream'}),400
    raw={'movieUrl':url,'title':page.get('title') or 'Manko','poster':page.get('poster') or '','metadata':page.get('metadata') or {},'playerId':st.get('playerId'),'playerUrl':st.get('playerUrl'),'streams':[{'name':'#1','url':st.get('url'),'vttUrl':st.get('vttUrl'),'headers':st.get('headers') or {'Referer':REFERER},'playerId':st.get('playerId'),'playerUrl':st.get('playerUrl')}],'collectedAt':utcnow()}
    item=sanitize_result(raw)
    with LOCK:
        STATE['movies'][item['id']]=item
        t=ensure_task(url);t['status']='done';t['leaseUntil']=None;t['updatedAt']=utcnow()
        cat=STATE['catalog'];urls=cat.setdefault('urls',[])
        if url not in urls:urls.append(url)
        cat['total']=len(urls);cat['updatedAt']=utcnow()
        commit_state()
        return jsonify({'ok':True,'id':item['id'],'stored':len(STATE['movies']),'catalogTotal':cat['total'],'visibleInAddon':True})

@app.post('/runner/fail')
def runner_fail():
    p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '');err=str(p.get('error') or 'runner failed')
    with LOCK:
        t=STATE['runner']['movieTasks'].get(str(p.get('taskId') or '')) or STATE['runner']['movieTasks'].get(task_id(url))
        if t:
            t['attempts']=int(t.get('attempts') or 0)+1;t['leaseUntil']=None;t['lastError']=err;t['updatedAt']=utcnow();t['status']='queued' if t['attempts']<MAX_RETRIES else 'failed'
            if t['status']=='failed':STATE['errors'][task_id(url)]={'movieUrl':url,'error':err,'retries':t['attempts'],'updatedAt':utcnow()}
        commit_state();return jsonify({'ok':True,'retry':bool(t and t['status']=='queued'),'attempts':t.get('attempts') if t else None})

@app.get('/runner/discovery/next')
def discovery_next():
    with LOCK:
        reset_expired();r=STATE['runner'];chosen=None
        while r['discoveryPending']:
            u=r['discoveryPending'].pop(0)
            if u in r['discoveryVisited'] or u in r['discoveryLeases']:continue
            chosen=u;r['discoveryLeases'][u]=(datetime.now(timezone.utc)+timedelta(seconds=LEASE_SECONDS)).isoformat();break
        commit_state();return jsonify({'ok':True,'task':{'url':chosen,'id':task_id(chosen)} if chosen else None})

@app.post('/runner/discovery/result')
def discovery_result():
    p=request.get_json(silent=True) or {};url=str(p.get('url') or '');movies=list(dict.fromkeys(x for x in (p.get('movies') or []) if is_movie_url(x)));lists=list(dict.fromkeys(x for x in (p.get('lists') or []) if is_list_url(x)))
    if not is_list_url(url):return jsonify({'ok':False,'error':'invalid list url'}),400
    sig=hashlib.sha1('|'.join(movies).encode()).hexdigest() if movies else ''
    with LOCK:
        r=STATE['runner'];r['discoveryLeases'].pop(url,None)
        if url not in r['discoveryVisited']:r['discoveryVisited'].append(url)
        fam=family_key(url);f=r['families'].setdefault(fam,{'signatures':[],'done':False});repeated=bool(sig and sig in f['signatures'])
        if sig and not repeated:f['signatures'].append(sig)
        for m in movies:ensure_task(m)
        cat=STATE['catalog'];urls=cat.setdefault('urls',[]);seen=set(urls)
        for m in movies:
            if m not in seen:urls.append(m);seen.add(m)
        cat['total']=len(urls);cat['pageUrl']=url;cat['updatedAt']=utcnow()
        if url=='https://manko.fun/home' or urlparse(url).path=='/home':
            for li in lists:
                st=page1(li)
                if st not in r['discoveryVisited'] and st not in r['discoveryPending']:r['discoveryPending'].append(st)
        elif movies and not repeated:
            nx=next_page(url)
            if nx and nx not in r['discoveryVisited'] and nx not in r['discoveryPending']:r['discoveryPending'].insert(0,nx)
        else:f['done']=True
        for li in lists:
            st=page1(li)
            if family_key(st)!=fam and st not in r['discoveryVisited'] and st not in r['discoveryPending']:r['discoveryPending'].append(st)
        commit_state()
        return jsonify({'ok':True,'moviesAdded':len(movies),'queued':sum(1 for t in r['movieTasks'].values() if t.get('status')=='queued'),'catalogTotal':cat['total'],'nextDiscovery':r['discoveryPending'][0] if r['discoveryPending'] else None})

@app.post('/runner/discovery/fail')
def discovery_fail():
    p=request.get_json(silent=True) or {};url=str(p.get('url') or '')
    with LOCK:
        r=STATE['runner'];r['discoveryLeases'].pop(url,None)
        if is_list_url(url) and url not in r['discoveryVisited'] and url not in r['discoveryPending']:r['discoveryPending'].append(url)
        commit_state();return jsonify({'ok':True})

@app.get('/runner/status')
def runner_status():
    with LOCK:
        r=STATE['runner'];counts={'queued':0,'leased':0,'done':0,'failed':0}
        for t in r['movieTasks'].values():counts[t.get('status','queued')]=counts.get(t.get('status','queued'),0)+1
        return jsonify({'ok':True,'startedAt':r.get('startedAt'),'movies':counts,'discoveryPending':len(r['discoveryPending']),'discoveryVisited':len(r['discoveryVisited']),'stored':len(STATE['movies']),'catalogTotal':STATE['catalog'].get('total'),'storeBackend':'neon' if DB_URL else 'memory'})

@app.post('/collector/result')
def collector_result():
    p=request.get_json(silent=True) or {}
    if not is_movie_url(p.get('movieUrl')):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
    item=sanitize_result(p)
    if not item['streams']:return jsonify({'ok':False,'error':'no valid streams'}),400
    with LOCK:
        STATE['movies'][item['id']]=item;t=ensure_task(item['movieUrl']);t['status']='done';t['leaseUntil']=None
        urls=STATE['catalog'].setdefault('urls',[])
        if item['movieUrl'] not in urls:urls.append(item['movieUrl'])
        STATE['catalog']['total']=len(urls);STATE['catalog']['updatedAt']=utcnow();commit_state()
        return jsonify({'ok':True,'id':item['id'],'stored':len(STATE['movies']),'visibleInAddon':True})

@app.post('/collector/catalog')
def collector_catalog():
    p=request.get_json(silent=True) or {};incoming=list(dict.fromkeys(x for x in (p.get('urls') or []) if is_movie_url(x)))
    with LOCK:
        urls=STATE['catalog'].setdefault('urls',[]);seen=set(urls)
        for u in incoming:
            if u not in seen:urls.append(u);seen.add(u)
            ensure_task(u)
        STATE['catalog']['total']=len(urls);STATE['catalog']['updatedAt']=utcnow();commit_state();return jsonify({'ok':True,'total':len(urls),'submitted':len(incoming)})

@app.get('/collector/results')
def collector_results():
    with LOCK:
        movies=STATE['movies'];order=STATE['catalog'].get('urls') or [];byurl={x.get('movieUrl'):x for x in movies.values()};items=[byurl[u] for u in order if u in byurl];known={x['id'] for x in items};items.extend(x for x in movies.values() if x.get('id') not in known);skip=max(0,int(request.args.get('skip',0)));limit=min(500,max(1,int(request.args.get('limit',100))));return jsonify({'total':len(items),'items':items[skip:skip+limit]})

@app.get('/collector/stats')
def collector_stats():
    with LOCK:
        total=STATE['catalog'].get('total') or 0;resolved=len(STATE['movies']);return jsonify({'catalogTotal':total,'resolved':resolved,'errors':len(STATE['errors']),'remaining':max(0,total-resolved),'catalogUpdatedAt':STATE['catalog'].get('updatedAt')})

from manko_addon import register_manko_addon
register_manko_addon(app,load_store)

import os, json, hashlib
from datetime import datetime, timezone, timedelta
from threading import RLock
from urllib.parse import urlparse
from flask import Flask, jsonify, request
import psycopg
import film4k_addon
from film4k_addon import register_film4k_addon

app = Flask(__name__)
DB_URL = os.environ.get('DATABASE_URL','').strip()
LOCK = RLock()
LEASE_SECONDS = 120
MAX_RETRIES = 3

# Keep VOD requests on the normal Film4K origin path. Sports-specific endpoints still work
# with this generic referer, while using /sports globally was making movie/series APIs return empty data.
def _fixed_headers(extra=None):
    h={"User-Agent":"Mozilla/5.0","Accept":"*/*","Referer":"https://film4k.net/","Origin":"https://film4k.net"}
    if extra:h.update(extra)
    return h
film4k_addon._headers=_fixed_headers
film4k_addon.MANIFEST["version"]="0.5.4"

def now(): return datetime.now(timezone.utc).isoformat()
def valid_url(u):
    try:
        x=urlparse(str(u or ''))
        return x.scheme=='https' and x.netloc.lower().split(':',1)[0] in {'film4k.net','www.film4k.net'} and x.path not in {'','/'}
    except Exception:return False

def task_id(u): return hashlib.sha1(str(u).encode()).hexdigest()[:20]
def movie_id(u): return 'movie_film4k_'+hashlib.sha1(str(u).encode()).hexdigest()[:16]
def blank():
    return {'movies':{},'catalog':{'urls':[],'total':0,'updatedAt':None},'probes':{},'runner':{'tasks':{},'order':[],'startedAt':None}}

def db_init():
    if not DB_URL:return
    with psycopg.connect(DB_URL) as c:
        with c.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS app_state (id text PRIMARY KEY, data jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        c.commit()
def load_db():
    if not DB_URL:return blank()
    try:
        with psycopg.connect(DB_URL) as c:
            with c.cursor() as cur:
                cur.execute("SELECT data FROM app_state WHERE id='film4k_store'")
                row=cur.fetchone(); d=row[0] if row else blank()
                if not isinstance(d,dict):d=blank()
                b=blank()
                for k,v in b.items():d.setdefault(k,v)
                return d
    except Exception:return blank()
def save_db():
    if not DB_URL:return
    payload=json.dumps(STATE,ensure_ascii=False)
    with psycopg.connect(DB_URL) as c:
        with c.cursor() as cur:
            cur.execute("INSERT INTO app_state(id,data,updated_at) VALUES('film4k_store',%s::jsonb,now()) ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data,updated_at=now()",(payload,))
        c.commit()

try:db_init()
except Exception:pass
STATE=load_db()

def load_store():
    with LOCK:return json.loads(json.dumps(STATE,ensure_ascii=False))

def ensure_task(url):
    if not valid_url(url):return None
    r=STATE['runner']; tid=task_id(url)
    if tid not in r['tasks']:
        r['tasks'][tid]={'id':tid,'movieUrl':url,'status':'queued','attempts':0,'leaseUntil':None,'updatedAt':now()}
        r['order'].append(tid)
    return r['tasks'][tid]

def candidate_streams(resources):
    out=[];seen=set();priority=[]
    for r in resources or []:
        u=str((r or {}).get('url') or '')
        if not u.startswith(('http://','https://')) or u in seen:continue
        low=u.lower().split('#',1)[0]
        if low.endswith('/site.webmanifest') or low.endswith('.webmanifest'):continue
        if '.m3u8' in low or '.mpd' in low or '.mp4' in low or '.webm' in low:
            seen.add(u);score=0 if '/master.m3u8' in low else 1;priority.append((score,u))
    priority.sort(key=lambda x:x[0])
    for _,u in priority:out.append({'name':f'#{len(out)+1}','url':u,'headers':{'Referer':'https://film4k.net/'}})
    return out

def upsert_probe(payload):
    url=str(payload.get('pageUrl') or payload.get('movieUrl') or '')
    if not valid_url(url):return None
    meta=payload.get('meta') if isinstance(payload.get('meta'),dict) else {}
    resources=payload.get('resources') if isinstance(payload.get('resources'),list) else []
    key=task_id(url)
    STATE['probes'][key]={'pageUrl':url,'meta':meta,'resources':resources[-500:],'updatedAt':now()}
    streams=candidate_streams(resources)
    if streams:
        mid=movie_id(url)
        STATE['movies'][mid]={'id':mid,'title':meta.get('title') or 'Film4K','titleVi':'','movieUrl':url,'poster':meta.get('poster') or '','streams':streams,'streamUrl':streams[0]['url'],'headers':{'Referer':'https://film4k.net/'},'metadata':{'source':'film4k','description':meta.get('description') or ''},'collectedAt':now(),'updatedAt':now()}
        t=ensure_task(url)
        if t:t['status']='done';t['leaseUntil']=None;t['updatedAt']=now()
    return {'url':url,'streams':len(streams),'resources':len(resources)}

@app.get('/')
def root():return jsonify({'service':'film4k-api','ok':True,'manifest':'/film4k/manifest.json','store':'neon' if DB_URL else 'memory'})
@app.get('/health')
def health():return jsonify({'ok':True,'service':'film4k-api','database':bool(DB_URL)})

@app.post('/film4k/probe')
def probe():
    p=request.get_json(silent=True) or {}
    with LOCK:
        res=upsert_probe(p)
        if not res:return jsonify({'ok':False,'error':'invalid Film4K URL'}),400
        save_db();return jsonify({'ok':True,**res})

@app.get('/film4k/probes')
def probes():
    with LOCK:return jsonify({'items':list(STATE['probes'].values()),'total':len(STATE['probes'])})

@app.post('/collector/catalog')
def catalog_submit():
    p=request.get_json(silent=True) or {};incoming=list(dict.fromkeys(x for x in (p.get('urls') or []) if valid_url(x)))
    with LOCK:
        urls=STATE['catalog'].setdefault('urls',[]);seen=set(urls)
        for u in incoming:
            if u not in seen:urls.append(u);seen.add(u)
            ensure_task(u)
        STATE['catalog']['total']=len(urls);STATE['catalog']['updatedAt']=now();save_db()
        return jsonify({'ok':True,'submitted':len(incoming),'total':len(urls)})

@app.post('/collector/result')
def collector_result():
    p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or p.get('pageUrl') or '')
    if not valid_url(url):return jsonify({'ok':False,'error':'invalid Film4K URL'}),400
    with LOCK:
        res=upsert_probe({'pageUrl':url,'meta':p.get('meta') or p.get('metadata') or {},'resources':p.get('resources') or []})
        streams=p.get('streams') if isinstance(p.get('streams'),list) else []
        if streams:
            mid=movie_id(url);item=STATE['movies'].get(mid) or {'id':mid,'movieUrl':url,'metadata':{'source':'film4k'}}
            item.update({'title':p.get('title') or item.get('title') or 'Film4K','poster':p.get('poster') or item.get('poster') or '','streams':streams,'streamUrl':str((streams[0] or {}).get('url') or ''),'updatedAt':now(),'collectedAt':item.get('collectedAt') or now()});STATE['movies'][mid]=item
        save_db();return jsonify({'ok':True,'id':movie_id(url),'streams':len((STATE['movies'].get(movie_id(url)) or {}).get('streams') or [])})

@app.post('/runner/start')
def runner_start():
    with LOCK:
        STATE['runner']['startedAt']=now()
        for t in STATE['runner']['tasks'].values():
            if t.get('status')!='done':t['status']='queued';t['leaseUntil']=None
        save_db();return jsonify({'ok':True,'workers':2})

@app.get('/runner/next')
def runner_next():
    with LOCK:
        r=STATE['runner'];cur=datetime.now(timezone.utc)
        for t in r['tasks'].values():
            if t.get('status')=='leased' and t.get('leaseUntil'):
                try:
                    if datetime.fromisoformat(t['leaseUntil'])<cur:t['status']='queued';t['leaseUntil']=None
                except Exception:t['status']='queued';t['leaseUntil']=None
        chosen=None
        for tid in r['order']:
            t=r['tasks'].get(tid)
            if t and t.get('status')=='queued' and int(t.get('attempts') or 0)<MAX_RETRIES:
                t['status']='leased';t['leaseUntil']=(cur+timedelta(seconds=LEASE_SECONDS)).isoformat();t['updatedAt']=now();chosen=dict(t);break
        save_db();return jsonify({'ok':True,'task':chosen})

@app.post('/runner/result')
def runner_result():
    p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or p.get('pageUrl') or '')
    with LOCK:
        res=upsert_probe({'pageUrl':url,'meta':p.get('meta') or {},'resources':p.get('resources') or []})
        if not res:return jsonify({'ok':False,'error':'invalid Film4K URL'}),400
        t=STATE['runner']['tasks'].get(str(p.get('taskId') or task_id(url)))
        if t:
            if res['streams']>0:t['status']='done'
            else:t['status']='queued';t['attempts']=int(t.get('attempts') or 0)+1
            t['leaseUntil']=None;t['updatedAt']=now()
        save_db();return jsonify({'ok':True,**res})

@app.post('/runner/fail')
def runner_fail():
    p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '')
    with LOCK:
        t=STATE['runner']['tasks'].get(str(p.get('taskId') or task_id(url)))
        if t:
            t['attempts']=int(t.get('attempts') or 0)+1;t['status']='queued' if t['attempts']<MAX_RETRIES else 'failed';t['leaseUntil']=None;t['updatedAt']=now()
        save_db();return jsonify({'ok':True,'status':t.get('status') if t else None})

@app.get('/runner/status')
def runner_status():
    with LOCK:
        counts={}
        for t in STATE['runner']['tasks'].values():counts[t.get('status','queued')]=counts.get(t.get('status','queued'),0)+1
        return jsonify({'ok':True,'movies':counts,'catalogTotal':STATE['catalog'].get('total',0),'resolved':len(STATE['movies']),'probes':len(STATE['probes'])})

register_film4k_addon(app,load_store)

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))

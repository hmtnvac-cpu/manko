import os, json, hashlib, base64
from datetime import datetime, timezone, timedelta
from threading import RLock
from urllib.parse import urlparse, quote, unquote
from flask import Flask, jsonify, request, Response
import psycopg
from film4k_addon import register_film4k_addon
import film4k_browser_resolver as sports_browser

app = Flask(__name__)
DB_URL = os.environ.get('DATABASE_URL','').strip()
LOCK = RLock()
LEASE_SECONDS = 120
MAX_RETRIES = 3

def now(): return datetime.now(timezone.utc).isoformat()
def valid_url(u):
    try:
        x=urlparse(str(u or ''))
        return x.scheme=='https' and x.netloc.lower().split(':',1)[0] in {'film4k.net','www.film4k.net'} and x.path not in {'','/'}
    except Exception:return False

def task_id(u): return hashlib.sha1(str(u).encode()).hexdigest()[:20]
def movie_id(u): return 'movie_film4k_'+hashlib.sha1(str(u).encode()).hexdigest()[:16]
def blank(): return {'movies':{},'catalog':{'urls':[],'total':0,'updatedAt':None},'probes':{},'runner':{'tasks':{},'order':[],'startedAt':None}}

def db_init():
    if not DB_URL:return
    with psycopg.connect(DB_URL) as c:
        with c.cursor() as cur:cur.execute("CREATE TABLE IF NOT EXISTS app_state (id text PRIMARY KEY, data jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
        c.commit()
def load_db():
    if not DB_URL:return blank()
    try:
        with psycopg.connect(DB_URL) as c:
            with c.cursor() as cur:
                cur.execute("SELECT data FROM app_state WHERE id='film4k_store'");row=cur.fetchone();d=row[0] if row else blank()
                if not isinstance(d,dict):d=blank()
                for k,v in blank().items():d.setdefault(k,v)
                return d
    except Exception:return blank()
def save_db():
    if not DB_URL:return
    payload=json.dumps(STATE,ensure_ascii=False)
    with psycopg.connect(DB_URL) as c:
        with c.cursor() as cur:cur.execute("INSERT INTO app_state(id,data,updated_at) VALUES('film4k_store',%s::jsonb,now()) ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data,updated_at=now()",(payload,))
        c.commit()
try:db_init()
except Exception:pass
STATE=load_db()
def load_store():
    with LOCK:return json.loads(json.dumps(STATE,ensure_ascii=False))

def ensure_task(url):
    if not valid_url(url):return None
    r=STATE['runner'];tid=task_id(url)
    if tid not in r['tasks']:
        r['tasks'][tid]={'id':tid,'movieUrl':url,'status':'queued','attempts':0,'leaseUntil':None,'updatedAt':now()};r['order'].append(tid)
    return r['tasks'][tid]

def candidate_streams(resources):
    out=[];seen=set();priority=[]
    for r in resources or []:
        u=str((r or {}).get('url') or '')
        if not u.startswith(('http://','https://')) or u in seen:continue
        low=u.lower().split('#',1)[0]
        if low.endswith('/site.webmanifest') or low.endswith('.webmanifest'):continue
        if '.m3u8' in low or '.mpd' in low or '.mp4' in low or '.webm' in low:
            seen.add(u);priority.append((0 if '/master.m3u8' in low else 1,u))
    priority.sort(key=lambda x:x[0])
    for _,u in priority:out.append({'name':f'#{len(out)+1}','url':u,'headers':{'Referer':'https://film4k.net/'}})
    return out

def upsert_probe(payload):
    url=str(payload.get('pageUrl') or payload.get('movieUrl') or '')
    if not valid_url(url):return None
    meta=payload.get('meta') if isinstance(payload.get('meta'),dict) else {};resources=payload.get('resources') if isinstance(payload.get('resources'),list) else []
    key=task_id(url);STATE['probes'][key]={'pageUrl':url,'meta':meta,'resources':resources[-500:],'updatedAt':now()}
    streams=candidate_streams(resources)
    if streams:
        mid=movie_id(url);STATE['movies'][mid]={'id':mid,'title':meta.get('title') or 'Film4K','titleVi':'','movieUrl':url,'poster':meta.get('poster') or '','streams':streams,'streamUrl':streams[0]['url'],'headers':{'Referer':'https://film4k.net/'},'metadata':{'source':'film4k','description':meta.get('description') or ''},'collectedAt':now(),'updatedAt':now()}
        t=ensure_task(url)
        if t:t['status']='done';t['leaseUntil']=None;t['updatedAt']=now()
    return {'url':url,'streams':len(streams),'resources':len(resources)}

@app.get('/')
def root():return jsonify({'service':'film4k-api','ok':True,'manifest':'/film4k/manifest.json','store':'neon' if DB_URL else 'memory','sportsResolver':'browser-session'})
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
        STATE['catalog']['total']=len(urls);STATE['catalog']['updatedAt']=now();save_db();return jsonify({'ok':True,'submitted':len(incoming),'total':len(urls)})
@app.post('/collector/result')
def collector_result():
    p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or p.get('pageUrl') or '')
    if not valid_url(url):return jsonify({'ok':False,'error':'invalid Film4K URL'}),400
    with LOCK:
        res=upsert_probe({'pageUrl':url,'meta':p.get('meta') or p.get('metadata') or {},'resources':p.get('resources') or []});streams=p.get('streams') if isinstance(p.get('streams'),list) else []
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
        if t:t['attempts']=int(t.get('attempts') or 0)+1;t['status']='queued' if t['attempts']<MAX_RETRIES else 'failed';t['leaseUntil']=None;t['updatedAt']=now()
        save_db();return jsonify({'ok':True,'status':t.get('status') if t else None})
@app.get('/runner/status')
def runner_status():
    with LOCK:
        counts={}
        for t in STATE['runner']['tasks'].values():counts[t.get('status','queued')]=counts.get(t.get('status','queued'),0)+1
        return jsonify({'ok':True,'movies':counts,'catalogTotal':STATE['catalog'].get('total',0),'resolved':len(STATE['movies']),'probes':len(STATE['probes'])})

register_film4k_addon(app,load_store)
_original_stream_view=app.view_functions.get('stream')

def _decode_live_sid(sid):
    raw=str(sid or '').split(':',1)[0];prefix='film4k_live_'
    if not raw.startswith(prefix):return ''
    try:
        b=raw[len(prefix):];b+='='*((4-len(b)%4)%4);return base64.urlsafe_b64decode(b.encode()).decode()
    except Exception:return ''

def _browser_stream(typ,sid):
    slug=_decode_live_sid(sid)
    if not slug:
        return _original_stream_view(typ,sid) if _original_stream_view else jsonify({'streams':[]})
    # Resolve every sports play request inside a real Film4K browser session. Do not reuse captured HLS URLs.
    result=sports_browser.resolve(slug,force=True)
    streams=[];base=request.host_url.rstrip('/')
    session=result.get('session')
    for i,u in enumerate(result.get('streams') or [],1):
        prox=base+'/film4k/sports-hls?sid='+quote(session or '',safe='')+'&u='+quote(u,safe='')
        streams.append({'name':f'LIVE #{i}','title':f'Film4K Sports • LIVE #{i}','url':prox,'behaviorHints':{'notWebReady':True}})
    return jsonify({'streams':streams})
if _original_stream_view is not None:app.view_functions['stream']=_browser_stream

@app.get('/film4k/sports-hls')
def sports_hls():
    sid=str(request.args.get('sid') or '');target=unquote(str(request.args.get('u') or ''))
    if not sid or not target.startswith('https://'):return Response('bad sports session',400)
    try:
        status,headers,body=sports_browser.fetch(sid,target,request.headers.get('Range'))
        ct=headers.get('content-type') or 'application/octet-stream'
        if '.m3u8' in target.lower() or 'mpegurl' in ct.lower():
            text=body.decode('utf-8','replace')
            body=sports_browser.rewrite_playlist(text,target,request.host_url.rstrip('/')+'/film4k/sports-hls',sid).encode('utf-8')
            ct='application/vnd.apple.mpegurl'
        resp=Response(body,status=status,content_type=ct)
        for k in ['content-range','accept-ranges']:
            if headers.get(k):resp.headers[k.title()]=headers[k]
        resp.headers['Access-Control-Allow-Origin']='*';resp.headers['Cache-Control']='no-store'
        return resp
    except Exception as e:return Response('sports upstream error: '+str(e),502)

@app.get('/film4k/sports/browser-debug/<path:slug>')
def sports_browser_debug(slug):
    r=sports_browser.resolve(slug,force=True)
    safe={k:v for k,v in r.items() if k!='session'}
    safe['sessionCreated']=bool(r.get('session'))
    return jsonify(safe)

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))

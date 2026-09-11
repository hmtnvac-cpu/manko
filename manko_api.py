from flask import Flask,jsonify,request
from datetime import datetime,timezone,timedelta
from threading import Lock
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlparse,parse_qsl,urlencode,urlunparse
from urllib.request import Request,urlopen
import hashlib,json,os,re,time

app=Flask(__name__)
REFERER='https://javplayer.cc/'
STORE_FILE=os.environ.get('MANKO_RESULTS_FILE','/tmp/manko_collector_results.json')
STORE_LOCK=Lock()
MAX_RETRIES=3
LEASE_SECONDS=90

def utcnow():return datetime.now(timezone.utc).isoformat()
def _blank_store():
 return {'movies':{},'errors':{},'catalog':{'total':None,'urls':[],'updatedAt':None},'runner':{'movieTasks':{},'movieOrder':[],'discoveryPending':['https://manko.fun/home'],'discoveryLeases':{},'discoveryVisited':[],'families':{},'startedAt':None}}
def load_store():
 try:
  with open(STORE_FILE,'r',encoding='utf-8') as f:d=json.load(f)
 except:d=_blank_store()
 b=_blank_store()
 for k,v in b.items():d.setdefault(k,v)
 r=d.setdefault('runner',{})
 for k,v in b['runner'].items():r.setdefault(k,v)
 return d
def save_store(d):
 os.makedirs(os.path.dirname(STORE_FILE) or '.',exist_ok=True);t=STORE_FILE+'.tmp'
 with open(t,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
 os.replace(t,STORE_FILE)
def movie_key(p):
 u=str(p.get('movieUrl') or '');return 'movie_manko_'+hashlib.sha1(u.encode()).hexdigest()[:16]
def task_id(url):return hashlib.sha1(str(url).encode()).hexdigest()[:20]
def is_movie_url(u):return str(u or '').startswith('https://manko.fun/movie-info/')
def is_list_url(u):
 try:
  x=urlparse(str(u));return x.scheme=='https' and x.netloc=='manko.fun' and (x.path=='/home' or 'movie-list' in x.path or 'cate-list' in x.path)
 except:return False
def family_key(u):
 try:
  x=urlparse(u);q=[(k,v) for k,v in parse_qsl(x.query,keep_blank_values=True) if k!='page'];q.sort();return urlunparse((x.scheme,x.netloc,x.path,'',urlencode(q),'')).rstrip('?')
 except:return str(u)
def next_page(u):
 try:
  x=urlparse(u)
  if x.path=='/home':return None
  q=dict(parse_qsl(x.query,keep_blank_values=True));n=max(1,int(q.get('page','1') or 1));q['page']=str(n+1);return urlunparse((x.scheme,x.netloc,x.path,'',urlencode(q),'')).rstrip('?')
 except:return None
def page1(u):
 try:
  x=urlparse(u)
  if x.path=='/home':return u
  q=dict(parse_qsl(x.query,keep_blank_values=True));q['page']='1';return urlunparse((x.scheme,x.netloc,x.path,'',urlencode(q),'')).rstrip('?')
 except:return u

def translate_vi(text):
 text=str(text or '').strip()
 if not text:return ''
 try:
  q=urlencode({'client':'gtx','sl':'auto','tl':'vi','dt':'t','q':text[:4500]})
  req=Request('https://translate.googleapis.com/translate_a/single?'+q,headers={'User-Agent':'Mozilla/5.0'})
  with urlopen(req,timeout=12) as r:j=json.loads(r.read().decode('utf-8'))
  out=''.join((x[0] or '') for x in (j[0] or []) if x)
  return out.strip() or text
 except:return text

def sanitize_result(p):
 streams=[]
 for n,s in enumerate(p.get('streams') or [],1):
  if isinstance(s,dict) and str(s.get('url') or '').startswith(('http://','https://')):
   h=s.get('headers') if isinstance(s.get('headers'),dict) else {'Referer':REFERER};h.setdefault('Referer',REFERER)
   streams.append({'name':s.get('name') or f'#{n}','url':s['url'],'vttUrl':s.get('vttUrl'),'headers':h,'playerId':s.get('playerId'),'playerUrl':s.get('playerUrl')})
 if not streams and str(p.get('streamUrl') or '').startswith(('http://','https://')):streams=[{'name':'#1','url':p['streamUrl'],'vttUrl':p.get('vttUrl'),'headers':p.get('headers') or {'Referer':REFERER},'playerId':p.get('playerId'),'playerUrl':p.get('playerUrl')}]
 meta=dict(p.get('metadata') or {}) if isinstance(p.get('metadata'),dict) else {}
 meta.pop('subtitleVi',None)
 if meta.get('description') and not meta.get('descriptionVi'):meta['descriptionVi']=translate_vi(meta.get('description'))
 title=str(p.get('title') or 'Manko').strip();titleVi=str(p.get('titleVi') or meta.get('titleVi') or '').strip()
 if title and not titleVi:titleVi=translate_vi(re.sub(r'\s*-\s*Watch Free in HD\s*\|\s*Manko\s*$','',title,flags=re.I))
 return {'id':movie_key(p),'title':title,'titleVi':titleVi,'movieUrl':str(p.get('movieUrl') or '').strip(),'poster':str(p.get('poster') or '').strip(),'playerId':str(p.get('playerId') or (streams[0].get('playerId') if streams else '') or ''),'playerUrl':str(p.get('playerUrl') or (streams[0].get('playerUrl') if streams else '') or ''),'streamUrl':streams[0]['url'] if streams else '','streams':streams,'subtitleVi':'','metadata':meta,'headers':streams[0].get('headers') if streams else {'Referer':REFERER},'collectedAt':str(p.get('collectedAt') or utcnow()),'updatedAt':utcnow()}

def ensure_movie_task(s,url):
 if not is_movie_url(url):return
 r=s['runner'];tid=task_id(url)
 if tid not in r['movieTasks']:
  r['movieTasks'][tid]={'id':tid,'movieUrl':url,'status':'queued','attempts':0,'leaseUntil':None,'updatedAt':utcnow()};r['movieOrder'].append(tid)

def reset_expired_leases(r):
 now=datetime.now(timezone.utc)
 for t in r.get('movieTasks',{}).values():
  if t.get('status')=='leased' and t.get('leaseUntil'):
   try:
    if datetime.fromisoformat(t['leaseUntil'])<now:t['status']='queued';t['leaseUntil']=None
   except:t['status']='queued';t['leaseUntil']=None
 for u,lease in list(r.get('discoveryLeases',{}).items()):
  try:
   if datetime.fromisoformat(lease)<now:r['discoveryLeases'].pop(u,None);r['discoveryPending'].insert(0,u)
  except:r['discoveryLeases'].pop(u,None)

@app.get('/')
def root():return jsonify({'service':'manko-api','status':'ok','addon_manifest':'/manifest.json','collector':'/collector/results','runner':'/runner/status'})
@app.get('/health')
def health():return jsonify({'ok':True,'service':'manko-api','runner':True})
@app.get('/server-test')
def server_test():
 target=request.args.get('url','https://manko.fun/movie-info/6aa2f0d3131836087eb79867?series=false')
 if not target.startswith('https://manko.fun/movie-info/'):return jsonify({'status':'ERROR','error':'invalid Manko URL'}),400
 result={'status':'STARTED','target':target,'startedAt':utcnow(),'title':None,'playerUrl':None,'playerId':None,'streamUrl':None,'hlsStatus':None,'hlsPreview':None,'notes':[]};browser=None
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled']);context=browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',locale='en-US',viewport={'width':1365,'height':900,},extra_http_headers={'Accept-Language':'en-US,en;q=0.9'});page=context.new_page();observed=[];page.on('response',lambda r: observed.append({'url':r.url,'status':r.status}) if ('javplayer.cc' in r.url or '.m3u8' in r.url) else None)
   try:page.goto(target,wait_until='domcontentloaded',timeout=45000)
   except PlaywrightTimeoutError:result['notes'].append('Manko navigation timeout; inspecting loaded DOM')
   result['title']=page.title();html=page.content()
   if ('Just a moment' in result['title'] or 'challenge-platform' in html or 'cf-chl' in html) and 'javplayer.cc/e/' not in html:result['status']='MANKO_BLOCKED';result['observed']=observed[-20:];return jsonify(result)
   result['status']='NO_IFRAME';return jsonify(result)
 except Exception as e:result['status']='ERROR';result['error']=str(e);return jsonify(result),500
 finally:
  try:
   if browser:browser.close()
  except:pass

@app.post('/collector/result')
def result():
 p=request.get_json(silent=True) or {}
 if not is_movie_url(p.get('movieUrl')):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
 i=sanitize_result(p)
 if not i['streams']:return jsonify({'ok':False,'error':'no valid streams'}),400
 with STORE_LOCK:s=load_store();s.setdefault('movies',{})[i['id']]=i;ensure_movie_task(s,i['movieUrl']);s['runner']['movieTasks'][task_id(i['movieUrl'])]['status']='done';save_store(s)
 return jsonify({'ok':True,'id':i['id'],'stored':len(s.get('movies',{})),'streams':len(i['streams']),'metadata':bool(i['metadata'])})

@app.post('/collector/metadata')
def metadata_update():
 p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '')
 if not is_movie_url(url):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
 k=movie_key({'movieUrl':url});incoming=p.get('metadata') if isinstance(p.get('metadata'),dict) else {};clean={x:v for x,v in incoming.items() if x!='subtitleVi'}
 if clean.get('description') and not clean.get('descriptionVi'):clean['descriptionVi']=translate_vi(clean['description'])
 with STORE_LOCK:
  s=load_store();movies=s.setdefault('movies',{});old=movies.get(k)
  if not old:return jsonify({'ok':False,'error':'movie not found','id':k}),404
  old['metadata']={**(old.get('metadata') or {}),**clean};old['metadata'].pop('subtitleVi',None)
  if p.get('title'):old['title']=p['title']
  if p.get('titleVi'):old['titleVi']=p['titleVi']
  if p.get('poster'):old['poster']=p['poster']
  old['subtitleVi']='';old['updatedAt']=utcnow();movies[k]=old;save_store(s)
 return jsonify({'ok':True,'id':k,'streamsPreserved':len(old.get('streams') or []),'metadata':old.get('metadata')})

@app.post('/collector/error')
def error():
 p=request.get_json(silent=True) or {};k=hashlib.sha1(str(p.get('movieUrl') or '').encode()).hexdigest()[:16]
 with STORE_LOCK:s=load_store();s.setdefault('errors',{})[k]={**p,'updatedAt':utcnow()};save_store(s)
 return jsonify({'ok':True})

@app.post('/collector/catalog')
def catpost():
 p=request.get_json(silent=True) or {};urls=list(dict.fromkeys(str(x) for x in p.get('urls',[]) if is_movie_url(x)))
 with STORE_LOCK:
  s=load_store();old=s.get('catalog') or {};old_urls=old.get('urls') or [];seen=set(urls);merged=urls+[u for u in old_urls if u not in seen]
  s['catalog']={'total':len(merged),'urls':merged,'pageUrl':p.get('pageUrl'),'updatedAt':utcnow()}
  for u in merged:ensure_movie_task(s,u)
  save_store(s)
 return jsonify({'ok':True,'total':len(merged),'submitted':len(urls)})

@app.get('/collector/results')
def results():
 s=load_store();movies=s.get('movies') or {};order=(s.get('catalog') or {}).get('urls') or [];byurl={x.get('movieUrl'):x for x in movies.values()};a=[byurl[u] for u in order if u in byurl];seen={x.get('id') for x in a};a.extend(sorted((x for x in movies.values() if x.get('id') not in seen),key=lambda x:x.get('collectedAt') or '',reverse=True));skip=max(0,int(request.args.get('skip',0)));limit=min(500,max(1,int(request.args.get('limit',100))));return jsonify({'total':len(a),'items':a[skip:skip+limit]})
@app.get('/collector/stats')
def stats():
 s=load_store();c=s.get('catalog') or {};n=len(s.get('movies',{}));e=len(s.get('errors',{}));t=c.get('total');return jsonify({'catalogTotal':t,'resolved':n,'errors':e,'remaining':max(0,t-n-e) if isinstance(t,int) else None,'catalogUpdatedAt':c.get('updatedAt')})

@app.post('/runner/start')
def runner_start():
 with STORE_LOCK:
  s=load_store();r=s['runner'];r['startedAt']=utcnow();r['discoveryPending']=['https://manko.fun/home'];r['discoveryLeases']={};r['discoveryVisited']=[];r['families']={}
  for t in r['movieTasks'].values():
   if t.get('status')!='done':t['status']='queued';t['leaseUntil']=None
  save_store(s)
 return jsonify({'ok':True,'mode':'server-driven','workers':2})

@app.get('/runner/next')
def runner_next():
 with STORE_LOCK:
  s=load_store();r=s['runner'];reset_expired_leases(r)
  movies=s.get('movies') or {};done_urls={m.get('movieUrl') for m in movies.values()}
  chosen=None
  for tid in r.get('movieOrder',[]):
   t=r['movieTasks'].get(tid)
   if not t:continue
   if t.get('movieUrl') in done_urls:t['status']='done';continue
   if t.get('status')=='queued' and int(t.get('attempts') or 0)<MAX_RETRIES:
    t['status']='leased';t['leaseUntil']=(datetime.now(timezone.utc)+timedelta(seconds=LEASE_SECONDS)).isoformat();t['updatedAt']=utcnow();chosen=dict(t);break
  save_store(s)
 return jsonify({'ok':True,'task':chosen})

@app.post('/runner/result')
def runner_result():
 p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '');tid=str(p.get('taskId') or task_id(url));page=p.get('page') if isinstance(p.get('page'),dict) else {};stream=p.get('stream') if isinstance(p.get('stream'),dict) else {}
 if not is_movie_url(url):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
 if not p.get('ok') or not str(stream.get('url') or '').startswith(('http://','https://')):return jsonify({'ok':False,'error':'no valid stream'}),400
 raw={'movieUrl':url,'title':page.get('title') or 'Manko','titleVi':'','poster':page.get('poster') or '','metadata':page.get('metadata') or {},'playerId':stream.get('playerId'),'playerUrl':stream.get('playerUrl'),'streams':[{'name':'#1','url':stream.get('url'),'vttUrl':stream.get('vttUrl'),'headers':stream.get('headers') or {'Referer':REFERER},'playerId':stream.get('playerId'),'playerUrl':stream.get('playerUrl')}],'collectedAt':utcnow()}
 i=sanitize_result(raw)
 with STORE_LOCK:
  s=load_store();s['movies'][i['id']]=i;ensure_movie_task(s,url);t=s['runner']['movieTasks'].get(tid) or s['runner']['movieTasks'].get(task_id(url));
  if t:t['status']='done';t['leaseUntil']=None;t['updatedAt']=utcnow()
  save_store(s);stored=len(s['movies'])
 return jsonify({'ok':True,'id':i['id'],'stored':stored,'visibleInAddon':True})

@app.post('/runner/fail')
def runner_fail():
 p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '');tid=str(p.get('taskId') or task_id(url));err=str(p.get('error') or 'runner failed')
 with STORE_LOCK:
  s=load_store();r=s['runner'];t=r['movieTasks'].get(tid) or r['movieTasks'].get(task_id(url))
  if t:
   t['attempts']=int(t.get('attempts') or 0)+1;t['leaseUntil']=None;t['status']='queued' if t['attempts']<MAX_RETRIES else 'failed';t['lastError']=err;t['updatedAt']=utcnow()
   if t['status']=='failed':s['errors'][task_id(url)]={'movieUrl':url,'error':err,'retries':t['attempts'],'updatedAt':utcnow()}
  save_store(s)
 return jsonify({'ok':True,'retry':bool(t and t.get('status')=='queued'),'attempts':int(t.get('attempts') or 0) if t else None})

@app.get('/runner/discovery/next')
def runner_discovery_next():
 with STORE_LOCK:
  s=load_store();r=s['runner'];reset_expired_leases(r);chosen=None
  while r['discoveryPending']:
   u=r['discoveryPending'].pop(0)
   if u in r['discoveryVisited'] or u in r['discoveryLeases']:continue
   chosen=u;r['discoveryLeases'][u]=(datetime.now(timezone.utc)+timedelta(seconds=LEASE_SECONDS)).isoformat();break
  save_store(s)
 return jsonify({'ok':True,'task':{'url':chosen,'id':task_id(chosen)} if chosen else None})

@app.post('/runner/discovery/result')
def runner_discovery_result():
 p=request.get_json(silent=True) or {};url=str(p.get('url') or '');movies=[x for x in p.get('movies',[]) if is_movie_url(x)];lists=[x for x in p.get('lists',[]) if is_list_url(x)]
 if not is_list_url(url):return jsonify({'ok':False,'error':'invalid list url'}),400
 sig=hashlib.sha1('|'.join(movies).encode()).hexdigest() if movies else ''
 with STORE_LOCK:
  s=load_store();r=s['runner'];r['discoveryLeases'].pop(url,None)
  if url not in r['discoveryVisited']:r['discoveryVisited'].append(url)
  fam=family_key(url);f=r['families'].setdefault(fam,{'signatures':[],'done':False})
  repeated=bool(sig and sig in f['signatures'])
  if sig and not repeated:f['signatures'].append(sig)
  for m in movies:ensure_movie_task(s,m)
  old=(s.get('catalog') or {}).get('urls') or [];seen=set(old);ordered=old+[m for m in movies if m not in seen and not seen.add(m)];s['catalog']={'total':len(ordered),'urls':ordered,'pageUrl':url,'updatedAt':utcnow()}
  # Source-order rule: finish current family page1->2->3 before moving to next family.
  if url.endswith('/home') or url=='https://manko.fun/home':
   for li in lists:
    st=page1(li);fk=family_key(st)
    if fk!=fam and not r['families'].get(fk,{}).get('done') and st not in r['discoveryPending'] and st not in r['discoveryVisited']:r['discoveryPending'].append(st)
  elif movies and not repeated:
   nx=next_page(url)
   if nx and nx not in r['discoveryVisited'] and nx not in r['discoveryPending']:r['discoveryPending'].insert(0,nx)
  else:f['done']=True
  # Also remember newly exposed families but defer until current sequence ends.
  for li in lists:
   st=page1(li);fk=family_key(st)
   if fk!=fam and not r['families'].get(fk,{}).get('done') and st not in r['discoveryPending'] and st not in r['discoveryVisited']:r['discoveryPending'].append(st)
  save_store(s)
 return jsonify({'ok':True,'moviesAdded':len(movies),'catalogTotal':len(s['catalog']['urls']),'nextDiscovery':r['discoveryPending'][0] if r['discoveryPending'] else None})

@app.post('/runner/discovery/fail')
def runner_discovery_fail():
 p=request.get_json(silent=True) or {};url=str(p.get('url') or '')
 with STORE_LOCK:
  s=load_store();r=s['runner'];r['discoveryLeases'].pop(url,None)
  if is_list_url(url) and url not in r['discoveryVisited'] and url not in r['discoveryPending']:r['discoveryPending'].append(url)
  save_store(s)
 return jsonify({'ok':True})

@app.get('/runner/status')
def runner_status():
 s=load_store();r=s['runner'];counts={'queued':0,'leased':0,'done':0,'failed':0}
 for t in r.get('movieTasks',{}).values():counts[t.get('status','queued')]=counts.get(t.get('status','queued'),0)+1
 return jsonify({'ok':True,'startedAt':r.get('startedAt'),'movies':counts,'discoveryPending':len(r.get('discoveryPending',[])),'discoveryVisited':len(r.get('discoveryVisited',[])),'stored':len(s.get('movies',{})),'catalogTotal':(s.get('catalog') or {}).get('total'),'storeBackend':'file-fallback' if not os.environ.get('DATABASE_URL') else 'postgres-configured'})

from manko_addon import register_manko_addon
register_manko_addon(app,load_store)
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))

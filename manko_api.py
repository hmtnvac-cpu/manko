from flask import Flask,jsonify,request
from datetime import datetime,timezone
from threading import Lock
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import hashlib,json,os,re,time
app=Flask(__name__);REFERER='https://javplayer.cc/';STORE_FILE=os.environ.get('MANKO_RESULTS_FILE','/tmp/manko_collector_results.json');STORE_LOCK=Lock()
def utcnow():return datetime.now(timezone.utc).isoformat()
def load_store():
 try:
  with open(STORE_FILE,'r',encoding='utf-8') as f:return json.load(f)
 except:return {'movies':{},'errors':{},'catalog':{'total':None,'urls':[],'updatedAt':None}}
def save_store(d):
 os.makedirs(os.path.dirname(STORE_FILE) or '.',exist_ok=True);t=STORE_FILE+'.tmp'
 with open(t,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2)
 os.replace(t,STORE_FILE)
def movie_key(p):
 u=str(p.get('movieUrl') or '');return 'movie_manko_'+hashlib.sha1(u.encode()).hexdigest()[:16]
def sanitize_result(p):
 streams=[]
 for n,s in enumerate(p.get('streams') or [],1):
  if isinstance(s,dict) and str(s.get('url') or '').startswith(('http://','https://')):
   h=s.get('headers') if isinstance(s.get('headers'),dict) else {'Referer':REFERER};h.setdefault('Referer',REFERER)
   streams.append({'name':s.get('name') or f'#{n}','url':s['url'],'vttUrl':s.get('vttUrl'),'headers':h,'playerId':s.get('playerId'),'playerUrl':s.get('playerUrl')})
 if not streams and str(p.get('streamUrl') or '').startswith(('http://','https://')):streams=[{'name':'#1','url':p['streamUrl'],'vttUrl':p.get('vttUrl'),'headers':p.get('headers') or {'Referer':REFERER},'playerId':p.get('playerId'),'playerUrl':p.get('playerUrl')}]
 meta=p.get('metadata') if isinstance(p.get('metadata'),dict) else {}
 meta.pop('genres',None);meta.pop('genresVi',None);meta.pop('subtitleVi',None)
 return {'id':movie_key(p),'title':str(p.get('title') or 'Manko').strip(),'titleVi':str(p.get('titleVi') or meta.get('titleVi') or '').strip(),'movieUrl':str(p.get('movieUrl') or '').strip(),'poster':str(p.get('poster') or '').strip(),'playerId':str(p.get('playerId') or (streams[0].get('playerId') if streams else '') or ''),'playerUrl':str(p.get('playerUrl') or (streams[0].get('playerUrl') if streams else '') or ''),'streamUrl':streams[0]['url'] if streams else '','streams':streams,'subtitleVi':'','metadata':meta,'headers':streams[0].get('headers') if streams else {'Referer':REFERER},'collectedAt':str(p.get('collectedAt') or utcnow()),'updatedAt':utcnow()}
@app.get('/')
def root():return jsonify({'service':'manko-api','status':'ok','addon_manifest':'/manifest.json','collector':'/collector/results','stats':'/collector/stats','server_test':'/server-test'})
@app.get('/health')
def health():return jsonify({'ok':True,'service':'manko-api'})
@app.get('/server-test')
def server_test():
 target=request.args.get('url','https://manko.fun/movie-info/6aa2f0d3131836087eb79867?series=false')
 if not target.startswith('https://manko.fun/movie-info/'):return jsonify({'status':'ERROR','error':'invalid Manko URL'}),400
 result={'status':'STARTED','target':target,'startedAt':utcnow(),'title':None,'playerUrl':None,'playerId':None,'streamUrl':None,'hlsStatus':None,'hlsPreview':None,'notes':[]};browser=None
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled']);context=browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',locale='en-US',viewport={'width':1365,'height':900},extra_http_headers={'Accept-Language':'en-US,en;q=0.9'});page=context.new_page();observed=[];page.on('response',lambda r: observed.append({'url':r.url,'status':r.status}) if ('javplayer.cc' in r.url or '.m3u8' in r.url) else None)
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
 if not str(p.get('movieUrl') or '').startswith('https://manko.fun/movie-info/'):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
 i=sanitize_result(p)
 if not i['streams']:return jsonify({'ok':False,'error':'no valid streams'}),400
 with STORE_LOCK:s=load_store();s.setdefault('movies',{})[i['id']]=i;save_store(s)
 return jsonify({'ok':True,'id':i['id'],'stored':len(s.get('movies',{})),'streams':len(i['streams']),'metadata':bool(i['metadata'])})
@app.post('/collector/metadata')
def metadata_update():
 p=request.get_json(silent=True) or {};url=str(p.get('movieUrl') or '')
 if not url.startswith('https://manko.fun/movie-info/'):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
 k=movie_key({'movieUrl':url});incoming=p.get('metadata') if isinstance(p.get('metadata'),dict) else {}
 clean={x:v for x,v in incoming.items() if x not in ('genres','genresVi','subtitleVi')}
 with STORE_LOCK:
  s=load_store();movies=s.setdefault('movies',{});old=movies.get(k)
  if not old:return jsonify({'ok':False,'error':'movie not found','id':k}),404
  old['metadata']={**(old.get('metadata') or {}),**clean};old['metadata'].pop('genres',None);old['metadata'].pop('genresVi',None);old['metadata'].pop('subtitleVi',None)
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
 p=request.get_json(silent=True) or {};urls=list(dict.fromkeys(str(x) for x in p.get('urls',[]) if str(x).startswith('https://manko.fun/movie-info/')))
 with STORE_LOCK:s=load_store();s['catalog']={'total':len(urls),'urls':urls,'pageUrl':p.get('pageUrl'),'updatedAt':utcnow()};save_store(s)
 return jsonify({'ok':True,'total':len(urls)})
@app.get('/collector/results')
def results():
 a=list((load_store().get('movies') or {}).values());a.sort(key=lambda x:x.get('collectedAt') or '',reverse=True);skip=max(0,int(request.args.get('skip',0)));limit=min(500,max(1,int(request.args.get('limit',100))));return jsonify({'total':len(a),'items':a[skip:skip+limit]})
@app.get('/collector/stats')
def stats():
 s=load_store();c=s.get('catalog') or {};n=len(s.get('movies',{}));e=len(s.get('errors',{}));t=c.get('total');return jsonify({'catalogTotal':t,'resolved':n,'errors':e,'remaining':max(0,t-n-e) if isinstance(t,int) else None,'catalogUpdatedAt':c.get('updatedAt')})
from manko_addon import register_manko_addon
register_manko_addon(app,load_store)
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))

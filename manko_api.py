from flask import Flask,jsonify,request
from datetime import datetime,timezone
from threading import Lock
import hashlib,json,re,os
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
  if isinstance(s,dict) and str(s.get('url') or '').startswith(('http://','https://')):streams.append({'name':s.get('name') or f'#{n}','url':s['url'],'vttUrl':s.get('vttUrl'),'headers':s.get('headers') or {'Referer':REFERER},'playerId':s.get('playerId'),'playerUrl':s.get('playerUrl')})
 if not streams and str(p.get('streamUrl') or '').startswith(('http://','https://')):streams=[{'name':'#1','url':p['streamUrl'],'vttUrl':p.get('vttUrl'),'headers':p.get('headers') or {'Referer':REFERER},'playerId':p.get('playerId'),'playerUrl':p.get('playerUrl')}]
 return {'id':movie_key(p),'title':str(p.get('title') or 'Manko').strip(),'movieUrl':str(p.get('movieUrl') or '').strip(),'poster':str(p.get('poster') or '').strip(),'playerId':str(p.get('playerId') or streams[0].get('playerId') if streams else ''),'playerUrl':str(p.get('playerUrl') or streams[0].get('playerUrl') if streams else ''),'streamUrl':streams[0]['url'] if streams else '','streams':streams,'metadata':p.get('metadata') if isinstance(p.get('metadata'),dict) else {},'headers':streams[0].get('headers') if streams else {'Referer':REFERER},'collectedAt':str(p.get('collectedAt') or utcnow()),'updatedAt':utcnow()}
@app.get('/')
def root():return jsonify({'service':'manko-api','status':'ok','addon_manifest':'/manifest.json','collector':'/collector/results','stats':'/collector/stats'})
@app.get('/health')
def health():return jsonify({'ok':True,'service':'manko-api'})
@app.post('/collector/result')
def result():
 p=request.get_json(silent=True) or {}
 if not str(p.get('movieUrl') or '').startswith('https://manko.fun/movie-info/'):return jsonify({'ok':False,'error':'invalid movieUrl'}),400
 i=sanitize_result(p)
 if not i['streams']:return jsonify({'ok':False,'error':'no valid streams'}),400
 with STORE_LOCK:
  s=load_store();s.setdefault('movies',{})[i['id']]=i;save_store(s)
 return jsonify({'ok':True,'id':i['id'],'stored':len(s.get('movies',{})),'streams':len(i['streams']),'metadata':bool(i['metadata'])})
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

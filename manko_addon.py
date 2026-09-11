from flask import jsonify, request
import json
MANIFEST={"id":"community.manko.addon","version":"1.1.0","name":"Manko","description":"Manko movie catalog for Nuvio/Stremio","resources":["catalog","meta","stream"],"types":["movie"],"idPrefixes":["movie_manko_"],"catalogs":[{"type":"movie","id":"manko","name":"🎬 MANKO","extra":[{"name":"skip","isRequired":False},{"name":"search","isRequired":False}]}]}
def clean_title(v):
 t=str(v or 'Manko').strip()
 for s in [' - Watch Free in HD | Manko',' | Manko']:
  if t.endswith(s):t=t[:-len(s)]
 return t.strip() or 'Manko'
def meta_of(i):
 m=i.get('metadata') or {}; desc=m.get('descriptionVi') or m.get('description') or ''
 out={"id":i.get('id'),"type":"movie","name":clean_title(i.get('title')),"poster":i.get('poster') or None,"background":i.get('poster') or None,"posterShape":"poster","description":desc,"website":i.get('movieUrl') or None}
 if m.get('genres'):out['genres']=m['genres']
 if m.get('actors'):out['cast']=m['actors']
 if m.get('runtime'):out['runtime']=m['runtime']
 if m.get('year'):out['releaseInfo']=str(m['year'])
 elif m.get('releaseDate'):out['releaseInfo']=str(m['releaseDate'])
 details=[]
 for label,key in [('Mã phim','code'),('Studio','studio'),('Quốc gia','country'),('Ngôn ngữ','language')]:
  if m.get(key):details.append(f"{label}: {m[key]}")
 if details:out['description']=(out['description']+'\n\n' if out['description'] else '')+' • '.join(details)
 return out
def register_manko_addon(app,load_store):
 @app.get('/manifest.json')
 def manifest():return jsonify(MANIFEST)
 @app.get('/catalog/movie/manko.json')
 @app.get('/catalog/movie/manko/<path:extra>.json')
 def catalog(extra=None):
  items=list((load_store().get('movies') or {}).values());items.sort(key=lambda x:x.get('collectedAt') or '',reverse=True);p={}
  if extra:
   try:p=json.loads(extra)
   except:pass
  q=str(p.get('search') or request.args.get('search') or '').lower();skip=int(p.get('skip',request.args.get('skip',0)) or 0)
  if q:items=[x for x in items if q in f"{x.get('title','')} {(x.get('metadata') or {}).get('actors',[])} {(x.get('metadata') or {}).get('genres',[])}".lower()]
  return jsonify({'metas':[meta_of(x) for x in items[skip:skip+40]]})
 @app.get('/meta/movie/<mid>.json')
 def meta(mid):
  i=(load_store().get('movies') or {}).get(mid);return jsonify({'meta':meta_of(i) if i else None})
 @app.get('/stream/movie/<mid>.json')
 def stream(mid):
  i=(load_store().get('movies') or {}).get(mid)
  if not i:return jsonify({'streams':[]})
  src=i.get('streams') or ([{'name':'#1','url':i.get('streamUrl'),'headers':i.get('headers') or {}}] if i.get('streamUrl') else [])
  out=[]
  for n,s in enumerate(src,1):
   if not s.get('url'):continue
   h=dict(s.get('headers') or {});h.setdefault('Referer','https://javplayer.cc/')
   out.append({'name':s.get('name') or f'#{n}','title':f"{clean_title(i.get('title'))} • {s.get('name') or '#'+str(n)}",'url':s['url'],'behaviorHints':{'notWebReady':True,'proxyHeaders':{'request':h}}})
  return jsonify({'streams':out})

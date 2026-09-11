from flask import jsonify, request
import json

MANIFEST={
 "id":"community.manko.addon","version":"1.2.0","name":"Manko",
 "description":"Danh mục phim Manko đã Việt hóa cho Nuvio/Stremio",
 "resources":["catalog","meta","stream","subtitles"],"types":["movie"],"idPrefixes":["movie_manko_"],
 "catalogs":[{"type":"movie","id":"manko","name":"🎬 MANKO","extra":[{"name":"skip","isRequired":False},{"name":"search","isRequired":False}]}]
}

def clean_title(v):
 t=str(v or 'Manko').strip()
 for s in [' - Watch Free in HD | Manko',' | Manko']:
  if t.endswith(s):t=t[:-len(s)]
 return t.strip() or 'Manko'

def movie_title(i):
 m=i.get('metadata') or {}
 return clean_title(i.get('titleVi') or m.get('titleVi') or i.get('title'))

def meta_of(i):
 if not i:return None
 m=i.get('metadata') or {}
 desc=m.get('descriptionVi') or m.get('description') or ''
 out={"id":i.get('id'),"type":"movie","name":movie_title(i),"poster":i.get('poster') or None,"background":i.get('poster') or None,"posterShape":"poster","description":desc,"website":i.get('movieUrl') or None}
 genres=m.get('genresVi') or m.get('genres') or []
 if genres:out['genres']=genres
 if m.get('actors'):out['cast']=m['actors']
 if m.get('runtime'):out['runtime']=str(m['runtime'])
 if m.get('year'):out['releaseInfo']=str(m['year'])
 elif m.get('releaseDate'):out['releaseInfo']=str(m['releaseDate'])
 details=[]
 for label,key in [('Mã phim','code'),('Ngày phát hành','releaseDate'),('Thời lượng','runtime'),('Hãng sản xuất','studio')]:
  if m.get(key):details.append(f"{label}: {m[key]}")
 country=m.get('countryVi') or m.get('country')
 language=m.get('languageVi') or m.get('language')
 if country:details.append(f"Quốc gia: {country}")
 if language:details.append(f"Ngôn ngữ: {language}")
 if m.get('actors'):details.append('Diễn viên: '+', '.join(m['actors']))
 if genres:details.append('Thể loại: '+', '.join(genres))
 if details:out['description']=(out['description']+'\n\n' if out['description'] else '')+'\n'.join(details)
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
  if q:items=[x for x in items if q in f"{movie_title(x)} {(x.get('metadata') or {}).get('actors',[])} {(x.get('metadata') or {}).get('genresVi',[])}".lower()]
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
   label=s.get('name') or f'#{n}'
   out.append({'name':label,'title':f"{movie_title(i)} • {label}",'url':s['url'],'behaviorHints':{'notWebReady':True,'proxyHeaders':{'request':h}}})
  return jsonify({'streams':out})

 @app.get('/subtitles/movie/<mid>.json')
 @app.get('/subtitles/movie/<mid>/<path:extra>.json')
 def subtitles(mid,extra=None):
  i=(load_store().get('movies') or {}).get(mid)
  if not i:return jsonify({'subtitles':[]})
  url=i.get('subtitleVi') or (i.get('metadata') or {}).get('subtitleVi') or ''
  if not str(url).startswith(('http://','https://')):return jsonify({'subtitles':[]})
  return jsonify({'subtitles':[{'id':'vi','lang':'vie','url':url}]})

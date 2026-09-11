from flask import jsonify, request
import json,re
from urllib.parse import parse_qs, unquote_plus

GENRES={
 "popular":"Phổ biến","top rated":"Đánh giá cao","new":"Mới","uncensored":"Không che",
 "censored":"Kiểm duyệt","western":"Phương Tây","big tits":"Ngực lớn","love affair":"Ngoại tình",
 "voyeur":"Nhìn trộm","solowork":"Một mình","cuckold":"Ngoại tình","pov":"Góc nhìn thứ nhất",
 "female teacher":"Cô giáo","school swimsuit":"Đồ bơi học sinh","leaked":"Rò rỉ","fc2":"FC2"
}
MANIFEST={
 "id":"community.manko.addon","version":"1.6.1","name":"Manko",
 "description":"Danh mục Manko đã Việt hóa, có Snapshots và phân loại theo từ khóa",
 "resources":["catalog","meta","stream"],"types":["series"],"idPrefixes":["series_manko_"],
 "catalogs":[{"type":"series","id":"manko_snapshots","name":"🎬 MANKO","extra":[{"name":"skip","isRequired":False},{"name":"search","isRequired":False},{"name":"genre","isRequired":False,"options":["Phổ biến","Đánh giá cao","Mới","Không che","Kiểm duyệt","Phương Tây","Ngực lớn","Ngoại tình","Nhìn trộm","Một mình","Góc nhìn thứ nhất","Cô giáo","Đồ bơi học sinh","Rò rỉ","FC2"]}]}]
}

def clean_title(v):
 t=str(v or 'Manko').strip()
 for s in [' - Watch Free in HD | Manko',' | Manko']:
  if t.endswith(s):t=t[:-len(s)]
 return t.strip() or 'Manko'
def movie_title(i):
 m=i.get('metadata') or {};return clean_title(i.get('titleVi') or m.get('titleVi') or i.get('title'))
def runtime_text(v):
 s=str(v or '').strip();m=re.search(r'(\d+)\s*(?:minutes?|mins?|min|phút)',s,re.I) if s else None
 return f"{m.group(1)} phút" if m else s
def parse_extra(extra):
 p={}
 if extra:
  raw=unquote_plus(str(extra))
  try:
   j=json.loads(raw)
   if isinstance(j,dict):p.update(j)
  except:pass
  if not p:
   try:
    for k,v in parse_qs(raw,keep_blank_values=True).items():p[k]=v[-1] if v else ''
   except:pass
 return p
def snapshots_of(i):
 m=i.get('metadata') or {};return [x for x in (m.get('snapshots') or []) if isinstance(x,str) and x.startswith(('http://','https://'))][:24]
def keywords_of(i):
 m=i.get('metadata') or {};vals=[]
 for k in ('genres','genre','tags','categories','category'):
  v=m.get(k)
  if isinstance(v,list):vals+=map(str,v)
  elif v:vals.append(str(v))
 blob=' '.join(vals+[str(m.get('description') or ''),str(i.get('title') or '')]).lower()
 return sorted({vi for en,vi in GENRES.items() if en in blob})
def series_id(i):return str(i.get('id') or '').replace('movie_manko_','series_manko_',1)
def movie_id_from_series(sid):return str(sid or '').split(':',1)[0].replace('series_manko_','movie_manko_',1)
def base_meta(i):
 if not i:return None
 m=i.get('metadata') or {};actors=m.get('actors') or [];rt=runtime_text(m.get('runtime'));desc=m.get('descriptionVi') or m.get('description') or ''
 out={"id":series_id(i),"type":"series","name":movie_title(i),"poster":i.get('poster') or None,"background":i.get('poster') or None,"posterShape":"poster","description":desc,"website":i.get('movieUrl') or None}
 if actors:out['cast']=actors
 if rt:out['runtime']=rt
 if m.get('year'):out['releaseInfo']=str(m['year'])
 elif m.get('releaseDate'):out['releaseInfo']=str(m['releaseDate'])
 gs=keywords_of(i)
 if gs:out['genres']=gs
 details=[]
 if m.get('rating'):details.append(f"Đánh giá: {m['rating']} ⭐")
 if rt:details.append(f"Thời lượng: {rt}")
 if m.get('studio'):details.append(f"Hãng sản xuất: {m['studio']}")
 if m.get('size'):details.append(f"Dung lượng: {m['size']}")
 if m.get('releaseDate'):details.append(f"Ngày phát hành: {m['releaseDate']}")
 country=m.get('countryVi') or m.get('country');language=m.get('languageVi') or m.get('language')
 if country:details.append(f"Quốc gia: {country}")
 if language:details.append(f"Ngôn ngữ: {language}")
 if actors:details.append('Diễn viên: '+', '.join(actors))
 if details:out['description']=(desc+'\n\n' if desc else '')+'\n'.join(details)
 return out
def series_meta_of(i,with_videos=False):
 out=base_meta(i)
 if out and with_videos:
  shots=snapshots_of(i)
  out['videos']=[{"id":f"{out['id']}:1:{n}","title":f"Ảnh {n}","season":1,"episode":n,"thumbnail":u,"overview":movie_title(i)} for n,u in enumerate(shots,1)]
 return out
def ordered_items(store):
 movies=store.get('movies') or {};order=(store.get('catalog') or {}).get('urls') or [];byurl={x.get('movieUrl'):x for x in movies.values()};items=[byurl[u] for u in order if u in byurl];seen={x.get('id') for x in items};items.extend(sorted((x for x in movies.values() if x.get('id') not in seen),key=lambda x:x.get('collectedAt') or '',reverse=True));return items
def streams_for(i):
 if not i:return []
 src=i.get('streams') or ([{'name':'#1','url':i.get('streamUrl'),'headers':i.get('headers') or {}}] if i.get('streamUrl') else []);out=[]
 for n,s in enumerate(src,1):
  if not s.get('url'):continue
  h=dict(s.get('headers') or {});h.setdefault('Referer','https://javplayer.cc/');label=s.get('name') or f'#{n}';out.append({'name':label,'title':f"{movie_title(i)} • {label}",'url':s['url'],'behaviorHints':{'notWebReady':True,'proxyHeaders':{'request':h}}})
 return out

def register_manko_addon(app,load_store):
 @app.get('/manifest.json')
 def manifest():return jsonify(MANIFEST)
 @app.get('/catalog/series/manko_snapshots.json')
 @app.get('/catalog/series/manko_snapshots/<path:extra>.json')
 def snapshots_catalog(extra=None):
  items=ordered_items(load_store());p=parse_extra(extra);q=str(p.get('search') or request.args.get('search') or '').lower();genre=str(p.get('genre') or request.args.get('genre') or '')
  try:skip=int(p.get('skip') or request.args.get('skip') or 0)
  except:skip=0
  if q:items=[x for x in items if q in (movie_title(x)+' '+str((x.get('metadata') or {}).get('actors',[]))).lower()]
  if genre:items=[x for x in items if genre in keywords_of(x)]
  return jsonify({'metas':[series_meta_of(x,False) for x in items[skip:skip+40]]})
 @app.get('/meta/series/<sid>.json')
 def series_meta(sid):
  i=(load_store().get('movies') or {}).get(movie_id_from_series(sid));return jsonify({'meta':series_meta_of(i,True) if i else None})
 @app.get('/stream/series/<path:sid>.json')
 def series_stream(sid):return jsonify({'streams':streams_for((load_store().get('movies') or {}).get(movie_id_from_series(sid)))})

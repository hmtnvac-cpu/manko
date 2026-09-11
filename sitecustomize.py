import builtins, io, json, os

_REAL_OPEN=builtins.open
_REAL_REPLACE=os.replace
_DB_URL=os.environ.get('DATABASE_URL','')
_TARGET=os.environ.get('MANKO_RESULTS_FILE','/tmp/manko_collector_results.json')
_TMP=_TARGET+'.tmp'
_PENDING={}

def _db_load():
    if not _DB_URL:return None
    try:
        import psycopg
        with psycopg.connect(_DB_URL) as c:
            with c.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS app_state (id text PRIMARY KEY, data jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
                cur.execute("SELECT data FROM app_state WHERE id='manko_store'")
                row=cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None

def _db_save(obj):
    if not _DB_URL:return False
    try:
        import psycopg
        with psycopg.connect(_DB_URL) as c:
            with c.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS app_state (id text PRIMARY KEY, data jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())")
                cur.execute("INSERT INTO app_state(id,data,updated_at) VALUES('manko_store',%s::jsonb,now()) ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data,updated_at=now()",(json.dumps(obj,ensure_ascii=False),))
            c.commit()
        return True
    except Exception:
        return False

class _WriteBuffer(io.StringIO):
    def __init__(self,path):super().__init__();self._path=path
    def close(self):
        if not self.closed:_PENDING[self._path]=self.getvalue()
        super().close()

def _open(file,mode='r',*args,**kwargs):
    path=str(file)
    if _DB_URL and path==_TARGET and 'r' in mode:
        obj=_db_load()
        if obj is not None:return io.StringIO(json.dumps(obj,ensure_ascii=False))
    if _DB_URL and path==_TMP and ('w' in mode or 'a' in mode):return _WriteBuffer(path)
    return _REAL_OPEN(file,mode,*args,**kwargs)

def _replace(src,dst,*args,**kwargs):
    if _DB_URL and str(src)==_TMP and str(dst)==_TARGET and str(src) in _PENDING:
        raw=_PENDING.pop(str(src))
        try:obj=json.loads(raw)
        except Exception:obj={}
        if _db_save(obj):return None
    return _REAL_REPLACE(src,dst,*args,**kwargs)

builtins.open=_open
os.replace=_replace

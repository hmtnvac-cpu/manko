const MANKO_SYNC_API='https://manko-api.onrender.com';
const MANKO_STATE_KEY='manko_collector_state';
const MANKO_SCAN_KEY='manko_catalog_scan';
const MANKO_SYNC_KEY='manko_sync_status';

async function srGetJson(path){
  try{const r=await fetch(MANKO_SYNC_API+path,{cache:'no-store'});const text=await r.text();let data=null;try{data=JSON.parse(text)}catch{}return{ok:r.ok,status:r.status,data,text:text.slice(0,500)}}
  catch(e){return{ok:false,error:String(e?.message||e)}}
}
async function srPost(path,body){
  try{const r=await fetch(MANKO_SYNC_API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const text=await r.text();let data=null;try{data=JSON.parse(text)}catch{}return{ok:r.ok,status:r.status,data,text:text.slice(0,500)}}
  catch(e){return{ok:false,error:String(e?.message||e)}}
}
async function syncAllManko(reason='manual'){
  const local=await chrome.storage.local.get([MANKO_STATE_KEY,MANKO_SCAN_KEY]);
  const state=local[MANKO_STATE_KEY]||{results:[],errors:[]};
  const scan=local[MANKO_SCAN_KEY]||null;
  const results=(state.results||[]).filter(x=>x.source==='manko'&&x.movieUrl&&x.streamUrl);
  const errors=(state.errors||[]).filter(x=>x.source==='manko'&&x.movieUrl);
  const st={running:true,reason,startedAt:new Date().toISOString(),catalog:false,resultsTotal:results.length,resultsSynced:0,errorsTotal:errors.length,errorsSynced:0,lastError:null};
  await chrome.storage.local.set({[MANKO_SYNC_KEY]:st});
  if(scan?.urls?.length){const r=await srPost('/collector/catalog',{pageUrl:scan.pageUrl,urls:scan.urls});st.catalog=!!r.ok;if(!r.ok)st.lastError=r.error||r.text||`catalog HTTP ${r.status}`;await chrome.storage.local.set({[MANKO_SYNC_KEY]:{...st}})}
  for(const item of results){const r=await srPost('/collector/result',item);if(r.ok)st.resultsSynced++;else st.lastError=r.error||r.text||`result HTTP ${r.status}`;if(st.resultsSynced%10===0||!r.ok)await chrome.storage.local.set({[MANKO_SYNC_KEY]:{...st}})}
  for(const item of errors){const r=await srPost('/collector/error',item);if(r.ok)st.errorsSynced++;else st.lastError=r.error||r.text||`error HTTP ${r.status}`}
  st.running=false;st.finishedAt=new Date().toISOString();st.ok=st.resultsSynced===st.resultsTotal&&st.errorsSynced===st.errorsTotal&&(!scan?.urls?.length||st.catalog);
  await chrome.storage.local.set({[MANKO_SYNC_KEY]:st});return st;
}
async function autoRestoreManko(){
  const local=await chrome.storage.local.get([MANKO_STATE_KEY,MANKO_SCAN_KEY]);
  const state=local[MANKO_STATE_KEY]||{results:[]};
  const localResolved=(state.results||[]).filter(x=>x.source==='manko'&&x.streamUrl).length;
  const localCatalog=local[MANKO_SCAN_KEY]?.urls?.length||0;
  if(!localResolved&&!localCatalog)return{ok:true,skipped:'no local Manko data'};
  const stats=await srGetJson('/collector/stats');
  if(!stats.ok)return syncAllManko('server-unreachable-or-reset');
  const serverResolved=Number(stats.data?.resolved||0),serverCatalog=Number(stats.data?.catalogTotal||0);
  if(serverResolved<localResolved||serverCatalog<localCatalog)return syncAllManko('auto-restore');
  return{ok:true,skipped:'server already complete',serverResolved,localResolved,serverCatalog,localCatalog};
}
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
  if(msg?.type==='SYNC_ALL'){syncAllManko('manual').then(sendResponse);return true}
  if(msg?.type==='AUTO_RESTORE'){autoRestoreManko().then(sendResponse);return true}
  if(msg?.type==='GET_SYNC_STATUS'){chrome.storage.local.get(MANKO_SYNC_KEY).then(r=>sendResponse(r[MANKO_SYNC_KEY]||null));return true}
});
chrome.runtime.onInstalled.addListener(()=>autoRestoreManko().catch(()=>{}));
chrome.runtime.onStartup.addListener(()=>autoRestoreManko().catch(()=>{}));

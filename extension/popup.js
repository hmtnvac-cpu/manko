const $ = id => document.getElementById(id);
const SCAN_KEY = 'manko_catalog_scan';

function show(state){
  $('status').textContent = JSON.stringify({
    running: state.running,
    current: state.current,
    queued: state.queue?.length || 0,
    results: state.results?.length || 0,
    errors: state.errors?.length || 0,
    lastResult: state.results?.at(-1) || null,
    lastError: state.errors?.at(-1) || null
  }, null, 2);
}

async function refresh(){
  const state = await chrome.runtime.sendMessage({type:'GET_STATE'});
  show(state);
  const scan = (await chrome.storage.local.get(SCAN_KEY))[SCAN_KEY];
  if (scan) $('scanInfo').textContent = `Catalog scan: ${scan.count} unique movie URL(s) from ${scan.pageUrl}`;
  return state;
}

$('start').onclick = async () => {
  const urls = $('urls').value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const r = await chrome.runtime.sendMessage({type:'START_QUEUE', urls});
  $('status').textContent = `Added ${r.added} URL(s)`;
  setTimeout(refresh, 500);
};

$('scanManko').onclick = async () => {
  $('scanInfo').textContent = 'Scanning current Manko page…';
  const tabs = await chrome.tabs.query({active:true,currentWindow:true});
  const tab = tabs[0];
  if (!tab?.id || !String(tab.url || '').startsWith('https://manko.fun/')) {
    $('scanInfo').textContent = 'Open a Manko catalog/list page in the active tab first.';
    return;
  }
  try {
    const r = await chrome.tabs.sendMessage(tab.id,{type:'SCAN_MANKO_CATALOG'});
    if (!r?.ok) throw new Error(r?.error || 'Scan failed');
    const urls = [...new Set(r.urls || [])];
    const scan = {pageUrl:r.pageUrl,count:urls.length,urls,scannedAt:new Date().toISOString()};
    await chrome.storage.local.set({[SCAN_KEY]:scan});
    const sync = await chrome.runtime.sendMessage({type:'SYNC_CATALOG',pageUrl:r.pageUrl,urls});
    $('scanInfo').textContent = `Found ${urls.length} unique movie URL(s). Server sync: ${sync?.ok ? 'OK' : 'FAILED'}.`;
  } catch (e) {
    $('scanInfo').textContent = `Scan error: ${e.message || e}`;
  }
};

$('test10').onclick = async () => {
  const scan = (await chrome.storage.local.get(SCAN_KEY))[SCAN_KEY];
  if (!scan?.urls?.length) {
    $('scanInfo').textContent = 'Scan a Manko catalog first.';
    return;
  }
  const state = await chrome.runtime.sendMessage({type:'GET_STATE'});
  const done = new Set((state.results || []).map(x => x.movieUrl));
  const failed = new Set((state.errors || []).map(x => x.movieUrl));
  const batch = scan.urls.filter(u => !done.has(u) && !failed.has(u)).slice(0,10);
  if (!batch.length) {
    $('scanInfo').textContent = 'No untested movie URLs remain in this scan.';
    return;
  }
  const r = await chrome.runtime.sendMessage({type:'START_QUEUE',urls:batch});
  $('scanInfo').textContent = `Batch test started: ${r.added} movie(s), maximum 10.`;
  setTimeout(refresh,500);
};

$('refresh').onclick = refresh;

$('clear').onclick = async () => {
  await chrome.runtime.sendMessage({type:'CLEAR_RESULTS'});
  refresh();
};

$('export').onclick = async () => {
  const state = await chrome.runtime.sendMessage({type:'GET_STATE'});
  const scan = (await chrome.storage.local.get(SCAN_KEY))[SCAN_KEY] || null;
  const blob = new Blob([JSON.stringify({scan,results:state.results || [], errors:state.errors || []}, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({url, filename:`manko-streams-${Date.now()}.json`, saveAs:true});
  setTimeout(() => URL.revokeObjectURL(url), 30000);
};

refresh();
setInterval(refresh, 2000);

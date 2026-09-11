const $ = id => document.getElementById(id);

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
  return state;
}

$('start').onclick = async () => {
  const urls = $('urls').value.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const r = await chrome.runtime.sendMessage({type:'START_QUEUE', urls});
  $('status').textContent = `Added ${r.added} URL(s)`;
  setTimeout(refresh, 500);
};

$('refresh').onclick = refresh;

$('clear').onclick = async () => {
  await chrome.runtime.sendMessage({type:'CLEAR_RESULTS'});
  refresh();
};

$('export').onclick = async () => {
  const state = await chrome.runtime.sendMessage({type:'GET_STATE'});
  const blob = new Blob([JSON.stringify({results:state.results || [], errors:state.errors || []}, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({url, filename:`manko-streams-${Date.now()}.json`, saveAs:true});
  setTimeout(() => URL.revokeObjectURL(url), 30000);
};

refresh();
setInterval(refresh, 2000);

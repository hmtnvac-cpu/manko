const STATE_KEY = 'manko_collector_state';

async function getState() {
  const r = await chrome.storage.local.get(STATE_KEY);
  return r[STATE_KEY] || {queue:[], running:false, current:null, results:[], errors:[]};
}
async function setState(state) { await chrome.storage.local.set({[STATE_KEY]: state}); }

function sourceFor(url='') {
  if (url.startsWith('https://manko.fun/movie-info/')) return 'manko';
  if (url.startsWith('https://film4k.net/watch/')) return 'film4k';
  return null;
}

async function processNext() {
  const state = await getState();
  if (state.running || !state.queue.length) return;
  const movieUrl = state.queue.shift();
  const source = sourceFor(movieUrl);
  if (!source) {
    state.errors.push({movieUrl,error:'Unsupported URL',collectedAt:new Date().toISOString()});
    await setState(state);
    return processNext();
  }
  state.running = true;
  state.current = {source,movieUrl,movieTabId:null,playerTabId:null,title:null,playerUrl:null,candidates:[]};
  await setState(state);
  const tab = await chrome.tabs.create({url: movieUrl, active:false});
  state.current.movieTabId = tab.id;
  await setState(state);
}

async function finishCurrent(success, payload) {
  const state = await getState();
  const cur = state.current || {};
  if (success) state.results.push({...cur, ...payload, collectedAt:new Date().toISOString()});
  else state.errors.push({...cur, ...payload, collectedAt:new Date().toISOString()});
  for (const id of [cur.movieTabId, cur.playerTabId]) {
    if (id) { try { await chrome.tabs.remove(id); } catch (_) {} }
  }
  state.running = false;
  state.current = null;
  await setState(state);
  processNext();
}

function headerMap(headers=[]) {
  const out = {};
  for (const h of headers) {
    const k = String(h.name || '').toLowerCase();
    if (['referer','origin','user-agent','authorization','cookie'].includes(k)) out[h.name] = h.value || '';
  }
  return out;
}

function scoreCandidate(url='') {
  let s = 0;
  if (/\.m3u8(?:\?|$)/i.test(url)) s += 100;
  if (/master|playlist|manifest/i.test(url)) s += 30;
  if (/\/api\/hls\//i.test(url)) s += 20;
  if (/fiml4k\.fun/i.test(url)) s += 10;
  if (/segment|\.m4s|\.ts(?:\?|$)/i.test(url)) s -= 40;
  return s;
}

async function captureFilm4k(details) {
  const state = await getState();
  const cur = state.current;
  if (!cur || cur.source !== 'film4k' || details.tabId !== cur.movieTabId) return;
  const u = details.url || '';
  if (!(/\.m3u8(?:\?|$)/i.test(u) || /\/api\/hls\//i.test(u) || /fiml4k\.fun/i.test(u))) return;
  const headers = headerMap(details.requestHeaders || []);
  if (!cur.candidates.some(x => x.url === u)) {
    cur.candidates.push({url:u,method:details.method||'GET',headers,score:scoreCandidate(u),seenAt:new Date().toISOString()});
    cur.candidates = cur.candidates.slice(-100);
    await setState(state);
  }
}

chrome.webRequest.onBeforeSendHeaders.addListener(
  details => { captureFilm4k(details).catch(()=>{}); },
  {urls:['https://film4k.net/*','https://*.film4k.net/*','https://fiml4k.fun/*','https://*.fiml4k.fun/*']},
  ['requestHeaders','extraHeaders']
);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === 'START_QUEUE') {
      const state = await getState();
      const incoming = [...new Set((msg.urls || []).map(x => x.trim()).filter(x => sourceFor(x)))];
      state.queue.push(...incoming);
      await setState(state);
      processNext();
      sendResponse({ok:true, added:incoming.length});
      return;
    }

    if (msg.type === 'MANKO_PLAYER_FOUND') {
      const state = await getState();
      if (!state.current) return;
      state.current.title = msg.title;
      state.current.playerUrl = msg.playerUrl;
      const tab = await chrome.tabs.create({url: msg.playerUrl, active:false});
      state.current.playerTabId = tab.id;
      await setState(state);
      sendResponse({ok:true});
      return;
    }

    if (msg.type === 'JAVPLAYER_RESULT') {
      if (msg.ok) {
        await finishCurrent(true, {
          playerId: msg.playerId,
          playerUrl: msg.playerUrl,
          streamUrl: msg.streamUrl,
          vttUrl: msg.vttUrl,
          headers: msg.headers || {Referer:'https://javplayer.cc/'}
        });
      } else {
        await finishCurrent(false, {
          playerId: msg.playerId,
          playerUrl: msg.playerUrl,
          status: msg.status || null,
          contentType: msg.contentType || null,
          error: msg.error || null,
          raw: msg.raw || null
        });
      }
      sendResponse({ok:true});
      return;
    }

    if (msg.type === 'FILM4K_READY') {
      const state = await getState();
      if (state.current?.source === 'film4k') {
        state.current.title = msg.title || state.current.title;
        await setState(state);
      }
      sendResponse({ok:true});
      return;
    }

    if (msg.type === 'FILM4K_DONE') {
      const state = await getState();
      if (!state.current || state.current.source !== 'film4k') return;
      state.current.title = msg.title || state.current.title;
      const candidates = [...(state.current.candidates || [])].sort((a,b)=>(b.score||0)-(a.score||0));
      const best = candidates[0] || null;
      if (best) {
        await finishCurrent(true, {
          streamUrl: best.url,
          headers: best.headers || {},
          candidates,
          captureMode:'webRequest'
        });
      } else {
        await finishCurrent(false, {error:msg.error || 'No Film4K HLS/API request captured', candidates:[]});
      }
      sendResponse({ok:true});
      return;
    }

    if (msg.type === 'GET_STATE') {
      sendResponse(await getState());
      return;
    }

    if (msg.type === 'CLEAR_RESULTS') {
      const state = await getState();
      state.results = [];
      state.errors = [];
      await setState(state);
      sendResponse({ok:true});
      return;
    }
  })();
  return true;
});

chrome.runtime.onInstalled.addListener(() => processNext());
chrome.runtime.onStartup.addListener(() => processNext());

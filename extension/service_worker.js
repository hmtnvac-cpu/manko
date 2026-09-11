const STATE_KEY = 'manko_collector_state';

async function getState() {
  const r = await chrome.storage.local.get(STATE_KEY);
  return r[STATE_KEY] || {queue:[], running:false, current:null, results:[], errors:[]};
}
async function setState(state) { await chrome.storage.local.set({[STATE_KEY]: state}); }

async function processNext() {
  const state = await getState();
  if (state.running || !state.queue.length) return;
  const movieUrl = state.queue.shift();
  state.running = true;
  state.current = {movieUrl, movieTabId:null, playerTabId:null, title:null, playerUrl:null};
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

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === 'START_QUEUE') {
      const state = await getState();
      const incoming = [...new Set((msg.urls || []).map(x => x.trim()).filter(x => x.startsWith('https://manko.fun/movie-info/')))];
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

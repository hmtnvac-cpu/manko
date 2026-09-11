(() => {
  async function resolve() {
    const m = location.pathname.match(/\/e\/([^/?#]+)/);
    if (!m) return;
    const id = m[1];
    const u = new URL('/stream', location.origin);
    new URLSearchParams(location.search).forEach((v, k) => u.searchParams.set(k, v));
    u.searchParams.set('id', id);

    let resp;
    try {
      resp = await fetch(u.toString(), {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Accept': 'application/json,text/plain,*/*' }
      });
    } catch (e) {
      chrome.runtime.sendMessage({type:'JAVPLAYER_RESULT', ok:false, playerId:id, playerUrl:location.href, error:String(e)});
      return;
    }

    const raw = await resp.text();
    let data = null;
    try { data = JSON.parse(raw); } catch (_) {}

    if (!resp.ok || !data || !data.media || !data.media.stream) {
      chrome.runtime.sendMessage({
        type:'JAVPLAYER_RESULT',
        ok:false,
        playerId:id,
        playerUrl:location.href,
        status:resp.status,
        contentType:resp.headers.get('content-type'),
        raw:raw.slice(0,1500)
      });
      return;
    }

    chrome.runtime.sendMessage({
      type:'JAVPLAYER_RESULT',
      ok:true,
      playerId:id,
      playerUrl:location.href,
      streamUrl:data.media.stream,
      vttUrl:data.media.vtt || null,
      headers:{Referer:'https://javplayer.cc/'}
    });
  }

  // Allow Cloudflare or page JS to settle first.
  setTimeout(resolve, 2500);
})();

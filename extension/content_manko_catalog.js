(() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const normalize = href => {
    try {
      const u = new URL(href, location.origin);
      if (u.origin !== 'https://manko.fun') return null;
      if (!u.pathname.startsWith('/movie-info/')) return null;
      u.searchParams.delete('utm_source');
      u.searchParams.delete('utm_medium');
      u.searchParams.delete('utm_campaign');
      return u.href;
    } catch { return null; }
  };

  function collect() {
    const out = new Set();
    for (const a of document.querySelectorAll('a[href]')) {
      const u = normalize(a.href || a.getAttribute('href'));
      if (u) out.add(u);
    }
    return [...out];
  }

  async function scanDeep() {
    const found = new Set(collect());
    let stable = 0;
    let previous = found.size;

    for (let round = 0; round < 30 && stable < 5; round++) {
      window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'});

      for (const el of [...document.querySelectorAll('button,a,[role="button"]')]) {
        const t = (el.textContent || '').trim().toLowerCase();
        if (/load more|show more|xem thêm|more/.test(t)) {
          try { el.click(); } catch (_) {}
        }
      }

      await sleep(1200);
      for (const u of collect()) found.add(u);

      if (found.size === previous) stable++;
      else stable = 0;
      previous = found.size;
    }

    window.scrollTo({top: 0, behavior: 'instant'});
    return [...found];
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg?.type !== 'SCAN_MANKO_CATALOG') return;
    (async () => {
      const urls = await scanDeep();
      sendResponse({ok:true, pageUrl:location.href, count:urls.length, urls});
    })().catch(e => sendResponse({ok:false,error:String(e?.message || e)}));
    return true;
  });
})();

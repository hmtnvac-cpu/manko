(() => {
  const seen = new Set();
  const interesting = [];
  const abs = value => { try { return new URL(value, location.href).href; } catch { return ''; } };
  const add = (url, kind='resource') => {
    const u = abs(url);
    if (!u || seen.has(u)) return;
    seen.add(u);
    if (/\.m3u8(?:$|\?)/i.test(u) || /\.mpd(?:$|\?)/i.test(u) || /\.(?:mp4|mkv|webm)(?:$|\?)/i.test(u) || /stream|playlist|manifest|episode|source|play|video|media|api/i.test(u)) {
      interesting.push({url:u, kind});
    }
  };

  const snapshot = () => {
    try {
      for (const e of performance.getEntriesByType('resource')) add(e.name, e.initiatorType || 'resource');
    } catch {}
    for (const v of document.querySelectorAll('video')) {
      add(v.currentSrc || v.src, 'video');
      add(v.poster, 'poster');
      for (const s of v.querySelectorAll('source[src]')) add(s.src, 'source');
    }
    for (const i of document.querySelectorAll('iframe[src]')) add(i.src, 'iframe');
  };

  const meta = () => ({
    title: document.querySelector('meta[property="og:title"]')?.content || document.title || '',
    poster: document.querySelector('meta[property="og:image"]')?.content || document.querySelector('meta[name="twitter:image"]')?.content || '',
    description: document.querySelector('meta[name="description"]')?.content || document.querySelector('meta[property="og:description"]')?.content || '',
    canonical: document.querySelector('link[rel="canonical"]')?.href || location.href
  });

  const report = () => {
    snapshot();
    chrome.runtime.sendMessage({
      type:'FILM4K_PROBE',
      pageUrl:location.href,
      meta:meta(),
      resources:interesting.slice(-250)
    });
  };

  const obs = new MutationObserver(snapshot);
  const start = () => {
    if (!document.documentElement) return setTimeout(start, 50);
    obs.observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['src','href']});
    snapshot();
    let n=0;
    const timer=setInterval(() => {
      snapshot();
      n++;
      if (n % 3 === 0) report();
      if (n >= 30) { clearInterval(timer); report(); obs.disconnect(); }
    }, 1000);
  };
  start();
})();

(() => {
  const text = el => (el?.textContent || '').replace(/\s+/g,' ').trim();
  const uniq = xs => [...new Set(xs.filter(Boolean))];

  function firstPlayer() {
    for (const el of document.querySelectorAll('iframe')) {
      const src = el.src || el.getAttribute('src') || '';
      if (src.includes('javplayer.cc/e/')) return src.replace(/&amp;/g,'&');
    }
    const html = document.documentElement.innerHTML.replace(/\\\//g, '/');
    const m = html.match(/https:\/\/javplayer\.cc\/e\/[^"'<>\\s]+/);
    return m ? m[0].replace(/&amp;/g,'&') : '';
  }

  function poster() {
    return document.querySelector('meta[property="og:image"]')?.content ||
      document.querySelector('meta[name="twitter:image"]')?.content ||
      document.querySelector('video')?.poster ||
      document.querySelector('img[src*="poster"],img[src*="cover"]')?.src || '';
  }

  function metadata() {
    const description = document.querySelector('meta[name="description"]')?.content ||
      document.querySelector('meta[property="og:description"]')?.content ||
      text(document.querySelector('[class*="description"],[class*="overview"],[class*="synopsis"]'));
    const genres = uniq([...document.querySelectorAll('a[href*="genre"],a[href*="the-loai"],a[href*="category"]')]
      .map(text).filter(x => x && x.length < 80));
    return {
      description,
      genres,
      source:'film4k',
      sourceUrl:location.href
    };
  }

  let sent = false;
  function send() {
    if (sent) return true;
    const player = firstPlayer();
    if (!player) return false;
    sent = true;
    const movieId = (location.pathname.split('/').filter(Boolean).pop() || '').replace(/[^a-zA-Z0-9_-]/g,'');
    chrome.runtime.sendMessage({
      type:'MANKO_PLAYER_FOUND',
      movieId,
      movieUrl:location.href,
      title:document.querySelector('meta[property="og:title"]')?.content || document.title,
      poster:poster(),
      playerUrls:[player],
      playerUrl:player,
      metadata:metadata()
    });
    return true;
  }

  if (send()) return;
  const obs = new MutationObserver(() => { if (send()) obs.disconnect(); });
  obs.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});
  setTimeout(() => obs.disconnect(),15000);
})();

(() => {
  function findPlayerUrl() {
    const iframes = [...document.querySelectorAll('iframe')];
    for (const el of iframes) {
      const src = el.src || el.getAttribute('src') || '';
      if (src.includes('https://javplayer.cc/e/')) return src;
    }
    const html = document.documentElement.innerHTML.replace(/\\\//g, '/');
    const m = html.match(/https:\/\/javplayer\.cc\/e\/[^"'<>\\s]+/);
    return m ? m[0].replace(/&amp;/g, '&') : null;
  }

  function findPoster() {
    const values = [
      document.querySelector('meta[property="og:image"]')?.content,
      document.querySelector('meta[name="twitter:image"]')?.content,
      document.querySelector('video')?.poster,
      document.querySelector('img[src*="cover"]')?.src,
      document.querySelector('img')?.src
    ].filter(Boolean);
    return values[0] || '';
  }

  function send() {
    const playerUrl = findPlayerUrl();
    if (!playerUrl) return false;
    chrome.runtime.sendMessage({
      type: 'MANKO_PLAYER_FOUND',
      movieUrl: location.href,
      title: document.title,
      poster: findPoster(),
      playerUrl
    });
    return true;
  }

  if (send()) return;
  const obs = new MutationObserver(() => {
    if (send()) obs.disconnect();
  });
  obs.observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['src']});
  setTimeout(() => obs.disconnect(), 30000);
})();

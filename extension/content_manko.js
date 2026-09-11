(() => {
  const text = el => (el?.textContent || '').replace(/\s+/g,' ').trim();
  const uniq = xs => [...new Set(xs.filter(Boolean))];

  function playerUrls() {
    const out = [];
    for (const el of document.querySelectorAll('iframe')) {
      const src = el.src || el.getAttribute('src') || '';
      if (src.includes('javplayer.cc/e/')) out.push(src);
    }
    const html = document.documentElement.innerHTML.replace(/\\\//g, '/');
    for (const m of html.matchAll(/https:\/\/javplayer\.cc\/e\/[^"'<>\\s]+/g)) out.push(m[0]);
    return uniq(out.map(x=>x.replace(/&amp;/g,'&')));
  }

  function poster() {
    return document.querySelector('meta[property="og:image"]')?.content ||
      document.querySelector('meta[name="twitter:image"]')?.content ||
      document.querySelector('video')?.poster ||
      document.querySelector('img[src*="cover"]')?.src || '';
  }

  function metaValue(labels) {
    const wanted = labels.map(x=>x.toLowerCase());
    for (const el of document.querySelectorAll('div,li,p,tr,dt')) {
      const s = text(el);
      const low = s.toLowerCase();
      if (!wanted.some(x=>low.startsWith(x))) continue;
      const colon = s.indexOf(':');
      if (colon >= 0) return s.slice(colon+1).trim();
      const next = el.nextElementSibling;
      if (next) return text(next);
    }
    return '';
  }

  function metadata() {
    const description = document.querySelector('meta[name="description"]')?.content ||
      text(document.querySelector('[class*="description"], [class*="synopsis"], [class*="overview"]'));
    const genres = uniq([...document.querySelectorAll('a[href*="genre"],a[href*="category"],a[href*="tag"]')].map(text));
    const actors = uniq([...document.querySelectorAll('a[href*="actor"],a[href*="actress"],a[href*="star"]')].map(text));
    return {
      description,
      genres,
      actors,
      code: metaValue(['code','movie code','品番']),
      runtime: metaValue(['runtime','duration','length','収録時間']),
      year: metaValue(['year','release year','発売年']),
      releaseDate: metaValue(['release date','released','発売日']),
      studio: metaValue(['studio','maker','label','メーカー']),
      country: metaValue(['country','国']),
      language: metaValue(['language','言語'])
    };
  }

  function send() {
    const players = playerUrls();
    if (!players.length) return false;
    chrome.runtime.sendMessage({
      type:'MANKO_PLAYER_FOUND', movieUrl:location.href, title:document.title,
      poster:poster(), playerUrls:players, playerUrl:players[0], metadata:metadata()
    });
    return true;
  }
  if (send()) return;
  const obs = new MutationObserver(()=>{ if(send()) obs.disconnect(); });
  obs.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});
  setTimeout(()=>obs.disconnect(),30000);
})();

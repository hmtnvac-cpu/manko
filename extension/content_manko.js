(() => {
  const text = el => (el?.textContent || '').replace(/\s+/g,' ').trim();
  const uniq = xs => [...new Set(xs.filter(Boolean))];
  const movieId = (location.pathname.match(/\/movie-info\/([^/?#]+)/) || [])[1] || '';

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

  function field(label) {
    const wanted=label.toLowerCase();
    for(const el of document.querySelectorAll('div,p,li,span')){
      const s=text(el), low=s.toLowerCase();
      if(!low.startsWith(wanted+':')) continue;
      const value=s.slice(s.indexOf(':')+1).trim();
      if(value && value.length<500) return value;
    }
    return '';
  }

  function actors() {
    const raw=field('Actor') || field('Actors');
    if(raw) return uniq(raw.split(',').map(x=>x.trim()));
    return uniq([...document.querySelectorAll('a[href*="actor"],a[href*="actress"],a[href*="star"]')].map(text));
  }

  function metadata() {
    const description = document.querySelector('meta[name="description"]')?.content ||
      text(document.querySelector('[class*="description"], [class*="synopsis"], [class*="overview"]'));
    const runtimeRaw=field('Video Duration') || field('Duration') || field('Runtime');
    const ratingRaw=field('Rating');
    return {
      description,
      actors:actors(),
      code:field('Title'),
      rating:ratingRaw,
      runtime:runtimeRaw,
      size:field('Size'),
      releaseDate:field('Release date') || field('Release Date'),
      studio:field('Maker') || field('Studio'),
      country:'Japan',
      language:'Japanese'
    };
  }

  function send(){
    const players=playerUrls();
    if(!players.length) return false;
    chrome.runtime.sendMessage({type:'MANKO_PLAYER_FOUND',movieId,movieUrl:location.href,title:document.title,poster:poster(),playerUrls:players,playerUrl:players[0],metadata:metadata()});
    return true;
  }
  if(send()) return;
  const obs=new MutationObserver(()=>{if(send())obs.disconnect()});
  obs.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});
  setTimeout(()=>obs.disconnect(),30000);
})();

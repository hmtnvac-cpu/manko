(() => {
  const text = el => (el?.textContent || '').replace(/\s+/g,' ').trim();
  const uniq = xs => [...new Set(xs.filter(Boolean))];
  const movieId = (location.pathname.match(/\/movie-info\/([^/?#]+)/) || [])[1] || '';

  function isServerError() {
    const t=(document.title||'').trim();
    const b=(document.body?.innerText||'').slice(0,800);
    return /^500\b/i.test(t) || /500\s+internal\s+server\s+error/i.test(b) || /internal\s+server\s+error/i.test(b);
  }

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

  function genres(){
    const raw=field('Genre')||field('Genres')||field('Category')||field('Categories');
    const list=[];
    if(raw) list.push(...raw.split(/[,|]/).map(x=>x.trim()));
    for(const a of document.querySelectorAll('a[href*="genre"],a[href*="category"],a[href*="cate-list"]')){
      const t=text(a);if(t&&t.length<80)list.push(t);
    }
    return uniq(list).filter(x=>x && !/^genre$/i.test(x) && !/^category$/i.test(x)).slice(0,40);
  }

  function snapshotUrls(){
    const out=[];
    const add=src=>{try{const u=new URL(src,location.href);if(/^https?:$/.test(u.protocol))out.push(u.href)}catch{}};
    const headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,p,span')].filter(el=>/^snapshots?$/i.test(text(el)));
    for(const h of headings){
      let box=h.parentElement;
      for(let depth=0;box&&depth<4;depth++,box=box.parentElement){
        const imgs=[...box.querySelectorAll('img')];
        if(imgs.length>=2){for(const img of imgs)add(img.currentSrc||img.src||img.getAttribute('data-src')||img.getAttribute('data-lazy-src'));break}
      }
    }
    for(const img of document.querySelectorAll('img')){
      const src=img.currentSrc||img.src||img.getAttribute('data-src')||img.getAttribute('data-lazy-src')||'';
      if(/snapshot|sample|scene|screenshot|thumb/i.test(src))add(src);
    }
    const p=poster();return uniq(out).filter(u=>u!==p).slice(0,24);
  }

  function metadata() {
    const description = document.querySelector('meta[name="description"]')?.content ||
      text(document.querySelector('[class*="description"], [class*="synopsis"], [class*="overview"]'));
    return {
      description,actors:actors(),genres:genres(),code:field('Title'),rating:field('Rating'),
      runtime:field('Video Duration') || field('Duration') || field('Runtime'),size:field('Size'),
      releaseDate:field('Release date') || field('Release Date'),studio:field('Maker') || field('Studio'),
      country:'Japan',language:'Japanese',snapshots:snapshotUrls()
    };
  }

  let sent=false;
  function send(){
    if(sent) return true;
    if(isServerError()){
      sent=true;chrome.runtime.sendMessage({type:'MANKO_PAGE_ERROR',movieUrl:location.href,status:500,error:'Manko HTTP 500'});return true;
    }
    const player=firstPlayer();if(!player)return false;
    sent=true;chrome.runtime.sendMessage({type:'MANKO_PLAYER_FOUND',movieId,movieUrl:location.href,title:document.title,poster:poster(),playerUrls:[player],playerUrl:player,metadata:metadata()});return true;
  }
  if(send()) return;
  const obs=new MutationObserver(()=>{if(send())obs.disconnect()});
  obs.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});
  setTimeout(()=>{if(!sent&&isServerError())send();obs.disconnect()},12000);
})();

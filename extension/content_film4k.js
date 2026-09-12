(() => {
  const seen=new Set();
  const resources=[];
  const abs=v=>{try{return new URL(v,location.href).href}catch{return String(v||'')}};
  const isMedia=u=>/\.m3u8(?:$|\?)/i.test(u)||/\.mpd(?:$|\?)/i.test(u)||/\.(?:mp4|mkv|webm)(?:$|\?)/i.test(u);
  const interesting=u=>isMedia(u)||/stream|playlist|episode|source|play|video|media|api|blob:/i.test(u);
  function add(url,kind='resource',extra={}){
    const u=abs(url);
    const uniqueKey=kind+'|'+u+'|'+JSON.stringify(extra.requestHeaders||{})+'|'+String(extra.requestBody||'')+'|'+String(extra.responseBody||'');
    if(!u||seen.has(uniqueKey))return;
    if(!interesting(u)&&kind!=='ready'&&kind!=='mediasource'&&kind!=='api-detail')return;
    seen.add(uniqueKey);resources.push({url:u,kind,...extra});if(resources.length>1000)resources.splice(0,resources.length-1000);
  }
  function snapshot(){
    try{for(const e of performance.getEntriesByType('resource'))add(e.name,e.initiatorType||'resource')}catch{}
    try{for(const v of document.querySelectorAll('video,audio')){add(v.currentSrc||v.src,'media');for(const s of v.querySelectorAll('source[src]'))add(s.src,'source')}}catch{}
    try{for(const i of document.querySelectorAll('iframe[src]'))add(i.src,'iframe')}catch{}
  }
  const meta=()=>({title:document.querySelector('meta[property="og:title"]')?.content||document.title||'',poster:document.querySelector('meta[property="og:image"]')?.content||document.querySelector('meta[name="twitter:image"]')?.content||'',description:document.querySelector('meta[name="description"]')?.content||document.querySelector('meta[property="og:description"]')?.content||'',canonical:document.querySelector('link[rel="canonical"]')?.href||location.href,frameUrl:location.href,topFrame:window===top,collectorVersion:'4.3.0'});
  function mediaLinks(){
    snapshot();
    const out=[],uSeen=new Set();
    for(const r of resources){
      const u=String(r?.url||'');
      if(!isMedia(u)||uSeen.has(u))continue;
      uSeen.add(u);
      let type='MEDIA';
      if(/\.m3u8(?:$|\?)/i.test(u))type='HLS'; else if(/\.mpd(?:$|\?)/i.test(u))type='DASH'; else if(/\.mp4(?:$|\?)/i.test(u))type='MP4';
      out.push({url:u,type,kind:r.kind||'',status:r.status||0,requestHeaders:r.requestHeaders||{},responseHeaders:r.responseHeaders||{}});
    }
    return out;
  }
  let sending=false,pending=false;
  async function report(){
    if(sending){pending=true;return}
    sending=true;pending=false;snapshot();
    try{await chrome.runtime.sendMessage({type:'FILM4K_PROBE',pageUrl:top===window?location.href:(document.referrer||location.href),meta:meta(),resources:resources.slice(-1000)})}catch{}
    sending=false;if(pending)setTimeout(report,100);
  }
  window.addEventListener('message',e=>{
    const d=e.data;if(!d||d.__film4kProbe!==true)return;
    add(d.url||'',d.kind||'page-hook',{method:d.method||'',mime:d.mime||'',frame:d.href||location.href,status:d.status||0,contentType:d.contentType||'',requestHeaders:d.requestHeaders||{},responseHeaders:d.responseHeaders||{},requestBody:d.requestBody||'',responseBody:d.responseBody||'',probeVersion:d.probeVersion||''});
    if(d.kind==='ready'||d.url||d.kind==='api-detail')report();
  });
  chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
    if(msg?.type!=='FILM4K_SCAN_NOW')return;
    (async()=>{
      snapshot();
      await report();
      sendResponse({ok:true,pageUrl:location.href,title:document.title||'',links:mediaLinks(),resources:resources.length});
    })();
    return true;
  });
  const obs=new MutationObserver(()=>snapshot());
  function start(){if(!document.documentElement)return setTimeout(start,50);obs.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src','href']});snapshot();report();let n=0;const t=setInterval(()=>{snapshot();report();if(++n>=180){clearInterval(t);obs.disconnect()}},1000)}
  start();
})();
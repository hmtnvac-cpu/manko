(() => {
  if (window.__FILM4K_DEEP_PROBE__) return;
  window.__FILM4K_DEEP_PROBE__ = true;
  const emit=(kind,data={})=>{try{window.postMessage({__film4kProbe:true,kind,href:location.href,ts:Date.now(),...data},'*')}catch{}};
  const interesting=u=>/\.m3u8(?:$|\?)/i.test(u)||/\.mpd(?:$|\?)/i.test(u)||/\.(?:mp4|mkv|webm)(?:$|\?)/i.test(u)||/stream|playlist|manifest|episode|source|play|video|media|api/i.test(u);
  const scanText=(text,kind='body')=>{
    if(typeof text!=='string'||!text) return;
    const matches=text.match(/https?:\/\/[^\s"'<>\\]+/g)||[];
    for(const raw of matches.slice(0,100)) if(interesting(raw)) emit(kind,{url:raw});
  };
  try{
    const ofetch=window.fetch;
    window.fetch=async function(input,init){
      const url=typeof input==='string'?input:input?.url||'';
      emit('fetch',{url,method:init?.method||'GET'});
      const res=await ofetch.apply(this,arguments);
      try{const c=res.clone();const ct=c.headers.get('content-type')||'';if(/json|text|javascript|mpegurl|dash\+xml/i.test(ct)){c.text().then(t=>scanText(t.slice(0,300000),'fetch-body')).catch(()=>{})}}catch{}
      return res;
    };
  }catch{}
  try{
    const X=XMLHttpRequest.prototype, oopen=X.open, osend=X.send;
    X.open=function(method,url){this.__f4k={method,url};return oopen.apply(this,arguments)};
    X.send=function(){
      const info=this.__f4k||{};emit('xhr',{url:info.url||'',method:info.method||'GET'});
      this.addEventListener('load',()=>{try{if(typeof this.responseText==='string')scanText(this.responseText.slice(0,300000),'xhr-body')}catch{}});
      return osend.apply(this,arguments);
    };
  }catch{}
  try{
    const oc=URL.createObjectURL;
    URL.createObjectURL=function(obj){const u=oc.apply(this,arguments);emit('blob',{url:u,objType:obj?.constructor?.name||''});return u};
  }catch{}
  try{
    const oadd=MediaSource.prototype.addSourceBuffer;
    MediaSource.prototype.addSourceBuffer=function(mime){emit('mediasource',{mime});return oadd.apply(this,arguments)};
  }catch{}
  try{
    const set=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'src')?.set;
    if(set)Object.defineProperty(HTMLMediaElement.prototype,'src',{set(v){emit('media-src',{url:v});return set.call(this,v)},get:Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'src')?.get,configurable:true});
  }catch{}
  emit('ready',{title:document.title||''});
})();
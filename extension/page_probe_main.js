(() => {
  if (window.__FILM4K_DEEP_PROBE__) return;
  window.__FILM4K_DEEP_PROBE__ = true;
  const emit=(kind,data={})=>{try{window.postMessage({__film4kProbe:true,kind,href:location.href,ts:Date.now(),...data},'*')}catch{}};
  const interesting=u=>/\.m3u8(?:$|\?)/i.test(u)||/\.mpd(?:$|\?)/i.test(u)||/\.(?:mp4|mkv|webm)(?:$|\?)/i.test(u)||/stream|playlist|episode|source|play|video|media|api/i.test(u);
  const targetApi=u=>/\/api\/(?:watch(?:\/|$)|play-ticket(?:$|\?)|home(?:$|\?)|explore(?:$|\?)|movies(?:$|\?)|series(?:$|\?)|search(?:$|\?))/i.test(String(u||''));
  const targetMedia=u=>/\.m3u8(?:$|\?)/i.test(String(u||''))||/\.mpd(?:$|\?)/i.test(String(u||''));
  const clip=v=>{try{return typeof v==='string'?v.slice(0,500000):JSON.stringify(v).slice(0,500000)}catch{return String(v||'').slice(0,500000)}};
  const headerObj=h=>{const o={};try{if(h instanceof Headers){h.forEach((v,k)=>o[k]=v)}else if(Array.isArray(h)){for(const [k,v] of h)o[k]=String(v)}else if(h&&typeof h==='object'){for(const [k,v] of Object.entries(h))o[k]=String(v)}}catch{}return o};
  const scanText=(text,kind='body')=>{if(typeof text!=='string'||!text)return;const matches=text.match(/https?:\/\/[^\s"'<>\\]+/g)||[];for(const raw of matches.slice(0,200))if(interesting(raw))emit(kind,{url:raw})};
  try{
    const ofetch=window.fetch;
    window.fetch=async function(input,init={}){
      const url=typeof input==='string'?input:input?.url||'';
      const method=init?.method||input?.method||'GET';
      const reqHeaders={...headerObj(input?.headers),...headerObj(init?.headers)};
      let reqBody='';try{reqBody=clip(init?.body||'')}catch{}
      emit('fetch',{url,method,requestHeaders:(targetApi(url)||targetMedia(url))?reqHeaders:{},requestBody:targetApi(url)?reqBody:''});
      const res=await ofetch.apply(this,arguments);
      try{
        const c=res.clone();const ct=c.headers.get('content-type')||'';
        if(/json|text|javascript|mpegurl|dash\+xml/i.test(ct)||targetApi(url)||targetMedia(url)){
          c.text().then(t=>{const body=clip(t);scanText(body,'fetch-body');if(targetApi(url)||targetMedia(url))emit('api-detail',{url,method,status:res.status,requestHeaders:reqHeaders,responseHeaders:headerObj(res.headers),requestBody:reqBody,responseBody:body,contentType:ct})}).catch(()=>{});
        }
      }catch{}
      return res;
    };
  }catch{}
  try{
    const X=XMLHttpRequest.prototype,oopen=X.open,osend=X.send,oset=X.setRequestHeader;
    X.open=function(method,url){this.__f4k={method,url,headers:{}};return oopen.apply(this,arguments)};
    X.setRequestHeader=function(k,v){try{this.__f4k=this.__f4k||{headers:{}};this.__f4k.headers=this.__f4k.headers||{};this.__f4k.headers[String(k)]=String(v)}catch{}return oset.apply(this,arguments)};
    X.send=function(body){
      const info=this.__f4k||{};const reqBody=clip(body||'');const reqHeaders=info.headers||{};
      emit('xhr',{url:info.url||'',method:info.method||'GET',requestHeaders:(targetApi(info.url)||targetMedia(info.url))?reqHeaders:{},requestBody:targetApi(info.url)?reqBody:''});
      this.addEventListener('load',()=>{try{const text=typeof this.responseText==='string'?clip(this.responseText):'';scanText(text,'xhr-body');if(targetApi(info.url)||targetMedia(info.url))emit('api-detail',{url:info.url||'',method:info.method||'GET',status:this.status,requestHeaders:reqHeaders,responseHeaders:this.getAllResponseHeaders?.()||'',requestBody:reqBody,responseBody:text,contentType:this.getResponseHeader('content-type')||''})}catch{}});
      return osend.apply(this,arguments);
    };
  }catch{}
  try{const oc=URL.createObjectURL;URL.createObjectURL=function(obj){const u=oc.apply(this,arguments);emit('blob',{url:u,objType:obj?.constructor?.name||''});return u}}catch{}
  try{const oadd=MediaSource.prototype.addSourceBuffer;MediaSource.prototype.addSourceBuffer=function(mime){emit('mediasource',{mime});return oadd.apply(this,arguments)}}catch{}
  try{const d=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'src');if(d?.set)Object.defineProperty(HTMLMediaElement.prototype,'src',{set(v){emit('media-src',{url:v});return d.set.call(this,v)},get:d.get,configurable:true})}catch{}
  emit('ready',{title:document.title||'',probeVersion:'4.2.2'});
})();
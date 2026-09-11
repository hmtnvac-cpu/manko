// Translation/metadata repair patch. Loaded after service_worker.js so it can replace translateVi.
const JP_RE=/[\u3040-\u30ff\u3400-\u9fff]/;

async function gt(text,sl,tl){
  text=String(text||'').trim();
  if(!text)return'';
  try{
    const u='https://translate.googleapis.com/translate_a/single?client=gtx&sl='+encodeURIComponent(sl)+'&tl='+encodeURIComponent(tl)+'&dt=t&q='+encodeURIComponent(text.slice(0,4500));
    const r=await fetch(u,{cache:'no-store'});
    if(!r.ok)return text;
    const j=await r.json();
    return (j?.[0]||[]).map(x=>x?.[0]||'').join('').trim()||text;
  }catch{return text}
}

function cleanVietnamese(s){
  s=String(s||'').replace(/\s+/g,' ').trim();
  // Remove obvious machine-translation boilerplate and duplicated punctuation.
  s=s.replace(/([.!?])\1+/g,'$1')
     .replace(/\s+([,.!?;:])/g,'$1')
     .replace(/([,.!?;:])([^\s])/g,'$1 $2')
     .replace(/\bvideo này sẽ làm tan chảy não bạn\b/gi,'')
     .replace(/\bngười ủng hộ thủ dâm\b/gi,'người phụ nữ có vẻ ngoài trẻ trung')
     .replace(/\bcó lỗi nói chuyện tục tĩu ngọt ngào\b/gi,'có cách nói chuyện táo bạo nhưng cuốn hút')
     .replace(/\bquyến rũ tràn ngập tình mẫu tử\b/gi,'mang vẻ quyến rũ, dịu dàng')
     .replace(/\s{2,}/g,' ').trim();
  return s;
}

// Override the raw translator from service_worker.js.
translateVi=async function(text){
  text=String(text||'').trim();
  if(!text)return'';
  if(/^[A-Z0-9_-]{2,24}$/.test(text))return text;
  let base=text;
  // Japanese -> English -> Vietnamese is noticeably more stable for Manko marketing copy.
  if(JP_RE.test(text)) base=await gt(text,'ja','en');
  let vi=await gt(base,JP_RE.test(base)?'auto':'en','vi');
  if(!vi||vi===base)vi=await gt(base,'auto','vi');
  return cleanVietnamese(vi||text);
};

async function repairTranslations(){
  const progress={running:true,total:0,done:0,updated:0,errors:0,current:null,startedAt:new Date().toISOString()};
  await chrome.storage.local.set({manko_translation_repair:progress});
  let skip=0,total=1,items=[];
  while(skip<total){
    const j=await getJson(`${API}/collector/results?skip=${skip}&limit=500`);
    if(!j)break;
    items.push(...(j.items||[]));
    total=Number(j.total||0);skip+=500;
    if(skip>50000)break;
  }
  progress.total=items.length;await chrome.storage.local.set({manko_translation_repair:progress});
  for(const item of items){
    const m=item.metadata||{};
    const sourceTitle=m.originalTitle||item.title||'';
    const sourceDesc=m.description||'';
    progress.current=item.movieUrl||item.id;await chrome.storage.local.set({manko_translation_repair:progress});
    try{
      const [titleVi,descriptionVi]=await Promise.all([translateVi(sourceTitle),translateVi(sourceDesc)]);
      const meta={...m,titleVi,descriptionVi};
      const r=await postJson('/collector/metadata',{movieUrl:item.movieUrl,title:item.title,titleVi,poster:item.poster,metadata:meta});
      if(r.ok)progress.updated++;else progress.errors++;
    }catch{progress.errors++}
    progress.done++;await chrome.storage.local.set({manko_translation_repair:progress});
  }
  progress.running=false;progress.current=null;progress.finishedAt=new Date().toISOString();
  await chrome.storage.local.set({manko_translation_repair:progress});
  return progress;
}

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{
  if(msg?.type==='REPAIR_TRANSLATIONS'){
    repairTranslations().then(sendResponse).catch(e=>sendResponse({running:false,error:String(e)}));
    return true;
  }
  if(msg?.type==='GET_TRANSLATION_REPAIR'){
    chrome.storage.local.get('manko_translation_repair').then(r=>sendResponse(r.manko_translation_repair||null));
    return true;
  }
});

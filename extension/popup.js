const $=id=>document.getElementById(id);
let busyMessage='';
function show(s){if(busyMessage)return;$('status').textContent=JSON.stringify({running:s.running,current:s.current,queued:s.queue?.length||0,results:s.results?.length||0,errors:s.errors?.length||0,lastResult:s.results?.at(-1)||null,lastError:s.errors?.at(-1)||null},null,2)}
async function refresh(){try{show(await chrome.runtime.sendMessage({type:'GET_STATE'}))}catch(e){if(!busyMessage)$('status').textContent='Lỗi đọc trạng thái: '+(e.message||e)}}

async function scanActiveManko(tabId){
  const injected=await chrome.scripting.executeScript({
    target:{tabId},
    func:async()=>{
      const sleep=ms=>new Promise(r=>setTimeout(r,ms));
      const normalize=href=>{try{const u=new URL(href,location.origin);if(u.origin!=='https://manko.fun'||!u.pathname.startsWith('/movie-info/'))return null;['utm_source','utm_medium','utm_campaign'].forEach(k=>u.searchParams.delete(k));return u.href}catch{return null}};
      const collect=()=>{const out=new Set();for(const a of document.querySelectorAll('a[href]')){const u=normalize(a.href||a.getAttribute('href'));if(u)out.add(u)}return [...out]};
      const found=new Set(collect());let stable=0,previous=found.size;
      for(let round=0;round<12&&stable<3;round++){
        window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
        for(const el of [...document.querySelectorAll('button,a,[role="button"]')]){const t=(el.textContent||'').trim().toLowerCase();if(/load more|show more|xem thêm|more/.test(t)){try{el.click()}catch{}}}
        await sleep(700);for(const u of collect())found.add(u);if(found.size===previous)stable++;else stable=0;previous=found.size;
        if(found.size>=10)break;
      }
      window.scrollTo({top:0,behavior:'instant'});
      return {ok:true,pageUrl:location.href,count:found.size,urls:[...found]};
    }
  });
  return injected?.[0]?.result||{ok:false,urls:[]};
}

$('start10').onclick=async()=>{try{
  const tabs=await chrome.tabs.query({active:true,currentWindow:true});
  const tab=tabs[0];
  if(!tab?.id||!String(tab.url||'').startsWith('https://manko.fun/')){busyMessage='Hãy mở trang danh sách Manko trước.';$('status').textContent=busyMessage;return}
  busyMessage='Đang quét trực tiếp trang Manko…';$('status').textContent=busyMessage;
  const scan=await scanActiveManko(tab.id);
  if(!scan?.ok||!scan.urls?.length){busyMessage=`Không tìm thấy link phim trên trang hiện tại (${scan?.count||0}).`;$('status').textContent=busyMessage;return}
  const batch=[...new Set(scan.urls)].slice(0,10);
  await chrome.runtime.sendMessage({type:'CLEAR_RESULTS'});
  const r=await chrome.runtime.sendMessage({type:'START_QUEUE',urls:batch});
  busyMessage='';
  $('status').textContent=`Đã tìm thấy ${scan.urls.length} link. Bắt đầu xử lý ${r.added} phim.`;
  setTimeout(refresh,1200);
}catch(e){busyMessage='Lỗi bắt đầu test: '+(e.message||e);$('status').textContent=busyMessage}};
$('refresh').onclick=()=>{busyMessage='';refresh()};
refresh();
setInterval(refresh,2000);

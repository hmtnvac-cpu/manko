const $=id=>document.getElementById(id);
function show(s){$('status').textContent=JSON.stringify({running:s.running,current:s.current,queued:s.queue?.length||0,results:s.results?.length||0,errors:s.errors?.length||0,lastResult:s.results?.at(-1)||null,lastError:s.errors?.at(-1)||null},null,2)}
async function refresh(){try{show(await chrome.runtime.sendMessage({type:'GET_STATE'}))}catch(e){$('status').textContent='Lỗi đọc trạng thái: '+(e.message||e)}}
$('start10').onclick=async()=>{try{
  const tabs=await chrome.tabs.query({active:true,currentWindow:true});
  const tab=tabs[0];
  if(!tab?.id||!String(tab.url||'').startsWith('https://manko.fun/')){ $('status').textContent='Hãy mở trang danh sách Manko trước.'; return; }
  $('status').textContent='Đang quét danh sách Manko…';
  const scan=await chrome.tabs.sendMessage(tab.id,{type:'SCAN_MANKO_CATALOG'});
  if(!scan?.ok||!scan.urls?.length){$('status').textContent='Không lấy được danh sách phim từ trang Manko.';return;}
  const batch=[...new Set(scan.urls)].slice(0,10);
  await chrome.runtime.sendMessage({type:'CLEAR_RESULTS'});
  const r=await chrome.runtime.sendMessage({type:'START_QUEUE',urls:batch});
  $('status').textContent=`Bắt đầu test mới ${r.added} phim. Tổng link tìm thấy: ${scan.urls.length}.`;
  setTimeout(refresh,1000);
}catch(e){$('status').textContent='Lỗi bắt đầu test: '+(e.message||e)}};
$('refresh').onclick=refresh;
refresh();
setInterval(refresh,2000);

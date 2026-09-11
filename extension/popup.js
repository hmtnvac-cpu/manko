const $=id=>document.getElementById(id);
let busy='';
function show(s){if(busy)return;const c=s.crawl||{},workers=Object.values(s.workers||{}).filter(Boolean).map(w=>({id:w.id,movie:w.movieUrl}));$('status').textContent=JSON.stringify({workersActive:workers.length,workers,queued:s.queue?.length||0,success:s.successCount||0,errors:s.errors?.length||0,crawlActive:!!c.active,pagesScanned:c.pagesScanned||0,pagesPending:c.pagesPending?.length||0,moviesFound:c.moviesFound||0,totalDiscovered:s.totalDiscovered||0,currentPage:c.currentPage||null,crawlError:c.lastError||null},null,2)}
async function refresh(){try{show(await chrome.runtime.sendMessage({type:'GET_STATE'}))}catch(e){if(!busy)$('status').textContent='Lỗi đọc trạng thái: '+(e.message||e)}}
$('crawlAll').onclick=async()=>{try{busy='Đang khởi động quét toàn bộ Manko…';$('status').textContent=busy;const r=await chrome.runtime.sendMessage({type:'START_FULL_CRAWL'});busy='';$('status').textContent=r?.ok?`Đã bắt đầu với ${r.workers||3} worker song song. Server đã có ${r.alreadyStored||0} phim; phim đó sẽ tự bỏ qua.`:`Không thể bắt đầu: ${r?.error||'unknown'}`;setTimeout(refresh,800)}catch(e){busy='Lỗi crawler: '+(e.message||e);$('status').textContent=busy}};
$('retry').onclick=async()=>{busy='';const r=await chrome.runtime.sendMessage({type:'RETRY_ERRORS'});$('status').textContent=`Đã đưa lại ${r.added||0} phim lỗi vào queue.`;setTimeout(refresh,600)};
$('refresh').onclick=()=>{busy='';refresh()};
refresh();setInterval(refresh,1500);

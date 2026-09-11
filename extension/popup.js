const $=id=>document.getElementById(id);
function show(s){$('status').textContent=JSON.stringify({running:s.running,current:s.current,queued:s.queue?.length||0,results:s.results?.length||0,errors:s.errors?.length||0,lastResult:s.results?.at(-1)||null,lastError:s.errors?.at(-1)||null},null,2)}
async function refresh(){try{show(await chrome.runtime.sendMessage({type:'GET_STATE'}))}catch(e){$('status').textContent='Lỗi đọc trạng thái: '+(e.message||e)}}
$('backfill').onclick=async()=>{try{$('status').textContent='Đang lấy danh sách phim hiện có từ server…';const r=await chrome.runtime.sendMessage({type:'BACKFILL_RESULTS'});if(!r?.ok){$('status').textContent='Backfill failed: '+(r?.error||'unknown');return}$('status').textContent=`Đã nạp ${r.queued} phim từ ${r.source}. Chrome bắt đầu xử lý tự động…`;setTimeout(refresh,1000)}catch(e){$('status').textContent='Backfill failed: '+(e.message||e)}};
$('refresh').onclick=refresh;
refresh();
setInterval(refresh,2000);

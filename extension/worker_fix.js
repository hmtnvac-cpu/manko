// Clean-run worker fix: every new full crawl starts from zero locally and reprocesses every discovered movie.
// Also keeps workers alive whenever queue contains work.
const WATCHDOG_ALARM='manko_worker_watchdog';

pumpWorkers=async function(){
  const s=await getState();
  s.queue=Array.isArray(s.queue)?s.queue:[];
  s.workers=s.workers||{};
  const active=new Set(Object.values(s.workers).filter(Boolean).map(w=>w.movieUrl));
  let changed=false;

  for(let id=0;id<WORKERS;id++){
    if(s.workers[id])continue;
    let u=null;
    while(s.queue.length){
      const candidate=s.queue.shift();
      if(isManko(candidate)&&!active.has(candidate)){u=candidate;break}
    }
    if(!u)continue;
    s.workers[id]={id,movieUrl:u,movieId:null,movieTabId:null,playerTabId:null,title:'',titleVi:'',poster:'',metadata:{},stream:null,startedAt:new Date().toISOString()};
    active.add(u);changed=true;
  }
  if(changed)await setState(s);

  const latest=await getState();
  for(let id=0;id<WORKERS;id++){
    const w=latest.workers?.[id];
    if(!w||w.movieTabId||w.playerTabId)continue;
    try{
      const t=await chrome.tabs.create({url:w.movieUrl,active:false});
      const s2=await getState();
      if(s2.workers?.[id]&&s2.workers[id].movieUrl===w.movieUrl){
        s2.workers[id].movieTabId=t.id;
        await setState(s2);
        await armWorker(id,30);
      }
    }catch(e){await failWorker(id,'open movie failed: '+String(e))}
  }
};

enqueueMovies=async function(s,urls){
  s.queue=Array.isArray(s.queue)?s.queue:[];
  const busy=activeUrls(s),queued=new Set(s.queue);
  for(const u of urls||[]){
    if(isManko(u)&&!busy.has(u)&&!queued.has(u)){s.queue.push(u);queued.add(u)}
  }
};

startFullCrawl=async function(){
  // Close tabs owned by the previous run first.
  const old=await getState();
  for(const w of Object.values(old.workers||{}))await closeTabs(w);
  if(old.crawl?.tabId)try{await chrome.tabs.remove(old.crawl.tabId)}catch{}
  for(let i=0;i<WORKERS;i++)await chrome.alarms.clear(workerAlarm(i));

  const fresh={
    queue:[],workers:{},retryCounts:{},errors:[],results:[],successCount:0,totalDiscovered:0,
    crawl:{active:true,startUrl:'https://manko.fun/home',pagesPending:['https://manko.fun/home'],pagesVisited:[],orderedUrls:[],serverDone:[],pagesScanned:0,moviesFound:0,currentPage:null,tabId:null,processing:false,startedAt:new Date().toISOString(),lastError:null,pageSignatures:{},familiesCompleted:{}}
  };
  await setState(fresh);
  chrome.alarms.create(WATCHDOG_ALARM,{periodInMinutes:0.2});
  await gotoNextPage();
  return{ok:true,alreadyStored:0,workers:WORKERS,mode:'clean-full-reprocess'};
};

chrome.alarms.onAlarm.addListener(async a=>{
  if(a.name!==WATCHDOG_ALARM)return;
  const s=await getState();
  const active=Object.values(s.workers||{}).filter(Boolean).length;
  if((s.queue?.length||0)>0&&active===0)await pumpWorkers();
  if(!s.crawl?.active&&(s.queue?.length||0)===0&&active===0)await chrome.alarms.clear(WATCHDOG_ALARM);
});

// Recover any stranded queue immediately when this patch loads.
setTimeout(async()=>{
  const s=await getState();
  if((s.queue?.length||0)>0&&Object.values(s.workers||{}).filter(Boolean).length===0)await pumpWorkers();
},500);

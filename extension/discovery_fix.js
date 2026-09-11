// Discovery-only fix. Do NOT override worker/stream/result logic.
function dfNormalize(u){
  try{
    const U=new URL(u,'https://manko.fun/home');
    if(U.origin!=='https://manko.fun')return null;
    if(!(U.pathname==='/home'||U.pathname.includes('movie-list')||U.pathname.includes('cate-list')))return null;
    U.hash='';return U.href;
  }catch{return null}
}
function dfFamily(u){
  try{const U=new URL(u);U.searchParams.delete('page');U.hash='';return U.href}catch{return String(u||'')}
}
function dfNext(u){
  try{
    const U=new URL(u);
    if(U.pathname==='/home')return null;
    const n=Math.max(1,parseInt(U.searchParams.get('page')||'1',10)||1);
    if(n>=2000)return null;
    U.searchParams.set('page',String(n+1));return U.href;
  }catch{return null}
}
function dfSig(urls){return [...new Set(urls||[])].sort().join('|')}

// Keep the proven worker logic untouched; replace discovery only.
handleCrawlLoaded=async function(tabId){
  const s=await getState(),c=s.crawl;
  if(!c?.active||c.tabId!==tabId||c.processing)return;
  c.processing=true;c.pageSignatures=c.pageSignatures||{};c.completedFamilies=c.completedFamilies||{};
  await setState(s);
  try{
    const p=await scrapeCatalog(tabId);
    const cur=dfNormalize(p.url||c.currentPage)||c.currentPage;
    if(!c.pagesVisited.includes(cur))c.pagesVisited.push(cur);

    // Discover all category/list families exposed by the site.
    for(const raw of p.pages||[]){
      const u=dfNormalize(raw);if(!u)continue;
      if(!c.pagesVisited.includes(u)&&!c.pagesPending.includes(u))c.pagesPending.push(u);
    }

    const family=dfFamily(cur),sig=dfSig(p.movies);
    const seen=c.pageSignatures[family]||[];
    const repeated=!!sig&&seen.includes(sig);
    if(sig&&!repeated)seen.push(sig);
    c.pageSignatures[family]=seen.slice(-2000);

    const fresh=[];
    for(const u of p.movies||[]){
      if(!c.orderedUrls.includes(u)){c.orderedUrls.push(u);fresh.push(u)}
    }
    c.pagesScanned=c.pagesVisited.length;
    c.moviesFound=c.orderedUrls.length;
    s.totalDiscovered=c.orderedUrls.length;
    await enqueueMovies(s,fresh);

    // Generate page N+1 ourselves. Empty/repeated page is the only normal stop for a family.
    if(cur!=='https://manko.fun/home'&&p.movies?.length&&!repeated){
      const nxt=dfNext(cur);
      if(nxt&&!c.pagesVisited.includes(nxt)&&!c.pagesPending.includes(nxt))c.pagesPending.push(nxt);
    }else if(family&&(!p.movies?.length||repeated)){
      c.completedFamilies[family]=true;
    }

    c.processing=false;
    await setState(s);
    await syncCatalogOrder(s);
    pumpWorkers();
    gotoNextPage();
  }catch(e){
    c.lastError=String(e);c.processing=false;
    if(c.currentPage&&!c.pagesVisited.includes(c.currentPage))c.pagesVisited.push(c.currentPage);
    await setState(s);gotoNextPage();
  }
};

startFullCrawl=async function(){
  const s=await getState();
  if(s.crawl?.active)return{ok:false,error:'Crawler đang chạy'};
  const done=await serverDoneSet();
  s.queue=[];s.errors=[];s.retryCounts=s.retryCounts||{};s.workers={};
  s.crawl={
    active:true,startUrl:'https://manko.fun/home',pagesPending:['https://manko.fun/home'],pagesVisited:[],orderedUrls:[],serverDone:[...done],
    pagesScanned:0,moviesFound:0,currentPage:null,tabId:null,processing:false,startedAt:new Date().toISOString(),lastError:null,
    pageSignatures:{},completedFamilies:{}
  };
  await setState(s);gotoNextPage();return{ok:true,alreadyStored:done.size,workers:WORKERS,discovery:'exhaustive-pagination'};
};

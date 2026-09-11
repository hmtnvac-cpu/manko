// Discovery-only fix. Stable worker/stream/result logic is intentionally untouched.
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
function dfPageNo(u){try{return Math.max(1,parseInt(new URL(u).searchParams.get('page')||'1',10)||1)}catch{return 1}}
function dfNext(u){
  try{
    const U=new URL(u);if(U.pathname==='/home')return null;
    const n=dfPageNo(U.href);if(n>=2000)return null;
    U.searchParams.set('page',String(n+1));return U.href;
  }catch{return null}
}
function dfSig(urls){return [...new Set(urls||[])].sort().join('|')}
function dfFamilyStart(u){
  try{const U=new URL(u);if(U.pathname==='/home')return U.href;U.searchParams.set('page','1');return U.href}catch{return u}
}

handleCrawlLoaded=async function(tabId){
  const s=await getState(),c=s.crawl;
  if(!c?.active||c.tabId!==tabId||c.processing)return;
  c.processing=true;
  c.pageSignatures=c.pageSignatures||{};
  c.completedFamilies=c.completedFamilies||{};
  c.deferredFamilies=c.deferredFamilies||[];
  await setState(s);

  try{
    const p=await scrapeCatalog(tabId);
    const cur=dfNormalize(p.url||c.currentPage)||c.currentPage;
    if(!c.pagesVisited.includes(cur))c.pagesVisited.push(cur);

    // Remember newly discovered list/category families in the exact order Manko exposes them,
    // but DO NOT interrupt the current family's page 1 -> 2 -> 3 sequence.
    for(const raw of p.pages||[]){
      const u=dfNormalize(raw);if(!u||u===cur)continue;
      const start=dfFamilyStart(u),fam=dfFamily(start);
      if(c.completedFamilies[fam])continue;
      if(dfFamily(cur)===fam)continue;
      if(!c.deferredFamilies.some(x=>dfFamily(x)===fam))c.deferredFamilies.push(start);
    }

    const family=dfFamily(cur),sig=dfSig(p.movies);
    const seen=c.pageSignatures[family]||[];
    const repeated=!!sig&&seen.includes(sig);
    if(sig&&!repeated)seen.push(sig);
    c.pageSignatures[family]=seen.slice(-2000);

    // Preserve exact movie order as it appears on the source page.
    const fresh=[];
    for(const u of p.movies||[]){
      if(!c.orderedUrls.includes(u)){c.orderedUrls.push(u);fresh.push(u)}
    }
    c.pagesScanned=c.pagesVisited.length;
    c.moviesFound=c.orderedUrls.length;
    s.totalDiscovered=c.orderedUrls.length;
    await enqueueMovies(s,fresh);

    // Critical ordering rule: next page of current family goes to the FRONT of the queue.
    if(cur!=='https://manko.fun/home'&&p.movies?.length&&!repeated){
      const nxt=dfNext(cur);
      if(nxt&&!c.pagesVisited.includes(nxt)){
        c.pagesPending=c.pagesPending.filter(x=>x!==nxt);
        c.pagesPending.unshift(nxt);
      }
    }else if(cur!=='https://manko.fun/home'){
      c.completedFamilies[family]=true;
      // Current family is exhausted. Only now start the next family, in source-discovery order.
      while(c.deferredFamilies.length){
        const nextFamily=c.deferredFamilies.shift();
        const fam=dfFamily(nextFamily);
        if(!c.completedFamilies[fam]&&!c.pagesVisited.includes(nextFamily)){
          c.pagesPending=c.pagesPending.filter(x=>dfFamily(x)!==fam);
          c.pagesPending.unshift(nextFamily);
          break;
        }
      }
    }else{
      // Home is only the seed. After it, start the first discovered family.
      while(c.deferredFamilies.length){
        const nextFamily=c.deferredFamilies.shift();
        if(!c.pagesVisited.includes(nextFamily)){
          c.pagesPending.unshift(nextFamily);
          break;
        }
      }
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
    pageSignatures:{},completedFamilies:{},deferredFamilies:[]
  };
  await setState(s);gotoNextPage();return{ok:true,alreadyStored:done.size,workers:WORKERS,discovery:'source-order-pagination'};
};

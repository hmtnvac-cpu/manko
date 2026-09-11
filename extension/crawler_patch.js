// Exhaustive site-crawler patch. Loaded after service_worker.js.
// It actively increments page=1,2,3... for every Manko list/category until an empty or repeated page is reached.
function crawlerNormalizeList(u){
  try{
    const U=new URL(u,'https://manko.fun/home');
    if(U.origin!=='https://manko.fun')return null;
    if(!(U.pathname==='/home'||U.pathname.includes('movie-list')||U.pathname.includes('cate-list')))return null;
    U.hash='';
    return U.href;
  }catch{return null}
}
function crawlerFamily(u){
  try{
    const U=new URL(u);U.searchParams.delete('page');U.hash='';
    const params=[...U.searchParams.entries()].sort((a,b)=>(a[0]+a[1]).localeCompare(b[0]+b[1]));
    U.search='';for(const [k,v] of params)U.searchParams.append(k,v);
    return U.href;
  }catch{return String(u||'')}
}
function crawlerNextPage(u){
  try{
    const U=new URL(u);if(U.pathname==='/home')return null;
    const n=Math.max(1,Number(U.searchParams.get('page')||1)||1);
    if(n>=2000)return null;
    U.searchParams.set('page',String(n+1));return U.href;
  }catch{return null}
}
function crawlerSignature(urls){return [...new Set(urls||[])].sort().join('|')}

scrapeCatalog=async function(tabId){
  const r=await chrome.scripting.executeScript({target:{tabId},func:async()=>{
    const wait=ms=>new Promise(r=>setTimeout(r,ms));
    const norm=h=>{try{return new URL(h,location.href).href}catch{return null}};
    const movies=()=>{const out=[],seen=new Set();for(const a of document.querySelectorAll('a[href]')){const u=norm(a.href||a.getAttribute('href'));if(u&&u.startsWith('https://manko.fun/movie-info/')&&!seen.has(u)){seen.add(u);out.push(u)}}return out};
    let stable=0,last=-1;
    for(let i=0;i<14&&stable<3;i++){
      window.scrollTo(0,document.body.scrollHeight);await wait(300);
      const n=movies().length;if(n===last)stable++;else stable=0;last=n;
    }
    const pages=[],seenPages=new Set();
    for(const a of document.querySelectorAll('a[href]')){
      const u=norm(a.href||a.getAttribute('href'));if(!u||seenPages.has(u))continue;
      try{const U=new URL(u);if(U.origin!=='https://manko.fun')continue;if(U.pathname==='/home'||U.pathname.includes('movie-list')||U.pathname.includes('cate-list')){seenPages.add(u);pages.push(u)}}catch{}
    }
    window.scrollTo(0,0);
    return{url:location.href,movies:movies(),pages};
  }});
  return r?.[0]?.result||{url:'',movies:[],pages:[]};
};

handleCrawlLoaded=async function(tabId){
  const s=await getState(),c=s.crawl;
  if(!c?.active||c.tabId!==tabId||c.processing)return;
  c.processing=true;c.pageSignatures=c.pageSignatures||{};c.familiesCompleted=c.familiesCompleted||{};
  await setState(s);
  try{
    const p=await scrapeCatalog(tabId),cur=crawlerNormalizeList(p.url||c.currentPage)||c.currentPage;
    if(!c.pagesVisited.includes(cur))c.pagesVisited.push(cur);

    // Discover every category/list link visible on the page.
    for(const raw of p.pages||[]){
      const u=crawlerNormalizeList(raw);if(!u)continue;
      if(!c.pagesVisited.includes(u)&&!c.pagesPending.includes(u))c.pagesPending.push(u);
    }

    const sig=crawlerSignature(p.movies);
    const fam=crawlerFamily(cur);
    const prior=c.pageSignatures[fam]||[];
    const repeated=!!sig&&prior.includes(sig);
    if(sig&&!repeated)prior.push(sig);
    c.pageSignatures[fam]=prior.slice(-2000);

    const fresh=[];
    for(const u of p.movies||[])if(!c.orderedUrls.includes(u)){c.orderedUrls.push(u);fresh.push(u)}
    c.pagesScanned=c.pagesVisited.length;c.moviesFound=c.orderedUrls.length;s.totalDiscovered=c.orderedUrls.length;
    await enqueueMovies(s,fresh);

    // Do not trust visible pagination. Generate page N+1 ourselves until empty or repeated.
    if(cur!=='https://manko.fun/home'&&p.movies?.length&&!repeated){
      const nxt=crawlerNextPage(cur);
      if(nxt&&!c.pagesVisited.includes(nxt)&&!c.pagesPending.includes(nxt))c.pagesPending.push(nxt);
    }else if((!p.movies?.length||repeated)&&fam){
      c.familiesCompleted[fam]=true;
    }

    c.processing=false;await setState(s);await syncCatalogOrder(s);pumpWorkers();gotoNextPage();
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
  s.crawl={active:true,startUrl:'https://manko.fun/home',pagesPending:['https://manko.fun/home'],pagesVisited:[],orderedUrls:[],serverDone:[...done],pagesScanned:0,moviesFound:0,currentPage:null,tabId:null,processing:false,startedAt:new Date().toISOString(),lastError:null,pageSignatures:{},familiesCompleted:{}};
  await setState(s);gotoNextPage();return{ok:true,alreadyStored:done.size,workers:WORKERS,mode:'exhaustive'};
};

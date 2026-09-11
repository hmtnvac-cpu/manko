const STATE_KEY='manko_collector_state';
const API='https://manko-api.onrender.com';
const HEAL='https://healertanker.com';
const REFERER='https://javplayer.cc/';
async function getState(){const r=await chrome.storage.local.get(STATE_KEY);return r[STATE_KEY]||{queue:[],running:false,current:null,results:[],errors:[],totalDiscovered:0}}
async function setState(s){await chrome.storage.local.set({[STATE_KEY]:s})}
function isManko(u=''){return u.startsWith('https://manko.fun/movie-info/')}
async function postJson(path,body){try{const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const t=await r.text();return{ok:r.ok,status:r.status,text:t.slice(0,300)}}catch(e){return{ok:false,error:String(e?.message||e)}}}
async function getJson(url){try{const r=await fetch(url,{credentials:'include',cache:'no-store'});if(!r.ok)return null;return await r.json()}catch{return null}}
const normKey=k=>String(k||'').toLowerCase().replace(/[^a-z0-9]/g,'');
function pickDeep(obj,names){const wanted=new Set(names.map(normKey));let found;function walk(v){if(found!==undefined||v==null)return;if(Array.isArray(v)){for(const x of v)walk(x);return}if(typeof v==='object'){for(const [k,val] of Object.entries(v)){if(wanted.has(normKey(k))&&(typeof val==='string'||typeof val==='number')){found=String(val);return}walk(val)}}}walk(obj);return found||''}
async function translateVi(text){text=String(text||'').trim();if(!text)return'';if(/^[A-Z0-9_-]{2,20}$/.test(text))return text;try{const u='https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q='+encodeURIComponent(text.slice(0,4500));const r=await fetch(u);if(!r.ok)return text;const j=await r.json();return (j?.[0]||[]).map(x=>x?.[0]||'').join('').trim()||text}catch{return text}}
function countryVi(v){return ({japan:'Nhật Bản',japanese:'Nhật Bản',korea:'Hàn Quốc',china:'Trung Quốc',taiwan:'Đài Loan'})[String(v||'').trim().toLowerCase()]||v}
function languageVi(v){return ({japanese:'Tiếng Nhật',english:'Tiếng Anh',korean:'Tiếng Hàn',chinese:'Tiếng Trung'})[String(v||'').trim().toLowerCase()]||v}
function cleanPageTitle(t){return String(t||'').replace(/\s*-\s*Watch Free in HD\s*\|\s*Manko\s*$/i,'').trim()}
async function enrichManko(movieId,pageTitle,pageMeta){
 const detail=await getJson(`${HEAL}/swx/movie/detail/${encodeURIComponent(movieId)}`);
 const originalTitle=pickDeep(detail,['title','name','movieTitle','englishTitle'])||cleanPageTitle(pageTitle);
 const description=pickDeep(detail,['description','overview','synopsis','plot','summary'])||pageMeta.description||'';
 const releaseDate=pageMeta.releaseDate||pickDeep(detail,['releaseDate','released','release','date','publishDate'])||'';
 const year=(releaseDate.match(/\b(19|20)\d{2}\b/)||[])[0]||pickDeep(detail,['year','releaseYear'])||'';
 const runtime=pageMeta.runtime||pickDeep(detail,['runtime','duration','length','movieLength'])||'';
 const studio=pageMeta.studio||pickDeep(detail,['studio','maker','label','publisher'])||'';
 const actors=(pageMeta.actors||[]).filter(Boolean);
 const code=pageMeta.code||cleanPageTitle(pageTitle);
 const rating=pageMeta.rating||pickDeep(detail,['rating','score'])||'';
 const size=pageMeta.size||pickDeep(detail,['size','fileSize'])||'';
 const country=pageMeta.country||'Japan',language=pageMeta.language||'Japanese';
 const [titleVi,descriptionVi]=await Promise.all([translateVi(originalTitle),translateVi(description)]);
 return {originalTitle,titleVi,description,descriptionVi,actors,code,rating,runtime,size,year,releaseDate,studio,country,countryVi:countryVi(country),language,languageVi:languageVi(language),rawAvailable:{detail:!!detail}};
}
async function processNext(){const s=await getState();if(s.running||!s.queue.length)return;const movieUrl=s.queue.shift();if(!isManko(movieUrl)){await setState(s);return processNext()}s.running=true;s.current={source:'manko',movieUrl,movieTabId:null,playerTabId:null,title:null,titleVi:null,poster:null,movieId:null,playerUrls:[],playerIndex:0,streams:[],metadata:{}};await setState(s);try{const tab=await chrome.tabs.create({url:movieUrl,active:false});s.current.movieTabId=tab.id;await setState(s)}catch(e){await finishCurrent(false,{error:String(e?.message||e)})}}
async function finishCurrent(ok,payload={}){const s=await getState(),cur=s.current||{},record={...cur,...payload,collectedAt:new Date().toISOString()};delete record.movieTabId;delete record.playerTabId;if(ok&&record.streams?.length){record.streamUrl=record.streams[0].url;record.headers=record.streams[0].headers||{Referer:REFERER};record.sync=await postJson('/collector/result',record);s.results=(s.results||[]).filter(x=>x.movieUrl!==record.movieUrl);s.results.push(record)}else{s.errors=(s.errors||[]).filter(x=>x.movieUrl!==record.movieUrl);s.errors.push(record)}for(const id of [cur.movieTabId,cur.playerTabId])if(id)try{await chrome.tabs.remove(id)}catch{}s.running=false;s.current=null;await setState(s);processNext()}
async function openNextPlayer(){const s=await getState(),c=s.current;if(!c)return;if(c.playerTabId)try{await chrome.tabs.remove(c.playerTabId)}catch{}c.playerTabId=null;if(c.playerIndex>=c.playerUrls.length){await setState(s);return finishCurrent(c.streams.length>0)}const u=c.playerUrls[c.playerIndex++];try{const tab=await chrome.tabs.create({url:u,active:false});c.playerTabId=tab.id;await setState(s)}catch{await setState(s);return openNextPlayer()}}
async function recoverAndResume(){const s=await getState();if(s.running&&s.current?.movieUrl){if(!s.queue.includes(s.current.movieUrl)&&!(s.results||[]).some(x=>x.movieUrl===s.current.movieUrl))s.queue.unshift(s.current.movieUrl);s.running=false;s.current=null;await setState(s)}processNext()}
chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{
 if(msg.type==='START_QUEUE'){const s=await getState();const done=new Set((s.results||[]).map(x=>x.movieUrl));const busy=new Set([...(s.queue||[]),s.current?.movieUrl].filter(Boolean));const incoming=[...new Set((msg.urls||[]).map(x=>String(x).trim()).filter(isManko))];const added=incoming.filter(u=>!done.has(u)&&!busy.has(u));s.queue.push(...added);s.totalDiscovered=Math.max(Number(s.totalDiscovered||0),incoming.length);await setState(s);processNext();sendResponse({ok:true,added:added.length,alreadyDone:incoming.length-added.length,total:incoming.length});return}
 if(msg.type==='SYNC_CATALOG'){sendResponse(await postJson('/collector/catalog',{pageUrl:msg.pageUrl,urls:msg.urls||[]}));return}
 if(msg.type==='RETRY_ERRORS'){const s=await getState();const done=new Set((s.results||[]).map(x=>x.movieUrl));const retry=[...new Set((s.errors||[]).map(x=>x.movieUrl).filter(u=>isManko(u)&&!done.has(u)))];s.errors=[];for(const u of retry)if(!s.queue.includes(u))s.queue.push(u);await setState(s);processNext();sendResponse({ok:true,added:retry.length});return}
 if(msg.type==='MANKO_PLAYER_FOUND'){const s=await getState();if(!s.current)return;s.current.movieId=msg.movieId||((msg.movieUrl.match(/\/movie-info\/([^/?#]+)/)||[])[1]||'');s.current.title=msg.title||'';s.current.poster=msg.poster||'';s.current.playerUrls=[...new Set((msg.playerUrls||[msg.playerUrl]).filter(Boolean))];s.current.playerIndex=0;s.current.streams=[];s.current.metadata=await enrichManko(s.current.movieId,msg.title,msg.metadata||{});s.current.titleVi=s.current.metadata.titleVi||cleanPageTitle(msg.title);await setState(s);if(!s.current.playerUrls.length){sendResponse({ok:false});return finishCurrent(false,{error:'No javplayer embed'})}await openNextPlayer();sendResponse({ok:true,players:s.current.playerUrls.length});return}
 if(msg.type==='JAVPLAYER_RESULT'){const s=await getState(),c=s.current;if(!c)return;if(msg.ok&&msg.streamUrl&&!c.streams.some(x=>x.url===msg.streamUrl))c.streams.push({name:'#'+(c.streams.length+1),url:msg.streamUrl,headers:msg.headers||{Referer:REFERER},playerId:msg.playerId,playerUrl:msg.playerUrl});await setState(s);await openNextPlayer();sendResponse({ok:true});return}
 if(msg.type==='GET_STATE'){sendResponse(await getState());return}
 })();return true});
chrome.runtime.onInstalled.addListener(()=>recoverAndResume());chrome.runtime.onStartup.addListener(()=>recoverAndResume());recoverAndResume();

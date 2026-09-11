const STATE_KEY='manko_collector_state';
const API='https://manko-api.onrender.com';
const HEAL='https://healertanker.com';
const REFERER='https://javplayer.cc/';

async function getState(){const r=await chrome.storage.local.get(STATE_KEY);return r[STATE_KEY]||{queue:[],running:false,current:null,results:[],errors:[]}}
async function setState(s){await chrome.storage.local.set({[STATE_KEY]:s})}
function sourceFor(u=''){if(u.startsWith('https://manko.fun/movie-info/'))return'manko';if(u.startsWith('https://film4k.net/watch/'))return'film4k';return null}
async function postJson(path,body){try{const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const t=await r.text();let d=null;try{d=JSON.parse(t)}catch{}return{ok:r.ok,status:r.status,data:d,text:t.slice(0,500)}}catch(e){return{ok:false,error:String(e?.message||e)}}}
async function getJson(url){try{const r=await fetch(url,{credentials:'include',cache:'no-store'});if(!r.ok)return null;return await r.json()}catch{return null}}
const normKey=k=>String(k||'').toLowerCase().replace(/[^a-z0-9]/g,'');
function pickDeep(obj,names){const wanted=new Set(names.map(normKey));let found;function walk(v){if(found!==undefined||v==null)return;if(Array.isArray(v)){for(const x of v)walk(x);return}if(typeof v==='object'){for(const [k,val] of Object.entries(v)){if(wanted.has(normKey(k))&&(typeof val==='string'||typeof val==='number')){found=String(val);return}walk(val)}}}walk(obj);return found||''}
function collectDeep(obj,names){const wanted=new Set(names.map(normKey)),out=[];function add(v){if(typeof v==='string'&&v.trim())out.push(v.trim());else if(Array.isArray(v))for(const x of v)add(x);else if(v&&typeof v==='object'){for(const [k,val] of Object.entries(v)){if(['name','title','label','value'].includes(normKey(k)))add(val)}}}function walk(v){if(v==null)return;if(Array.isArray(v)){for(const x of v)walk(x);return}if(typeof v==='object'){for(const [k,val] of Object.entries(v)){if(wanted.has(normKey(k)))add(val);walk(val)}}}walk(obj);return [...new Set(out)]}
function allUrls(v){const out=[];function walk(x){if(x==null)return;if(typeof x==='string'){for(const m of x.matchAll(/https?:\/\/[^\s"'<>]+/g))out.push(m[0]);return}if(Array.isArray(x)){for(const y of x)walk(y);return}if(typeof x==='object')for(const y of Object.values(x))walk(y)}walk(v);return [...new Set(out)]}
function findVietnameseSubtitle(obj){let best='';function walk(v,ctx=''){if(v==null||best)return;if(Array.isArray(v)){for(const x of v)walk(x,ctx);return}if(typeof v==='object'){const text=JSON.stringify(v).toLowerCase();const isVi=/vietnam|tiếng việt|tieng viet|"vi"|"vie"|"vn"/.test(text);if(isVi){for(const [k,val] of Object.entries(v)){if(typeof val==='string'&&/^https?:\/\//.test(val)&&/(\.vtt|\.srt|subtitle|caption|sub)/i.test(val)){best=val;return}if(/url|link|src|file/.test(normKey(k))&&typeof val==='string'&&/^https?:\/\//.test(val)){best=val;return}}}for(const [k,val] of Object.entries(v))walk(val,ctx+' '+k);return}if(typeof v==='string'&&/vietnam|tiếng việt|tieng viet/i.test(ctx)&&/^https?:\/\//.test(v))best=v}walk(obj);if(best)return best;return allUrls(obj).find(u=>/(vi|vie|vietnam)/i.test(u)&&/(\.vtt|\.srt|subtitle|caption|sub)/i.test(u))||''}
async function translateVi(text){text=String(text||'').trim();if(!text)return'';if(/^[A-Z0-9_-]{2,20}$/.test(text))return text;try{const u='https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q='+encodeURIComponent(text.slice(0,4500));const r=await fetch(u);if(!r.ok)return text;const j=await r.json();const vi=(j?.[0]||[]).map(x=>x?.[0]||'').join('').trim();return vi||text}catch{return text}}
const GENRE_VI={drama:'Chính kịch',romance:'Tình cảm',amateur:'Nghiệp dư',mature:'Phụ nữ trưởng thành',milf:'Phụ nữ trưởng thành',wife:'Vợ',married:'Đã kết hôn',office:'Công sở',school:'Học đường',teacher:'Giáo viên',student:'Học sinh',nurse:'Y tá',doctor:'Bác sĩ',cosplay:'Hóa trang',massage:'Mát-xa',lesbian:'Đồng tính nữ',group:'Nhiều người',outdoor:'Ngoài trời',voyeur:'Nhìn trộm',uncensored:'Không che',subtitles:'Phụ đề',subtitle:'Phụ đề',jav:'JAV'};
async function genreVi(g){const k=String(g||'').trim().toLowerCase();if(!k)return'';return GENRE_VI[k]||await translateVi(g)}
function countryVi(v){const k=String(v||'').trim().toLowerCase();return ({japan:'Nhật Bản',japanese:'Nhật Bản',korea:'Hàn Quốc',china:'Trung Quốc',taiwan:'Đài Loan'})[k]||v}
function languageVi(v){const k=String(v||'').trim().toLowerCase();return ({japanese:'Tiếng Nhật',english:'Tiếng Anh',korean:'Tiếng Hàn',chinese:'Tiếng Trung','chinese simplified':'Tiếng Trung giản thể','chinese traditional':'Tiếng Trung phồn thể'})[k]||v}
function cleanPageTitle(t){return String(t||'').replace(/\s*-\s*Watch Free in HD\s*\|\s*Manko\s*$/i,'').trim()}
async function enrichManko(movieId,pageTitle,pageMeta){
 const [detail,actorsApi,subApi]=await Promise.all([getJson(`${HEAL}/swx/movie/detail/${encodeURIComponent(movieId)}`),getJson(`${HEAL}/swx/movie/actors/${encodeURIComponent(movieId)}?size=20&page=1`),getJson(`${HEAL}/swx/subtitle-link/${encodeURIComponent(movieId)}`)]);
 const originalTitle=pickDeep(detail,['title','name','movieTitle','englishTitle'])||cleanPageTitle(pageTitle);
 const description=pickDeep(detail,['description','overview','synopsis','plot','summary'])||pageMeta.description||'';
 const actors=[...new Set([...collectDeep(actorsApi,['actors','items','content','data']),...collectDeep(detail,['actors','actresses','stars','cast']),...(pageMeta.actors||[])])].filter(x=>x.length<100);
 const genres=[...new Set([...collectDeep(detail,['genres','genre','categories','category','tags']),...(pageMeta.genres||[])])].filter(x=>x.length<80);
 const runtime=pickDeep(detail,['runtime','duration','length','movieLength'])||pageMeta.runtime||'';
 const releaseDate=pickDeep(detail,['releaseDate','released','release','date','publishDate'])||pageMeta.releaseDate||'';
 const year=pickDeep(detail,['year','releaseYear'])||pageMeta.year||(releaseDate.match(/\b(19|20)\d{2}\b/)||[])[0]||'';
 const code=pickDeep(detail,['code','movieCode','productId','productCode','dvdId'])||pageMeta.code||'';
 const studio=pickDeep(detail,['studio','maker','label','publisher'])||pageMeta.studio||'';
 const country=pickDeep(detail,['country','nation'])||pageMeta.country||'Japan';
 const language=pickDeep(detail,['language','audioLanguage'])||pageMeta.language||'Japanese';
 const [titleVi,descriptionVi,genresVi]=await Promise.all([translateVi(originalTitle),translateVi(description),Promise.all(genres.map(genreVi))]);
 let subtitleVi=findVietnameseSubtitle(subApi);
 if(!subtitleVi){for(const suffix of ['?lang=vi','?language=vi','/vi']){const x=await getJson(`${HEAL}/swx/subtitle-link/${encodeURIComponent(movieId)}${suffix}`);subtitleVi=findVietnameseSubtitle(x);if(subtitleVi)break}}
 return {originalTitle,titleVi,description,descriptionVi,genres,genresVi:[...new Set(genresVi.filter(Boolean))],actors,code,runtime,year,releaseDate,studio,country,countryVi:countryVi(country),language,languageVi:languageVi(language),subtitleVi,rawAvailable:{detail:!!detail,actors:!!actorsApi,subtitle:!!subApi}};
}

async function processNext(){const s=await getState();if(s.running||!s.queue.length)return;const movieUrl=s.queue.shift(),source=sourceFor(movieUrl);if(!source){s.errors.push({movieUrl,error:'Unsupported URL'});await setState(s);return processNext()}s.running=true;s.current={source,movieUrl,movieTabId:null,playerTabId:null,title:null,titleVi:null,poster:null,movieId:null,playerUrls:[],playerIndex:0,streams:[],metadata:{}};await setState(s);const tab=await chrome.tabs.create({url:movieUrl,active:false});s.current.movieTabId=tab.id;await setState(s)}
async function finishCurrent(ok,payload){const s=await getState(),cur=s.current||{},record={...cur,...payload,collectedAt:new Date().toISOString()};delete record.playerTabId;delete record.movieTabId;if(ok){if(cur.source==='manko')record.sync=await postJson('/collector/result',record);s.results=s.results.filter(x=>x.movieUrl!==record.movieUrl);s.results.push(record)}else{s.errors.push(record)}for(const id of [cur.movieTabId,cur.playerTabId])if(id)try{await chrome.tabs.remove(id)}catch{}s.running=false;s.current=null;await setState(s);processNext()}
async function openNextPlayer(){const s=await getState(),c=s.current;if(!c)return;if(c.playerTabId)try{await chrome.tabs.remove(c.playerTabId)}catch{}if(c.playerIndex>=c.playerUrls.length)return finishCurrent(c.streams.length>0,{streams:c.streams,streamUrl:c.streams[0]?.url||'',headers:c.streams[0]?.headers||{Referer:REFERER},subtitleVi:c.metadata?.subtitleVi||''});const u=c.playerUrls[c.playerIndex++];const tab=await chrome.tabs.create({url:u,active:false});c.playerTabId=tab.id;await setState(s)}

async function backfillExisting(){
 const s=await getState();
 let urls=[...new Set((s.results||[]).filter(x=>x.source==='manko').map(x=>x.movieUrl).filter(Boolean))];
 let source='chrome';
 if(!urls.length){
  const server=await getJson(`${API}/collector/results?skip=0&limit=500`);
  urls=[...new Set((server?.items||[]).map(x=>x.movieUrl).filter(u=>sourceFor(u)==='manko'))];
  source='server';
 }
 if(!urls.length){
  const local=await chrome.storage.local.get('manko_catalog_scan');
  urls=[...new Set((local.manko_catalog_scan?.urls||[]).filter(u=>sourceFor(u)==='manko'))].slice(0,20);
  source='catalog-first-20';
 }
 if(!urls.length)return{ok:false,queued:0,source,error:'No existing Manko movie URLs found in Chrome, server, or saved catalog scan'};
 s.queue=urls;s.running=false;s.current=null;await setState(s);processNext();return{ok:true,queued:urls.length,source};
}

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{
 if(msg.type==='START_QUEUE'){const s=await getState();const incoming=[...new Set((msg.urls||[]).map(x=>x.trim()).filter(x=>sourceFor(x)))];const existing=new Set([...(s.queue||[]),s.current?.movieUrl].filter(Boolean));const added=incoming.filter(x=>!existing.has(x));s.queue.push(...added);await setState(s);processNext();sendResponse({ok:true,added:added.length});return}
 if(msg.type==='BACKFILL_RESULTS'){sendResponse(await backfillExisting());return}
 if(msg.type==='MANKO_PLAYER_FOUND'){const s=await getState();if(!s.current)return;s.current.movieId=msg.movieId||((msg.movieUrl.match(/\/movie-info\/([^/?#]+)/)||[])[1]||'');s.current.title=msg.title;s.current.poster=msg.poster||'';s.current.playerUrls=[...new Set(msg.playerUrls||[msg.playerUrl].filter(Boolean))];s.current.playerIndex=0;s.current.streams=[];s.current.metadata=await enrichManko(s.current.movieId,msg.title,msg.metadata||{});s.current.titleVi=s.current.metadata.titleVi||cleanPageTitle(msg.title);await setState(s);await openNextPlayer();sendResponse({ok:true});return}
 if(msg.type==='JAVPLAYER_RESULT'){const s=await getState(),c=s.current;if(!c)return;if(msg.ok&&msg.streamUrl&&!c.streams.some(x=>x.url===msg.streamUrl))c.streams.push({name:'#'+(c.streams.length+1),url:msg.streamUrl,vttUrl:msg.vttUrl||null,headers:msg.headers||{Referer:REFERER},playerId:msg.playerId,playerUrl:msg.playerUrl});await setState(s);await openNextPlayer();sendResponse({ok:true});return}
 if(msg.type==='SYNC_CATALOG'){sendResponse(await postJson('/collector/catalog',{pageUrl:msg.pageUrl,urls:msg.urls||[]}));return}
 if(msg.type==='GET_STATE'){sendResponse(await getState());return}
 if(msg.type==='CLEAR_RESULTS'){const s=await getState();s.results=[];s.errors=[];await setState(s);sendResponse({ok:true});return}
 })();return true});
chrome.runtime.onInstalled.addListener(()=>processNext());
chrome.runtime.onStartup.addListener(()=>processNext());

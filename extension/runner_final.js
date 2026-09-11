const RUNNER_API='https://manko-api.onrender.com';
const RUNNER_WORKERS=2;
const RUNNER_POLL_ALARM='manko_runner_poll';
const RUNNER_STATE='manko_final_runner_state';

async function rfGet(){const r=await chrome.storage.local.get(RUNNER_STATE);return r[RUNNER_STATE]||{workers:{},discovery:null}}
async function rfSet(s){await chrome.storage.local.set({[RUNNER_STATE]:s})}
async function rfJson(path,opt={}){try{const r=await fetch(RUNNER_API+path,{cache:'no-store',...opt,headers:{'Content-Type':'application/json',...(opt.headers||{})}});const t=await r.text();let j=null;try{j=JSON.parse(t)}catch{}return{ok:r.ok,status:r.status,data:j,text:t}}catch(e){return{ok:false,error:String(e)}}}
async function rfClose(id){if(id)try{await chrome.tabs.remove(id)}catch{}}
async function rfCloseJob(job){await rfClose(job?.movieTabId);await rfClose(job?.playerTabId)}

async function rfPoll(){
  const s=await rfGet();
  for(let i=0;i<RUNNER_WORKERS;i++){
    if(s.workers[i])continue;
    const r=await rfJson('/runner/next');
    const task=r.data?.task;
    if(!r.ok||!task?.id||!task?.movieUrl)break;
    const t=await chrome.tabs.create({url:task.movieUrl,active:false});
    s.workers[i]={slot:i,taskId:task.id,movieUrl:task.movieUrl,movieTabId:t.id,playerTabId:null,startedAt:Date.now()};
  }
  await rfSet(s);
}

async function rfFinish(slot,payload){
  const s=await rfGet(),w=s.workers?.[slot];if(!w)return;
  const r=await rfJson('/runner/result',{method:'POST',body:JSON.stringify({taskId:w.taskId,movieUrl:w.movieUrl,...payload})});
  if(r.ok&&r.data?.ok){await rfCloseJob(w);delete s.workers[slot];await rfSet(s);setTimeout(rfPoll,250)}
  else {await rfCloseJob(w);delete s.workers[slot];await rfSet(s);await rfJson('/runner/fail',{method:'POST',body:JSON.stringify({taskId:w.taskId,movieUrl:w.movieUrl,error:r.error||r.text||'result rejected'})});setTimeout(rfPoll,1000)}
}

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{
  const s=await rfGet(),tabId=sender.tab?.id;
  if(msg.type==='MANKO_PLAYER_FOUND'){
    const ent=Object.entries(s.workers||{}).find(([,w])=>w?.movieTabId===tabId);if(!ent)return;
    const slot=Number(ent[0]),w=ent[1];
    const player=msg.playerUrl||(msg.playerUrls||[])[0];
    if(!player)return rfFinish(slot,{ok:false,error:'No javplayer embed'});
    try{const t=await chrome.tabs.create({url:player,active:false});w.playerTabId=t.id;w.page={movieId:msg.movieId,title:msg.title,poster:msg.poster,metadata:msg.metadata||{}};s.workers[slot]=w;await rfSet(s);sendResponse({ok:true})}catch(e){await rfFinish(slot,{ok:false,error:String(e)})}
    return;
  }
  if(msg.type==='JAVPLAYER_RESULT'){
    const ent=Object.entries(s.workers||{}).find(([,w])=>w?.playerTabId===tabId);if(!ent)return;
    const slot=Number(ent[0]),w=ent[1];
    if(msg.ok&&msg.streamUrl)return rfFinish(slot,{ok:true,page:w.page||{},stream:{url:msg.streamUrl,vttUrl:msg.vttUrl||null,headers:msg.headers||{Referer:'https://javplayer.cc/'},playerId:msg.playerId,playerUrl:msg.playerUrl}});
    return rfFinish(slot,{ok:false,error:msg.error||'Javplayer failed'});
  }
  if(msg.type==='MANKO_PAGE_ERROR'){
    const ent=Object.entries(s.workers||{}).find(([,w])=>w?.movieTabId===tabId);if(!ent)return;
    return rfFinish(Number(ent[0]),{ok:false,error:msg.error||'Manko page error'});
  }
})();return true});

chrome.alarms.onAlarm.addListener(a=>{if(a.name===RUNNER_POLL_ALARM)rfPoll()});
chrome.runtime.onInstalled.addListener(()=>{chrome.alarms.create(RUNNER_POLL_ALARM,{periodInMinutes:0.1});rfPoll()});
chrome.runtime.onStartup.addListener(async()=>{const s=await rfGet();for(const w of Object.values(s.workers||{}))await rfCloseJob(w);await rfSet({workers:{},discovery:null});chrome.alarms.create(RUNNER_POLL_ALARM,{periodInMinutes:0.1});rfPoll()});

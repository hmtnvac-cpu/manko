const API='https://manko-api.onrender.com';
const STATE_KEY='film4k_runner_state';
const ALARM='film4k_runner_poll';
const WORKERS=2;
let polling=false;

async function getState(){const r=await chrome.storage.local.get(STATE_KEY);return r[STATE_KEY]||{workers:{},paused:false,lastError:null}}
async function setState(s){await chrome.storage.local.set({[STATE_KEY]:s})}
async function api(path,opt={}){try{const r=await fetch(API+path,{cache:'no-store',...opt,headers:{'Content-Type':'application/json',...(opt.headers||{})}});const t=await r.text();let data=null;try{data=JSON.parse(t)}catch{}return{ok:r.ok,status:r.status,data,text:t}}catch(e){return{ok:false,error:String(e)}}}
async function closeTab(id){if(id)try{await chrome.tabs.remove(id)}catch{}}

async function fail(slot,error){const s=await getState(),w=s.workers?.[slot];if(!w)return;await closeTab(w.tabId);delete s.workers[slot];s.lastError=String(error||'failed');await setState(s);await api('/runner/fail',{method:'POST',body:JSON.stringify({taskId:w.taskId,movieUrl:w.movieUrl,error:s.lastError})});setTimeout(poll,500)}

async function finish(slot,msg){const s=await getState(),w=s.workers?.[slot];if(!w)return;const r=await api('/runner/result',{method:'POST',body:JSON.stringify({taskId:w.taskId,movieUrl:w.movieUrl,meta:msg.meta||{},resources:msg.resources||[]})});if(r.ok){await closeTab(w.tabId);delete s.workers[slot];s.lastError=null;await setState(s);setTimeout(poll,250)}else await fail(slot,r.error||r.text||'result rejected')}

async function poll(){if(polling)return;polling=true;try{let s=await getState();if(s.paused)return;for(let i=0;i<WORKERS;i++){s=await getState();if(s.paused||s.workers[i])continue;const r=await api('/runner/next');const task=r.data?.task;if(!r.ok||!task?.movieUrl)break;try{const tab=await chrome.tabs.create({url:task.movieUrl,active:false});s=await getState();s.workers[i]={taskId:task.id,movieUrl:task.movieUrl,tabId:tab.id,startedAt:Date.now()};await setState(s)}catch(e){await api('/runner/fail',{method:'POST',body:JSON.stringify({taskId:task.id,movieUrl:task.movieUrl,error:String(e)})})}}}finally{polling=false}}

chrome.runtime.onMessage.addListener((msg,sender,sendResponse)=>{(async()=>{
  if(msg.type==='RUNNER_STATUS'){sendResponse({ok:true,state:await getState()});return}
  if(msg.type==='RUNNER_PAUSE'){const s=await getState();s.paused=true;for(const w of Object.values(s.workers||{}))await closeTab(w.tabId);s.workers={};await setState(s);sendResponse({ok:true});return}
  if(msg.type==='RUNNER_RESUME'){const s=await getState();s.paused=false;s.lastError=null;await setState(s);poll();sendResponse({ok:true});return}
  if(msg.type==='RUNNER_STOP'){const s=await getState();s.paused=true;for(const w of Object.values(s.workers||{}))await closeTab(w.tabId);s.workers={};await setState(s);sendResponse({ok:true});return}
  if(msg.type==='FILM4K_PROBE'){
    const tabId=sender.tab?.id;
    const s=await getState();
    const ent=Object.entries(s.workers||{}).find(([,w])=>w?.tabId===tabId);
    if(ent){await finish(Number(ent[0]),msg);sendResponse({ok:true,runner:true});return}
    const r=await api('/film4k/probe',{method:'POST',body:JSON.stringify(msg)});sendResponse({ok:r.ok,data:r.data});return;
  }
})();return true});

chrome.alarms.onAlarm.addListener(a=>{if(a.name===ALARM)poll()});
async function boot(){const s=await getState();s.workers={};if(typeof s.paused!=='boolean')s.paused=false;await setState(s);chrome.alarms.create(ALARM,{periodInMinutes:0.1});if(!s.paused){await api('/runner/start',{method:'POST',body:'{}'});poll()}}
chrome.runtime.onInstalled.addListener(boot);
chrome.runtime.onStartup.addListener(boot);

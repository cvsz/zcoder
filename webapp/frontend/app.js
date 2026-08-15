const el=(id)=>document.getElementById(id);
const state={sessionId:null,busy:false,apiBase:"",online:false};
const ids=["transcript","chatForm","promptInput","sendBtn","modelSelect","personalitySelect","agentSelect","skillSelect","tempRange","tempVal","systemPrompt","apiKeyInput","newSessionBtn","sessionIdTag","healthText","streamToggle","sessionList","sessionCount","connectionPill","connectionLabel","connectionDialog","apiBaseInput","openConnectionBtn","heroConnectBtn","connectionForm","clearApiBtn","themeToggle","modelMetric","agentMetric","skillMetric","versionMetric","pipelineState"];
const ui=Object.fromEntries(ids.map(id=>[id,el(id)]));

function isPages(){return location.hostname.endsWith("github.io")}
function normalizeApiBase(value){
  const raw=(value||"").trim(); if(!raw)return "";
  const url=new URL(raw);
  const local=["localhost","127.0.0.1","::1"].includes(url.hostname);
  if(url.protocol!=="https:"&&!(local&&url.protocol==="http:"))throw new Error("Use HTTPS for remote APIs (HTTP is allowed only on localhost).");
  url.search="";url.hash="";return url.toString().replace(/\/$/,"");
}
function loadApiBase(){
  const query=new URLSearchParams(location.search).get("api");
  if(query){try{const v=normalizeApiBase(query);localStorage.setItem("zcoder-api-base",v);return v}catch{}}
  try{return normalizeApiBase(localStorage.getItem("zcoder-api-base")||"")}catch{return ""}
}
state.apiBase=loadApiBase();
function apiUrl(path){return `${state.apiBase}/api${path}`}

function applyTheme(theme){document.documentElement.dataset.theme=theme;localStorage.setItem("zcoder-theme",theme)}
applyTheme(localStorage.getItem("zcoder-theme")||"dark");
ui.themeToggle.addEventListener("click",()=>applyTheme(document.documentElement.dataset.theme==="light"?"dark":"light"));

function setConnection(online,message){state.online=online;ui.connectionPill.classList.toggle("online",online);ui.connectionLabel.textContent=message;ui.pipelineState.textContent=online?"CONNECTED":"DISCONNECTED";ui.healthText.textContent=online?"backend healthy":"backend unavailable"}
function openConnection(){ui.apiBaseInput.value=state.apiBase;ui.connectionDialog.showModal()}
ui.openConnectionBtn.addEventListener("click",openConnection);ui.heroConnectBtn.addEventListener("click",openConnection);
ui.clearApiBtn.addEventListener("click",()=>{state.apiBase="";localStorage.removeItem("zcoder-api-base");ui.apiBaseInput.value=""});
ui.connectionForm.addEventListener("submit",async(e)=>{e.preventDefault();try{state.apiBase=normalizeApiBase(ui.apiBaseInput.value);if(state.apiBase)localStorage.setItem("zcoder-api-base",state.apiBase);else localStorage.removeItem("zcoder-api-base");ui.connectionDialog.close();await bootstrap()}catch(err){alert(err.message)}});

async function request(path,options={}){const res=await fetch(apiUrl(path),{...options,headers:{"Content-Type":"application/json",...(options.headers||{})}});const data=await res.json().catch(()=>({}));if(!res.ok)throw new Error(data.detail||`${path} → HTTP ${res.status}`);return data}
const getJSON=(path)=>request(path);
const postJSON=(path,body)=>request(path,{method:"POST",body:JSON.stringify(body)});

function escapeHtml(text){return String(text).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
function renderLite(target,text){
  target.innerHTML="";const parts=String(text).split(/```(\w*)\n?([\s\S]*?)```/g);
  for(let i=0;i<parts.length;i+=3){if(parts[i]){const span=document.createElement("span");span.innerHTML=escapeHtml(parts[i]).replace(/`([^`]+)`/g,"<code>$1</code>").replace(/\n/g,"<br>");target.appendChild(span)}if(parts[i+2]!==undefined){const pre=document.createElement("pre"),code=document.createElement("code"),btn=document.createElement("button");code.textContent=parts[i+2].replace(/\n$/,'');btn.className="copy-btn";btn.textContent="copy";btn.type="button";btn.onclick=()=>navigator.clipboard.writeText(parts[i+2]).then(()=>{btn.textContent="copied";setTimeout(()=>btn.textContent="copy",1200)});pre.append(code,btn);target.appendChild(pre)}}
}
function addMessage(role,text,meta=""){
  const row=document.createElement("div"),symbol=document.createElement("div"),content=document.createElement("div"),bubble=document.createElement("div");row.className=`msg ${role}`;symbol.className="symbol";symbol.textContent=role==="user"?"$":role==="error"?"!":">";bubble.className="bubble";role==="assistant"?renderLite(bubble,text):bubble.textContent=text;content.appendChild(bubble);if(meta){const m=document.createElement("div");m.className="meta";m.textContent=meta;content.appendChild(m)}row.append(symbol,content);ui.transcript.appendChild(row);ui.transcript.scrollTop=ui.transcript.scrollHeight;return bubble
}
function setBusy(v){state.busy=v;ui.sendBtn.disabled=v;ui.sendBtn.textContent=v?"Running…":"Run task →"}

function fillSelect(select,items,valueKey="name",label=(x)=>x.name){const keep=select.querySelector('option[value=""]');select.innerHTML="";if(keep)select.appendChild(keep);items.forEach(item=>{const o=document.createElement("option");o.value=item[valueKey];o.textContent=label(item);select.appendChild(o)})}
async function loadCapabilities(){
  const [version,models,agents,skills,personalities]=await Promise.all([getJSON("/version"),getJSON("/models"),getJSON("/agents"),getJSON("/skills"),getJSON("/personalities")]);
  fillSelect(ui.modelSelect,models,"id",m=>`${m.display_name}${m.tier?` · ${m.tier}`:""}`);fillSelect(ui.agentSelect,agents);fillSelect(ui.skillSelect,skills);fillSelect(ui.personalitySelect,personalities);
  ui.modelMetric.textContent=models.length;ui.agentMetric.textContent=agents.length;ui.skillMetric.textContent=skills.length;ui.versionMetric.textContent=`v${version.version}`;
}
async function refreshSessions(){try{const sessions=await getJSON("/sessions");ui.sessionCount.textContent=sessions.length;ui.sessionList.innerHTML="";if(!sessions.length){ui.sessionList.innerHTML='<div class="empty-state">No live sessions yet.</div>';return}sessions.forEach(s=>{const item=document.createElement("div");item.className=`session-item${s.session_id===state.sessionId?" active":""}`;item.innerHTML=`<b>${escapeHtml(s.preview||"Untitled session")}</b><small>${s.session_id.slice(0,8)} · ${s.turns} turns</small>`;item.onclick=()=>loadSession(s.session_id);ui.sessionList.appendChild(item)})}catch{}}
async function loadSession(id){try{const data=await getJSON(`/sessions/${id}`);state.sessionId=id;ui.sessionIdTag.textContent=`session:${id.slice(0,8)}`;ui.transcript.innerHTML="";(data.history||[]).forEach(m=>addMessage(m.role==="user"?"user":"assistant",m.content));refreshSessions()}catch(err){addMessage("error",err.message)}}
function newSession(){state.sessionId=null;ui.sessionIdTag.textContent="session:new";ui.transcript.innerHTML='<div class="welcome-card"><span class="mini-mark">Z</span><h3>New engineering session.</h3><p>Choose a configuration and describe the bounded task you want ZCoder to execute.</p></div>';refreshSessions()}
ui.newSessionBtn.addEventListener("click",newSession);

function payload(){return{prompt:ui.promptInput.value.trim(),session_id:state.sessionId,model:ui.modelSelect.value,temperature:Number(ui.tempRange.value),system:ui.systemPrompt.value.trim()||null,personality:ui.personalitySelect.value||null,agent:ui.agentSelect.value||null,skill:ui.skillSelect.value||null,api_key:ui.apiKeyInput.value||null}}
async function runNonStreaming(body){const data=await postJSON("/chat",body);state.sessionId=data.session_id;ui.sessionIdTag.textContent=`session:${data.session_id.slice(0,8)}`;addMessage("assistant",data.response,`${data.model} · completed`)}
async function runStreaming(body){
  const res=await fetch(apiUrl("/chat/stream"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(data.detail||`stream → HTTP ${res.status}`)}
  const bubble=addMessage("assistant","");let full="",buffer="";const reader=res.body.getReader(),decoder=new TextDecoder();
  while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const frames=buffer.split("\n\n");buffer=frames.pop()||"";for(const frame of frames){for(const line of frame.split("\n")){if(!line.startsWith("data:"))continue;const event=JSON.parse(line.slice(5).trim());if(event.type==="token"){full+=event.text||"";renderLite(bubble,full)}else if(event.type==="done"){state.sessionId=event.session_id;ui.sessionIdTag.textContent=`session:${event.session_id.slice(0,8)}`}else if(event.type==="error")throw new Error(event.message||"stream failed")}}}
}
ui.chatForm.addEventListener("submit",async(e)=>{e.preventDefault();if(state.busy)return;if(!state.online){openConnection();return}const body=payload();if(!body.prompt)return;addMessage("user",body.prompt);ui.promptInput.value="";setBusy(true);try{ui.streamToggle.checked?await runStreaming(body):await runNonStreaming(body);await refreshSessions()}catch(err){addMessage("error",err.message||String(err))}finally{setBusy(false);ui.promptInput.focus()}});
ui.promptInput.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();ui.chatForm.requestSubmit()}});ui.tempRange.addEventListener("input",()=>ui.tempVal.textContent=Number(ui.tempRange.value).toFixed(2));
document.querySelectorAll(".starter").forEach(btn=>btn.addEventListener("click",()=>{ui.promptInput.value=btn.dataset.prompt||"";ui.promptInput.focus()}));

async function bootstrap(){
  setConnection(false,"API offline");if(isPages()&&!state.apiBase){ui.connectionLabel.textContent="Connect backend";return}
  try{await getJSON("/health");setConnection(true,"API connected");await Promise.all([loadCapabilities(),refreshSessions()])}catch(err){setConnection(false,"API unreachable");console.warn("ZCoder backend connection failed",err)}
}
bootstrap();

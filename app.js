const dash=document.querySelector("#dash"),file=document.querySelector("#video"),caption=document.querySelector("#caption"),privacy=document.querySelector("#privacy"),status=document.querySelector("#status");
async function init(){
  const r=await fetch("/api/session");
  if(!r.ok)return;
  const d=await r.json();
  if(!d.connected)return;
  dash.classList.remove("hidden");
  document.querySelector("#name").textContent=d.display_name||"Connected TikTok account";
  const x=await fetch("/api/creator-info",{method:"POST"});
  if(x.ok){
    const info=await x.json();
    (info.privacy_level_options||["SELF_ONLY"]).forEach(v=>{
      const o=document.createElement("option");
      o.value=v;o.textContent=v.replaceAll("_"," ");
      privacy.appendChild(o);
    });
  }
}
async function publish(){
  if(!file.files[0])return show("Choose a video first.");
  const f=new FormData();
  f.append("video",file.files[0]);
  f.append("caption",caption.value);
  f.append("privacy_level",privacy.value||"SELF_ONLY");
  show("Publishing…");
  try{
    const r=await fetch("/api/publish",{method:"POST",body:f});
    const d=await r.json();
    if(!r.ok)throw Error(d.error||"Request failed");
    show(d.message||"Completed.");
  }catch(e){show(e.message);}
}
function show(x){status.classList.remove("hidden");status.textContent=x}
document.querySelector("#publish").onclick=publish;
init();

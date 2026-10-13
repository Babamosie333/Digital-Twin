const $=id=>document.getElementById(id);
const err=m=>{$("err").textContent=m||""};
function msg(e){return (e.errors&&e.errors[0]&&(e.errors[0].longMessage||e.errors[0].message))||e.message||"Something went wrong"}
function busy(b,on){b.disabled=on;b.classList.toggle("spin",on)}
async function loadClerk(PK){
  if(!PK){err("Clerk is not configured on this server.");const d=$("dev");if(d)d.style.display="block";return null}
  const host=atob(PK.split("_")[2]).slice(0,-1);
  await new Promise((ok,bad)=>{const s=document.createElement("script");s.async=true;s.crossOrigin="anonymous";
    s.setAttribute("data-clerk-publishable-key",PK);s.src="https://"+host+"/npm/@clerk/clerk-js@5/dist/clerk.browser.js";
    s.onload=ok;s.onerror=()=>bad(new Error("Could not load Clerk"));document.head.appendChild(s)});
  await window.Clerk.load({signInUrl:location.origin+"/sign-in",signUpUrl:location.origin+"/sign-up",
    signInFallbackRedirectUrl:"/sso-callback",signUpFallbackRedirectUrl:"/sso-callback",signInForceRedirectUrl:"/sso-callback",signUpForceRedirectUrl:"/sso-callback"});return window.Clerk}
async function syncAndGo(C){
  const u=C.user,email=u.primaryEmailAddress?u.primaryEmailAddress.emailAddress:"";
  await fetch("/api/auth/session",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({clerk_user_id:u.id,email})});
  location.href="/dashboard"}
async function finish(C,sid){await C.setActive({session:sid});await syncAndGo(C)}
async function google(C,mode){try{const r="/sso-callback";const f=mode==="up"?C.client.signUp:C.client.signIn;
  await f.authenticateWithRedirect({strategy:"oauth_google",redirectUrl:r,redirectUrlComplete:r})}catch(e){err(msg(e))}}
function eyes(){document.querySelectorAll(".eye").forEach(b=>b.onclick=()=>{const i=b.parentNode.querySelector("input");i.type=i.type==="password"?"text":"password";b.textContent=i.type==="password"?"Show":"Hide"})}
document.addEventListener("mousemove",e=>{document.querySelectorAll(".orb").forEach((o,i)=>{o.style.translate=((e.clientX/innerWidth-.5)*(20+i*14))+"px "+((e.clientY/innerHeight-.5)*(20+i*14))+"px"})});
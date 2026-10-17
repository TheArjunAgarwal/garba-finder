// ---- CONFIG: fill these in (Supabase > Project Settings > API) ----
const SUPABASE_URL = 'https://fjktybrsdtazirhvmurx.supabase.co';
const SUPABASE_KEY = 'sb_publishable_WX6OwAZ4rSefa0iJB0JWFQ_U2gi4OfJ';
// -------------------------------------------------------------------
const OTP_LENGTH = 6; // must match Supabase > Authentication > Sign In / Providers > Email > OTP length
const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
const $ = s => document.querySelector(s), stage = $('#stage');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const KEY = 'pf';

// Progress lives in a cookie (localStorage mirror as a fallback) so a refresh never resets the form.
const store = {
  set(v){ const s = JSON.stringify(v);
    document.cookie = `${KEY}=${encodeURIComponent(s)};max-age=${7*86400};path=/;SameSite=Lax`;
    try{ localStorage.setItem(KEY, s) }catch{} },
  get(){ const m = document.cookie.match(`(?:^|; )${KEY}=([^;]*)`);
    try{ return JSON.parse(m ? decodeURIComponent(m[1]) : localStorage.getItem(KEY)) }catch{ return null } },
  clear(){ document.cookie = `${KEY}=;max-age=0;path=/`; try{ localStorage.removeItem(KEY) }catch{} }
};

let Q, themes, domain, total;
let st = store.get() || { a:{}, i:0 };
let lock = false, dir = 0; // dir: 1 forward, -1 back, 0 no animation
delete st.a.theme_rank;
const PAUSE = 700; // ms to show the highlighted answer before moving on
let otp = { sent:false, busy:false, msg:'' };
const save = () => store.set(st);
const A = id => st.a[id];

const checks = {
  intro: () => true,
  name: a => a?.first?.trim() && a?.last?.trim(),
  email: a => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(a||'') && (a.endsWith('@'+domain) || a.endsWith('.'+domain)),
  single: a => !!a, multi: a => a?.length > 0, scale: a => Number.isInteger(a),
  number: (a,q) => a >= q.min && a <= q.max,
  range: (a,q) => a && a.min >= q.min && a.max <= q.max && a.min <= a.max,
  dealbreaker: a => a?.mine && a?.tol, dual: a => a?.you && a?.ideal
};
const valid = q => !!checks[q.type](A(q.id), q);

const ends = (lo,hi) => `<div class="ends"><span>${esc(lo)}</span><span>${esc(hi)}</span></div>`;
const scale = (key,cur) => `<div class="scale">${[1,2,3,4,5,6,7].map(n=>`<button data-k="${key}" data-v="${n}" class="${cur===n?'on':''}">${n}</button>`).join('')}</div>`;
const pills = (key,opts,cur) => `<div class="pills">${opts.map(o=>`<button class="pill ${(Array.isArray(cur)?cur.includes(o):cur===o)?'on':''}" data-k="${key}" data-v="${esc(o)}">${esc(o)}</button>`).join('')}</div>`;

const link = t => esc(t).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
const paras = a => a.map(p => `<p>${link(p)}</p>`).join('');

function body(q){
  const a = A(q.id);
  switch(q.type){
    case 'intro': return `<div class="intro">${paras(q.paras)}${q.sections.map(x=>`<div class="priv"><h2>${esc(x.h)}</h2>${paras(x.paras)}</div>`).join('')}</div>`;
    case 'name': return `<div class="row"><input id="f1" placeholder="First name" autocomplete="given-name" value="${esc(a?.first)}"><input id="f2" placeholder="Last name" autocomplete="family-name" value="${esc(a?.last)}"></div>`;
    case 'email': return `<input id="f1" type="email" placeholder="School email" autocomplete="email" value="${esc(a)}">`;
    case 'number': return `<input id="f1" type="text" inputmode="numeric" maxlength="2" placeholder="Age" value="${a ?? ''}">`;
    case 'range': return `<div class="row"><input id="f1" type="text" inputmode="numeric" maxlength="2" placeholder="From" value="${a?.min ?? ''}"><input id="f2" type="text" inputmode="numeric" maxlength="2" placeholder="To" value="${a?.max ?? ''}"></div>`;
    case 'single': case 'multi': return pills('opt', q.options, a);
    case 'dealbreaker': return `<div class="grp"><p class="lab">${esc(q.mine)}…</p>${pills('mine',['Never','Occasionally','Regularly'],a?.mine)}</div>
      <div class="grp"><p class="lab">${esc(q.theirs)}…</p>${pills('tol',['Fine','Okay occasionally','Dealbreaker'],a?.tol)}</div>`;
    case 'scale': return scale('v',a) + ends(q.lo,q.hi);
    case 'dual': return `<div class="blk"><p class="who">You</p><p class="cap">${esc(q.yc)}</p>${scale('you',a?.you)}${ends(q.lo,q.hi)}</div>
      <div class="blk them"><p class="who">Your ideal partner</p><p class="cap">${esc(q.ic)}</p>${scale('ideal',a?.ideal)}${ends(q.ilo||q.lo,q.ihi||q.hi)}</div>`;
  }
}

function render(){
  const anim = dir>0 ? 'fwd' : dir<0 ? 'bk' : ''; dir = 0;
  const bar = $('#bar i'); bar.style.width = Math.min(100, st.i/total*100)+'%';
  $('#nav').style.display = 'flex';
  if(st.i >= total) return renderVerify(anim);
  const q = Q[st.i], th = themes.find(t=>t.id===q.theme);
  const needsNext = !['single','scale'].includes(q.type);
  stage.innerHTML = `<section class="q ${anim}">${th?`<p class="tag">${esc(th.name)}</p>`:''}<h1>${esc(q.text)}</h1>${q.sub?`<p class="sub">${esc(q.sub)}</p>`:''}${body(q)}${['number','range'].includes(q.type)?'<p class="err" id="qerr"></p>':''}
    <div class="act"><button class="btn" id="next" ${valid(q)?'':'disabled'}>${st.i===total-1?'FINISH':'NEXT'}</button></div></section>`;
  if(!needsNext) $('.act').style.display = 'none';
  $('#f1')?.focus({preventScroll:true});
  $('#f1')?.addEventListener('input', onInput); $('#f2')?.addEventListener('input', onInput);
  $('#next')?.addEventListener('click', next);
}

function onInput(e){
  const q = Q[st.i];
  if(['number','range'].includes(q.type)) e.target.value = e.target.value.replace(/\D/g,'');
  const v1 = $('#f1').value, v2 = $('#f2')?.value;
  if(q.type==='name') st.a[q.id] = {first:v1, last:v2};
  else if(q.type==='email') st.a[q.id] = v1.trim().toLowerCase();
  else if(q.type==='number') st.a[q.id] = v1===''?null:+v1;
  else if(q.type==='range') st.a[q.id] = {min:v1===''?null:+v1, max:v2===''?null:+v2};
  save(); $('#next').disabled = !valid(q);
  const qe = $('#qerr');
  if(qe){ const a = st.a[q.id], vals = q.type==='range' ? [a.min,a.max] : [a];
    qe.textContent = vals.some(v=>v!=null && (v<q.min||v>q.max)) ? `Use a number from ${q.min} to ${q.max}.` : (q.type==='range' && a.min!=null && a.max!=null && a.min>a.max ? 'The first age must be lower than the second.' : ''); }
}

stage.addEventListener('click', e => {
  const b = e.target.closest('[data-k]'); if(!b || st.i >= total || lock) return;
  const q = Q[st.i], k = b.dataset.k, v = b.dataset.v, a = st.a;
  if(q.type==='single') a[q.id] = v;
  else if(q.type==='multi'){ const s = new Set(a[q.id]||[]); s.has(v)?s.delete(v):s.add(v); a[q.id] = [...s]; }
  else if(q.type==='scale') a[q.id] = +v;
  else if(q.type==='dual') a[q.id] = {...a[q.id], [k]:+v};
  else if(q.type==='dealbreaker') a[q.id] = {...a[q.id], [k]:v};
  save();
  render();
  if(['single','scale'].includes(q.type)) advanceSoon();
});

function advanceSoon(){ lock = true; setTimeout(() => { lock = false; next(); }, PAUSE); }
function next(){ if(st.i<total && valid(Q[st.i]) || st.i>=total){ dir = 1; st.i = Math.min(total, st.i+1); save(); render(); } }
function back(){ if(!lock && st.i>0){ dir = -1; st.i--; save(); render(); } }
$('#up').onclick = back; $('#down').onclick = () => !lock && st.i<total && valid(Q[st.i]) && next();
document.addEventListener('keydown', e => {
  if(st.i>=total || lock) return;
  const q = Q[st.i];
  if(e.key==='Enter' && valid(q) && !['single','scale'].includes(q.type)) next();
  if(q.type==='scale' && /^[1-7]$/.test(e.key) && document.activeElement.tagName!=='INPUT'){ st.a[q.id] = +e.key; save(); render(); advanceSoon(); }
});

// ---- OTP + submit (only at the very end) ----
function renderVerify(anim=''){
  const email = A('email');
  stage.innerHTML = `<section class="q ${anim}"><h1>${otp.sent?'Check your inbox':'Almost done'}</h1>
    <p class="sub">${otp.sent?`We sent a code to <b>${esc(email)}</b>. Enter it to submit your answers.`:`We'll email a one-time code to <b>${esc(email)}</b> to confirm it's you. Your answers are only saved once the code is correct.`}</p>
    ${otp.sent?`<input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="${OTP_LENGTH}" placeholder="${OTP_LENGTH}-digit code">`:''}
    <p class="err" id="err">${esc(otp.msg)}</p>
    <div class="act"><button class="lnk" id="chg">Change email</button>${otp.sent?'<button class="lnk" id="resend">Resend code</button>':''}
    <button class="btn" id="go" ${otp.busy?'disabled':''}>${otp.sent?'VERIFY & SUBMIT':'SEND CODE'}</button></div></section>`;
  $('#chg').onclick = () => { st.i = Q.findIndex(q=>q.id==='email'); otp = {sent:false}; dir = -1; save(); render(); };
  $('#go').onclick = otp.sent ? verify : sendCode;
  if(otp.sent){ $('#resend').onclick = sendCode; const c = $('#code'); c.focus();
    c.addEventListener('input', () => { c.value = c.value.replace(/\D/g,'').slice(0,OTP_LENGTH); });
    c.addEventListener('keydown', e => { if(e.key==='Enter') verify(); }); }
}
async function sendCode(){
  otp = {...otp, busy:true, msg:''}; renderVerify();
  const { error } = await sb.auth.signInWithOtp({ email:A('email'), options:{ shouldCreateUser:true } });
  otp = error ? {sent:otp.sent, msg:error.message} : {sent:true, msg:''}; renderVerify();
}
async function verify(){
  const token = $('#code').value.trim();
  if(token.length !== OTP_LENGTH){ otp.msg = `Enter the ${OTP_LENGTH}-digit code from your email.`; return renderVerify(); }
  otp.busy = true; $('#go').disabled = true;
  const { data, error } = await sb.auth.verifyOtp({ email:A('email'), token, type:'email' });
  if(error){ otp = {sent:true, msg:'That code is wrong or expired. Check it or resend a new one.'}; return renderVerify(); }
  const n = A('name'), { error:e2 } = await sb.from('responses').insert({ email:data.user.email.toLowerCase(), name:`${n.first} ${n.last}`.trim(), data:st.a });
  await sb.auth.signOut();
  if(e2){ otp = {sent:true, msg: e2.code==='23505' ? 'This email has already submitted a response.' : 'Could not save: '+e2.message}; return renderVerify(); }
  store.clear(); $('#nav').style.display = 'none'; $('#bar i').style.width = '100%';
  stage.innerHTML = `<section class="q"><h1>You're in.</h1><p class="sub">Your answers are saved. Finger's crossed...</p></section>`;
}

fetch('questions.json').then(r=>r.json()).then(j => {
  Q = j.questions; themes = j.themes; domain = j.emailDomain; total = Q.length;
  st.i = Math.min(st.i, total); render();
}).catch(() => stage.innerHTML = '<p class="sub">Could not load questions.json. Serve this folder over http (e.g. <code>python3 -m http.server</code>) instead of opening the file directly.</p>');
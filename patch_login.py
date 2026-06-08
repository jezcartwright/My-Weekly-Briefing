#!/usr/bin/env python3
# Adds email+password sign-in / create-account flow to the login screen.
# Keeps Google + magic-link (now a quiet fallback). Safe-edit: assert each
# anchor is unique, write to .tmp, size-floor check, then os.replace.
import os, sys

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/weekly-briefing-local/test-repo/index.html')

with open(PATH, 'r', encoding='utf-8') as f:
    s = f.read()
orig_len = len(s)

edits = []

# ---------- 1) CSS: new classes after the btn-locked rule ----------
edits.append((
""".login-btn.btn-locked,.google-btn.btn-locked{opacity:.45;pointer-events:none}""",
""".login-btn.btn-locked,.google-btn.btn-locked{opacity:.45;pointer-events:none}
.seg{display:flex;background:var(--b2);border-radius:9px;padding:4px;margin-bottom:18px}
.seg button{flex:1;border:none;background:transparent;font-family:'Inter',sans-serif;font-size:13px;font-weight:700;color:#8a8580;padding:9px 0;border-radius:6px;cursor:pointer}
.seg button.on{background:#fff;color:var(--orange);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.pw-wrap{position:relative}
.pw-eye{position:absolute;right:12px;top:13px;font-size:12px;font-weight:600;color:#999;cursor:pointer;user-select:none}
.pw-hint{font-size:11px;color:#999;margin:-6px 0 12px 2px}
.forgot{display:block;text-align:right;font-size:12px;font-weight:600;color:var(--orange);margin:-4px 0 14px;text-decoration:none;cursor:pointer}
.link-fallback{display:block;text-align:center;font-size:12px;color:#888;margin-top:16px;text-decoration:none;cursor:pointer}
.link-fallback u{color:var(--orange);text-decoration:none;font-weight:600}
.link-fallback.btn-locked{opacity:.45;pointer-events:none}"""))

# ---------- 2A) Markup: replace h2+p with segmented toggle ----------
edits.append((
"""    <h2>Sign in or create account</h2>
    <p>Enter your details and we'll send you a secure sign-in link — no password needed.</p>""",
"""    <div class="seg"><button id="seg-signin" class="on" onclick="setAuthMode('signin')">Sign in</button><button id="seg-create" onclick="setAuthMode('create')">Create account</button></div>"""))

# ---------- 2B) Markup: wrap name grid so it hides in sign-in mode ----------
edits.append((
"""    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
      <input class="login-input" id="login-fname" type="text" placeholder="First name" autocomplete="given-name" style="margin-bottom:0">
      <input class="login-input" id="login-lname" type="text" placeholder="Last name" autocomplete="family-name" style="margin-bottom:0">
    </div>""",
"""    <div id="create-names" style="display:none"><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
      <input class="login-input" id="login-fname" type="text" placeholder="First name" autocomplete="given-name" style="margin-bottom:0">
      <input class="login-input" id="login-lname" type="text" placeholder="Last name" autocomplete="family-name" style="margin-bottom:0">
    </div></div>"""))

# ---------- 2C) Markup: add password field + hint + forgot after email ----------
edits.append((
"""    <input class="login-input" id="login-email" type="email" placeholder="your@email.com" autocomplete="email">""",
"""    <input class="login-input" id="login-email" type="email" placeholder="your@email.com" autocomplete="email">
    <div class="pw-wrap"><input class="login-input" id="login-pw" type="password" placeholder="Password" autocomplete="current-password" style="margin-bottom:6px"><span class="pw-eye" onclick="togglePw()">Show</span></div>
    <div class="pw-hint" id="pw-hint" style="display:none">At least 6 characters</div>
    <a class="forgot" id="forgot-link" onclick="forgotPassword()">Forgot password?</a>"""))

# ---------- 2D) Markup: wrap consent so it hides in sign-in mode ----------
edits.append((
"""    <label class="consent-row"><input type="checkbox" id="consent-box" onchange="consentChanged()"><span>I agree to the <a href="/privacy.html" target="_blank" rel="noopener">Privacy Policy</a> and to receiving the weekly briefing by email. You can unsubscribe anytime.</span></label>""",
"""    <div id="consent-wrap" style="display:none"><label class="consent-row"><input type="checkbox" id="consent-box" onchange="refreshLock()"><span>I agree to the <a href="/privacy.html" target="_blank" rel="noopener">Privacy Policy</a> and to receiving the weekly briefing by email. You can unsubscribe anytime.</span></label></div>"""))

# ---------- 2E) Markup: primary button -> mode-aware ----------
edits.append((
"""    <button class="login-btn btn-locked" onclick="sendMagicLink()">Send sign-in link</button>""",
"""    <button class="login-btn" id="login-primary" onclick="loginPrimary()">Sign in</button>"""))

# ---------- 2F) Markup: drop btn-locked default on Google button ----------
edits.append((
"""    <button class="google-btn btn-locked" onclick="signInGoogle()">""",
"""    <button class="google-btn" onclick="signInGoogle()">"""))

# ---------- 2G) Markup: Google label span + fallback link ----------
edits.append((
"""      Sign in with Google
    </button>
    <div class="login-msg" id="login-msg"></div>""",
"""      <span id="google-label">Sign in with Google</span>
    </button>
    <a class="link-fallback" id="login-fallback" onclick="sendMagicLink()">Or <u>email me a sign-in link instead</u></a>
    <div class="login-msg" id="login-msg"></div>"""))

# ---------- 3A) JS: replace consentChanged with full auth-mode machinery ----------
edits.append((
"""window.consentChanged = function(){ var ok=(document.getElementById('consent-box')||{}).checked; var b1=document.querySelector('.login-btn'), b2=document.querySelector('.google-btn'); if(b1)b1.classList.toggle('btn-locked',!ok); if(b2)b2.classList.toggle('btn-locked',!ok); };""",
"""window._authMode = 'signin';
window.refreshLock = function(){
  var mode = window._authMode || 'signin';
  var consent = (document.getElementById('consent-box')||{}).checked;
  var gate = (mode === 'create') && !consent;
  var pri = document.getElementById('login-primary');
  var g = document.querySelector('.google-btn');
  var fb = document.getElementById('login-fallback');
  if(pri) pri.classList.toggle('btn-locked', gate);
  if(g) g.classList.toggle('btn-locked', gate);
  if(fb) fb.classList.toggle('btn-locked', gate);
};
window.consentChanged = window.refreshLock;
window.setAuthMode = function(mode){
  window._authMode = mode;
  var isCreate = (mode === 'create');
  var disp = function(id,on){ var el=document.getElementById(id); if(el) el.style.display = on ? '' : 'none'; };
  var ss=document.getElementById('seg-signin'), sc=document.getElementById('seg-create');
  if(ss) ss.classList.toggle('on', !isCreate);
  if(sc) sc.classList.toggle('on', isCreate);
  disp('create-names', isCreate);
  disp('consent-wrap', isCreate);
  disp('pw-hint', isCreate);
  disp('forgot-link', !isCreate);
  var pri = document.getElementById('login-primary');
  if(pri) pri.textContent = isCreate ? 'Create account' : 'Sign in';
  var gl = document.getElementById('google-label');
  if(gl) gl.textContent = isCreate ? 'Sign up with Google' : 'Sign in with Google';
  var pw = document.getElementById('login-pw');
  if(pw) pw.setAttribute('autocomplete', isCreate ? 'new-password' : 'current-password');
  var msg = document.getElementById('login-msg'); if(msg){ msg.textContent=''; msg.style.color=''; }
  window.refreshLock();
};
window.togglePw = function(){
  var pw = document.getElementById('login-pw'); if(!pw) return;
  var eye = document.querySelector('.pw-eye');
  if(pw.type === 'password'){ pw.type='text'; if(eye) eye.textContent='Hide'; }
  else { pw.type='password'; if(eye) eye.textContent='Show'; }
};
window.loginPrimary = function(){ if((window._authMode||'signin')==='create') createAccount(); else signInPassword(); };
window.signInPassword = function(){
  var email = (document.getElementById('login-email').value||'').trim();
  var pw = document.getElementById('login-pw').value||'';
  var msg = document.getElementById('login-msg'); msg.style.color='';
  if(!email || !email.includes('@')){ msg.textContent='Please enter a valid email.'; return; }
  if(!pw){ msg.textContent='Please enter your password.'; return; }
  msg.textContent='Signing in…';
  auth.signInWithEmailAndPassword(email, pw).catch(function(e){
    msg.style.color='';
    if(e.code==='auth/wrong-password' || e.code==='auth/user-not-found' || e.code==='auth/invalid-credential' || e.code==='auth/invalid-login-credentials'){
      msg.textContent='No matching email and password. If you joined with a link or Google, use those below — or tap Forgot password to set one.';
    } else if(e.code==='auth/too-many-requests'){
      msg.textContent='Too many attempts. Please wait a moment and try again.';
    } else {
      msg.textContent='Error: ' + (e.message||e.code);
    }
  });
};
window.createAccount = function(){
  var fname=(document.getElementById('login-fname').value||'').trim();
  var lname=(document.getElementById('login-lname').value||'').trim();
  var email=(document.getElementById('login-email').value||'').trim();
  var pw=document.getElementById('login-pw').value||'';
  var hp=(document.getElementById('login-hp')||{}).value||'';
  var msg=document.getElementById('login-msg'); msg.style.color='';
  if(hp){ msg.textContent='Something went wrong. Please reload and try again.'; return; }
  if(!fname){ msg.textContent='Please enter your first name.'; return; }
  if(!email || !email.includes('@')){ msg.textContent='Please enter a valid email.'; return; }
  if(pw.length < 6){ msg.textContent='Password must be at least 6 characters.'; return; }
  if(!(document.getElementById('consent-box')||{}).checked){ msg.textContent='Please agree to the Privacy Policy to continue.'; return; }
  if(TURNSTILE_SITE_KEY && !turnstileToken && !window._turnstileFailed){ msg.textContent='Please complete the security check above.'; return; }
  msg.textContent='Creating your account…';
  localStorage.setItem('nameForSignIn', JSON.stringify({first:fname,last:lname}));
  auth.createUserWithEmailAndPassword(email, pw).then(function(cred){
    var dn=(fname+' '+lname).trim();
    if(cred && cred.user && dn){ cred.user.updateProfile({displayName:dn}).catch(function(){}); }
  }).catch(function(e){
    if(e.code==='auth/email-already-in-use'){
      msg.textContent='An account already exists for this email. Switch to Sign in, or tap Forgot password to set a new one.';
    } else if(e.code==='auth/weak-password'){
      msg.textContent='Password must be at least 6 characters.';
    } else if(e.code==='auth/invalid-email'){
      msg.textContent='Please enter a valid email.';
    } else {
      msg.textContent='Error: ' + (e.message||e.code);
    }
  });
};
window.forgotPassword = function(){
  var email=(document.getElementById('login-email').value||'').trim();
  var msg=document.getElementById('login-msg'); msg.style.color='';
  if(!email || !email.includes('@')){ msg.textContent='Enter your email above, then tap Forgot password?'; return; }
  msg.textContent='Sending reset link…';
  auth.sendPasswordResetEmail(email).then(function(){
    msg.textContent='Password reset link sent to '+email+'. Check your inbox (and spam).';
  }).catch(function(e){
    if(e.code==='auth/user-not-found'){
      msg.textContent='No account found for that email. Create an account, or use Google if you joined that way.';
    } else {
      msg.textContent='Error: ' + (e.message||e.code);
    }
  });
};"""))

# ---------- 3B) JS: sendMagicLink — name/consent only required in create mode ----------
edits.append((
"""  if(!fname){ msg.textContent = 'Please enter your first name.'; return; }
  if(!email || !email.includes('@')){ msg.textContent = 'Please enter a valid email.'; return; }
  if(!(document.getElementById('consent-box')||{}).checked){ msg.textContent = 'Please agree to the Privacy Policy to continue.'; return; }""",
"""  if((window._authMode||'signin')==='create' && !fname){ msg.textContent = 'Please enter your first name.'; return; }
  if(!email || !email.includes('@')){ msg.textContent = 'Please enter a valid email.'; return; }
  if((window._authMode||'signin')==='create' && !(document.getElementById('consent-box')||{}).checked){ msg.textContent = 'Please agree to the Privacy Policy to continue.'; return; }"""))

# ---------- 3C) JS: only seed nameForSignIn when a name was entered ----------
edits.append((
"""    localStorage.setItem('nameForSignIn', JSON.stringify({first: fname, last: lname}));""",
"""    if(fname) localStorage.setItem('nameForSignIn', JSON.stringify({first: fname, last: lname}));"""))

# ---------- 3D) JS: signInGoogle — consent only required in create mode ----------
edits.append((
"""  if(!(document.getElementById('consent-box')||{}).checked){ show('Please agree to the Privacy Policy to continue.','red'); return; }""",
"""  if((window._authMode||'signin')==='create' && !(document.getElementById('consent-box')||{}).checked){ show('Please agree to the Privacy Policy to continue.','red'); return; }"""))

# ---------- apply ----------
for i, (old, new) in enumerate(edits, 1):
    n = s.count(old)
    if n != 1:
        raise SystemExit('EDIT %d: anchor found %d times (expected 1). Aborting, no file written.' % (i, n))
    s = s.replace(old, new)

if len(s) < 300000:
    raise SystemExit('Result too small (%d bytes) — aborting.' % len(s))

tmp = PATH + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(s)
os.replace(tmp, PATH)
print('OK: %d edits applied. %d -> %d bytes (+%d).' % (len(edits), orig_len, len(s), len(s) - orig_len))

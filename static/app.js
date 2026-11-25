// LearnLoop front-end: multi-course plan + auto-graded exercises. No build step.
const S = {
  user: null, plan: null, courses: [], course: null, exercises: null,
  view: null, session: null, timer: null,
};

/* ------------------------------------------------------------------ helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const app = () => $('#app');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ----------------------------------------------------------- page metadata */
const SITE = 'LearnLoop';
const META = {
  session: { title: 'Session', kicker: '', desc: 'One study session: the reading, the timer, notes and the exercises that follow.' },
  plan: { title: 'Plan', kicker: 'Your plan', desc: 'Your dated study plan: every session, its deliverable, your progress and the exercises that prove it.' },
  exercises: { title: 'Exercises', kicker: 'Practice', desc: 'Chapter questions and server-graded lab exercises for this course.' },
  exercise: { title: 'Exercise', kicker: 'Practice', desc: 'One exercise, graded on the server against hidden tests.' },
  search: { title: 'Search', kicker: 'Find anything', desc: 'Search sessions, notes and exercises in this course.' },
  admin: { title: 'Admin', kicker: 'Accounts and traffic', desc: 'Approve accounts, review activity and read the first-party traffic counts.' },
  settings: { title: 'Settings', kicker: 'Instance', desc: 'Paths, site details and the NAS connection.' },
  login: { title: 'Sign in', kicker: 'Welcome back', desc: 'Sign in to your study plan, split PDFs, narrated lectures and auto-graded exercises.' },
  signup: { title: 'Request an account', kicker: 'New account', desc: 'Request a LearnLoop account. An administrator approves it before you can sign in.' },
  setup: { title: 'First run', kicker: 'Set up', desc: 'Create the administrator account for this LearnLoop instance.' },
  notfound: { title: 'Not found', kicker: '404', desc: 'That address does not exist on this LearnLoop server.' },
};

function setPage(title, kicker) {
  const t = document.getElementById('pagetitle');
  const k = document.getElementById('pagekicker');
  if (t && title) t.textContent = title;
  if (k && kicker !== undefined) k.textContent = kicker || '';
}

function setMeta(key, title, kicker) {
  const entry = META[key] || {};
  const t = title || entry.title || SITE;
  document.title = t.includes('LearnLoop') ? t : `${t} · LearnLoop`;
  setPage(t, kicker !== undefined ? kicker : (entry.kicker || ''));
  if (entry.desc) {
    let tag = document.querySelector('meta[name="description"]');
    if (!tag) {
      tag = document.createElement('meta');
      tag.setAttribute('name', 'description');
      document.head.appendChild(tag);
    }
    tag.setAttribute('content', entry.desc);
  }
  const og = document.querySelector('meta[property="og:title"]');
  if (og) og.setAttribute('content', document.title);
}

/* -------------------------------------------------------- consent + counting */
const CONSENT_KEY = 'll-consent';
function consentChoice() {
  try { return localStorage.getItem(CONSENT_KEY) || ''; } catch (e) { return ''; }
}

function trackView() {
  // Aggregate counting only, and only after the visitor chose "Allow traffic counts"
  if (consentChoice() !== 'all') return;
  if (!navigator.sendBeacon) return;
  const path = (location.hash || '#/plan').replace(/^#/, '') || '/';
  const body = new Blob([JSON.stringify({ path: path, ref: document.referrer || '' })],
                        { type: 'application/json' });
  try { navigator.sendBeacon('/api/hit', body); } catch (e) { /* counting is optional */ }
}

function initConsent() {
  const banner = $('#consent');
  if (!banner) return;
  const choose = (value) => {
    try { localStorage.setItem(CONSENT_KEY, value); } catch (e) { /* private mode */ }
    banner.hidden = true;
    document.body.classList.remove('has-consent');
    if (value === 'all') trackView();
  };
  if (consentChoice()) { banner.hidden = true; return; }
  banner.hidden = false;
  document.body.classList.add('has-consent');
  $('#consent-all').onclick = () => choose('all');
  $('#consent-essential').onclick = () => choose('essential');
}

/* ------------------------------------------------------------------- icons */
/* One visual family, drawn inline: emoji render differently on every platform
   and are announced by screen readers as words. */
const ICON_PATHS = {
  play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="7" y="5.5" width="3.4" height="13" rx="1" fill="currentColor" stroke="none"/>'
    + '<rect x="13.6" y="5.5" width="3.4" height="13" rx="1" fill="currentColor" stroke="none"/>',
  headphones: '<path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="2.6" y="14" width="4.4" height="6.4" rx="1.6"/>'
    + '<rect x="17" y="14" width="4.4" height="6.4" rx="1.6"/>',
  video: '<rect x="2.6" y="6" width="12.4" height="12" rx="2.4"/><path d="M15 10.6l6-3.2v9.2l-6-3.2z"/>',
};
function icon(name) {
  const body = ICON_PATHS[name];
  if (!body) return '';
  return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"`
    + ` stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${body}</svg>`;
}

/* -------------------------------------------------------- form validation */
const RULES = {
  username: (v) => (/^[A-Za-z0-9._-]{3,32}$/.test((v || '').trim())
    ? '' : 'Use 3-32 characters: letters, digits, dot, dash or underscore.'),
  password: (v) => ((v || '').length >= 8 ? '' : 'Use at least 8 characters.'),
  email: (v) => (!(v || '').trim() || /^[^@\s]+@[^@\s.]+\.[A-Za-z]{2,}$/.test((v || '').trim())
    ? '' : 'That address does not look right.'),
};

function clearFieldError(input) {
  if (!input) return;
  input.removeAttribute('aria-invalid');
  const err = document.getElementById(input.id + '-err');
  if (err) { err.textContent = ''; err.hidden = true; }
}

function showFieldError(input, message) {
  if (!input) return;
  if (!message) { clearFieldError(input); return; }
  input.setAttribute('aria-invalid', 'true');
  let err = document.getElementById(input.id + '-err');
  if (!err) {
    err = document.createElement('span');
    err.className = 'fielderr';
    err.id = input.id + '-err';
    input.insertAdjacentElement('afterend', err);
  }
  err.textContent = message;
  err.hidden = false;
  const described = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
  if (!described.includes(err.id)) {
    described.push(err.id);
    input.setAttribute('aria-describedby', described.join(' '));
  }
}

/* Validate on blur and while typing after the first error, never on load. */
function wireField(input, rule) {
  if (!input || !rule) return;
  const check = () => {
    const msg = rule(input.value);
    showFieldError(input, msg);
    return !msg;
  };
  input.addEventListener('blur', check);
  input.addEventListener('input', () => {
    if (input.getAttribute('aria-invalid') === 'true') check();
  });
}

function errorSummary(container, items) {
  const box = container.querySelector('.errsummary');
  if (!box) return;
  if (!items.length) { box.hidden = true; box.innerHTML = ''; return; }
  box.innerHTML = '<h2 id="errsum-title">There is a problem</h2><ul>'
    + items.map(i => `<li><a href="#${i.id}">${esc(i.message)}</a></li>`).join('') + '</ul>';
  box.hidden = false;
  box.focus();
}

/* Warm the cache for a session's text/audio/notes before it is opened. */
const _prefetched = new Set();
function prefetchSession(n) {
  n = Number(n);
  if (!n || !S.course) return;
  const key = S.course + ':' + n;
  if (_prefetched.has(key)) return;
  _prefetched.add(key);
  const c = 'course=' + encodeURIComponent(S.course);
  const opts = { credentials: 'include', headers: { 'X-LearnLoop': '1' } };
  if (S.course === 'build-llm') fetch(`/api/reader?${c}&session=${n}`, opts).catch(() => {});
  fetch(`/api/lecture?${c}&session=${n}`, opts).catch(() => {});
  fetch(`/api/notes?${c}&session=${n}`, opts).catch(() => {});
}

/* After a correct answer: offer the next exercise, then pull it up on its own. */
async function nextExerciseSlug(slug) {
  try {
    if (!S._exOrder) {
      const r = await api('/api/exercises' + q());
      S._exOrder = (r.exercises || []).map(x => x.slug);
    }
    const i = S._exOrder.indexOf(slug);
    return i >= 0 && i + 1 < S._exOrder.length ? S._exOrder[i + 1] : null;
  } catch (e) { return null; }
}

function autoAdvance(slug, hostSelector) {
  nextExerciseSlug(slug).then((nxt) => {
    if (!nxt) return;
    const host = $(hostSelector);
    if (!host) return;
    const btn = document.createElement('button');
    btn.className = 'primary small';
    btn.style.marginTop = '10px';
    btn.textContent = 'Next exercise →';
    btn.onclick = () => { location.hash = '#/exercise/' + nxt; };
    host.appendChild(btn);
  });
}

async function api(path, { method = 'GET', body = null } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (method !== 'GET') { opts.headers['X-LearnLoop'] = '1'; opts.headers['Content-Type'] = 'application/json'; }
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.detail) || res.statusText || ('HTTP ' + res.status));
  return data;
}

let toastTimer = null;
function toast(msg, isErr = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, isErr ? 6000 : 3200);
}

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined,
    { weekday: 'short', day: 'numeric', month: 'short' });
}

const q = () => S.course ? '?course=' + encodeURIComponent(S.course) : '';

/* ------------------------------------------------------- python highlighting */
const PY_KEYWORDS = new Set(('False None True and as assert async await break class continue def del '
  + 'elif else except finally for from global if import in is lambda nonlocal not or pass raise '
  + 'return try while with yield match case').split(' '));

const PY_BUILTINS = new Set(('abs all any ascii bin bool bytearray bytes callable chr classmethod compile '
  + 'complex delattr dict dir divmod enumerate eval exec filter float format frozenset getattr globals '
  + 'hasattr hash help hex id input int isinstance issubclass iter len list locals map max memoryview min '
  + 'next object oct open ord pow print property range repr reversed round set setattr slice sorted '
  + 'staticmethod str sum super tuple type vars zip __name__').split(' '));

const escHtml = (s) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

// strings first (so a # inside a string is not a comment), then comments, numbers, words
const TOKEN_RE = new RegExp([
  String.raw`(?:[rbufRBUF]{0,2})(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')`,
  String.raw`#[^\n]*`,
  String.raw`\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b`,
  String.raw`\b[A-Za-z_]\w*\b`,
].join('|'), 'g');

function highlightPython(code) {
  let out = '', last = 0, m;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(code)) !== null) {
    out += escHtml(code.slice(last, m.index));
    const tok = m[0];
    let cls = '';
    if (/^[rbufRBUF]{0,2}("""|'''|"|')/.test(tok)) cls = 'c-str';
    else if (tok[0] === '#') cls = 'c-com';
    else if (/^\d/.test(tok)) cls = 'c-num';
    else if (PY_KEYWORDS.has(tok)) cls = 'c-kw';
    else if (PY_BUILTINS.has(tok)) cls = 'c-bi';
    out += cls ? `<span class="${cls}">${escHtml(tok)}</span>` : escHtml(tok);
    last = m.index + tok.length;
  }
  out += escHtml(code.slice(last));
  return out + '\n';                 // keeps the last line's height equal to the textarea's
}


/* -------------------------------------------------------------------- shell */
function markActive(view) {
  document.querySelectorAll('#nav a').forEach(a => {
    if (a.dataset.view === view) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  document.querySelectorAll('#tabbar a').forEach(a => {
    if (a.dataset.view === view) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

/* The rail's progress card: done / total, the bar, and what comes next. */
function paintRailProgress() {
  const box = $('#railprogress');
  const count = $('#navcount');
  if (!box) return;
  const p = S.plan;
  if (!S.user || !p) { box.hidden = true; if (count) count.hidden = true; return; }
  const next = (p.sessions || []).find(s => !s.done);
  box.hidden = false;
  box.innerHTML = `
    <div class="rp-top">
      <span class="rp-num">${p.done_count}<span> / ${p.count}</span></span>
      <span class="rp-label">${p.percent}% done</span>
    </div>
    <div class="bar thin"><i style="width:${p.percent}%"></i></div>
    <div class="rp-next">${next
      ? `Next: <b>S${String(next.n).padStart(2, '0')}</b> · ${esc(next.block)}`
      : 'Every session is done.'}</div>`;
  if (count) {
    count.hidden = false;
    count.textContent = `${p.done_count}/${p.count}`;
  }
}

function paintChrome() {
  const nav = $('#nav'), chip = $('#userchip'), sel = $('#coursesel');
  const tabs = $('#tabbar');
  const signedIn = !!S.user;
  if (!signedIn) {
    nav.hidden = true; chip.hidden = true; sel.hidden = true;
    if (tabs) tabs.hidden = true;
    $('#brandsub').textContent = '';
    paintRailProgress();
    return;
  }
  document.body.classList.remove('auth-view');
  nav.hidden = false; chip.hidden = false;
  if (tabs) tabs.hidden = false;
  $('#username').innerHTML = esc(S.user.username)
    + (S.user.role === 'admin' ? ' <span class="badge admin">admin</span>' : '');
  const initial = (S.user.username || '?').slice(0, 1).toUpperCase();
  $('#avatar').textContent = initial;
  const avm = $('#avatarm');
  if (avm) avm.textContent = initial;
  if (tabs) tabs.hidden = false;
  $('#navadmin').hidden = S.user.role !== 'admin';
  $('#navsettings').hidden = S.user.role !== 'admin';

  if (S.courses.length > 1) {
    sel.hidden = false;
    if (sel.dataset.built !== S.courses.map(c => c.slug).join(',')) {
      sel.innerHTML = S.courses.map(c =>
        `<option value="${esc(c.slug)}">${esc(c.title)}</option>`).join('');
      sel.dataset.built = S.courses.map(c => c.slug).join(',');
    }
    sel.value = S.course;
  } else {
    sel.hidden = true;
  }
  const cur = S.courses.find(c => c.slug === S.course);
  $('#brandsub').textContent = cur ? cur.title : '';
  markActive(S.view === 'session' ? 'plan' : S.view);
  paintRailProgress();
}

/* Mobile drawer: the rail on small screens, opened from the bar, the avatar or "More". */
function setDrawer(open) {
  document.body.classList.toggle('nav-open', open);
  const scrim = $('#scrim');
  if (scrim) scrim.hidden = !open;
  ['#railopen', '#usermenu'].forEach(sel => {
    const el = $(sel);
    if (el) el.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  if (open) {
    const first = document.querySelector('#nav a');
    if (first) first.focus();
  }
}

function wireShell() {
  const open = () => setDrawer(true);
  ['#railopen', '#usermenu', '#tabmore'].forEach(sel => {
    const el = $(sel);
    if (el) el.onclick = open;
  });
  const close = () => setDrawer(false);
  ['#railclose'].forEach(sel => { const el = $(sel); if (el) el.onclick = close; });
  const scrim = $('#scrim');
  if (scrim) scrim.onclick = close;
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && document.body.classList.contains('nav-open')) close();
  });
  document.querySelectorAll('#nav a, #tabbar a').forEach(a => {
    a.addEventListener('click', () => { if (window.innerWidth <= 1080) close(); });
  });
}

async function loadCourses() {
  const r = await api('/api/courses');
  S.courses = r.courses || [];
  const saved = localStorage.getItem('ll-course');
  S.course = (saved && S.courses.some(c => c.slug === saved)) ? saved
    : (S.courses[0] ? S.courses[0].slug : null);
}

async function switchCourse(slug) {
  if (!slug || slug === S.course) return;
  S.course = slug;
  localStorage.setItem('ll-course', slug);
  S.plan = null; S.exercises = null; S._exOrder = null;
  await refreshPlan();
  paintChrome();
  route();
}

async function refreshPlan() {
  S.plan = await api('/api/plan' + q());
  return S.plan;
}

/* --------------------------------------------------------------------- auth */
/* The signed-out front door: a short product statement beside the form. */
function authHero() {
  return `
    <section class="auth-hero">
      <a class="brand" href="/"><span class="mark" aria-hidden="true"></span>LearnLoop</a>
      <h1>A study plan you can <em>actually finish</em>.</h1>
      <p>Turn a guide into dated sessions — read it, hear it, write it down, then prove it
         with exercises that are graded on the server.</p>
      <ul class="auth-points">
        <li>
          <span class="ap-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 3v3M16 3v3"/></svg></span>
          <div><b>Planned, dated sessions</b><span>Every session has a date, a page range and one deliverable.</span></div>
        </li>
        <li>
          <span class="ap-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15v-3a8 8 0 0 1 16 0v3"/><rect x="2.6" y="14" width="4.4" height="6.4" rx="1.6"/><rect x="17" y="14" width="4.4" height="6.4" rx="1.6"/></svg></span>
          <div><b>Read, listen, keep notes</b><span>Split PDFs or clean reader text, narration, a timer and a note box that saves to your vault.</span></div>
        </li>
        <li>
          <span class="ap-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4.5L7 19M17 4.5L15 19M4.5 9h16M3.5 15h16"/></svg></span>
          <div><b>Prove it, don't just read it</b><span>Chapter questions with explanations and lab exercises graded against hidden tests.</span></div>
        </li>
      </ul>
    </section>`;
}

function renderSetup() {
  S.view = 'setup'; paintChrome(); document.body.classList.add('auth-view');
  setMeta('setup');
  app().innerHTML = `
  <div class="auth-split">
    ${authHero()}
    <div class="card auth-card">
      <h1>First run</h1>
      <p class="muted small">No accounts exist yet. Create the administrator — this account approves everyone else.</p>
      <form id="setupform" novalidate>
        <div class="errsummary" role="alert" tabindex="-1" hidden></div>
        <label for="u">Admin username</label>
        <input id="u" name="username" autocomplete="username" placeholder="e.g. seeker" required>
        <label for="e">Email (optional)</label>
        <input id="e" name="email" type="email" autocomplete="email">
        <label for="p">Password</label>
        <input id="p" name="password" type="password" autocomplete="new-password" required aria-describedby="p-hint">
        <p class="field-hint" id="p-hint">8+ characters. Stored as a scrypt hash, never as text.</p>
        <div style="height:16px"></div>
        <button class="primary" id="go" type="submit" style="width:100%">Create administrator</button>
      </form>
      <p class="auth-legal">Using LearnLoop means you accept the
        <a href="/terms">terms</a> and the <a href="/privacy">privacy policy</a>.</p>
    </div>
  </div>`;

  wireField($('#u'), RULES.username);
  wireField($('#e'), RULES.email);
  wireField($('#p'), RULES.password);

  $('#setupform').onsubmit = async (ev) => {
    ev.preventDefault();
    const form = $('#setupform');
    const items = [];
    [['u', RULES.username], ['e', RULES.email], ['p', RULES.password]].forEach(([id, rule]) => {
      const input = $('#' + id);
      const msg = rule(input.value);
      showFieldError(input, msg);
      if (msg) items.push({ id, message: msg });
    });
    errorSummary(form, items);
    if (items.length) return;
    const btn = $('#go');
    btn.disabled = true;
    try {
      await api('/api/setup', { method: 'POST', body: { username: $('#u').value.trim(), email: $('#e').value.trim(), password: $('#p').value } });
      await login($('#u').value.trim(), $('#p').value);
    } catch (err) {
      toast(err.message, true);
      errorSummary(form, [{ id: 'u', message: err.message }]);
    }
    btn.disabled = false;
  };
}

function renderAuth(mode = 'login') {
  S.view = mode; paintChrome(); document.body.classList.add('auth-view');
  const isLogin = mode === 'login';
  setMeta(isLogin ? 'login' : 'signup');
  app().innerHTML = `
  <div class="auth-split">
    ${authHero()}
    <div class="card auth-card">
      <h1>${isLogin ? 'Sign in' : 'Request an account'}</h1>
      <p class="muted small">${isLogin
        ? 'Your plan, your notes and your graded exercises.'
        : 'An administrator approves every new account before it can sign in.'}</p>
      <form id="authform" novalidate>
        <div class="errsummary" role="alert" tabindex="-1" hidden></div>
        <label for="u">Username</label>
        <input id="u" name="username" autocomplete="username" required>
        ${isLogin ? '' : `<label for="e">Email (optional)</label>
        <input id="e" name="email" type="email" autocomplete="email">`}
        <label for="p">Password</label>
        <input id="p" name="password" type="password" required
               autocomplete="${isLogin ? 'current-password' : 'new-password'}"
               aria-describedby="p-hint">
        <p class="field-hint" id="p-hint">${isLogin ? 'At least 8 characters.' : '8+ characters. Pick something you do not reuse elsewhere.'}</p>
        <div class="sr-only" aria-hidden="true">
          <label for="company">Company</label>
          <input id="company" name="company" tabindex="-1" autocomplete="off">
        </div>
        <div style="height:16px"></div>
        <button class="primary" id="go" type="submit" style="width:100%">${isLogin ? 'Sign in' : 'Request account'}</button>
      </form>
      <p class="small dim" style="margin-top:14px">
        ${isLogin
          ? 'No account yet? <a href="#/signup">Request one</a>.'
          : 'Already approved? <a href="#/login">Sign in</a>.'}
      </p>
      <p class="auth-legal">By continuing you accept the <a href="/terms">terms</a> and the
        <a href="/privacy">privacy policy</a>. One essential cookie keeps you signed in.</p>
    </div>
  </div>`;

  const started = Date.now();
  wireField($('#u'), RULES.username);
  wireField($('#p'), isLogin ? null : RULES.password);
  if ($('#e')) wireField($('#e'), RULES.email);

  $('#authform').onsubmit = async (ev) => {
    ev.preventDefault();
    const form = $('#authform');
    const items = [];
    const u = $('#u').value.trim();
    const p = $('#p').value;
    const email = $('#e') ? $('#e').value.trim() : '';

    const uMsg = RULES.username(u);
    showFieldError($('#u'), uMsg);
    if (uMsg) items.push({ id: 'u', message: uMsg });
    if (!isLogin) {
      const pMsg = RULES.password(p);
      showFieldError($('#p'), pMsg);
      if (pMsg) items.push({ id: 'p', message: pMsg });
      if ($('#e')) {
        const eMsg = RULES.email(email);
        showFieldError($('#e'), eMsg);
        if (eMsg) items.push({ id: 'e', message: eMsg });
      }
    } else if (!p) {
      items.push({ id: 'p', message: 'Enter your password.' });
      showFieldError($('#p'), 'Enter your password.');
    }
    errorSummary(form, items);
    if (items.length) return;

    const btn = $('#go');
    btn.disabled = true;
    if (!isLogin) {
      try {
        const r = await api('/api/signup', {
          method: 'POST',
          body: { username: u, email: email, password: p, t: started,
                  company: $('#company') ? $('#company').value : '' },
        });
        S.view = 'signup'; setMeta('signup');
        app().innerHTML = `<div class="auth-wrap"><div class="card"><h1>Request sent</h1>
          <p class="muted">${esc(r.message)}</p>
          <p class="small dim">Username: <b>${esc(u)}</b></p>
          <a class="btnlink primary" href="#/login" style="width:100%;margin-top:14px">Back to sign in</a>
          </div></div>`;
      } catch (err) {
        toast(err.message, true);
        errorSummary(form, [{ id: 'u', message: err.message }]);
      }
      btn.disabled = false;
      return;
    }
    const ok = await login(u, p);
    if (!ok) btn.disabled = false;
  };
}

async function login(username, password) {
  try {
    const r = await api('/api/login', { method: 'POST', body: { username, password } });
    S.user = r.user;
    await loadCourses();
    await refreshPlan();
    paintChrome();
    location.hash = '#/plan';
    route();
    toast(`Welcome back, ${S.user.username}`);
    return true;
  } catch (err) {
    toast(err.message, true);
    const form = $('#authform');
    if (form) errorSummary(form, [{ id: 'u', message: err.message }]);
    return false;
  }
}

/* ---------------------------------------------------------------------- plan */
function sessionCard(s, nextN) {
  const cls = ['sess'];
  if (s.done) cls.push('done');
  if (s.n === nextN) cls.push('today');
  const marks = [
    s.n === nextN && !s.done ? '<span class="chip chip--ok">next up</span>' : '',
    s.has_file ? '<span class="tag">pdf</span>' : '<span class="tag">no pdf</span>',
    (s.exercise_slugs || []).length
      ? `<span class="tag">${s.exercises_passed}/${s.exercise_slugs.length} ex</span>` : '',
    s.notes ? `<span class="tag">${s.notes} note${s.notes > 1 ? 's' : ''}</span>` : '',
    s.minutes_spent ? `<span class="tag">${s.minutes_spent} min</span>` : '',
  ].filter(Boolean).join('');
  return `<div class="${cls.join(' ')}" data-n="${s.n}" role="link" tabindex="0">
    <span class="n">S${String(s.n).padStart(2, '0')}</span>
    <div>
      <div class="blk">${esc(s.block)}</div>
      <div class="meta">${esc(fmtDate(s.date))} · ${s.minutes} min${s.pages ? ' · p' + esc(s.pages) : ''}</div>
    </div>
    <div class="marks">${marks}</div>
  </div>`;
}

function renderPlan() {
  S.view = 'plan';
  const p = S.plan;
  if (!p) { paintChrome(); setMeta('plan'); app().innerHTML = '<div class="empty">No plan loaded.</div>'; return; }
  setMeta('plan', 'Plan', p.course.title);
  paintChrome();
  const next = p.sessions.find(s => !s.done);
  const weeks = {};
  p.sessions.forEach(s => { (weeks[s.week] ||= []).push(s); });
  const hoursLeft = Math.max(0, Math.round((p.total_minutes - p.minutes_done) / 60));
  const exPct = p.exercise_total ? Math.round(100 * p.exercise_passed / p.exercise_total) : 0;

  const hero = next ? `
    <section class="panel next">
      <p class="kicker">Next up · week ${next.week} · session ${next.n} of ${p.count}</p>
      <h2 class="next-title">${esc(next.block)}</h2>
      <p>${esc(next.what)}</p>
      <div class="row" style="margin-bottom:16px">
        <span class="chip chip--info">${next.minutes} min planned</span>
        ${next.pages ? `<span class="chip">pages ${esc(next.pages)}</span>` : ''}
        ${p.exercise_total ? `<span class="chip chip--ok">${p.exercise_passed}/${p.exercise_total} exercises passing</span>` : ''}
      </div>
      <p class="small muted" style="margin-bottom:18px">
        <b style="color:var(--text)">Deliverable:</b> ${esc(next.deliverable)}
      </p>
      <div class="next-actions">
        <button class="primary" id="open">Open session</button>
        <button class="ghost" id="markdone">Mark done</button>
        ${(next.exercise_slugs || []).length ? '<button class="ghost" id="toex">Chapter exercises</button>' : ''}
      </div>
    </section>` : `
    <section class="panel next">
      <p class="kicker">${esc(p.course.title)}</p>
      <h2 class="next-title">All ${p.count} sessions done</h2>
      <p>Nothing left in this course. Revisit any session below, or start another course from the rail.</p>
      <div class="next-actions"><a class="btnlink primary" href="#/exercises">Keep the exercises sharp</a></div>
    </section>`;

  const stats = `
    <aside class="next-stats">
      <div class="panel kpi">
        <div class="kpi-label">Sessions done</div>
        <div class="kpi-num">${p.done_count}<span> / ${p.count}</span></div>
        <div class="bar thin"><i style="width:${p.percent}%"></i></div>
        <div class="kpi-label">${p.percent}% · ${hoursLeft} h of study left</div>
      </div>
      <div class="panel kpi">
        <div class="kpi-label">Exercises passing</div>
        <div class="kpi-num">${p.exercise_passed}<span> / ${p.exercise_total || 0}</span></div>
        <div class="bar thin"><i style="width:${exPct}%"></i></div>
        <div class="kpi-label">${p.minutes_spent} min tracked on this course</div>
      </div>
    </aside>`;

  const adminBar = S.user.role === 'admin' ? `
    <div class="panel" style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center">
      <span class="chip chip--flat">Maintenance</span>
      <button class="small" id="split">Split the guide into session PDFs</button>
      <button class="small" id="syncall">Upload all PDFs to the NAS</button>
      <span class="dim small">${p.sessions.filter(s => s.has_file).length} of ${p.count} session PDFs ready</span>
    </div>` : `
    <p class="dim small" style="margin-top:16px">${p.sessions.filter(s => s.has_file).length} of ${p.count} session PDFs ready</p>`;

  const groups = Object.keys(weeks).sort((a, b) => a - b).map(w => `
    <div class="week-group">
      <div class="week-head"><h3>Week ${w}</h3>
      <span class="dim small">${weeks[w].length} sessions · ${weeks[w].reduce((a, s) => a + s.minutes, 0)} min</span></div>
      <div class="sessions">${weeks[w].map(s => sessionCard(s, next && next.n)).join('')}</div>
    </div>`).join('');

  app().innerHTML = `
    <div class="coursetitle"><h2>${esc(p.course.title)}</h2>
      <span class="muted small">${esc(p.course.subtitle || '')}</span></div>
    <div class="dash">${hero}${stats}</div>
    ${adminBar}
    ${groups}`;

  const openSession = (n) => { location.hash = '#/session/' + n; };
  document.querySelectorAll('.sess').forEach(el => {
    el.onclick = () => openSession(el.dataset.n);
    el.onkeydown = (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openSession(el.dataset.n); }
    };
    el.onmouseenter = () => prefetchSession(el.dataset.n);
  });
  if (next) {
    prefetchSession(next.n);
    $('#open').onclick = () => openSession(next.n);
    $('#markdone').onclick = () => markDone(next.n, true, renderPlan);
    if ($('#toex')) $('#toex').onclick = () => { location.hash = '#/exercises'; };
  }
  if (S.user.role === 'admin' && $('#split')) {
    $('#split').onclick = async (e) => {
      e.target.disabled = true; e.target.innerHTML = '<span class="spin"></span> splitting…';
      try {
        const r = await api('/api/split' + q(), { method: 'POST' });
        toast(`Wrote ${r.written.length} PDFs (${r.skipped.length} already there)`);
        await refreshPlan(); renderPlan();
      } catch (err) { toast(err.message, true); e.target.disabled = false; e.target.textContent = 'Split the guide into session PDFs'; }
    };
    $('#syncall').onclick = (e) => uploadAll(e.target);
  }
}

/* Which chapter a session's block belongs to (mirrors the server mapping). */
function chapterOfBlock(block) {
  const b = String(block || '');
  let m = b.match(/\bChapter\s+(\d+)/i) || b.match(/\bCh\s+(\d+)/i);
  if (m) return Number(m[1]);
  m = b.match(/\bLab\s+(\d+)/i);
  if (m) return 100 + Number(m[1]);
  return null;
}

async function chapterIsComplete(chapter) {
  try {
    const r = await api('/api/exercises' + q());
    const list = (r.exercises || []).filter(x => x.chapter === chapter);
    return list.length > 0 && list.every(x => x.passed);
  } catch (e) { return false; }
}

/* All exercises of a chapter are done: mark the owning session done, open the next one. */
async function finishChapter(chapter) {
  const sessions = (S.plan && S.plan.sessions) || [];
  const owning = sessions.filter(s => chapterOfBlock(s.block) === chapter);
  if (!owning.length) return false;
  const owner = owning[owning.length - 1].n;
  try {
    await api('/api/progress', { method: 'POST', body: { course: S.course, session: owner, done: true } });
  } catch (e) { /* the card already said done; keep moving */ }
  await refreshPlan();
  toast('That part is finished — moving to the next session');
  const next = sessions.find(s => s.n === owner + 1);
  location.hash = next ? '#/session/' + next.n : '#/plan';
  return true;
}

async function markDone(n, done, after) {
  try {
    const r = await api('/api/progress', { method: 'POST', body: { course: S.course, session: n, done } });
    if (r.warning) toast(r.warning, true); else toast(done ? `Session ${n} marked done` : `Session ${n} reopened`);
    await refreshPlan();
    if (done) {
      // finishing a part should take you straight to its exercise, or to the next part
      const nx = await api('/api/next-exercise?course=' + encodeURIComponent(S.course) + '&session=' + n).catch(() => null);
      if (nx && nx.slug) { location.hash = '#/exercise/' + nx.slug; return; }
      const sessions = (S.plan && S.plan.sessions) || [];
      const next = sessions.find(s => s.n === n + 1);
      location.hash = next ? '#/session/' + next.n : '#/plan';
      return;
    }
    (after || renderPlan)();
  } catch (err) { toast(err.message, true); }
}

/* ------------------------------------------------------------------ session */
function ensureTimer() {
  if (!S.timer) S.timer = { id: null, remaining: 0, total: 0, running: false, elapsed: 0, n: null, logged: 0 };
  return S.timer;
}
function clearTimer() {
  const t = ensureTimer();
  if (t.id) clearInterval(t.id);
  t.id = null; t.running = false;
}
const fmtClock = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

function timerTick() {
  const t = ensureTimer();
  if (!t.running) return;
  t.remaining -= 1; t.elapsed += 1;
  const clock = $('#clock');
  if (clock) { clock.textContent = fmtClock(Math.max(0, t.remaining)); clock.classList.toggle('low', t.remaining <= 60); }
  if (t.remaining <= 0) {
    t.running = false; clearInterval(t.id); t.id = null;
    logSpent(true);
    toast('Session time is up — save your notes');
  }
}

async function logSpent(finished) {
  const t = ensureTimer();
  const mins = Math.floor((t.elapsed - t.logged) / 60);
  if (mins <= 0 || !t.n) return 0;
  t.logged += mins * 60;
  try {
    const r = await api('/api/timer', { method: 'POST', body: { course: S.course, session: t.n, minutes: mins } });
    if (finished) toast(`Logged ${mins} min (${r.minutes_spent} total)`);
    return r.minutes_spent;
  } catch (err) { toast(err.message, true); return 0; }
}

function openVideo(url, title) {
  const old = document.querySelector('.videomodal');
  if (old) old.remove();
  const wrap = document.createElement('div');
  wrap.className = 'videomodal';
  wrap.innerHTML = `<div class="videobox">
    <div class="row" style="justify-content:space-between;align-items:center">
      <b>${esc(title || 'Lesson video')}</b>
      <button class="ghost small" id="vclose">Close</button>
    </div>
    <video id="vplayer" src="${esc(url)}" controls autoplay playsinline></video>
  </div>`;
  document.body.appendChild(wrap);
  $('#vclose').onclick = () => wrap.remove();
  wrap.onclick = (e) => { if (e.target === wrap) wrap.remove(); };
}

async function openPlayer(info, n) {
  const old = $('#player'); if (old) old.remove();
  const side = $('.side'); if (!side) return;
  const key = `ll-lecture-${S.user.id}-${S.course}-${n}`;
  const card = document.createElement('div');
  card.className = 'card player'; card.id = 'player';
  card.innerHTML = `
    <div class="row" style="justify-content:space-between;align-items:center">
      <h3 style="margin:0">${icon('headphones')} Lecture</h3>
      <span class="dim small" id="plect">${esc(info.title || '')}</span>
    </div>
    <audio id="paudio" preload="metadata" src="${esc(info.url)}"></audio>
    <div class="row" style="margin-top:12px;gap:10px;align-items:center">
      <button class="primary small" id="pplay">${icon('play')}Play</button>
      <input type="range" id="pseek" min="0" max="100" step="0.5" value="0" style="flex:1">
      <span class="small" id="ptime">0:00</span>
    </div>
    <div class="row" style="margin-top:10px;justify-content:space-between;align-items:center">
      <label class="small" style="display:flex;gap:6px;align-items:center;margin:0">speed
        <select id="pspeed">
          ${[0.75,1,1.25,1.5,1.75,2].map(v => `<option value="${v}"${v===1?' selected':''}>${v}×</option>`).join('')}
        </select>
      </label>
      <span class="dim small" id="pdur">${info.minutes ? '~' + info.minutes + ' min' : ''}</span>
    </div>`;
  side.insertBefore(card, side.firstChild);

  const a = $('#paudio'), play = $('#pplay'), seek = $('#pseek'), time = $('#ptime');
  const fmt = (s) => fmtClock(Math.floor(s || 0));
  const save = () => { try { localStorage.setItem(key, String(a.currentTime)); } catch (e) {} };
  const restore = () => {
    let v = 0; try { v = parseFloat(localStorage.getItem(key) || '0'); } catch (e) {}
    if (v > 5 && (!a.duration || v < a.duration - 5)) a.currentTime = v;
  };
  a.addEventListener('loadedmetadata', () => { seek.max = a.duration || 100; restore(); });
  a.addEventListener('timeupdate', () => {
    seek.value = a.currentTime;
    time.textContent = `${fmt(a.currentTime)} / ${fmt(a.duration)}`;
    if (a.currentTime > 0 && Math.floor(a.currentTime) % 5 === 0) save();
  });
  a.addEventListener('play', () => { play.innerHTML = icon('pause') + 'Pause'; });
  a.addEventListener('pause', () => { play.innerHTML = icon('play') + 'Play'; save(); });
  a.addEventListener('ended', () => {
    play.innerHTML = icon('play') + 'Play';
    try { localStorage.removeItem(key); } catch (e) {}
  });
  play.onclick = () => { if (a.paused) { a.play().catch(() => {}); } else { a.pause(); } };
  seek.oninput = () => { a.currentTime = Number(seek.value); };
  $('#pspeed').onchange = (e) => { a.playbackRate = Number(e.target.value); };
  a.playbackRate = 1;
  a.play().catch(() => {});
}

async function renderSession(n) {
  S.view = 'session';
  n = Number(n);
  if (!S.plan) await refreshPlan();
  const s = S.plan.sessions.find(x => x.n === n);
  if (!s) {
    setMeta('notfound', 'Session not found', '404');
    paintChrome();
    app().innerHTML = `<div class="panel notfound"><p class="kicker">404</p>
      <h1>No session ${esc(String(n))}</h1>
      <p class="muted">This course has sessions 1 to ${S.plan ? S.plan.count : '?'}. The link may be old.</p>
      <a class="btnlink primary" href="#/plan" style="margin-top:14px">Back to the plan</a></div>`;
    return;
  }
  S.session = s;
  setMeta('session', `S${String(n).padStart(2, '0')} · ${s.block}`, `${S.plan.course.title} · week ${s.week}`);
  paintChrome();
  clearTimer();
  const t = ensureTimer();
  t.n = n; t.total = s.minutes * 60; t.remaining = s.minutes * 60; t.elapsed = 0; t.logged = 0; t.running = false;

  app().innerHTML = `
  <div class="row row--between" style="margin-bottom:14px">
    <div class="row">
      <a class="btnlink" href="#/plan" style="min-height:34px;padding:6px 12px;font-size:13px">Back to plan</a>
      <span class="dim small">Session ${n} of ${S.plan.count} · ${esc(fmtDate(s.date))}</span>
    </div>
    <span class="chip ${s.done ? 'chip--ok' : 'chip--info'}">${s.done ? 'done' : 'in progress'}</span>
  </div>
  <div class="reader">
    <div class="paper pdfpane">
      <div class="paper-bar pdfbar">
        <span>S${String(n).padStart(2, '0')} · ${esc(s.block)}</span>
        <span class="spacer"></span>
        ${s.pages ? `<span class="dim">p${esc(s.pages)}</span>` : ''}
        <button class="ghost" id="watch" title="Narrated lesson video">${icon('video')}Watch</button>
        <button class="ghost" id="listen" title="Narrated audio of this chapter">${icon('headphones')}Listen</button>
        <a class="btnlink" href="/api/pdf/${n}${q()}" target="_blank" rel="noopener"
           style="min-height:30px;padding:4px 10px;font-size:12px">PDF</a>
      </div>
      <div id="pdfhost"></div>
    </div>
    <div class="side">
      <div class="rail-card">
        <h3>What to do</h3>
        <p class="small" style="margin:8px 0 0">${esc(s.what)}</p>
        <h3 style="margin-top:16px">Deliverable</h3>
        <p class="small" style="margin:8px 0 0;color:#d7e3f1">${esc(s.deliverable)}</p>
      </div>
      <div class="rail-card">
        <div class="row row--between"><h3>Timer</h3><span class="dim small">${s.minutes} min planned</span></div>
        <div class="timer">
          <div class="clock" id="clock">${fmtClock(s.minutes * 60)}</div>
          <div class="row"><button class="primary small" id="tstart">Start</button><button class="small" id="treset">Reset</button></div>
        </div>
        <div class="small dim" style="margin-top:10px">${s.minutes_spent} min tracked</div>
      </div>
      <div class="rail-card">
        <h3>Notes</h3>
        <textarea id="note" placeholder="What clicked? What is still fuzzy? Paste the deliverable here."></textarea>
        <div class="row row--between" style="margin-top:10px">
          <label class="small" style="margin:0;display:flex;gap:7px;align-items:center">
            <input type="checkbox" id="deliv" style="width:auto"> deliverable done</label>
          <button class="primary small" id="savenote">Save to vault</button>
        </div>
        <div id="notelist"></div>
      </div>
      <div class="rail-card">
        <h3>Progress${S.user.role === 'admin' ? ' &amp; sync' : ''}</h3>
        <div class="row" style="margin-top:10px">
          <button class="${s.done ? 'small' : 'primary small'}" id="toggle">${s.done ? 'Reopen session' : 'Mark done'}</button>
          ${S.user.role === 'admin' ? '<button class="small" id="nasup">Upload PDF</button>' : ''}
        </div>
        <div class="small dim" id="nasmsg" style="margin-top:8px"></div>
      </div>
    </div>
  </div>`;

  $('#listen').onclick = async () => {
    try {
      const r = await api(`/api/lecture?course=${encodeURIComponent(S.course)}&session=${n}`);
      if (!r.available) { toast(r.reason || 'No audio for this chapter yet', true); return; }
      openPlayer(r, n);
    } catch (e) { toast(e.message || 'Could not load the lecture', true); }
  };

  $('#watch').onclick = async () => {
    try {
      const r = await api(`/api/video?course=${encodeURIComponent(S.course)}&session=${n}`);
      if (!r.available) { toast(r.reason || 'No video for this session yet', true); return; }
      openVideo(r.url, s.block);
    } catch (e) { toast(e.message || 'Could not load the video', true); }
  };
  $('#tstart').onclick = () => {
    const t2 = ensureTimer();
    if (t2.running) { t2.running = false; clearInterval(t2.id); t2.id = null; $('#tstart').textContent = 'Resume'; logSpent(false); return; }
    t2.running = true; t2.id = setInterval(timerTick, 1000); $('#tstart').textContent = 'Pause';
  };
  $('#treset').onclick = () => {
    const t2 = ensureTimer(); clearTimer();
    t2.remaining = t2.total; t2.elapsed = 0; t2.logged = 0;
    $('#clock').textContent = fmtClock(t2.total); $('#tstart').textContent = 'Start';
  };
  $('#toggle').onclick = () => markDone(n, !S.session.done, () => renderSession(n));
  $('#savenote').onclick = async () => {
    const body = $('#note').value.trim();
    if (!body) { toast('Nothing to save', true); return; }
    try {
      const r = await api('/api/notes', { method: 'POST', body: { course: S.course, session: n, body, deliverable_done: $('#deliv').checked, minutes_spent: s.minutes_spent } });
      toast(r.warning || 'Saved to the vault');
      $('#note').value = '';
      await loadNotes(n);
      await refreshPlan();
    } catch (err) { toast(err.message, true); }
  };
  if ($('#nasup')) $('#nasup').onclick = async (e) => {
    e.target.disabled = true; e.target.innerHTML = '<span class="spin"></span> uploading';
    try {
      const r = await api('/api/nas/upload', { method: 'POST', body: { session: n, target: 'lan', course: S.course } });
      if (r.uploaded && r.uploaded.length) { $('#nasmsg').textContent = `Uploaded ${r.uploaded[0]}`; toast('Uploaded to the NAS'); }
      else { $('#nasmsg').textContent = r.message; toast(r.message, true); }
    } catch (err) { $('#nasmsg').textContent = err.message; toast(err.message, true); }
    e.target.disabled = false; e.target.textContent = 'Upload PDF to NAS';
  };

  if (S.course === 'build-llm') renderTextReader(n); else renderPdf(n);
  loadNotes(n);
}

async function renderTextReader(n) {
  const host = $('#pdfhost');
  if (!host) return;
  host.innerHTML = '<div class="empty"><span class="spin"></span> loading text…</div>';
  try {
    const r = await api('/api/reader?course=' + encodeURIComponent(S.course) + '&session=' + n);
    let html = '', inUl = false;
    for (const b of (r.blocks || [])) {
      if (b.t === 'li') {
        if (!inUl) { html += '<ul>'; inUl = true; }
        html += `<li>${esc(b.text)}</li>`;
        continue;
      }
      if (inUl) { html += '</ul>'; inUl = false; }
      if (b.t === 'h1') html += `<h1>${esc(b.text)}</h1>`;
      else if (b.t === 'h2') html += `<h2>${esc(b.text)}</h2>`;
      else if (b.t === 'quote') html += `<blockquote>${esc(b.text)}</blockquote>`;
      else if (b.t === 'pre') html += `<pre>${esc(b.text)}</pre>`;
      else html += `<p>${esc(b.text)}</p>`;
    }
    if (inUl) html += '</ul>';
    host.innerHTML = `<article class="prose">${html}</article>`;
  } catch (err) {
    host.innerHTML = `<div class="empty">Could not load the text (${esc(err.message)}).<br>
      <a href="/api/pdf/${n}${q()}" target="_blank">Open the PDF instead</a></div>`;
  }
}

async function loadNotes(n) {
  try {
    const r = await api('/api/notes?session=' + n + (S.course ? '&course=' + encodeURIComponent(S.course) : ''));
    const host = $('#notelist');
    if (!host) return;
    host.innerHTML = r.notes.length
      ? r.notes.map(x => `<div class="note"><span class="when">${new Date(x.created_at).toLocaleString()}${x.vault_path ? ' · vault' : ''}</span>${esc(x.body)}</div>`).join('')
      : '<div class="small dim" style="margin-top:10px">No notes yet.</div>';
  } catch { /* ignore */ }
}

async function renderPdf(n) {
  const host = $('#pdfhost');
  if (!host) return;
  host.innerHTML = '<div class="empty"><span class="spin"></span> loading PDF…</div>';
  try {
    const pdfjs = await import('/static/vendor/pdfjs/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
    const doc = await pdfjs.getDocument({ url: '/api/pdf/' + n + q(), withCredentials: true }).promise;
    host.innerHTML = '';
    const target = Math.max(320, (host.clientWidth || 700) - 24);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    for (let p = 1; p <= doc.numPages; p++) {
      const page = await doc.getPage(p);
      const base = page.getViewport({ scale: 1 });
      const scale = (target / base.width) * dpr;
      const vp = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.style.width = '100%'; canvas.height = Math.floor(vp.height); canvas.width = Math.floor(vp.width);
      host.appendChild(canvas);
      await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
    }
  } catch (err) {
    host.innerHTML = `<div class="empty">Could not render with pdf.js (${esc(err.message)}).<br>
      <a href="/api/pdf/${n}${q()}" target="_blank">Open the PDF in a new tab</a></div>`;
  }
}

/* ----------------------------------------------------------------- exercises */
async function renderExercises() {
  S.view = 'exercises'; paintChrome(); setMeta('exercises');
  app().innerHTML = '<div class="empty"><span class="spin"></span></div>';
  try {
    const r = await api('/api/exercises' + q());
    S.exercises = r;
    if (!r.exercises.length) {
      app().innerHTML = '<div class="empty">No exercises in this course yet.</div>';
      return;
    }
    const byChapter = {};
    r.exercises.forEach(e => { (byChapter[e.chapter] ||= []).push(e); });
    const blocks = Object.keys(byChapter).sort((a, b) => a - b).map(ch => `
      <div class="exchapter">
        <div class="week-head"><h3>${Number(ch) >= 100 ? 'Lab ' + (ch - 100) : 'Chapter ' + ch}</h3>
        <span class="dim small">${byChapter[ch].filter(e => e.passed).length}/${byChapter[ch].length} done</span></div>
        <div class="exlist">${byChapter[ch].map(e => `
          <a class="exitem ${e.passed ? 'passed' : ''}" href="#/exercise/${encodeURIComponent(e.slug)}">
            <span class="exname">${esc(e.title)}</span>
            <span class="exmeta">${e.kind === 'answer'
              ? 'written · reveal the answer'
              : e.kind === 'mcq'
                ? 'multiple choice · 4 options'
                : `${esc(e.difficulty)} · ${e.tests} test${e.tests === 1 ? '' : 's'}`}${e.attempts ? ' · ' + e.attempts + ' try' + (e.attempts === 1 ? '' : 'ies') : ''}</span>
            <span class="exstate">${e.passed ? '✓' : ''}</span>
          </a>`).join('')}</div>
      </div>`).join('');

    const pct = r.total ? Math.round(100 * r.passed / r.total) : 0;
    app().innerHTML = `
      <section class="panel" style="display:grid;gap:10px;margin-bottom:20px">
        <div class="row row--between">
          <div>
            <div class="kpi-label dim small">Exercises passing</div>
            <div class="kpi-num" style="font-size:26px">${r.passed}<span> / ${r.total}</span></div>
          </div>
          <span class="chip ${r.total && r.passed === r.total ? 'chip--ok' : 'chip--info'}">${pct}% complete</span>
        </div>
        <div class="bar thin"><i style="width:${pct}%"></i></div>
        <p class="muted small" style="margin:2px 0 0">Chapter questions are multiple choice — pick an answer and get told why. Lab exercises are graded on the server: your code runs against hidden tests.</p>
      </section>
      ${blocks}`;
  } catch (err) {
    app().innerHTML = `<div class="empty">${esc(err.message)}</div>`;
  }
}

async function renderExercise(slug) {
  S.view = 'exercise'; paintChrome();
  app().innerHTML = '<div class="empty"><span class="spin" aria-hidden="true"></span></div>';
  let ex;
  try { ex = await api('/api/exercise/' + encodeURIComponent(slug)); }
  catch (err) {
    setMeta('notfound', 'Exercise not found', '404');
    app().innerHTML = `<div class="panel notfound"><p class="kicker">404</p>
      <h1>That exercise is gone</h1>
      <p class="muted">${esc(err.message)}</p>
      <a class="btnlink primary" href="#/exercises" style="margin-top:14px">Back to exercises</a></div>`;
    return;
  }
  setMeta('exercise', ex.title, ex.chapter >= 100 ? `Lab ${ex.chapter - 100}` : `Chapter ${ex.chapter}`);

  // an exercise opened by URL may belong to a different course: follow it
  if (ex.course_id && S.courses.length) {
    const owner = S.courses.find(c => c.id === ex.course_id);
    if (owner && owner.slug !== S.course) {
      S.course = owner.slug;
      localStorage.setItem('ll-course', owner.slug);
      try { await refreshPlan(); } catch { /* keep going */ }
      paintChrome();
    }
  }

  // Drafts belong to an account, not to a browser. Keying them by slug alone meant the
  // next person to sign in on the same machine was shown the previous user's code.
  const uid = (S.user && S.user.id != null) ? S.user.id : 'anon';
  const draftKey = `ll-draft-${uid}-${slug}`;
  localStorage.removeItem('ll-draft-' + slug);      // drop the old shared-key drafts
  const draft = localStorage.getItem(draftKey);
  const code = draft || ex.starter || '';

  const isAnswer = (ex.kind || 'code') === 'answer';
  const isMcq = (ex.kind || 'code') === 'mcq';
  const chapterLabel = ex.chapter >= 100 ? `Lab ${ex.chapter - 100}` : `Chapter ${ex.chapter}`;

  app().innerHTML = `
  <div class="row row--between" style="margin-bottom:14px">
    <div class="row">
      <a class="btnlink" href="#/exercises" style="min-height:34px;padding:6px 12px;font-size:13px">Exercises</a>
      <span class="chip">${chapterLabel}</span>
      <span class="chip chip--flat">${esc(ex.difficulty)}</span>
    </div>
    ${isAnswer || isMcq ? '' : '<button class="small ghost" id="hints">Hints</button>'}
  </div>
  <div class="exwrap${isAnswer ? ' exwrap--single' : ''}">
    <div class="panel exprompt">
      <h2 style="font-size:19px">${esc(ex.title)}</h2>
      <pre class="prompttext">${esc(ex.prompt)}</pre>
      <div id="hintbox" hidden>
        <h3 style="margin-top:16px">Hints</h3>
        <ul class="small muted">${(ex.hints || []).map(h => `<li>${esc(h)}</li>`).join('') || '<li>No hints.</li>'}</ul>
      </div>
      ${isAnswer || isMcq ? '' : `<h3 style="margin-top:18px">Tests that will run</h3>
      <ul class="small dim">${(ex.tests || []).map(t => `<li>${esc(t.name)}</li>`).join('')}</ul>`}
    </div>
    ${isMcq ? `
    <div class="panel">
      <h3>Choose one</h3>
      <div id="choices" class="choices" style="margin-top:12px"></div>
      <div class="row" style="margin-top:14px">
        <button class="primary" id="check">Check answer</button>
        <span class="small dim" id="mcqstate"></span>
      </div>
      <div id="results" style="margin-top:12px"></div>
      <div id="explain" hidden style="margin-top:16px">
        <h3>Why</h3>
        <p class="small" style="color:#d7e3f1;margin-top:6px"></p>
      </div>
    </div>` : isAnswer ? `
    <div class="panel">
      <h3>Your turn</h3>
      <p class="small muted" style="margin-top:8px">Work it out on paper or in a note first — reading an answer you did not try teaches you nothing. Then compare.</p>
      <div class="row" style="margin-top:14px">
        <button class="primary" id="reveal">Reveal the answer</button>
        <button class="ghost" id="done">Mark as done</button>
      </div>
      <div id="answerbox" hidden style="margin-top:16px">
        <h3>The book's answer</h3>
        <pre class="prompttext" style="color:#d7e3f1">${esc(ex.answer || 'No answer recorded.')}</pre>
      </div>
      <div id="results" style="margin-top:12px"></div>
    </div>
    <div class="panel">
      <h3>How this works</h3>
      <ol class="steps">
        <li><div><b>Write it down first</b><span>One or two sentences in your own words. Analysing your own attempt is what makes the book's answer stick.</span></div></li>
        <li><div><b>Reveal and compare</b><span>Note what you missed and what you got right — that difference is the lesson.</span></div></li>
        <li><div><b>Mark it done</b><span>It counts in your progress, and the next exercise is one click away.</span></div></li>
      </ol>
    </div>` : `
    <div class="panel panel--flush">
      <div class="panel-head">
        <h3 style="margin:0">Your code</h3>
        <span class="small dim" id="draftstate"></span>
      </div>
      <div style="padding:14px">
        <div class="editor" id="editorbox">
          <pre class="hl" id="hl" aria-hidden="true"><code id="hlcode"></code></pre>
          <textarea id="code" class="codearea" spellcheck="false" autocomplete="off" autocapitalize="off" wrap="off"></textarea>
        </div>
        <div class="row" style="margin-top:12px">
          <button class="primary" id="run">Run tests</button>
          <button class="ghost small" id="reset">Reset</button>
          <span class="small dim" id="runsize"></span>
          <span class="small dim" style="margin-left:auto">Tab indents · Ctrl+Enter runs</span>
        </div>
        <div id="results" style="margin-top:14px"></div>
      </div>
    </div>`}
  </div>`;

  if (isAnswer) {
    $('#reveal').onclick = () => {
      const box = $('#answerbox');
      box.hidden = !box.hidden;
      $('#reveal').textContent = box.hidden ? 'Reveal the answer' : 'Hide the answer';
    };
    $('#done').onclick = async (e) => {
      e.target.disabled = true; e.target.innerHTML = '<span class="spin"></span> saving';
      try {
        await api('/api/exercise/' + encodeURIComponent(slug) + '/done', { method: 'POST', body: {} });
        toast('Marked as done');
        await loadCourses(); paintChrome();
        $('#results').innerHTML = '<div class="result good">Done — counted in your progress.</div>';
      } catch (err) { toast(err.message, true); }
      e.target.disabled = false; e.target.textContent = 'Mark as done';
    };
    return;
  }

  if (isMcq) {
    const box = $('#choices');
    box.innerHTML = (ex.options || []).map((o, i) => `
      <label class="choice"><input type="radio" name="mcq" value="${i}"><span>${esc(o)}</span></label>`).join('');

    if (ex.answered) {
      const pick = box.querySelector(`input[name="mcq"][value="${Number(ex.choice)}"]`);
      if (pick) pick.checked = true;
      box.querySelectorAll('input[name="mcq"]').forEach(i => { i.disabled = true; });
      box.querySelectorAll('label.choice').forEach(l => l.classList.add('locked'));
      const check = $('#check');
      check.disabled = true;
      check.textContent = '✓ Correct';
      const explain = $('#explain');
      explain.hidden = false;
      explain.querySelector('p').textContent = ex.explanation || '';
      $('#results').innerHTML = '<div class="result good">Already answered correctly — this exercise is done.</div>';
      autoAdvance(slug, '#results');
      return;
    }

    $('#check').onclick = async (e) => {
      const sel = box.querySelector('input[name="mcq"]:checked');
      if (!sel) { toast('Pick one option first', true); return; }
      e.target.disabled = true; e.target.innerHTML = '<span class="spin"></span> checking';
      try {
        const r = await api('/api/exercise/' + encodeURIComponent(slug) + '/check',
                            { method: 'POST', body: { choice: Number(sel.value) } });
        if (r.correct) {
          box.querySelectorAll('input[name="mcq"]').forEach(i => { i.disabled = true; });
          box.querySelectorAll('label.choice').forEach(l => { l.classList.add('locked'); });
          e.target.textContent = '✓ Correct';
          const explain = $('#explain');
          explain.hidden = false;
          explain.querySelector('p').textContent = r.explanation || '';
          $('#results').innerHTML = '<div class="result good">Correct — counted in your progress.</div>';
          toast('Correct');
          if (await chapterIsComplete(ex.chapter)) await finishChapter(ex.chapter);
          else autoAdvance(slug, '#results');
        } else {
          $('#results').innerHTML = '<div class="result bad">Not quite — think again, then check another option.</div>';
          e.target.disabled = false; e.target.textContent = 'Check answer';
        }
      } catch (err) {
        toast(err.message, true);
        e.target.disabled = false; e.target.textContent = 'Check answer';
      }
    };
    return;
  }

  const ta = $('#code');
  const hlPre = $('#hl');
  const hlCode = $('#hlcode');
  ta.value = code;
  const paint = () => {
    hlCode.innerHTML = highlightPython(ta.value);
    hlPre.scrollTop = ta.scrollTop;
    hlPre.scrollLeft = ta.scrollLeft;
  };
  paint();
  ta.addEventListener('scroll', () => { hlPre.scrollTop = ta.scrollTop; hlPre.scrollLeft = ta.scrollLeft; });
  const saveDraft = () => {
    localStorage.setItem(draftKey, ta.value);
    $('#draftstate').textContent = 'draft saved';
  };
  const updateSize = () => { $('#runsize').textContent = `${ta.value.length} chars`; };

  const INDENT = '    ';
  const INDENT_WIDTH = INDENT.length;

  function reindent(outdent) {
    const v = ta.value;
    const s = ta.selectionStart, e = ta.selectionEnd;
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    let le = v.indexOf('\n', e);
    if (le === -1) le = v.length;
    const block = v.slice(ls, le);
    const lines = block.split('\n');

    if (s === e) {
      // no selection: Tab inserts spaces at the cursor, Shift+Tab removes up to four
      if (!outdent) {
        ta.setRangeText(INDENT, s, e, 'end');
      } else {
        const before = v.slice(ls, s);
        const drop = Math.min(INDENT_WIDTH, (before.match(/ *$/) || [''])[0].length);
        if (drop) ta.setRangeText('', s - drop, s, 'end');
      }
    } else {
      let removedFirst = 0, removedTotal = 0;
      const out = lines.map((line, i) => {
        if (!outdent) return INDENT + line;
        const m = line.match(/^( {1,4}|\t)/);
        if (!m) return line;
        if (i === 0) removedFirst = m[0].length;
        removedTotal += m[0].length;
        return line.slice(m[0].length);
      });
      ta.value = v.slice(0, ls) + out.join('\n') + v.slice(le);
      const startNew = outdent ? Math.max(ls, s - removedFirst) : s + INDENT_WIDTH;
      const endNew = outdent ? Math.max(startNew, e - removedTotal) : e + INDENT_WIDTH * lines.length;
      ta.setSelectionRange(startNew, endNew);
    }
    paint(); saveDraft(); updateSize();
  }

  ta.addEventListener('input', () => { paint(); clearTimeout(ta._t); ta._t = setTimeout(saveDraft, 400); updateSize(); });

  ta.addEventListener('keydown', (ev) => {
    if (ev.key === 'Tab') {
      ev.preventDefault();
      reindent(ev.shiftKey);
      return;
    }
    if (ev.key === 'Enter' && !ev.ctrlKey && !ev.metaKey) {
      // keep Python indentation: continue the current line's indent, +4 after a colon
      const v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
      const ls = v.lastIndexOf('\n', s - 1) + 1;
      const lineText = v.slice(ls, s);
      const lead = (lineText.match(/^[ \t]*/) || [''])[0];
      const extra = /:\s*$/.test(lineText) ? INDENT : '';
      ev.preventDefault();
      const insert = '\n' + lead + extra;
      ta.setRangeText(insert, s, e, 'end');
      paint(); saveDraft(); updateSize();
      return;
    }
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      $('#run').click();
    }
  });

  updateSize();

  $('#hints').onclick = () => { const b = $('#hintbox'); b.hidden = !b.hidden; };
  $('#reset').onclick = () => { ta.value = ex.starter || ''; paint(); saveDraft(); updateSize(); };
  $('#run').onclick = async (e) => {
    e.target.disabled = true; e.target.innerHTML = '<span class="spin"></span> running';
    const host = $('#results');
    host.innerHTML = '<div class="small dim">Executing your code…</div>';
    try {
      const r = await api('/api/exercise/' + encodeURIComponent(slug) + '/run', { method: 'POST', body: { code: ta.value } });
      if (r.module_error) {
        host.innerHTML = `<div class="result bad"><b>Could not run</b><pre class="errbox">${esc(r.module_error)}</pre></div>`;
      } else {
        const rows = (r.results || []).map(t => `
          <div class="testrow ${t.ok ? 'ok' : 'bad'}">
            <span class="mark">${t.ok ? '✓' : '✗'}</span>
            <span>${esc(t.name)}</span>
            ${t.error ? `<span class="err">${esc(t.error)}</span>` : ''}
          </div>`).join('');
        host.innerHTML = `<div class="result ${r.ok ? 'good' : 'bad'}">
            <b>${r.ok ? 'All tests passed' : `${r.passed_count || 0} of ${r.total || 0} passed`}</b>
          </div>${rows}`;
        toast(r.ok ? 'All tests passed' : 'Not yet — see which test failed', !r.ok);
        if (r.ok) {
          await loadCourses(); paintChrome();
          if (await chapterIsComplete(ex.chapter)) await finishChapter(ex.chapter);
          else autoAdvance(slug, '#results');
        }
      }
    } catch (err) {
      host.innerHTML = `<div class="result bad">${esc(err.message)}</div>`;
    }
    e.target.disabled = false; e.target.textContent = 'Run tests';
  };
}

/* -------------------------------------------------------------------- search */
function renderSearch(qstr = '') {
  S.view = 'search'; paintChrome(); setMeta('search');
  app().innerHTML = `
    <div class="panel">
      <h2>Find a session, note or exercise</h2>
      <p class="muted small">Searching in ${esc(S.course || 'this course')}.</p>
      <div class="row" style="margin-top:12px">
        <input id="q" value="${esc(qstr)}" placeholder="softmax, loop, string, DataFrame…" style="flex:1">
        <button class="primary" id="go">Search</button>
      </div>
    </div>
    <div id="results" style="margin-top:16px"></div>`;
  const run = async () => {
    const query = $('#q').value.trim();
    if (query.length < 2) { toast('Type at least 2 characters', true); return; }
    const host = $('#results');
    host.innerHTML = '<div class="empty"><span class="spin"></span></div>';
    try {
      const r = await api('/api/search?q=' + encodeURIComponent(query) + (S.course ? '&course=' + encodeURIComponent(S.course) : ''));
      host.innerHTML = r.results.length ? r.results.map(x => `
        <div class="card resultcard" data-kind="${x.kind}" data-n="${x.session || ''}" data-slug="${esc(x.slug || '')}">
          <div class="row" style="justify-content:space-between">
            <b>${esc(x.title)}</b><span class="tag">${x.kind}${x.pages ? ' · p' + esc(x.pages) : ''}${x.chapter ? ' · ch' + x.chapter : ''}</span>
          </div>
          <div class="small muted" style="margin-top:6px">${esc(x.snippet)}</div>
        </div>`).join('') : '<div class="empty">Nothing matched.</div>';
      host.querySelectorAll('.resultcard').forEach(el => el.onclick = () => {
        if (el.dataset.kind === 'exercise') location.hash = '#/exercise/' + encodeURIComponent(el.dataset.slug);
        else location.hash = '#/session/' + el.dataset.n;
      });
    } catch (err) { host.innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
  };
  $('#go').onclick = run;
  $('#q').onkeydown = (e) => { if (e.key === 'Enter') run(); };
  if (qstr) run();
}

/* --------------------------------------------------------------------- admin */
async function renderAdmin() {
  S.view = 'admin'; paintChrome(); setMeta('admin');
  app().innerHTML = '<div class="empty"><span class="spin" aria-hidden="true"></span></div>';
  try {
    const [u, ev, stats] = await Promise.all([
      api('/api/admin/users'), api('/api/events'), api('/api/analytics?days=14').catch(() => null),
    ]);
    const pending = u.users.filter(x => x.status === 'pending');
    const peak = stats && stats.by_day.reduce((m, d) => Math.max(m, d.views), 0);
    const traffic = !stats ? '' : `
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:baseline">
          <h3 style="margin:0">Traffic</h3>
          <span class="small dim">first-party, no cookies · counted only for visitors who allowed it</span>
        </div>
        <div class="row" style="margin-top:14px;gap:26px">
          <div><div class="dim small">Today</div><div class="big" style="font-size:26px;font-weight:750">${stats.today}</div></div>
          <div><div class="dim small">Last 7 days</div><div class="big" style="font-size:26px;font-weight:750">${stats.last_7_days}</div></div>
          <div><div class="dim small">Last 30 days</div><div class="big" style="font-size:26px;font-weight:750">${stats.last_30_days}</div></div>
        </div>
        ${stats.by_day.length ? `<div class="row" style="margin-top:18px;align-items:flex-end;gap:6px">
          ${stats.by_day.map(d => `<span title="${esc(d.day)}: ${d.views}" style="display:flex;flex-direction:column;align-items:center;gap:6px">
            <i style="display:block;width:14px;border-radius:4px 4px 0 0;background:linear-gradient(180deg,var(--accent),var(--accent-2));height:${peak ? Math.max(3, Math.round(46 * d.views / peak)) : 3}px"></i>
            <span class="dim" style="font-size:10px">${esc(d.day.slice(5))}</span></span>`).join('')}
        </div>` : '<p class="small dim" style="margin-top:14px">No views counted yet.</p>'}
        ${stats.top_paths.length ? `<div class="tablewrap" style="margin-top:16px"><table><thead><tr><th>Path</th><th>Views</th></tr></thead>
          <tbody>${stats.top_paths.map(p => `<tr><td class="mono">${esc(p.path)}</td><td>${p.views}</td></tr>`).join('')}</tbody></table></div>` : ''}
        ${stats.referrers.length ? `<p class="small dim" style="margin-top:12px">Referrers: ${stats.referrers.map(r => `${esc(r.ref)} (${r.views})`).join(' · ')}</p>` : ''}
      </div>`;
    app().innerHTML = `
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <div><h2>Accounts</h2>
          <p class="muted small">${pending.length ? `<b style="color:var(--amber)">${pending.length} request${pending.length > 1 ? 's' : ''} waiting.</b>` : 'Nothing waiting for approval.'}</p></div>
          <button class="small" id="reload">Refresh</button>
        </div>
        <div class="tablewrap" style="margin-top:14px">
        <table>
          <thead><tr><th>User</th><th>Status</th><th>Role</th><th>Created</th><th>Last login</th><th><span class="sr-only">Actions</span></th></tr></thead>
          <tbody>${u.users.map(x => `
            <tr>
              <td><b>${esc(x.username)}</b>${x.email ? `<div class="dim small">${esc(x.email)}</div>` : ''}</td>
              <td><span class="badge ${x.status}">${x.status}</span></td>
              <td>${x.role === 'admin' ? '<span class="badge admin">admin</span>' : 'user'}</td>
              <td class="small dim">${x.created_at ? new Date(x.created_at).toLocaleDateString() : ''}</td>
              <td class="small dim">${x.last_login ? new Date(x.last_login).toLocaleString() : '—'}</td>
              <td style="text-align:right;white-space:nowrap">
                ${x.status !== 'approved' ? `<button class="small primary" data-act="approve" data-id="${x.id}">Approve</button>` : ''}
                ${x.status === 'pending' ? `<button class="small" data-act="reject" data-id="${x.id}">Reject</button>` : ''}
                ${x.role !== 'admin' ? `<button class="small" data-act="promote" data-id="${x.id}">Make admin</button>` : ''}
                ${x.id !== S.user.id ? `<button class="small danger" data-act="delete" data-id="${x.id}">Delete</button>` : ''}
              </td>
            </tr>`).join('')}
          </tbody></table>
        </div>
      </div>
      ${traffic}
      <div class="panel" style="margin-top:16px">
        <h3>Recent activity</h3>
        <div class="tablewrap" style="margin-top:10px">
        <table><tbody>${ev.events.map(e => `<tr>
          <td class="small dim" style="width:170px">${new Date(e.created_at).toLocaleString()}</td>
          <td class="small"><b>${esc(e.kind)}</b> ${esc(e.detail || '')}</td></tr>`).join('') || '<tr><td class="dim small">No events yet.</td></tr>'}
        </tbody></table></div>
      </div>`;
    $('#reload').onclick = renderAdmin;
    app().querySelectorAll('[data-act]').forEach(btn => {
      btn.onclick = async () => {
        const id = Number(btn.dataset.id), act = btn.dataset.act;
        try {
          if (act === 'approve') await api(`/api/admin/users/${id}/status`, { method: 'POST', body: { status: 'approved' } });
          if (act === 'reject') await api(`/api/admin/users/${id}/status`, { method: 'POST', body: { status: 'rejected' } });
          if (act === 'promote') await api(`/api/admin/users/${id}/role`, { method: 'POST', body: { role: 'admin' } });
          if (act === 'delete') { if (!confirm('Delete this account?')) return; await api(`/api/admin/users/${id}`, { method: 'DELETE' }); }
          toast('Updated'); renderAdmin();
        } catch (err) { toast(err.message, true); }
      };
    });
  } catch (err) { app().innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
}

/* ------------------------------------------------------------------ settings */
async function renderSettings() {
  S.view = 'settings'; paintChrome(); setMeta('settings');
  app().innerHTML = '<div class="empty"><span class="spin" aria-hidden="true"></span></div>';
  try {
    const cfg = await api('/api/config');
    const site = cfg.site || {};
    app().innerHTML = `
      <div class="panel">
        <h2>Instance settings</h2>
        <p class="muted small">Paths and the fnOS NAS connection. On the NAS the password comes from a 0600 environment file, not this form.</p>
        <div class="grid2" style="margin-top:14px">
          <div><label for="workbook">Workbook (.xlsx, default course)</label><input id="workbook" value="${esc(cfg.workbook)}"></div>
          <div><label for="guide">Guide (.pdf, default course)</label><input id="guide" value="${esc(cfg.guide)}"></div>
          <div><label for="vault">Vault folder for notes</label><input id="vault" value="${esc(cfg.vault)}"></div>
          <div><label for="owner">Owner username</label><input id="owner" value="${esc(cfg.owner_username)}"></div>
        </div>
      </div>
      <div class="panel" style="margin-top:16px">
        <h3>Site and legal pages</h3>
        <p class="small muted" style="margin-top:6px">These values fill in the privacy policy, the terms, the canonical URL and the sitemap.</p>
        <div class="grid2" style="margin-top:6px">
          <div><label for="sitename">Site name</label><input id="sitename" value="${esc(site.name || '')}"></div>
          <div><label for="publicurl">Public URL (canonical)</label><input id="publicurl" value="${esc(site.public_url || '')}" placeholder="https://learnloop.example.ts.net"></div>
          <div><label for="contact">Contact email shown on the legal pages</label><input id="contact" type="email" value="${esc(site.contact_email || '')}"></div>
          <div><label for="effective">Legal pages effective date</label><input id="effective" value="${esc(site.effective_date || '')}" placeholder="2026-11-25"></div>
          <div><label for="operator">Operator (who runs this instance)</label><input id="operator" value="${esc(site.operator || '')}"></div>
          <div><label for="jurisdiction">Governing law / jurisdiction</label><input id="jurisdiction" value="${esc(site.jurisdiction || '')}"></div>
        </div>
        <div class="row" style="margin-top:12px">
          <a class="btnlink" href="/privacy" target="_blank" rel="noopener">Preview privacy</a>
          <a class="btnlink" href="/terms" target="_blank" rel="noopener">Preview terms</a>
          <button class="small" id="cookiechoice">Cookie choice…</button>
        </div>
      </div>
      <div class="panel" style="margin-top:16px">
        <h3>NAS (fnOS · WebDAV)</h3>
        <div class="grid2" style="margin-top:6px">
          <div><label for="lan">LAN URL</label><input id="lan" value="${esc(cfg.nas.lan_url)}"></div>
          <div><label for="public">Remote URL (VPN / port-forward)</label><input id="public" value="${esc(cfg.nas.public_url)}"></div>
          <div><label for="nasuser">Username</label><input id="nasuser" value="${esc(cfg.nas.user)}"></div>
          <div><label for="naspw">Password ${cfg.nas.has_password ? '<span class="dim">(saved)</span>' : ''}</label><input id="naspw" type="password" autocomplete="new-password"></div>
          <div><label for="remote">Remote folder</label><input id="remote" value="${esc(cfg.nas.remote_dir)}"></div>
          <div><label for="active">Use</label><select id="active">
            <option value="lan" ${cfg.nas.active === 'lan' ? 'selected' : ''}>LAN</option>
            <option value="public" ${cfg.nas.active === 'public' ? 'selected' : ''}>Remote</option>
          </select></div>
        </div>
        <div class="row" style="margin-top:14px">
          <button class="primary" id="save">Save settings</button>
          <button id="test">Test connection</button>
          <button id="uploadall">Upload all PDFs</button>
        </div>
        <div id="queuebar" class="row" style="margin-top:12px"></div>
        <div id="nasout" class="small mono" style="margin-top:12px;color:var(--muted);white-space:pre-wrap"></div>
      </div>`;

    const out = (txt) => { $('#nasout').textContent = txt; };
    async function refreshQueue() {
      const bar = $('#queuebar'); if (!bar) return;
      try {
        const qq = await api('/api/nas/pending');
        bar.innerHTML = qq.count
          ? `<span class="pill amber">${qq.count} queued</span><button class="small primary" id="flush">Retry queued uploads</button>`
          : '<span class="small dim">Nothing queued.</span>';
        if ($('#flush')) $('#flush').onclick = async (e) => {
          e.target.disabled = true; e.target.innerHTML = '<span class="spin"></span> retrying';
          try { const r = await api('/api/nas/flush', { method: 'POST', body: { target: $('#active').value } }); toast(r.message); out(r.message); }
          catch (err) { toast(err.message, true); }
          refreshQueue();
        };
      } catch { /* ignore */ }
    }
    refreshQueue();

    $('#save').onclick = async () => {
      try {
        await api('/api/config', { method: 'POST', body: {
          workbook: $('#workbook').value, guide: $('#guide').value, vault: $('#vault').value, owner_username: $('#owner').value,
          site: {
            name: $('#sitename').value, public_url: $('#publicurl').value, contact_email: $('#contact').value,
            effective_date: $('#effective').value, operator: $('#operator').value, jurisdiction: $('#jurisdiction').value,
          },
          nas: { lan_url: $('#lan').value, public_url: $('#public').value, user: $('#nasuser').value, password: $('#naspw').value, remote_dir: $('#remote').value, active: $('#active').value },
        } });
        toast('Settings saved'); await refreshPlan();
      } catch (err) { toast(err.message, true); }
    };
    $('#cookiechoice').onclick = () => {
      try { localStorage.removeItem(CONSENT_KEY); } catch (e) { /* private mode */ }
      initConsent();
      toast('Cookie choice cleared — pick again in the banner');
    };
    $('#test').onclick = async () => {
      out('Testing…');
      try {
        const r = await api('/api/nas/status?target=' + $('#active').value);
        if (!r.ok) { out('FAILED: ' + r.error); return; }
        const files = (r.remote_files || []).filter(f => !f.is_dir);
        out(`OK  ${r.url}\nDAV: ${r.dav}\nFolder: ${r.remote_dir}\nFiles: ${files.length}\n` +
            files.slice(0, 10).map(f => `  · ${f.name}`).join('\n'));
      } catch (err) { out('FAILED: ' + err.message); }
    };
    $('#uploadall').onclick = (e) => uploadAll(e.target, out);
  } catch (err) { app().innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
}

async function uploadAll(btn, log) {
  const label = btn.textContent;
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> uploading…';
  try {
    const r = await api('/api/nas/upload', { method: 'POST', body: { target: 'lan', course: S.course } });
    toast(r.message || 'Done');
    if (log) log(r.message + '\n' + (r.uploaded || []).slice(0, 40).map(f => '  · ' + f).join('\n'));
  } catch (err) { toast(err.message, true); if (log) log('FAILED: ' + err.message); }
  btn.disabled = false; btn.textContent = label;
}

/* -------------------------------------------------------------------- router */
function renderNotFound() {
  S.view = 'notfound'; paintChrome(); setMeta('notfound');
  app().innerHTML = `
    <div class="panel notfound">
      <p class="kicker">404</p>
      <h1>That page is not here</h1>
      <p class="muted">The link may be old, or the session or exercise it pointed at no longer
      exists in this course.</p>
      <div class="row" style="margin-top:16px">
        <a class="btnlink primary" href="#/plan">Open the plan</a>
        <a class="btnlink" href="#/exercises">Exercises</a>
        <a class="btnlink" href="/privacy">Privacy</a>
      </div>
    </div>`;
}

function route() {
  if (!S.user) {
    if (S.setupRequired) { renderSetup(); return; }
    renderAuth(location.hash.includes('signup') ? 'signup' : 'login');
    return;
  }
  const hash = location.hash || '#/plan';
  // the legal pages are real documents, not views: hand them to the browser
  if (hash.startsWith('#/privacy')) { location.assign('/privacy'); return; }
  if (hash.startsWith('#/terms')) { location.assign('/terms'); return; }
  let m;
  if ((m = hash.match(/^#\/session\/(\d+)/))) return renderSession(m[1]);
  if ((m = hash.match(/^#\/exercise\/([^/?]+)/))) return renderExercise(decodeURIComponent(m[1]));
  if (hash.startsWith('#/exercises')) return renderExercises();
  if (hash.startsWith('#/search')) return renderSearch(new URLSearchParams(hash.split('?')[1] || '').get('q') || '');
  if (hash.startsWith('#/admin')) return renderAdmin();
  if (hash.startsWith('#/settings')) return renderSettings();
  if (hash === '#/plan' || hash === '#/' || hash === '#') return renderPlan();
  if (hash.startsWith('#/login')) { renderAuth('login'); return; }
  if (hash.startsWith('#/signup')) { renderAuth('signup'); return; }
  return renderNotFound();
}

/* ---------------------------------------------------------------------- boot */
async function boot() {
  initConsent();
  try {
    const st = await api('/api/state');
    S.setupRequired = st.setup_required;
    if (st.setup_required) { renderSetup(); return; }
    if (!st.user) { route(); return; }
    S.user = st.user;
    await loadCourses();
    await refreshPlan();
    paintChrome();
    route();
    trackView();
    try { sessionStorage.removeItem('ll-sw-reloaded'); } catch (e) { /* private mode */ }
  } catch (err) {
    setMeta('notfound', 'LearnLoop is unreachable');
    app().innerHTML = `<div class="panel notfound"><h1>Cannot reach LearnLoop</h1>
      <p class="muted">${esc(err.message)}</p>
      <button class="primary" id="retry" style="margin-top:14px">Try again</button></div>`;
    const retry = $('#retry');
    if (retry) retry.onclick = () => boot();
  }
}

$('#logout').onclick = async () => {
  try { await api('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
  S.user = null; S.plan = null; S.courses = []; clearTimer();
  paintChrome(); location.hash = ''; route();
};

$('#coursesel').onchange = (e) => switchCourse(e.target.value);
window.addEventListener('hashchange', () => { route(); trackView(); });

/* An open tab keeps running the script it loaded with. Ask the server for the current
   build stamp (the ?v= this script was fetched with) and reload when they differ, so a
   deploy is never invisible to a tab that was already open. Never reload while the
   visitor is typing — offer a bar instead. */
function ensureFreshBuild() {
  const mine = new URL(import.meta.url).searchParams.get('v');
  if (!mine) return;

  const offerReload = () => {
    if ($('#newbuild')) return;
    const bar = document.createElement('div');
    bar.id = 'newbuild';
    bar.className = 'newbuild';
    bar.innerHTML = '<span>A new version of LearnLoop is ready.</span>'
      + '<button class="small primary" id="newbuild-go">Reload</button>';
    document.body.appendChild(bar);
    $('#newbuild-go').onclick = () => location.reload();
  };

  const check = async () => {
    try {
      const res = await fetch('/api/health', { cache: 'no-store' });
      const data = await res.json();
      if (!data.build || data.build === mine) return;
      const el = document.activeElement;
      const typing = el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
      const draft = $('#note') && $('#note').value.trim();
      if (typing || draft) { offerReload(); return; }
      if (sessionStorage.getItem('ll-build-reload') === String(data.build)) { offerReload(); return; }
      sessionStorage.setItem('ll-build-reload', String(data.build));
      location.reload();
    } catch (e) { /* offline or the server is restarting */ }
  };

  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
  setTimeout(check, 20000);
  setInterval(check, 300000);
}

/* Replace an older service worker as soon as possible. The shell is versioned with
   ?v=, but a tab that was open before a deploy would otherwise keep the old worker
   (and its cached shell) for up to a day. */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' });
      reg.update().catch(() => {});
      let reloading = false;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (reloading || sessionStorage.getItem('ll-sw-reloaded') === '1') return;
        reloading = true;
        sessionStorage.setItem('ll-sw-reloaded', '1');
        location.reload();
      });
    } catch (e) { /* the app works without a service worker */ }
  });
}
wireShell();
boot();
ensureFreshBuild();

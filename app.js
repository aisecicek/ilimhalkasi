/* ==========================================================
   İLİM HALKASI — API'ye bağlı ön yüz
   Veriler SQLite veritabanından gelir (server.py).
   ========================================================== */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const renderIcons = () => {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
  }
};
const levelIconHTML = (name) => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[ch]));

const isImageCover = (cover) => /^(https?:\/\/|data:image\/)/i.test(String(cover || '').trim());
const COVER_TONES = ['olive', 'sand', 'copper', 'ink'];

function coverTone(book) {
  const cover = String(book?.cover || '').trim();
  if (COVER_TONES.includes(cover)) return cover;
  const seed = `${book?.title || ''}${book?.author || ''}`;
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.codePointAt(0)) >>> 0;
  return COVER_TONES[hash % COVER_TONES.length];
}

function placeholderCoverHTML(book, extraClass = '') {
  const title = String(book?.title || t('Kitap'));
  const author = String(book?.author || '');
  const classes = ['book-cover', 'book-cover--placeholder', `book-cover--${coverTone(book)}`, extraClass]
    .filter(Boolean).join(' ');
  return `<div class="${classes}">
    <span class="book-cover__imprint">${t('İLİM HALKASI')}</span>
    <span class="book-cover__title">${esc(title)}</span>
    ${author ? `<span class="book-cover__author">${esc(author)}</span>` : ''}
  </div>`;
}

function bookCoverHTML(book, extraClass = '') {
  const cover = String(book?.cover || '').trim();
  const className = ['book-cover', extraClass].filter(Boolean).join(' ');
  if (isImageCover(cover)) {
    return `<img class="${className}" src="${esc(cover)}" alt="${esc(book?.title || '')}${t(' kapağı')}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
      data-fallback-title="${esc(book?.title || '')}" data-fallback-author="${esc(book?.author || '')}"
      data-fallback-tone="${esc(coverTone(book))}" data-fallback-class="${esc(extraClass)}" />`;
  }
  return placeholderCoverHTML(book, extraClass);
}

function bookCoverFallback(img) {
  if (img.dataset.failed) return;
  img.dataset.failed = '1';
  const holder = document.createElement('span');
  holder.innerHTML = placeholderCoverHTML({
    title: img.dataset.fallbackTitle,
    author: img.dataset.fallbackAuthor,
    cover: img.dataset.fallbackTone
  }, img.dataset.fallbackClass || '');
  img.replaceWith(holder.firstElementChild);
}

// Inline onerror bazı tarayıcı/ CSP kombinasyonlarında çalışmadığından
// yakalama aşamasındaki bu dinleyici yüklenemeyen kapakları da placeholder'a çevirir.
document.addEventListener('error', (event) => {
  const img = event.target;
  if (img instanceof HTMLImageElement && img.classList.contains('book-cover')) {
    bookCoverFallback(img);
  }
}, true);

function bookGenres(book) {
  return String(book?.genre || '').split(',').map((part) => part.trim()).filter(Boolean);
}

function bookMetaHTML(book) {
  const meta = [];
  if (book?.genre) meta.push(esc(book.genre));
  if (book?.year) meta.push(book.year);
  if ((state.settings?.showRating ?? true) && book?.rating) meta.push(`★ ${Number(book.rating).toFixed(1)}`);
  return meta.join(' · ');
}

const FEED_LIMIT = 200;

const state = {
  user: null,
  csrfToken: '',
  data: null,
  lastPostPollTs: 0,
  serverTime: 0,
  currentView: 'home',
  viewHistory: [],
  tab: 'discover',
  filter: 'all',
  sort: 'recent',
  openComments: new Set(),
  shelfTab: 'reading',
  libraryTab: 'quotes',
  interactionTab: 'liked',
  interactions: null,
  currentBook: null,
  bookDetailBook: null,
  bookCategory: '',
  bookGenre: '',
  bookQuery: '',
  bookDecade: '',
  bookFocus: '',
  bookTopic: '',
  bookSort: 'title',
  filtersBound: false,
  bookCatalog: [],
  bookGenres: [],
  bookTotal: 0,
  bookOffset: 0,
  bookHasMore: true,
  bookLoading: false,
  communityTab: 'circles',
  journalTab: 'reviews',
  scholarSlug: null,
  scholarKind: 'all',
  scholarCategory: 'all',
  scholarQuery: '',
  profileAvatar: 'olive',
  profileAvatarImage: '',
  activeGroupId: null,
  activeCircleId: null,
  shareGroupId: null,
  meclisMembers: new Set(),
  globalSearchTimer: null,
  mobileSearchFilter: 'all',
  mobileSearchTimer: null,
  searchReturnView: 'home',
  publicProfile: null,
  publicReturnView: 'discover',
  statsTab: 'reading',
  statsYear: null,
  chartPeriod: 'monthly',
  chartMetric: 'books',
  followListMode: 'following',
  recommendedUsers: [],
  catalogAuthors: null,
  selectedAuthor: '',
  authorLetter: 'all',
  authorLimit: 200,
  editing: null,
  renamingListId: null,
  settings: null
};

const DEFAULT_SETTINGS = {
  notifyAnnouncements: true,
  notifyCirclePosts: true,
  notifyComments: true,
  notifyMentions: true,
  notifyMessages: true,
  notifyFollowers: true,
  notifySupport: true,
  yearlyGoal: 24,
  yearlyGoals: {},
  textSize: 'normal',
  showRating: true,
  showJoinYear: true,
  theme: 'auto',
  language: 'tr'
};

const THEMES = [
  { key: 'auto', label: 'Sistem' },
  { key: 'medine', label: 'Medine' },
  { key: 'kudus', label: 'Kudüs' },
  { key: 'mekke', label: 'Mekke' }
];
// 'gece' yalnızca Sistem seçeneğinin koyu paletidir; ayrı bir tema seçeneği değildir.

const SYSTEM_DARK = window.matchMedia('(prefers-color-scheme: dark)');
function resolvedTheme(mode) {
  if (mode === 'auto') return SYSTEM_DARK.matches ? 'gece' : 'medine';
  return THEMES.some((t) => t.key === mode) ? mode : 'medine';
}

/* Tek SVG şablonundan amblem üretir; clip kimliği her kopyada benzersiz olur. */
function initEmblems() {
  const tpl = $('#emblem-template');
  if (!tpl) return;
  $$('[data-emblem]').forEach((host, i) => {
    const svg = tpl.content.firstElementChild.cloneNode(true);
    const clipId = `archClip-${i}`;
    svg.querySelector('#archClip')?.setAttribute('id', clipId);
    svg.querySelector('[clip-path]')?.setAttribute('clip-path', `url(#${clipId})`);
    host.replaceChildren(svg);
  });
}

/* Karşılama kartındaki line-art filigranı aynı kemer/kitap oranlarıyla üretir. */
function initWatermarks() {
  const tpl = $('#watermark-template');
  if (!tpl) return;
  $$('[data-watermark]').forEach((host, i) => {
    const svg = tpl.content.firstElementChild.cloneNode(true);
    const clipId = `watermarkArchClip-${i}`;
    svg.querySelector('#watermarkArchClip')?.setAttribute('id', clipId);
    svg.querySelector('[clip-path]')?.setAttribute('clip-path', `url(#${clipId})`);
    host.replaceChildren(svg);
  });
}

/* Sekme simgesini de aktif temaya göre aynı şablondan üretir. */
function emblemFaviconUri(theme) {
  const palette = {
    medine: { bg: '#163D2B', cover: '#163D2B', dome: '#246346' },
    gece: { bg: '#121714', cover: '#1B2420', dome: '#6DB694' },
    kudus: { bg: '#16425B', cover: '#16425B', dome: '#D4AF37' },
    mekke: { bg: '#1F1F1F', cover: '#121212', dome: '#0D0D0D' }
  };
  const c = palette[theme] || palette.medine;
  const tpl = $('#emblem-template');
  if (!tpl) return '';
  const svg = tpl.content.firstElementChild.cloneNode(true);
  svg.querySelectorAll('.emblem-scene').forEach((g) => {
    if (!g.classList.contains(`emblem-scene--${theme}`)) g.remove();
  });
  [['.em-bg', c.bg], ['.em-cover', c.cover], ['.em-dome', c.dome]].forEach(([sel, fill]) => {
    const el = svg.querySelector(sel);
    if (el) { el.setAttribute('fill', fill); el.removeAttribute('class'); }
  });
  svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  return 'data:image/svg+xml,' + encodeURIComponent(new XMLSerializer().serializeToString(svg));
}

function applyTheme(mode) {
  const selected = THEMES.some((item) => item.key === mode) ? mode : 'auto';
  const theme = resolvedTheme(selected);
  document.documentElement.dataset.themeMode = selected;
  document.documentElement.dataset.theme = theme;
  const icon = $('link[rel="icon"]');
  const favicon = emblemFaviconUri(theme);
  if (icon && favicon) icon.href = favicon;
  const metaTheme = $('meta[name="theme-color"]');
  if (metaTheme) metaTheme.content = theme === 'gece' ? '#121714' : '#1F4E3D';
  $$('[data-theme-choice]').forEach((btn) => {
    const active = btn.dataset.themeChoice === selected;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
}

function cycleTheme() {
  const current = state.settings?.theme || 'auto';
  const index = THEMES.findIndex((item) => item.key === current);
  const next = THEMES[(index + 1) % THEMES.length];
  state.settings.theme = next.key;
  saveSettings(`${t(next.label)}${t(' iklimine geçildi')}`);
}

SYSTEM_DARK.addEventListener?.('change', () => {
  if ((state.settings?.theme || 'auto') === 'auto') applyTheme('auto');
});

function syncPasswordToggles() {
  $$('[data-password-toggle]').forEach((button) => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    const visible = input.type === 'text';
    const label = visible ? t('Şifreyi gizle') : t('Şifreyi göster');
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);
    button.setAttribute('aria-pressed', String(visible));
    button.querySelector('[data-lucide]')?.setAttribute('data-lucide', visible ? 'eye-off' : 'eye');
  });
  renderIcons();
}

function applyLanguage(lang) {
  const value = lang === 'en' ? 'en' : 'tr';
  window.ILIM_LANGUAGE = value;
  document.documentElement.lang = value;
  document.title = t('İlim Halkası · Birlikte ilim');
  const meta = document.querySelector('meta[name="description"]');
  if (meta) meta.content = t('İlim Halkası — ilim halkaları, kitaplar ve hatıratlar için sakin bir okuma dünyası.');
  applyStaticI18n();
  syncPasswordToggles();
}

function applySettings() {
  const s = state.settings || DEFAULT_SETTINGS;
  document.body.classList.toggle('text-large', s.textSize === 'large');
  applyTheme(s.theme);
  applyLanguage(s.language);
  syncPhoneNotificationPrefs();
  $$('[data-setting]').forEach((el) => {
    const key = el.dataset.setting;
    if (!(key in s)) return;
    if (el.type === 'checkbox') el.checked = Boolean(s[key]);
    else el.value = String(s[key]);
  });
}

function loadSettings() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('ilimhalkasi.settings') || '{}') || {}; }
  catch { saved = {}; }
  state.settings = { ...DEFAULT_SETTINGS, ...saved };
  if (state.settings.theme === 'gece') {
    state.settings.theme = 'auto';
    localStorage.setItem('ilimhalkasi.settings', JSON.stringify(state.settings));
  }
  applySettings();
}

function saveSettings(message = t('Tercihlerin kaydedildi')) {
  localStorage.setItem('ilimhalkasi.settings', JSON.stringify(state.settings));
  applySettings();
  toast(message);
}

const ISLAMIC_CATEGORIES = new Set([
  'Hadis', 'Siyer-i Nebi', 'Tasavvuf / Ahlak', 'İtikad', 'Tefsir', 'Fıkıh', 'Akaid', 'İslam Tarihi'
]);
const CLASSIC_CATEGORIES = new Set([
  'Dünya Klasikleri', 'Türk Edebiyatı', 'Felsefe', 'Roman', 'Genel', 'Keşfedilen'
]);

const announcementKinds = {
  duyuru: 'Duyuru', bayram: 'Bayram / özel gün', bilgi: 'Bilgi'
};

const levels = [
  { icon: 'book-open', name: 'Mülâzım', desc: '1. Seviye · Yola yeni çıkan, okuma halkasına ilk adımını atan.' },
  { icon: 'users-round', name: 'Ehl-i Suffa', desc: '2. Seviye · Halkaya düzenli katılan, okumayı alışkanlık haline getiren.' },
  { icon: 'graduation-cap', name: 'Müzâkereci', desc: '3. Seviye · Kitapları derinlemesine okuyan, alıntılar ve incelemeler paylaşan.' },
  { icon: 'sparkles', name: 'Müderris', desc: '4. Seviye · Halka kuran, incelemeleriyle başkalarına rehberlik eden.' }
];

/* ---------------- API ---------------- */

async function api(path, options = {}) {
  const method = options.method || (options.body !== undefined ? 'POST' : 'GET');
  let response;
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (method !== 'GET' && state.csrfToken) headers['X-CSRF-Token'] = state.csrfToken;
    response = await fetch(path, {
      credentials: 'same-origin',
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined
    });
  } catch {
    throw new Error(t('Sunucuya ulaşılamadı. python server.py çalışıyor mu?'));
  }
  let payload = {};
  try { payload = await response.json(); } catch { /* boş yanıt */ }
  if (payload.csrfToken) state.csrfToken = payload.csrfToken;
  if (!response.ok) {
    const isAuthCall = /^\/api\/(login|register|forgot-password|reset-password|logout)/.test(path);
    if (response.status === 401 && !state.user && !isAuthCall) {
      requestAccount();
      throw new Error(t('Bu işlem için hesap gerekli.'));
    }
    throw new Error(payload.error || t('Bir sorun oluştu'));
  }
  return payload;
}

function stripQueryParams(names) {
  const url = new URL(location.href);
  names.forEach((name) => url.searchParams.delete(name));
  history.replaceState(null, '', url.pathname + url.search + url.hash);
}

let postPollTimer = null;
let postPollBusy = false;
let phoneNotifiedIds = null;

function latestPostTimestamp() {
  return (state.data?.posts || []).reduce(
    (max, post) => Math.max(
      max,
      Number(post.created_at) || 0,
      Number(post.updated_at) || 0
    ),
    state.lastPostPollTs || 0
  );
}

async function pollNewPosts() {
  if (!state.user || !state.data || postPollBusy) return;
  postPollBusy = true;
  try {
    const [result, noteResult] = await Promise.all([
      api(`/api/posts/recent?after=${encodeURIComponent(state.lastPostPollTs || 0)}`),
      api('/api/notifications')
    ]);
    const incoming = result.posts || [];
    const deletedIds = new Set((result.deleted || []).map(Number));
    const byId = new Map((state.data.posts || []).map((post) => [Number(post.id), post]));
    let changed = false;

    if (deletedIds.size) {
      const before = state.data.posts.length;
      state.data.posts = state.data.posts.filter((post) => !deletedIds.has(Number(post.id)));
      if (state.data.posts.length !== before) changed = true;
    }

    incoming.forEach((post) => {
      const id = Number(post.id);
      const existing = byId.get(id);
      if (!existing) {
        state.data.posts = [post, ...state.data.posts];
        byId.set(id, post);
        changed = true;
      } else if (JSON.stringify(existing) !== JSON.stringify(post)) {
        state.data.posts = state.data.posts.map((item) => Number(item.id) === id ? post : item);
        byId.set(id, post);
        changed = true;
      }
    });

    const serverNotifications = noteResult.notifications || [];
    const notesChanged = JSON.stringify(state.data.notifications || []) !== JSON.stringify(serverNotifications);
    state.data.notifications = serverNotifications;

    const serverTime = Number(result.serverTime) || Number(noteResult.serverTime) || 0;
    state.lastPostPollTs = serverTime || latestPostTimestamp();

    if (changed) {
      const feed = $('#feed');
      const circleFeed = $('#circle-feed');
      const typingIn = (root) => {
        const el = document.activeElement;
        return !!(el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && el.value.trim() && root?.contains(el));
      };
      const feedTyping = typingIn(feed);
      const circleTyping = typingIn(circleFeed);
      if (!feedTyping) {
        const scrollTop = feed ? feed.scrollTop : 0;
        renderFeed();
        if (feed) feed.scrollTop = scrollTop;
      }
      if (!circleTyping) {
        const scrollTop = circleFeed ? circleFeed.scrollTop : 0;
        renderCircleFeed();
        if (circleFeed) circleFeed.scrollTop = scrollTop;
      }
    }
    if (notesChanged) renderNotifications();
    if (notesChanged || changed) pushNativeNotifications();
    renderDiscoverSections();
  } catch { /* arka planda sessizce tekrar dene */ }
  finally { postPollBusy = false; }
}

function startPostPolling() {
  if (postPollTimer) return;
  postPollTimer = setInterval(pollNewPosts, 12000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) pollNewPosts();
  });
}

function mergeBootstrapPosts(data) {
  // Akış yalnızca en yeni 200 paylaşımı taşır; kendi eski paylaşımlarımız
  // profilde görünmeye devam etsin diye ayrı gelen listeyi birleştiririz.
  const byId = new Map();
  (data.ownPosts || []).forEach((post) => byId.set(Number(post.id), post));
  (data.posts || []).forEach((post) => byId.set(Number(post.id), post));
  data.posts = [...byId.values()].sort(
    (a, b) => (Number(b.created_at) || 0) - (Number(a.created_at) || 0) || Number(b.id) - Number(a.id)
  );
  delete data.ownPosts;
}

async function refresh() {
  const loadedBooks = state.bookCatalog.slice();
  state.data = await api('/api/bootstrap');
  mergeBootstrapPosts(state.data);
  state.user = state.data.user;
  state.serverTime = Number(state.data.serverTime) || 0;
  state.lastPostPollTs = latestPostTimestamp();
  const deleteCard = $('#delete-account-card');
  if (deleteCard) deleteCard.hidden = Boolean(state.user?.is_admin);
  loadedBooks.forEach(rememberBook);
  renderAll();
  pushNativeNotifications(true);
}

/* ---------------- Yardımcılar ---------------- */

let toastTimer;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-visible'), 2600);
}

function timeAgo(ts) {
  const seconds = Math.max(0, Date.now() / 1000 - Number(ts || 0));
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return t('şimdi');
  if (minutes < 60) return t('{n} dk önce', { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('{n} saat önce', { n: hours });
  const days = Math.floor(hours / 24);
  if (days === 1) return t('Dün');
  if (days < 7) return t('{n} gün önce', { n: days });
  return new Date(Number(ts) * 1000).toLocaleDateString(
    (state.settings?.language === 'en' ? 'en-US' : 'tr-TR'),
    { day: 'numeric', month: 'long', year: 'numeric' }
  );
}

function starRow(rating) {
  return `<span class="stars" aria-label="${t('{n} / 5 yıldız', { n: rating })}">` +
    Array.from({ length: 5 }, (_, i) => `<span class="${i < rating ? '' : 'off'}">★</span>`).join('') + '</span>';
}

function initial(name) {
  return esc(String(name || '?').trim()[0] || '?').toLocaleUpperCase('tr-TR');
}

/* Yüklenen fotoğraf varsa daire içinde göster, yoksa baş harf. */
function avatarHTML(user, size = '') {
  const cls = ['avatar', size, `avatar--${esc(user?.avatar || 'olive')}`].filter(Boolean).join(' ');
  const inner = user?.avatar_image
    ? `<img src="${esc(user.avatar_image)}" alt="" />`
    : initial(user?.display_name || user?.name || '?');
  return `<span class="${cls}">${inner}</span>`;
}

function hideGlobalSearch() {
  const box = $('#global-search-results');
  if (box) { box.hidden = true; box.innerHTML = ''; }
}

/* ---------------- Mobil arama ekranı ---------------- */

let mobileAuthorsPromise = null;

function mobileSearchHTML(groups) {
  const html = groups.filter((group) => group.rows).map((group) => `
    <div class="global-result-group">
      <p data-i18n="${esc(group.title)}">${t(group.title)}</p>
      ${group.rows}
    </div>`).join('');
  return html || `<p class="rail-muted" data-i18n="Sonuç bulunamadı.">${t('Sonuç bulunamadı.')}</p>`;
}

async function runMobileSearch() {
  const input = $('#mobile-search-input');
  const host = $('#mobile-search-results');
  if (!input || !host) return;
  const query = String(input.value || '').trim();
  if (query.length < 2) {
    host.innerHTML = `<p class="rail-muted" data-i18n="En az iki harf yazmaya başla.">${t('En az iki harf yazmaya başla.')}</p>`;
    applyStaticI18n(host);
    return;
  }
  const filter = state.mobileSearchFilter;
  const needle = query.toLocaleLowerCase('tr-TR');
  host.innerHTML = `<p class="rail-muted">${t('Aranıyor…')}</p>`;

  try {
    const tasks = [];
    if (filter === 'all' || filter === 'books') {
      tasks.push(api(`/api/books?q=${encodeURIComponent(query)}&limit=8`).then((result) => ({ kind: 'books', result })));
    }
    if (filter === 'all' || filter === 'users') {
      tasks.push(api(`/api/users/search?q=${encodeURIComponent(query)}`).then((result) => ({ kind: 'users', result })));
    }
    if (filter === 'all' || filter === 'authors') {
      if (!mobileAuthorsPromise) {
        mobileAuthorsPromise = api('/api/catalog-authors')
          .then((result) => result.authors || [])
          .finally(() => { mobileAuthorsPromise = null; });
      }
      tasks.push(mobileAuthorsPromise.then((authors) => ({ kind: 'authors', authors })));
    }

    const results = await Promise.all(tasks);
    if ($('#mobile-search-input')?.value.trim() !== query) return;

    const groups = [];
    results.forEach((item) => {
      if (item.kind === 'books') {
        const books = item.result.books || [];
        books.forEach(rememberBook);
        const rows = books.map((book) => `
          <button class="global-result" type="button" data-global-book="${esc(book.id)}">
            ${bookCoverHTML(book, 'book-cover--mini')}
            <span><strong>${esc(book.title)}</strong><small>${esc(book.author || t('Yazar bilinmiyor'))}</small></span>
          </button>`).join('');
        if (rows) groups.push({ title: 'KİTAPLAR', rows });
      }
      if (item.kind === 'users') {
        const users = item.result.users || [];
        const rows = users.map((user) => `
          <button class="global-result" type="button" data-global-user="${esc(user.id)}">
            ${avatarHTML(user)}
            <span><strong>${esc(user.display_name)}</strong><small>@${esc(user.username)}</small></span>
          </button>`).join('');
        if (rows) groups.push({ title: 'KULLANICILAR', rows });
      }
      if (item.kind === 'authors') {
        const authors = (item.authors || [])
          .filter((author) => String(author.name || '').toLocaleLowerCase('tr-TR').includes(needle))
          .slice(0, 8);
        const rows = authors.map((author) => `
          <button class="global-result" type="button" data-mobile-author="${esc(author.name)}">
            <span class="avatar avatar--small avatar--olive">${esc(String(author.name || '?').charAt(0).toLocaleUpperCase('tr-TR'))}</span>
            <span><strong>${esc(author.name)}</strong><small>${esc(author.count)} ${t('kitap')}</small></span>
          </button>`).join('');
        if (rows) groups.push({ title: 'YAZARLAR', rows });
      }
    });

    if (filter === 'all' || filter === 'circles') {
      const allCircles = [];
      const circleIds = new Set();
      [...(state.data?.groups || []), ...(state.data?.discover_circles || [])].forEach((group) => {
        if (group.kind === 'halka' && !circleIds.has(group.id)) {
          circleIds.add(group.id);
          allCircles.push(group);
        }
      });
      const circles = allCircles
        .filter((group) => [group.name, group.description].some(
          (value) => String(value || '').toLocaleLowerCase('tr-TR').includes(needle)
        ))
        .slice(0, 8);
      const rows = circles.map((circle) => `
        <button class="global-result" type="button" data-global-circle="${esc(circle.id)}">
          <span class="global-result-icon" aria-hidden="true">◈</span>
          <span><strong>${esc(circle.name)}</strong><small>${esc(circle.member_count)}${t(' üye')} · ${t('Halka')}</small></span>
        </button>`).join('');
      if (rows) groups.push({ title: 'HALKALAR', rows });
    }

    host.innerHTML = mobileSearchHTML(groups);
    applyStaticI18n(host);
    renderIcons();
  } catch (error) {
    host.innerHTML = `<p class="rail-muted">${esc(error.message)}</p>`;
  }
}

function openMobileSearch() {
  if (state.currentView !== 'search') state.searchReturnView = state.currentView;
  switchView('search');
  $('#mobile-search-input')?.focus();
}

function closeMobileSearch() {
  const target = state.searchReturnView || 'home';
  switchView(target === 'search' ? 'home' : target);
}

function globalSearchHTML(books, users, circles) {
  const bookRows = books.length ? books.slice(0, 5).map((book) => `
    <button class="global-result" type="button" data-global-book="${esc(book.id)}">
      ${bookCoverHTML(book, 'book-cover--mini')}
      <span><strong>${esc(book.title)}</strong><small>${esc(book.author || t('Yazar bilinmiyor'))}</small></span>
    </button>`).join('') : `<p class="rail-muted">${t('Kitap bulunamadı.')}</p>`;
  const userRows = users.length ? users.slice(0, 5).map((user) => `
    <button class="global-result" type="button" data-global-user="${esc(user.id)}">
      ${avatarHTML(user)}
      <span><strong>${esc(user.display_name)}</strong><small>@${esc(user.username)}</small></span>
    </button>`).join('') : `<p class="rail-muted">${t('Kullanıcı bulunamadı.')}</p>`;
  const circleRows = circles.length ? circles.slice(0, 5).map((circle) => `
    <button class="global-result" type="button" data-global-circle="${esc(circle.id)}">
      <span class="global-result-icon" aria-hidden="true">◈</span>
      <span><strong>${esc(circle.name)}</strong><small>${esc(circle.member_count)}${t(' üye')} · ${t('Halka')}</small></span>
    </button>`).join('') : `<p class="rail-muted">${t('Halka bulunamadı.')}</p>`;
  return `<div class="global-result-group"><p>${t('KİTAPLAR')}</p>${bookRows}</div>
          <div class="global-result-group"><p>${t('KULLANICILAR')}</p>${userRows}</div>
          <div class="global-result-group"><p>${t('HALKALAR')}</p>${circleRows}</div>`;
}

async function runGlobalSearch(value) {
  const box = $('#global-search-results');
  if (!box) return;
  const query = String(value || '').trim();
  if (query.length < 2) { hideGlobalSearch(); return; }
  try {
    const [bookResult, userResult] = await Promise.all([
      api(`/api/books?q=${encodeURIComponent(query)}&limit=5`),
      api(`/api/users/search?q=${encodeURIComponent(query)}`)
    ]);
    if ($('#global-search')?.value.trim() !== query) return;
    const books = bookResult.books || [];
    books.forEach(rememberBook);

    const allCircles = [];
    const circleIds = new Set();
    [...(state.data?.groups || []), ...(state.data?.discover_circles || [])].forEach((group) => {
      if (group.kind === 'halka' && !circleIds.has(group.id)) {
        circleIds.add(group.id);
        allCircles.push(group);
      }
    });
    const needle = query.toLocaleLowerCase('tr');
    const circles = allCircles.filter((group) =>
      [group.name, group.description].some(
        (value) => String(value || '').toLocaleLowerCase('tr').includes(needle)
      )
    );

    box.innerHTML = globalSearchHTML(books, userResult.users || [], circles);
    box.hidden = false;
  } catch (error) {
    box.innerHTML = `<p class="rail-muted">${esc(error.message)}</p>`;
    box.hidden = false;
  }
}

/* Seçilen görseli kareye alıp daire içine kırpar, PNG veri URL'si döndürür. */
function cropAvatar(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith('image/')) {
      return reject(new Error(t('Lütfen bir görsel dosyası seç')));
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(t('Dosya okunamadı')));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error(t('Görsel açılamadı')));
      img.onload = () => {
        const size = 200;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        const sx = (img.naturalWidth - side) / 2;
        const sy = (img.naturalHeight - side) / 2;
        ctx.save();
        ctx.beginPath();
        ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
        ctx.restore();
        resolve(canvas.toDataURL('image/png'));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

/* Kitap kapağı için 2:3 oranında, daire içine alınmamış görsel üretir. */
function cropBookCover(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith('image/')) {
      return reject(new Error(t('Lütfen bir görsel dosyası seç')));
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(t('Dosya okunamadı')));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error(t('Görsel açılamadı')));
      img.onload = () => {
        const width = 300;
        const height = 450;
        const targetRatio = width / height;
        const sourceRatio = img.naturalWidth / img.naturalHeight;
        let sx = 0;
        let sy = 0;
        let sw = img.naturalWidth;
        let sh = img.naturalHeight;
        if (sourceRatio > targetRatio) {
          sw = img.naturalHeight * targetRatio;
          sx = (img.naturalWidth - sw) / 2;
        } else {
          sh = img.naturalWidth / targetRatio;
          sy = (img.naturalHeight - sh) / 2;
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        canvas.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, width, height);
        resolve(canvas.toDataURL('image/png'));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

/* Fotoğraf yükleme alanlarını ortak davranışa bağlar. */
function photoUploader({ input, button, remove, preview, onChange, crop = cropAvatar, message = 'Fotoğraf daire içine alındı ✧' }) {
  const previewEl = $(preview);
  const defaultHTML = previewEl.innerHTML;
  let value = '';
  $(button).addEventListener('click', () => $(input).click());
  $(input).addEventListener('change', async () => {
    const file = $(input).files && $(input).files[0];
    if (!file) return;
    $(input).value = ''; // Aynı dosyanın ikinci seçiminde de change olayı çalışsın.
    try {
      value = await crop(file);
      previewEl.innerHTML = `<img src="${value}" alt="" />`;
      if (onChange) onChange(value);
      toast(t(message));
    } catch (error) { toast(error.message); }
  });
  $(remove).addEventListener('click', () => {
    value = '';
    $(input).value = '';
    previewEl.innerHTML = defaultHTML;
    if (onChange) onChange('');
  });
  return {
    get: () => value,
    set: (next) => {
      value = next || '';
      previewEl.innerHTML = value ? `<img src="${value}" alt="" />` : defaultHTML;
    }
  };
}

function myPosts() {
  const uid = state.user?.id ?? 0;
  return state.data.posts.filter((p) => p.author.id === uid);
}
function myReviews() { return myPosts().filter((p) => p.type === 'review'); }
function myQuotes() { return myPosts().filter((p) => p.type === 'quote'); }

function ownActionsHTML(kind, id) {
  return `<div class="note-actions">
    <button type="button" data-own-action="edit" data-own-kind="${esc(kind)}" data-id="${esc(id)}">${t('✎ Düzenle')}</button>
    <button type="button" data-own-action="delete" data-own-kind="${esc(kind)}" data-id="${esc(id)}">${t('Sil')}</button>
  </div>`;
}

function levelIndex() {
  const finished = state.data.shelf.filter((s) => s.status === 'finished').length;
  const count = myPosts().length;
  if (finished >= 6 && count >= 3) return 3;
  if (finished >= 4 || count >= 3) return 2;
  if (count >= 1) return 1;
  return 0;
}

function yearlyGoal() {
  const n = Number(state.settings?.yearlyGoal);
  return Number.isFinite(n) && n > 0 ? Math.min(100000, Math.floor(n)) : 24;
}

function yearlyGoalFor(year) {
  const map = state.settings?.yearlyGoals || {};
  const v = Number(map[String(year)]);
  return Number.isFinite(v) && v > 0 ? Math.min(100000, Math.floor(v)) : yearlyGoal();
}

const MONTH_NAMES = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
const CHART_METRICS = [
  { key: 'books', label: 'Kitap' },
  { key: 'pages', label: 'Sayfa' },
  { key: 'posts', label: 'Paylaşım' }
];
const CHART_PERIODS = [
  { key: 'weekly', label: 'Haftalık' },
  { key: 'monthly', label: 'Aylık' },
  { key: 'yearly', label: 'Yıllık' }
];
const DAY_NAMES = ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'];

/* Yıllık istatistikler takvim yılına göre tutulur; 1 Ocak'ta kendiliğinden sıfırlanır. */
function statsYear() {
  const y = Number(state.statsYear);
  return Number.isInteger(y) && y >= 2000 && y <= 2100 ? y : new Date().getFullYear();
}

function yearRange(year) {
  return {
    start: new Date(year, 0, 1).getTime() / 1000,
    end: new Date(year + 1, 0, 1).getTime() / 1000
  };
}

function inYear(ts, year) {
  const t = Number(ts);
  if (!Number.isFinite(t) || t <= 0) return false;
  const { start, end } = yearRange(year);
  return t >= start && t < end;
}

function bookFinishedAt(s) {
  return Number(s?.finished_at) || Number(s?.created_at) || 0;
}

function readPages(s) {
  if (s?.status === 'finished') return Number(s.page_count) || 0;
  return Number(s?.page) || 0;
}

function finishedInYear(year) {
  return (state.data?.shelf || []).filter((s) => s.status === 'finished' && inYear(bookFinishedAt(s), year)).length;
}

function availableYears() {
  const years = new Set([new Date().getFullYear()]);
  const add = (ts) => {
    const t = Number(ts);
    if (t > 0) years.add(new Date(t * 1000).getFullYear());
  };
  (state.data?.shelf || []).forEach((s) => {
    add(s.created_at);
    if (s.status === 'finished') add(bookFinishedAt(s));
  });
  (state.data?.posts || []).forEach((p) => add(p.created_at));
  return [...years].sort((a, b) => b - a);
}

function metricValue(metric, since, until) {
  if (metric === 'books' || metric === 'pages') {
    const books = (state.data?.shelf || []).filter((s) => {
      const t = bookFinishedAt(s);
      return s.status === 'finished' && t >= since && t < until;
    });
    return metric === 'books' ? books.length : books.reduce((n, s) => n + readPages(s), 0);
  }
  if (metric === 'posts') {
    return myPosts().filter((p) => Number(p.created_at) >= since && Number(p.created_at) < until).length;
  }
  return 0;
}

function monthlySeries(year, metric) {
  return Array.from({ length: 12 }, (_, i) => metricValue(
    metric,
    new Date(year, i, 1).getTime() / 1000,
    new Date(year, i + 1, 1).getTime() / 1000
  ));
}

function weeklyDates() {
  const today = new Date();
  return Array.from({ length: 7 }, (_, i) =>
    new Date(today.getFullYear(), today.getMonth(), today.getDate() - (6 - i)));
}

function weeklySeries(metric) {
  return weeklyDates().map((day) => metricValue(
    metric, day.getTime() / 1000, (day.getTime() + 86400000) / 1000
  ));
}

function chartYears() {
  const current = new Date().getFullYear();
  const years = new Set(availableYears());
  for (let y = current - 4; y <= current; y++) years.add(y);
  return [...years].sort((a, b) => a - b).slice(-8);
}

function yearlySeries(metric) {
  return chartYears().map((year) => {
    const { start, end } = yearRange(year);
    return metricValue(metric, start, end);
  });
}

/* ---------------- Giriş / kayıt ---------------- */

function showAuth(show) {
  $('#auth-screen').hidden = !show;
  $('.app-shell').style.visibility = show ? 'hidden' : 'visible';
}

function authTab(mode) {
  $$('.auth-tab').forEach((t) => {
    const active = t.dataset.authTab === mode;
    t.classList.toggle('is-active', active);
    t.setAttribute('aria-selected', String(active));
  });
  $('#login-form').hidden = mode !== 'login';
  $('#register-form').hidden = mode !== 'register';
  $('#auth-error').hidden = true;
  $('#register-error').hidden = true;
}

function showAuthError(mode, message) {
  const el = $(mode === 'login' ? '#auth-error' : '#register-error');
  el.textContent = message;
  el.hidden = false;
}

/* Misafirler önce gezebilir; üye işlemi denediklerinde hesap daveti çıkar. */
const GUEST_FIRST_KEY = 'ilimhalkasi.guest.firstVisit';
const GUEST_REMINDER_KEY = 'ilimhalkasi.guest.reminderShown';
const GUEST_WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function rememberGuestVisit() {
  if (!localStorage.getItem(GUEST_FIRST_KEY)) {
    localStorage.setItem(GUEST_FIRST_KEY, String(Date.now()));
  }
}

function clearGuestReminder() {
  localStorage.removeItem(GUEST_FIRST_KEY);
  localStorage.removeItem(GUEST_REMINDER_KEY);
}

function maybeRemindGuest() {
  if (state.user) return;
  const first = Number(localStorage.getItem(GUEST_FIRST_KEY));
  if (!first || Date.now() - first < GUEST_WEEK_MS) return;
  if (localStorage.getItem(GUEST_REMINDER_KEY)) return;
  localStorage.setItem(GUEST_REMINDER_KEY, '1');
  toast(t('Bir haftadır keşfediyorsun. Hesap açarsan takip edebilir ve paylaşabilirsin.'));
}

function requestAccount(action = '') {
  if (state.user) return true;
  rememberGuestVisit();
  const sheet = $('#account-sheet');
  const text = $('#account-sheet-text');
  if (text) {
    text.textContent = action
      ? t('{action} için hesap gerekli.', { action })
      : t('Bu işlem için hesap gerekli.');
  }
  if (sheet) sheet.hidden = false;
  return false;
}

function closeAccountSheet() {
  const sheet = $('#account-sheet');
  if (sheet) sheet.hidden = true;
}

function openRegisterScreen() {
  closeAccountSheet();
  showAuth(true);
  authTab('register');
}

async function initAppSession() {
  showAuth(false);
  state.lastPostPollTs = 0;
  state.serverTime = 0;
  await refresh();
  startPostPolling();
  resetBookFilterState();
  if (!state.filtersBound) {
    bindBookFilters();
    state.filtersBound = true;
  }
  await loadBookFilterOptions();
  syncBookFilterInputs();
  await loadCatalog(true);
}

async function boot() {
  loadSettings();
  const params = new URLSearchParams(location.search);
  if (params.get('verified') === '1') {
    toast(t('E-postan doğrulandı. Şimdi giriş yapabilirsin.'));
  } else if (params.get('verify_failed') === '1') {
    toast(t('Doğrulama bağlantısı geçersiz veya süresi dolmuş.'));
  }
  if (params.has('verified') || params.has('verify_failed')) {
    stripQueryParams(['verified', 'verify_failed']);
  }
  try {
    const result = await api('/api/me');
    if (!result.user) rememberGuestVisit();
    // Misafir de uygulamaya girer; hesap yalnızca üye işlemi istenince sorulur.
    await initAppSession();
    maybeRemindGuest();
  } catch (error) {
    showAuth(false);
    toast(error.message);
  }
  const resetToken = new URLSearchParams(location.search).get('reset');
  if (resetToken) openResetStage(resetToken);
}

/* ---------------- Akış ---------------- */

function commentHTML(comment, postId, isReply = false) {
  return `
    <div class="comment">
      ${avatarHTML(comment.author)}
      <div class="comment-main">
        <div class="comment-bubble"><strong>${esc(comment.author.display_name)}</strong>${esc(comment.text)}</div>
        <div class="comment-meta">
          <span>${esc(timeAgo(comment.created_at))}</span>
          <button type="button" data-act="comment-like" data-post="${postId}" data-comment="${comment.id}">${comment.liked ? '♥' : '♡'} ${comment.likes}</button>
          ${isReply ? '' : `<button type="button" data-act="reply" data-post="${postId}" data-comment="${comment.id}">${t('Cevapla')}</button>`}
        </div>
        ${comment.replies && comment.replies.length ? `<div class="replies">${comment.replies.map((r) => commentHTML(r, postId, true)).join('')}</div>` : ''}
        <form class="reply-form" data-post="${postId}" data-reply-to="${comment.id}" hidden>
          <input type="text" placeholder="${t('{n} kişisine cevap yaz...', { n: esc(comment.author.display_name) })}" aria-label="${t('Cevap')}" />
          <button type="submit">${t('Gönder')}</button>
        </form>
      </div>
    </div>`;
}

const TEXT_COLLAPSE_LIMIT = 1000;

function collapsibleTextHTML(text, className = 'review-text') {
  const value = String(text || '');
  if (value.length <= TEXT_COLLAPSE_LIMIT) return `<p class="${className}">${esc(value)}</p>`;
  return `
    <div class="text-collapse">
      <p class="${className} text-collapse-short">${esc(value.slice(0, TEXT_COLLAPSE_LIMIT))}…</p>
      <p class="${className} text-collapse-full" hidden>${esc(value)}</p>
      <button class="text-collapse-btn" type="button" data-expand-text aria-expanded="false">${t('devamını oku')}</button>
    </div>`;
}

function postHTML(post) {
  const isQuote = post.type === 'quote';
  const body = isQuote
    ? `<div class="quote-frame">
         <span class="corner tl"></span><span class="corner tr"></span>
         <span class="corner bl"></span><span class="corner br"></span>
         <span class="quote-mark">“</span>
         <p class="quote-text">${esc(post.text)}</p>
         <div class="quote-source"><b>${esc(post.book)}</b> · ${esc(post.writer)}</div>
       </div>`
    : `<div class="review-head">
         ${bookCoverHTML({ title: post.book, cover: post.cover })}
         <div class="review-book"><strong>${esc(post.book)}</strong><small>${esc(post.writer)}</small></div>
         ${starRow(post.rating)}
       </div>
       ${collapsibleTextHTML(post.text)}
       ${post.status ? `<span class="read-status" data-status="${esc(post.status)}">${esc(post.status)}</span>` : ''}`;

  const commentCount = post.comments.reduce((n, c) => n + 1 + (c.replies ? c.replies.length : 0), 0);
  return `
  <article class="post" data-id="${post.id}">
    <div class="post-top">
      <span class="post-author-avatar" data-profile-user="${esc(post.author.id)}" title="${esc(t('Profili gör'))}">${avatarHTML(post.author)}</span>
      <div class="post-author">
        <button class="post-author-name" type="button" data-profile-user="${esc(post.author.id)}">${esc(post.author.display_name)}</button>
        <small><button class="post-author-handle" type="button" data-profile-user="${esc(post.author.id)}">@${esc(post.author.username)}</button> · ${esc(timeAgo(post.created_at))}</small>
      </div>
      ${(post.followed || post.author.id === (state.user?.id ?? 0)) ? '' : `<button class="follow-btn" type="button" data-act="follow" data-user="${post.author.id}">${t('Takip et')}</button>`}
    </div>
    <div class="post-body">${body}</div>
    <div class="post-actions">
      <button class="action ${post.liked ? 'is-on' : ''}" type="button" data-act="like" aria-pressed="${post.liked}">
        <span class="ico">♥</span><span data-count="likes">${post.likes}</span> ${t('Beğeni')}
      </button>
      <button class="action ${post.favorited ? 'is-on' : ''}" type="button" data-act="favorite" aria-pressed="${post.favorited}">
        <span class="ico">★</span><span data-count="favorites">${post.favorites}</span> ${t('Kaydet')}
      </button>
      <button class="action" type="button" data-act="comment" aria-expanded="false">
        <span class="ico">❍</span><span data-count="comments">${commentCount}</span> ${t('Yorum')}
      </button>
      <button class="action action-share" type="button" data-act="share"><span class="ico">↗</span> ${t('Paylaş')}</button>
      ${post.author.id === (state.user?.id ?? 0) ? `
        <button class="action" type="button" data-own-action="edit" data-own-kind="post" data-id="${post.id}"><span class="ico">✎</span> ${t('Düzenle')}</button>
        <button class="action" type="button" data-own-action="delete" data-own-kind="post" data-id="${post.id}"><span class="ico">×</span> ${t('Sil')}</button>` : ''}
    </div>
    <div class="comments ${state.openComments.has(post.id) ? 'is-open' : ''}">
      ${post.comments.length ? post.comments.map((c) => commentHTML(c, post.id)).join('') : `<p class="rail-muted">${t('Henüz yorum yok. İlk yorumu sen yaz.')}</p>`}
      <form class="comment-form" data-post="${post.id}">
        <input type="text" placeholder="${t('Düşünceni paylaş...')}" aria-label="${t('Yorum yaz')}" />
        <button type="submit">${t('Gönder')}</button>
      </form>
    </div>
  </article>`;
}

function joinedCircles() {
  return (state.data.groups || []).filter((g) => g.kind === 'halka' && g.is_member);
}

function circleTabKey(id) {
  return `circle:${id}`;
}

function renderFeedTabs() {
  const host = $('.feed-controls .tabs');
  if (!host) return;
  const circles = joinedCircles();
  const keys = new Set(circles.map((c) => circleTabKey(c.id)));
  if (state.tab.startsWith('circle:') && !keys.has(state.tab)) state.tab = 'discover';
  host.innerHTML = `
    <button class="tab${state.tab === 'discover' ? ' is-active' : ''}" role="tab" aria-selected="${state.tab === 'discover'}" data-tab="discover" type="button" data-i18n="Keşfet">Keşfet</button>
    <button class="tab${state.tab === 'following' ? ' is-active' : ''}" role="tab" aria-selected="${state.tab === 'following'}" data-tab="following" type="button" data-i18n="Takip Edilenler">Takip Edilenler</button>
    ${circles.map((c) => {
      const active = state.tab === circleTabKey(c.id);
      return `<button class="tab${active ? ' is-active' : ''}" role="tab" aria-selected="${active}" data-tab="${esc(circleTabKey(c.id))}" type="button">${esc(c.name)}</button>`;
    }).join('')}`;
  applyStaticI18n(host);
}

function visiblePosts() {
  let list = state.data.posts.filter((p) => {
    if (state.tab === 'following') return p.followed || p.author.id === (state.user?.id ?? 0);
    if (state.tab.startsWith('circle:')) return Number(p.group_id) === Number(state.tab.slice(7));
    return true;
  });
  if (state.filter !== 'all') list = list.filter((p) => p.type === state.filter);
  if (state.sort === 'recent') list.sort((a, b) => b.created_at - a.created_at);
  else list.sort((a, b) => b[state.sort] - a[state.sort]);
  return list.slice(0, FEED_LIMIT);
}

function renderFeed() {
  const list = visiblePosts();
  $('#feed').innerHTML = list.map(postHTML).join('');
  $('#feed-empty').hidden = list.length > 0;
}

function findPost(id) { return state.data.posts.find((p) => p.id === Number(id)); }
function findComment(post, id) {
  for (const c of post.comments) {
    if (c.id === Number(id)) return c;
    const reply = (c.replies || []).find((r) => r.id === Number(id));
    if (reply) return reply;
  }
  return null;
}

/* ---------------- Diğer bölümler ---------------- */

function renderActiveCircles() {
  const host = $('#profile-circles');
  if (!host || !state.data) return;
  const circles = (state.data.groups || []).filter((g) => g.kind === 'halka');
  host.innerHTML = circles.length
    ? circles.map((g) => {
      const color = ['olive', 'copper', 'gold'].includes(g.avatar_color) ? g.avatar_color : 'olive';
      return `
        <div class="profile-circle-row">
          <span class="dot dot--${color}"></span>
          <div>
            <strong>${esc(g.name)}</strong>
            <small>◈ ${esc(g.member_count)}${t(' üye')} · ${t('kayıtlı halka')}</small>
          </div>
          <button class="circle-shortcut" type="button" data-open-circle="${g.id}">${t('✧ Akışa git')}</button>
        </div>`;
    }).join('')
    : `<p class="rail-muted">${t('Henüz bir halkaya katılmadın. Halkalar sayfasından açık bir halkaya katılabilirsin.')}</p>`;
}

function renderIdentity() {
  const isGuest = !state.user;
  const user = state.user || {
    id: 0,
    display_name: t('Misafir'),
    username: 'misafir',
    avatar: 'olive',
    avatar_image: '',
    bio: '',
    created_at: 0
  };
  const data = state.data;
  const short = user.display_name.split(' ')[0];

  const avatarInner = user.avatar_image
    ? `<img src="${esc(user.avatar_image)}" alt="" />`
    : initial(user.display_name);
  const sideAvatar = $('#side-avatar');
  sideAvatar.innerHTML = avatarInner;
  sideAvatar.className = `avatar avatar--${esc(user.avatar)}`;
  $('#side-name').textContent = user.display_name;
  $('#side-handle').textContent = '@' + user.username;

  const locale = state.settings?.language === 'en' ? 'en-US' : 'tr-TR';
  $('#greeting-date').textContent = new Date()
    .toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' })
    .toLocaleUpperCase(locale);
  $('#greeting-title').textContent = isGuest
    ? t('Selamün Aleyküm, hoş geldin')
    : t('Selamün Aleyküm {name}', { name: short });

  const reading = data.shelf.filter((s) => s.status === 'reading');
  const topBook = reading[0];
  $('#greeting-stats').innerHTML = `
    <span class="stat-chip"><b>${reading.length}</b> ${t('aktif kitap')}</span>
    <span class="stat-chip"><b>${topBook ? topBook.progress + '%' : '0%'}</b> ${topBook ? esc(topBook.title) : t('Aktif kitap yok')}</span>`;

  const profileAvatar = $('#profile-avatar');
  profileAvatar.innerHTML = avatarInner;
  profileAvatar.className = `avatar avatar--xl avatar--${esc(user.avatar)}`;
  $('#profile-title').textContent = user.display_name;
  const level = levelIndex();
  $('#profile-title-badge').innerHTML = `${levelIconHTML(levels[level].icon)} ${esc(t(levels[level].name))}`;
  const created = Number(user.created_at) * 1000;
  const joinYear = Number.isFinite(created) && created > 0
    ? new Date(created).getFullYear()
    : new Date().getFullYear();
  $('#profile-handle-line').textContent = isGuest
    ? t('Misafir olarak geziyorsun · Hesap açarak paylaşımlara katılabilirsin')
    : (state.settings?.showJoinYear ?? true)
      ? `@${user.username} · ${t('{n} yılından beri İlim Halkası’nda', { n: joinYear })}`
      : `@${user.username}`;
  const bioEl = $('#profile-bio');
  bioEl.textContent = user.bio || '';
  bioEl.hidden = !user.bio;
  const stats = data.stats || {};
  $('#follow-counts').innerHTML = `
    <button type="button" data-open-follow-list="followers" data-user-id="${esc(user.id)}"><b>${stats.followers || 0}</b>${t(' takipçi')}</button>
    <button type="button" data-open-follow-list="following" data-user-id="${esc(user.id)}"><b>${stats.following || 0}</b>${t(' takip edilen')}</button>
    <span><b>${stats.circles || 0}</b>${t(' ilim halkası')}</span>`;
  renderActiveCircles();

  const finished = data.shelf.filter((s) => s.status === 'finished').length;
  const year = statsYear();
  const yearFinished = finishedInYear(year);
  const goal = yearlyGoalFor(year);
  const pct = Math.min(100, Math.round((yearFinished / goal) * 100));
  $('#goal-line').innerHTML = `<strong>${yearFinished} / ${goal} ${t('kitap')}</strong><span>${t('{n} · %{p} tamamlandı', { n: year, p: pct })}</span>`;
  $('#goal-progress').style.width = pct + '%';
  const pages = data.shelf.reduce((n, s) => n + readPages(s), 0);
  $('#profile-stats').innerHTML = [
    [finished, t('Toplam okunan')], [pages.toLocaleString('tr-TR'), t('Toplam sayfa')],
    [myPosts().length, t('Paylaşım')], [myReviews().length, t('İnceleme')]
  ].map(([n, label]) => `<div class="profile-stat"><strong>${n}</strong><small>${label}</small></div>`).join('');
  const series = Number(stats.ilimSeries) || 0;
  $('#streak-title').textContent = `${series} İlim Serisi`;
  $('#streak-desc').textContent = '';
  $('#streak-desc').hidden = true;

  $('#title-ladder').innerHTML = levels.map((l, i) => `
    <div class="ladder-item ${i < level ? 'is-done' : ''} ${i === level ? 'is-current' : ''}">
      <span class="ladder-icon">${levelIconHTML(l.icon)}</span><strong>${esc(l.name)}</strong><small>${esc(t(l.desc))}</small>
      ${i === level ? `<small style="color:var(--gold)">${t('● Şu anki unvanın')}</small>` : ''}
    </div>`).join('');

  const railPct = pct;
  $('#rail-goal-ring').style.setProperty('--pct', railPct + '%');
  $('#rail-goal-count').textContent = yearFinished;
  $('#rail-goal-target').textContent = `/ ${goal} ${t('kitap')}`;
  $('#rail-goal-pct').textContent = railPct + '%';
  $('#rail-goal-copy').textContent = railPct >= 100
    ? t('{n} hedefi tamamlandı, mâşallah!', { n: year })
    : t('{n} boyunca kitapları bitirdikçe hedefin dolacak.', { n: year });

  $$('[data-guest-auth-btn]').forEach((b) => { b.hidden = !isGuest; });
  $$('[data-member-only]').forEach((b) => { b.hidden = isGuest; });
}

function renderRightRail() {
  const data = state.data;
  if (!data) return;

  const reading = (data.shelf || []).filter((s) => s.status === 'reading');
  const currentCard = $('#rail-current-card');
  if (currentCard) {
    const book = reading[0];
    currentCard.hidden = !book;
    if (book) {
      const progress = shelfProgress(book);
      $('#rail-current-title').textContent = book.title || '';
      $('#rail-current-detail').textContent = pageProgressText(progress) || `${progress.page} ${t('sayfa')}`;
      $('#rail-current-bar').style.width = `${progress.pct}%`;
      const openBtn = $('#rail-current-open');
      openBtn.dataset.globalBook = book.book_id;
    }
  }

  const mobileContinue = $('#home-continue-card');
  if (mobileContinue) {
    const book = reading[0];
    mobileContinue.hidden = !book;
    if (book) {
      const progress = shelfProgress(book);
      const progressText = pageProgressText(progress) || `${progress.page} ${t('sayfa')}`;
      mobileContinue.innerHTML = `
        <button class="mobile-continue-card" type="button" data-global-book="${esc(book.book_id)}">
          <span class="mobile-continue-cover">${bookCoverHTML(book)}</span>
          <span class="mobile-continue-copy">
            <p data-i18n="Okumaya devam et">${t('Okumaya devam et')}</p>
            <strong>${esc(book.title || '')}</strong>
            <small>${esc(progressText)}</small>
            <span class="progress"><span style="width:${progress.pct}%"></span></span>
          </span>
        </button>`;
      applyStaticI18n(mobileContinue);
      renderIcons();
    }
  }

  const days = weeklyDates();
  const values = weeklySeries('books');
  const weekTotal = values.reduce((n, v) => n + v, 0);
  const weeklyCard = $('#rail-weekly-card');
  if (weeklyCard) {
    weeklyCard.hidden = weekTotal === 0;
    if (weekTotal > 0) {
      const max = Math.max(1, ...values);
      $('#rail-weekly-bars').innerHTML = values.map((v, i) =>
        `<span style="height:${Math.max(4, Math.round((v / max) * 100))}%" title="${esc(t(DAY_NAMES[days[i].getDay()]))}: ${v} ${t('Kitap')}"></span>`
      ).join('');
      $('#rail-weekly-labels').innerHTML = days.map((d) =>
        `<span>${t(DAY_NAMES[d.getDay()])}</span>`).join('');
      $('#rail-weekly-copy').innerHTML = `${t('Bu hafta')} <b>${weekTotal}</b> ${t('kitap tamamlandı')}`;
    }
  }

  const finished = (data.shelf || []).filter((s) => s.status === 'finished').length;
  const posts = myPosts().length;
  const reviews = myReviews().length;
  const founded = (data.groups || []).filter((g) => g.is_creator).length;
  const badges = [];
  if (finished) badges.push(['★', t('İlk Kitap'), t('{n} kitap okudun', { n: finished })]);
  if (posts) badges.push(['✎', t('İlk Paylaşım'), t('{n} paylaşımın var', { n: posts })]);
  if (reviews) badges.push(['✧', t('İlk İnceleme'), t('{n} incelemen var', { n: reviews })]);
  if (founded) badges.push(['❖', t('Kurucu'), t('{n} halka/meclis kurdun', { n: founded })]);
  const badgesCard = $('#rail-badges-card');
  if (badgesCard) {
    badgesCard.hidden = badges.length === 0;
    $('#rail-badges').innerHTML = badges.map(([icon, label, title]) =>
      `<span title="${esc(title)}">${icon} <small>${esc(label)}</small></span>`).join('');
  }
}

function renderStatsView() {
  const panel = $('#stats-panel');
  if (!panel || !state.data || !state.user) return;
  const data = state.data;
  const stats = data.stats || {};
  const tab = state.statsTab || 'reading';
  const finished = data.shelf.filter((s) => s.status === 'finished').length;
  const pages = data.shelf.reduce((n, s) => n + readPages(s), 0);
  const halkalar = (data.groups || []).filter((g) => g.kind === 'halka');
  const meclisler = (data.groups || []).filter((g) => g.kind === 'meclis');
  const stat = (value, label) => `<div class="profile-stat"><strong>${esc(String(value))}</strong><small>${esc(label)}</small></div>`;

  if (tab === 'circles') {
    panel.innerHTML = `
      <div class="karne-card">
        <div class="karne-head"><span>${t('HALKALARIM')}</span><span>${halkalar.length + meclisler.length}${t(' KAYIT')}</span></div>
        <div class="profile-stats">
          ${stat(halkalar.length, t('İlim halkası'))}
          ${stat(meclisler.length, t('Özel meclis'))}
          ${stat(data.groups.filter((g) => g.kind !== 'halka').length, t('Toplam sohbet'))}
          ${stat(stats.circles || 0, t('Aktif halka'))}
        </div>
        <div class="profile-circles" style="margin-top:16px">
          ${halkalar.length
            ? halkalar.map((g) => `
              <div class="profile-circle-row">
                <span class="dot dot--olive"></span>
                <div><strong>${esc(g.name)}</strong><small>◈ ${esc(g.member_count)}${t(' üye')}</small></div>
                <button class="circle-shortcut" type="button" data-open-circle="${g.id}">${t('✧ Akışa git')}</button>
              </div>`).join('')
            : `<p class="rail-muted">${t('Henüz bir halkaya katılmadın.')}</p>`}
        </div>
      </div>`;
    return;
  }

  const year = statsYear();
  const goal = yearlyGoalFor(year);
  const years = availableYears();
  const yearFinished = finishedInYear(year);
  const pct = Math.min(100, Math.round((yearFinished / goal) * 100));
  const metric = CHART_METRICS.some((m) => m.key === state.chartMetric) ? state.chartMetric : 'books';
  const metricLabel = t(CHART_METRICS.find((m) => m.key === metric).label);
  const period = CHART_PERIODS.some((p) => p.key === state.chartPeriod) ? state.chartPeriod : 'monthly';
  const periodLabel = t(CHART_PERIODS.find((p) => p.key === period).label);
  const chart = period === 'weekly'
    ? { labels: weeklyDates().map((d) => t(DAY_NAMES[d.getDay()])), values: weeklySeries(metric), caption: t('Son 7 gün') }
    : period === 'yearly'
      ? { labels: chartYears().map(String), values: yearlySeries(metric), caption: t('Yıllık karşılaştırma') }
      : { labels: MONTH_NAMES.map((m) => t(m === 'Ara' ? 'Aralık' : m)), values: monthlySeries(year, metric), caption: String(year) };
  const max = Math.max(1, ...chart.values);

  const now = Date.now() / 1000;
  const { start: yearStart, end: yearEnd } = yearRange(year);
  const periods = [
    { label: t('Haftalık'), note: t('Son 7 gün'), since: now - 7 * 86400, until: Infinity },
    { label: t('Aylık'), note: t('Son 30 gün'), since: now - 30 * 86400, until: Infinity },
    { label: t('Yıllık'), note: String(year), since: yearStart, until: yearEnd }
  ].map(({ label, note, since, until }) => {
    const inRange = (ts) => Number(ts) >= since && Number(ts) < until;
    const books = data.shelf.filter((s) => s.status === 'finished' && inRange(bookFinishedAt(s)));
    const posts = myPosts().filter((p) => inRange(p.created_at));
    return {
      label, note,
      books: books.length,
      pages: books.reduce((n, s) => n + readPages(s), 0),
      posts: posts.length
    };
  });

  const yearPages = data.shelf
    .filter((s) => s.status === 'finished' && inYear(bookFinishedAt(s), year))
    .reduce((n, s) => n + readPages(s), 0);
  const yearPosts = myPosts().filter((p) => inYear(p.created_at, year)).length;
  const yearReviews = myReviews().filter((p) => inYear(p.created_at, year)).length;

  panel.innerHTML = `
    <div class="karne-card">
      <div class="karne-head">
        <span>${t('YILLIK OKUMA HEDEFİ')}</span>
        <label class="year-pick">
          <select id="stats-year" aria-label="${t('İstatistik yılı')}">
            ${years.map((y) => `<option value="${y}"${y === year ? ' selected' : ''}>${y}</option>`).join('')}
          </select>
        </label>
      </div>
      <div class="goal-line"><strong>${yearFinished} / ${goal} ${t('kitap')}</strong><span>${t('{n} · %{p} tamamlandı', { n: year, p: pct })}</span></div>
      <div class="progress progress--gold"><span style="width:${pct}%"></span></div>
      <div class="goal-edit">
        <label for="stats-goal-input">${t('{n} hedefini değiştir', { n: year })}</label>
        <input id="stats-goal-input" type="number" min="1" max="100000" step="1" value="${goal}" inputmode="numeric" aria-label="${t('{n} yıllık kitap hedefi', { n: year })}" />
        <span>${t('kitap')}</span>
        <button type="button" id="stats-goal-save">${t('Kaydet')}</button>
      </div>
      <div class="profile-stats">
        ${stat(yearFinished, t('Okunan kitap'))}
        ${stat(yearPages.toLocaleString('tr-TR'), t('Okunan sayfa'))}
        ${stat(yearPosts, t('Paylaşım'))}
        ${stat(yearReviews, t('İnceleme'))}
      </div>
    </div>
    <div class="karne-card">
      <div class="karne-head"><span>${t('GRAFİKLER')}</span><span>${esc(periodLabel)} · ${esc(metricLabel.toLocaleUpperCase('tr-TR'))}</span></div>
      <div class="chart-periods" role="group" aria-label="${t('Grafik zaman aralığı')}">
        ${CHART_PERIODS.map((p) => `<button type="button" class="chart-period${p.key === period ? ' is-active' : ''}" data-chart-period="${p.key}" aria-pressed="${p.key === period}">${t(p.label)}</button>`).join('')}
      </div>
      <div class="chart-metrics" role="group" aria-label="${t('Grafik verisi')}">
        ${CHART_METRICS.map((m) => `<button type="button" class="chart-chip${m.key === metric ? ' is-active' : ''}" data-chart-metric="${m.key}" aria-pressed="${m.key === metric}">${t(m.label)}</button>`).join('')}
      </div>
      <div class="bar-chart" role="img" aria-label="${esc(periodLabel)} ${esc(metricLabel.toLocaleLowerCase('tr-TR'))}${t(' grafiği')}">
        ${chart.values.map((v, i) => `
          <div class="bar-col" title="${esc(chart.labels[i])}: ${v}">
            <span class="bar-value">${v || ''}</span>
            <div class="bar-track"><span class="bar-fill" style="height:${v ? Math.max(6, Math.round((v / max) * 100)) : 0}%"></span></div>
            <small>${esc(chart.labels[i])}</small>
          </div>`).join('')}
      </div>
      <p class="chart-caption">${esc(chart.caption)} · ${esc(metricLabel)}</p>
    </div>
    <div class="karne-card">
      <div class="karne-head"><span>${t('ZAMAN ARALIKLARI')}</span><span>${t('HAFTALIK · AYLIK · YILLIK')}</span></div>
      <div class="period-grid">
        ${periods.map((p) => `
          <div class="period-col">
            <strong>${p.label}</strong>
            <small class="period-note">${esc(String(p.note))}</small>
            <div><span>${t('Okunan kitap')}</span><b>${p.books}</b></div>
            <div><span>${t('Sayfa')}</span><b>${p.pages.toLocaleString('tr-TR')}</b></div>
            <div><span>${t('Paylaşım')}</span><b>${p.posts}</b></div>
          </div>`).join('')}
      </div>
    </div>`;
}

$$('[data-stats-tab]').forEach((tab) => tab.addEventListener('click', () => {
  state.statsTab = tab.dataset.statsTab;
  $$('[data-stats-tab]').forEach((t) => {
    const active = t === tab;
    t.classList.toggle('is-active', active);
    t.setAttribute('aria-selected', String(active));
  });
  renderStatsView();
}));

/* İstatistik yılı ve grafik verisi; panel içeriği yeniden çizildiği için delege edilir. */
$('#stats-panel')?.addEventListener('change', (e) => {
  if (e.target.id !== 'stats-year') return;
  state.statsYear = Number(e.target.value) || new Date().getFullYear();
  renderStatsView();
});
$('#stats-panel')?.addEventListener('click', (e) => {
  const period = e.target.closest('[data-chart-period]');
  if (period) {
    state.chartPeriod = period.dataset.chartPeriod;
    renderStatsView();
    return;
  }
  const chip = e.target.closest('[data-chart-metric]');
  if (chip) {
    state.chartMetric = chip.dataset.chartMetric;
    renderStatsView();
    return;
  }
  if (e.target.id === 'stats-goal-save') {
    const input = document.querySelector('#stats-goal-input');
    const value = Number(input?.value);
    if (!Number.isFinite(value) || value < 1) {
      toast(t('Geçerli bir kitap hedefi gir'));
      return;
    }
    const year = statsYear();
    const goal = Math.min(100000, Math.floor(value));
    state.settings.yearlyGoals = { ...(state.settings.yearlyGoals || {}), [String(year)]: goal };
    if (year === new Date().getFullYear()) state.settings.yearlyGoal = goal;
    saveSettings(`${t('{n} hedefi güncellendi', { n: year })}`);
    renderIdentity();
    renderStatsView();
  }
});
$('#stats-panel')?.addEventListener('keydown', (e) => {
  if (e.target.id === 'stats-goal-input' && e.key === 'Enter') {
    e.preventDefault();
    document.querySelector('#stats-goal-save')?.click();
  }
});

function rememberBook(book) {
  if (!book || !book.id) return;
  const index = state.data.books.findIndex((b) => b.id === book.id);
  if (index >= 0) state.data.books[index] = book;
  else state.data.books.push(book);
}

async function loadCatalog(reset = false) {
  if (!state.data || state.bookLoading) return;
  if (reset) {
    state.bookOffset = 0;
    state.bookTotal = 0;
    state.bookHasMore = true;
    state.bookCatalog = [];
  }
  if (!state.bookHasMore) return;
  state.bookLoading = true;
  try {
    const params = new URLSearchParams({ limit: '100', offset: String(state.bookOffset) });
    const filters = {
      q: state.bookQuery, genre: state.bookGenre, category: state.bookCategory,
      decade: state.bookDecade, focus: state.bookFocus, sort: state.bookSort
    };
    Object.entries(filters).forEach(([key, value]) => {
      if (value && value !== 'all') params.set(key, value);
    });
    const result = await api('/api/books?' + params.toString());
    state.bookGenres = result.genres || [];
    state.bookTotal = Number(result.total || 0);
    (result.books || []).forEach(rememberBook);
    state.bookCatalog.push(...(result.books || []));
    state.bookOffset += (result.books || []).length;
    state.bookHasMore = state.bookOffset < state.bookTotal && (result.books || []).length > 0;
  } catch (error) {
    toast(error.message);
  } finally {
    state.bookLoading = false;
    renderLibrary();
  }
}

async function loadBookFilterOptions() {
  try {
    const options = await api('/api/books/filters');
    state.bookGenres = options.genres || [];
    const fill = (selector, values, allLabel, selected) => {
      const el = $(selector);
      if (!el) return;
      el.innerHTML = `<option value="">${allLabel}</option>` + (values || []).map((value) => {
        const item = typeof value === 'string' ? { value, label: value } : value;
        return `<option value="${esc(item.value)}"${item.value === selected ? ' selected' : ''}>${esc(item.label)}</option>`;
      }).join('');
    };
    const topic = $('#filter-topic');
    if (topic) {
      const selected = topic.value;
      const focusOptions = [
        { value: 'focus:islamic', label: t('İslami ilimler') },
        { value: 'focus:classics', label: t('Dünya klasikleri') },
        { value: 'focus:turkish', label: t('Türk edebiyatı') },
        { value: 'focus:science', label: t('Bilim ve teknoloji') }
      ];
      const entries = [
        ...(options.categories || []).map((value) => ({ value: `cat:${value}`, label: value })),
        ...(options.genres || []).map((value) => ({ value: `genre:${value}`, label: value })),
        ...focusOptions
      ];
      const unique = entries.sort((a, b) => compareCatalogNames(a.label, b.label));
      topic.innerHTML = `<option value="">${t('Tüm türler')}</option>` + unique
        .map((item) => `<option value="${esc(item.value)}">${esc(item.label)}</option>`).join('');
      topic.value = selected;
    }
    fill('#filter-decade', (options.decades || []).map((d) => ({ value: String(d), label: t("{n}'ler", { n: d }) })),
      t('Tüm yıllar'), state.bookDecade);
    syncBookFilterInputs();
  } catch (error) {
    toast(error.message);
  }
}

function resetBookFilterState() {
  Object.assign(state, {
    bookQuery: '', bookGenre: '', bookDecade: '', bookCategory: '',
    bookFocus: '', bookTopic: '', bookSort: 'title'
  });
}

function syncBookFilterInputs() {
  const topic = state.bookCategory ? `cat:${state.bookCategory}`
    : state.bookGenre ? `genre:${state.bookGenre}`
      : state.bookFocus ? `focus:${state.bookFocus}` : '';
  const values = {
    '#filter-q': state.bookQuery,
    '#filter-topic': topic, '#filter-decade': state.bookDecade,
    '#filter-sort': state.bookSort
  };
  Object.entries(values).forEach(([selector, value]) => {
    const el = $(selector);
    if (el) el.value = value || '';
  });
}

function bindBookFilters() {
  const textFilters = { '#filter-q': 'bookQuery' };
  Object.entries(textFilters).forEach(([selector, key]) => {
    const el = $(selector);
    if (!el) return;
    const apply = async () => { state[key] = el.value.trim(); await loadCatalog(true); };
    el.addEventListener('change', apply);
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); apply(); }
    });
  });
  const selectFilters = { '#filter-decade': 'bookDecade', '#filter-sort': 'bookSort' };
  Object.entries(selectFilters).forEach(([selector, key]) => {
    $(selector)?.addEventListener('change', async (e) => {
      state[key] = e.target.value;
      await loadCatalog(true);
    });
  });
  $('#filter-topic')?.addEventListener('change', async (e) => {
    const value = e.target.value;
    state.bookCategory = '';
    state.bookGenre = '';
    state.bookFocus = '';
    state.bookTopic = value;
    if (value.startsWith('cat:')) state.bookCategory = value.slice(4);
    else if (value.startsWith('genre:')) state.bookGenre = value.slice(6);
    else if (value.startsWith('focus:')) state.bookFocus = value.slice(6);
    await loadCatalog(true);
  });
  $('#filter-reset')?.addEventListener('click', async () => {
    resetBookFilterState();
    syncBookFilterInputs();
    await loadCatalog(true);
  });
}

function renderLibrary() {
  const grid = $('#book-grid');
  if (!grid || !state.data) return;
  const books = state.bookCatalog;
  const cards = books.length ? books.map((b) => {
    const meta = bookMetaHTML(b);
    return `
    <div class="book-card" data-book="${esc(b.id)}" title="${t('Kitap detayını ve müzakere masasını aç')}">
      ${bookCoverHTML(b)}
      <strong>${esc(b.title)}</strong>
      <small>${esc(b.author || t('Yazar bilinmiyor'))}${meta ? `<br />${meta}` : ''}</small>
      <span class="read-status">${esc(b.category)}</span>
    </div>`;
  }).join('') : `<p class="rail-muted">${t('Bu kategoride kitap yok.')}</p>`;
  const more = state.bookHasMore
    ? `<button class="btn btn-outline btn-sm book-load-more" type="button" data-load-more>${
        state.bookLoading ? t('Yükleniyor…') : t('Daha fazla kitap yükle')
      }</button>`
    : '';
  grid.innerHTML = cards + more;
}

function groupIcon(g) {
  if (g.avatar_image) return `<img src="${esc(g.avatar_image)}" alt="" />`;
  const icon = g.kind === 'meclis' ? 'users' : g.kind === 'direct' ? 'message-circle' : 'users-round';
  return `<i data-lucide="${icon}" aria-hidden="true"></i>`;
}

function groupCardHTML(g) {
  const isHalka = g.kind === 'halka';
  const kindLabel = isHalka
    ? `◈ ${t('Halka')} · ${g.member_count}${t(' üye')}`
    : `❖ ${t('Özel meclis')} · ${g.member_count}/50${t(' üye')}`;
  const openAttr = isHalka ? 'data-open-circle' : 'data-open-group';
  return `
    <div class="group-card">
      <span class="group-avatar group-avatar--${esc(g.avatar_color)}">${groupIcon(g)}</span>
      <h3>${esc(g.name)}</h3>
      <p>${esc(g.description || (isHalka ? t('Açık ilim halkası') : t('Özel ilim meclisi')))}</p>
      <div class="group-meta"><span>${kindLabel}</span></div>
      <div class="group-card-actions">
        <button class="text-btn" type="button" ${openAttr}="${g.id}">${isHalka ? t('Akışa git →') : t('Mesajlara git →')}</button>
        ${isHalka && g.is_member !== false ? `<button class="text-btn text-btn--muted" type="button" data-leave-halka="${g.id}">${t('Halkadan ayrıl')}</button>` : ''}
      </div>
    </div>`;
}

function discoverCardHTML(g) {
  return `
    <div class="group-card discover-card">
      <span class="group-avatar group-avatar--${esc(g.avatar_color)}">${groupIcon(g)}</span>
      <h3>${esc(g.name)}</h3>
      <p>${esc(g.description || t('Herkese açık ilim halkası'))}</p>
      <div class="group-meta"><span>◈ ${g.member_count}${t(' üye')}</span></div>
      <div class="group-card-actions">
        ${g.is_member ? '' : `<button class="btn btn-gold btn-sm" type="button" data-join-halka="${g.id}">${t('Bu halkaya katıl')}</button>`}
        <button class="btn btn-outline btn-sm" type="button" data-open-circle="${g.id}">${t('Akışı aç →')}</button>
      </div>
    </div>`;
}

function renderRailCircles() {
  const halkalar = (state.data.groups || []).filter((g) => g.kind === 'halka');
  $('#rail-circles').innerHTML = halkalar.length
    ? halkalar.slice(0, 5).map((g) =>
        `<li><span class="dot dot--${esc(g.avatar_color)}"></span> ${esc(g.name)} <i>${g.member_count}</i></li>`
      ).join('')
    : `<li class="rail-muted">${t('Henüz bir halkaya katılmadın.')}</li>`;
}

function renderCircles() {
  const groups = state.data.groups || [];
  const halkalar = groups.filter((g) => g.kind === 'halka');
  const meclisler = groups.filter((g) => g.kind === 'meclis');
  const discover = state.data.discover_circles || [];

  $('#circle-grid').innerHTML = halkalar.length
    ? halkalar.map(groupCardHTML).join('')
    : `<p class="rail-muted">${t('Henüz bir halkaya katılmadın. Aşağıdaki açık halkalardan birine katılabilirsin.')}</p>`;

  $('#discover-circles').innerHTML = discover.length
    ? discover.map(discoverCardHTML).join('')
    : `<p class="rail-muted">${t('Katılabileceğin başka halka yok. Yeni bir halka sen kurabilirsin.')}</p>`;

  $('#meclis-grid').innerHTML = meclisler.length
    ? meclisler.map(groupCardHTML).join('')
    : `<p class="rail-muted">${t('Henüz bir meclisin yok. Meclisler en az 3 kişiyle kurulur; şu anda hazır meclis bulunmuyor.')}</p>`;

  renderRailCircles();
}

function renderPostcards() {
  const quotes = myPosts().filter((p) => p.type === 'quote');
  $('#postcard-grid').innerHTML = quotes.length ? quotes.map((p) => `
    <div class="mini-postcard">
      <span class="quote-mark">“</span>
      <p>${esc(p.text)}</p>
      <small>— ${esc(p.book)}, ${esc(p.writer)}</small>
      ${ownActionsHTML('post', p.id)}
    </div>`).join('') : `<p class="shelf-empty">${t('Henüz alıntı paylaşmadın.')}</p>`;
}

function renderCircleFeed() {
  const group = [...(state.data?.groups || []), ...(state.data?.discover_circles || [])]
    .find((g) => g.id === state.activeCircleId && g.kind === 'halka');
  const title = $('#circle-feed-title');
  const desc = $('#circle-feed-desc');
  const shareBtn = $('#circle-feed-share');
  if (title) title.textContent = group?.name || t('Halka akışı');
  if (desc) desc.textContent = group?.description || t('Bu halkanın alıntıları ve incelemeleri.');
  const backLabel = $('#circle-feed-back span');
  if (backLabel) {
    const from = state.viewHistory[state.viewHistory.length - 1];
    const key = from === 'home' ? '← Ana sayfaya dön' : from ? '← Halkalara dön' : '← Geri dön';
    backLabel.textContent = t(key);
    backLabel.setAttribute('data-i18n', key);
  }
  if (shareBtn) {
    shareBtn.hidden = !group?.is_member;
    shareBtn.dataset.openShareCircle = group?.id || '';
  }
  const posts = (state.data?.posts || [])
    .filter((p) => p.group_id === state.activeCircleId)
    .sort((a, b) => b.created_at - a.created_at);
  const feed = $('#circle-feed');
  if (feed) feed.innerHTML = posts.map(postHTML).join('');
  const empty = $('#circle-feed-empty');
  if (empty) empty.hidden = posts.length > 0;
}

function directPeer(group) {
  if (group?.kind !== 'direct') return null;
  return (group.members || []).find((m) => Number(m.id) !== Number(state.user?.id)) || null;
}

function messageAuthorLabel(author) {
  if (!author) return t('Bilinmeyen yazar');
  return author.username ? `@${author.username}` : author.display_name || t('Bilinmeyen yazar');
}

function renderMessages() {
  const groups = (state.data.groups || []).filter((g) => g.kind !== 'halka');
  const list = $('#conversation-list');
  list.innerHTML = groups.length ? groups.map((g) => {
    const peer = directPeer(g);
    const title = peer ? `@${esc(peer.username || peer.display_name || '')}` : esc(g.name);
    const avatar = peer
      ? `<span class="conversation-avatar" data-profile-user="${esc(peer.id)}">${avatarHTML(peer)}</span>`
      : `<span class="group-avatar group-avatar--${esc(g.avatar_color)}">${groupIcon(g)}</span>`;
    const last = g.last_message || (g.kind === 'direct' ? '' : t('Sohbet'));
    return `
    <button class="conversation-item ${g.id === state.activeGroupId ? 'is-active' : ''}" type="button" data-open-group="${g.id}">
      ${avatar}
      <span class="conversation-copy">
        <strong${peer ? ` data-profile-user="${esc(peer.id)}"` : ''}>${title}</strong>
        ${last ? `<small>${esc(last)}</small>` : ''}
      </span>
      ${g.last_at ? `<time>${esc(timeAgo(g.last_at))}</time>` : ''}
    </button>`;
  }).join('')
    : `<p class="rail-muted">${t('Henüz sohbetin yok. “Yeni Mesaj” ile birine yazabilirsin.')}</p>`;

  const group = groups.find((g) => g.id === state.activeGroupId);
  if (!group) {
    $('#conversation-empty').hidden = false;
    $('#message-chat').hidden = true;
    return;
  }
  $('#conversation-empty').hidden = true;
  $('#message-chat').hidden = false;
  const nameEl = $('#message-chat-name');
  const peer = directPeer(group);
  nameEl.textContent = peer ? `@${peer.username || peer.display_name || ''}` : group.name;
  if (peer) nameEl.dataset.profileUser = peer.id;
  else delete nameEl.dataset.profileUser;
  nameEl.classList.toggle('is-profile-link', Boolean(peer));
  const avatarHost = $('#message-chat-avatar');
  if (avatarHost) {
    avatarHost.innerHTML = peer
      ? `<span data-profile-user="${esc(peer.id)}" title="${esc(t('Profili gör'))}">${avatarHTML(peer)}</span>`
      : `<span class="group-avatar group-avatar--${esc(g.avatar_color)}">${groupIcon(group)}</span>`;
  }
  $('#message-chat-meta').textContent = group.kind === 'direct'
    ? (peer?.display_name || '')
    : group.kind === 'meclis'
      ? `❖ ${t('Meclis')} · ${group.member_count}${t(' üye')}`
      : `◈ ${t('Halka')} · ${group.member_count}${t(' üye')}`;

  const messages = (state.data.group_messages || {})[group.id] || [];
  const box = $('#message-messages');
  box.innerHTML = messages.length ? messages.map((m) => `
    <div class="chat-bubble ${m.is_me ? 'is-me' : ''}">
      ${m.is_me ? '' : `<span class="chat-bubble-avatar" data-profile-user="${esc(m.author.id)}">${avatarHTML(m.author)}</span>`}
      <span class="chat-bubble-copy"><button class="chat-profile-link" type="button" data-profile-user="${esc(m.author.id)}">${esc(messageAuthorLabel(m.author))}</button>${esc(m.text)}</span>
    </div>`).join('')
    : `<p class="rail-muted">${t('Henüz mesaj yok. İlk cümleyi sen yaz.')}</p>`;
  box.scrollTop = box.scrollHeight;
}

function renderCurricula() {
  const host = $('#curriculum-grid');
  if (!host) return;
  host.innerHTML = (state.data.curricula || []).map(curriculumCardHTML).join('');
}

/* ---------------- Ana sayfa: duyurular ve kitap seçkisi ---------------- */

const FEATURED_CLASSIC_TITLES = ['Suç ve Ceza', 'Simyacı', 'İnsan Ne İle Yaşar', 'Dil Belası / Afetleri'];

function homePicks(type) {
  if (type === 'classic') {
    const byTitle = new Map(state.data.books.map((b) => [b.title, b]));
    const featured = FEATURED_CLASSIC_TITLES.map((title) => byTitle.get(title)).filter(Boolean);
    if (featured.length) return featured;
  }
  const wanted = type === 'islamic' ? ISLAMIC_CATEGORIES : CLASSIC_CATEGORIES;
  return state.data.books
    .filter((b) => wanted.has(b.category) && !FEATURED_CLASSIC_TITLES.includes(b.title))
    .slice(0, 4);
}

function miniBook(b) {
  const meta = bookMetaHTML(b);
  return `<div class="home-book-card" data-book="${esc(b.id)}" title="${t('Kitap detayını aç')}">
    ${bookCoverHTML(b)}
    <strong>${esc(b.title)}</strong>
    <small>${esc(b.author || t('Yazar bilinmiyor'))}${meta ? `<br />${meta}` : ''}</small>
  </div>`;
}

function renderHomeBooks() {
  const islamic = homePicks('islamic');
  const classics = homePicks('classic');
  $('#home-islamic-books').innerHTML = islamic.length
    ? islamic.map(miniBook).join('')
    : `<p class="rail-muted">${t('Bu kategoride henüz kitap yok.')}</p>`;
  $('#home-classic-books').innerHTML = classics.length
    ? classics.map(miniBook).join('')
    : `<p class="rail-muted">${t('Bu kategoride henüz kitap yok.')}</p>`;
}

/* ---------------- Bildirimler ---------------- */

function notificationsSeenKey(scope = 'activity') {
  return `ilimhalkasi.notifications.${state.user?.id || 'guest'}.${scope}`;
}

function notificationsSeenAt(scope = 'activity') {
  let raw = Number(localStorage.getItem(notificationsSeenKey(scope)));
  if (!raw && scope === 'activity') {
    raw = Number(localStorage.getItem(`ilimhalkasi.notifications.${state.user?.id || 'guest'}`));
  }
  return Number.isFinite(raw) && raw > 0 ? raw : 0;
}

function markNotificationsSeen(scope = 'activity') {
  const now = String(Date.now() / 1000);
  if (scope === 'all') {
    localStorage.setItem(notificationsSeenKey('activity'), now);
    localStorage.setItem(notificationsSeenKey('announcement'), now);
  } else {
    localStorage.setItem(notificationsSeenKey(scope), now);
  }
  renderNotifications();
}

const NOTIFICATION_PREFS = {
  announcement: 'notifyAnnouncements',
  circle_post: 'notifyCirclePosts',
  comment: 'notifyComments',
  mention: 'notifyMentions',
  group_message: 'notifyMessages',
  follow: 'notifyFollowers',
  like: 'notifyComments',
  favorite: 'notifyComments',
  book_request: 'notifySupport',
  support: 'notifySupport'
};

// Tercihler yalnızca telefon bildirimini açıp kapatır; uygulama içi bildirim
// merkezi her olayı göstermeye devam eder.
function phoneNotificationAllowed(kind) {
  const key = NOTIFICATION_PREFS[kind];
  return !key || state.settings?.[key] !== false;
}

function syncPhoneNotificationPrefs() {
  const bridge = window.IlimNative;
  if (!bridge || typeof bridge.setNotificationPreferences !== 'function') return;
  const prefs = {};
  Object.entries(NOTIFICATION_PREFS).forEach(([kind, key]) => {
    prefs[kind] = phoneNotificationAllowed(kind);
  });
  bridge.setNotificationPreferences(JSON.stringify(prefs));
}

// Uygulama içi bildirimler her olayı gösterir; tercihler yalnızca telefonu etkiler.
// Yeni görünen olayları yerel Android bildirimi olarak da ilet.
function pushNativeNotifications(baselineOnly = false) {
  const bridge = window.IlimNative;
  if (!bridge || typeof bridge.showNotification !== 'function') return;
  const items = collectNotifications();
  const ids = new Set(items.map((item) => String(item.id)));
  if (phoneNotifiedIds === null || baselineOnly) {
    phoneNotifiedIds = ids;
    return;
  }
  items.forEach((item) => {
    const id = String(item.id);
    if (phoneNotifiedIds.has(id)) return;
    phoneNotifiedIds.add(id);
    if (!phoneNotificationAllowed(item.kind)) return;
    bridge.showNotification(
      String(item.kind || 'announcement'),
      String(item.title || t('Yeni bildirim')),
      String(item.body || ''),
      id
    );
  });
  phoneNotifiedIds = ids;
}

function collectNotifications() {
  const data = state.data;
  const me = state.user;
  if (!data || !me) return [];
  const meId = Number(me.id);
  const items = [];

  (data.announcements || []).forEach((a) => {
    items.push({
      id: `announcement-${a.id}`,
      icon: '◈',
      title: t('Duyuru yayınlandı'),
      body: [a.title, a.body].filter(Boolean).join(' · '),
      ts: Number(a.created_at) || 0,
      kind: 'announcement',
      view: 'home',
      target: ''
    });
  });

  (data.notifications || []).forEach((note) => {
    // Yorum bildirimleri aşağıda bootstrap içindeki yorumlardan toplanıyor;
    // sunucu kaydıyla çift oluşmaması için bu türü atla.
    if (note.kind === 'comment') return;
    const actor = note.actor?.display_name || t('Bilinmeyen yazar');
    const group = note.group?.name || t('Halka');
    let title;
    let body;
    if (note.kind === 'follow') {
      title = t('Yeni takipçi');
      body = t('{name} seni takip etti', { name: actor });
    } else if (note.kind === 'circle_post') {
      title = t('Halkada yeni paylaşım');
      body = t('{name} {group} halkasında yeni bir paylaşım yaptı', { name: actor, group });
    } else if (note.kind === 'mention') {
      title = t('Bir paylaşımda anıldın');
      body = t('{name} seni bir paylaşımda andı', { name: actor });
    } else if (note.kind === 'group_message') {
      title = t('Yeni meclis mesajı');
      body = t('{name} {group} sohbetine mesaj yazdı', { name: actor, group });
    } else if (note.kind === 'like') {
      title = t('Paylaşımın beğenildi');
      body = String(note.text || t('{name} paylaşımını beğendi', { name: actor }));
    } else if (note.kind === 'favorite') {
      title = t('Paylaşımın kaydedildi');
      body = String(note.text || t('{name} paylaşımını kaydetti', { name: actor }));
    } else if (note.kind === 'book_request') {
      title = t('Kitap önerisi');
      body = String(note.text || '');
    } else {
      title = t('Yeni bildirim');
      body = String(note.text || '');
    }
    items.push({
      id: note.id || `server-${note.ts}`,
      icon: note.icon || '◈',
      title,
      body,
      ts: Number(note.ts || note.created_at) || 0,
      kind: note.kind,
      view: note.view || 'home',
      target: note.target || '',
      actorId: note.actor?.id
    });
  });

  const walkComments = (comments, post) => {
    (comments || []).forEach((c) => {
      const authorId = Number(c.author?.id);
      if (authorId && authorId !== meId) {
        items.push({
          id: `comment-${c.id}`,
          icon: '✎',
          title: t('Yorumun var'),
          body: `${c.author?.display_name || t('Bilinmeyen yazar')} ${t('yeni bir yorum yazdı')} · ${post.book}`,
          ts: Number(c.created_at) || 0,
          kind: 'comment',
          view: 'journal',
          target: null
        });
      }
      if (c.replies) walkComments(c.replies, post);
    });
  };
  (data.posts || []).forEach((post) => {
    if (Number(post.author_id || post.author?.id) === meId) walkComments(post.comments, post);
  });

  (data.tickets || []).forEach((ticket) => {
    (ticket.replies || []).forEach((reply) => {
      if (!reply.admin) return;
      items.push({
        id: `ticket-${ticket.id}-${reply.created_at}`,
        icon: '✉',
        title: t('Destek talebine yanıt geldi'),
        body: `${reply.admin.display_name}: ${reply.body}`,
        ts: Number(reply.created_at) || 0,
        kind: 'support',
        view: 'support',
        target: null
      });
    });
  });

  return items
    .sort((a, b) => b.ts - a.ts)
    .slice(0, 30);
}

function notificationItemHTML(n, unread) {
  return `
    <button class="notification-item${unread ? ' is-unread' : ''}" type="button"
      data-notification-id="${esc(n.id)}" data-notification-kind="${esc(n.kind || '')}"
      data-notification-view="${esc(n.view)}" data-notification-actor="${esc(n.actorId || '')}"
      data-notification-target="${esc(n.target || '')}">
      <span class="notification-icon" aria-hidden="true">${n.icon}</span>
      <span class="notification-body">
        <strong>${esc(n.title)}</strong>
        <p>${esc(n.body)}</p>
        <small>${esc(timeAgo(n.ts))}</small>
      </span>
    </button>`;
}

function renderNotifications() {
  const announcementList = $('#notifications-list');
  const allList = $('#notifications-view-list');
  if (!announcementList && !allList) return;

  const items = collectNotifications();
  const announcementSeen = notificationsSeenAt('announcement');
  const activitySeen = notificationsSeenAt('activity');
  const isUnread = (n) => n.ts > (n.kind === 'announcement' ? announcementSeen : activitySeen);
  const unread = items.filter(isUnread).length;

  $$('#notifications-btn .badge-count, #sidebar-notifications-btn .badge-count').forEach((badge) => {
    badge.textContent = unread > 99 ? '99+' : String(unread);
    badge.hidden = unread === 0;
  });
  $('#notifications-btn')?.setAttribute('aria-label', `${t('Duyurular')}${unread ? ` (${unread})` : ''}`);
  $('#sidebar-notifications-btn')?.setAttribute('aria-label', `${t('Bildirimlerim')}${unread ? ` (${unread})` : ''}`);

  const paint = (el, rows, emptyKey) => {
    if (!el) return;
    el.innerHTML = rows.length
      ? rows.map((n) => notificationItemHTML(n, isUnread(n))).join('')
      : `<p class="notifications-empty">${t(emptyKey)}</p>`;
  };
  paint(announcementList, items.filter((n) => n.kind === 'announcement'), 'Henüz duyuru yok.');
  paint(allList, items, 'Henüz bildirim yok.');
  const panel = $('#notifications-panel');
  if (panel && !panel.hidden) applyStaticI18n(panel);
  const view = $('#view-notifications');
  if (view?.classList.contains('is-active')) applyStaticI18n(view);
}

function toggleNotifications(force) {
  const panel = $('#notifications-panel');
  if (!panel) return;
  const open = typeof force === 'boolean' ? force : panel.hidden;
  panel.hidden = !open;
  $('#notifications-btn')?.setAttribute('aria-expanded', String(open));
  if (open) {
    renderNotifications();
    markNotificationsSeen('announcement');
  }
}

/* ---------------- Rehberler / âlimler ---------------- */

function scholarBookCardHTML(book) {
  return `
    <button class="scholar-book-card" type="button" data-detail-book="${esc(book.id)}" title="${t('Kitap sayfasını aç')}">
      ${bookCoverHTML(book)}
      <strong>${esc(book.title)}</strong>
      <small>${esc(book.author || '')}</small>
    </button>`;
}

function renderScholars() {
  if (!$('#scholar-list')) return;
  const all = state.data.scholars || [];
  if (!all.length) return;
  const categories = [...new Set(all.map((s) => s.category || 'Genel'))].sort((a, b) => a.localeCompare(b, 'tr-TR'));
  const categoryBox = $('#scholar-categories');
  if (categoryBox) {
    categoryBox.innerHTML = `
      <button class="chip ${state.scholarCategory === 'all' ? 'is-active' : ''}" type="button"
        data-scholar-category="all">${t('Tüm kategoriler')}</button>
      ${categories.map((category) => `
        <button class="chip ${state.scholarCategory === category ? 'is-active' : ''}" type="button"
          data-scholar-category="${esc(category)}">${esc(category)}</button>`).join('')}`;
  }
  const query = (state.scholarQuery || '').trim().toLocaleLowerCase('tr-TR');
  const scholars = all.filter((s) => {
    if (state.scholarKind !== 'all' && (s.kind || 'alim') !== state.scholarKind) return false;
    if (state.scholarCategory !== 'all' && (s.category || 'Genel') !== state.scholarCategory) return false;
    if (!query) return true;
    const haystack = [s.name, s.full_name, s.years, s.era, s.category, ...(s.books || [])]
      .join(' ').toLocaleLowerCase('tr-TR');
    return haystack.includes(query);
  });
  if (scholars.length && (!state.scholarSlug || !scholars.some((s) => s.slug === state.scholarSlug))) {
    state.scholarSlug = scholars[0].slug;
  }
  $('#scholar-list').innerHTML = scholars.length
    ? scholars.map((s) => `
        <button class="scholar-item ${s.slug === state.scholarSlug ? 'is-active' : ''}" type="button" data-scholar="${esc(s.slug)}">
          ${avatarHTML(s)}
          <span><strong>${esc(s.name)}</strong><small>${esc(s.category || t('Genel'))}</small></span>
        </button>`).join('')
    : `<p class="scholar-empty">${t('Aramana uyan rehber bulunamadı.')}</p>`;

  const s = scholars.find((item) => item.slug === state.scholarSlug) || scholars[0];
  if (!s) { $('#scholar-detail').innerHTML = `<p class="scholar-empty">${t('Rehber seçilmedi.')}</p>`; return; }
  const isAdmin = !!(state.user && state.user.is_admin);
  $('#scholar-detail').innerHTML = `
    <div class="scholar-hero">
      ${avatarHTML(s)}
      <div><h2>${esc(s.name)}</h2><p>${esc(s.category || t('Genel'))} · ${esc(s.years)} · ${esc(s.era)}</p></div>
    </div>
    <div class="scholar-section">
      <h3>${t('Hakkında')}</h3>
      <p>${esc(s.bio)}</p>
    </div>
    <div class="scholar-section">
      <h3>${t('İlim âlemindeki yeri ve önemi')}</h3>
      <p>${esc(s.importance)}</p>
    </div>
    <div class="scholar-section">
      <h3>${t('Neler yaptı?')}</h3>
      <p>${esc(s.contribution)}</p>
    </div>
    <div class="scholar-section">
      <h3>${t('Eserleri')}</h3>
      ${s.bookItems?.length
        ? `<div class="scholar-book-grid">${s.bookItems.map(scholarBookCardHTML).join('')}</div>`
        : `<div class="scholar-books">${(s.books || []).map((b) => `<span>${esc(b)}</span>`).join('')}</div>`}
    </div>
    <div class="scholar-section">
      <h3>${t('Önerdiği kitaplar')}</h3>
      ${s.recommendedItems?.length
        ? `<div class="scholar-book-grid">${s.recommendedItems.map(scholarBookCardHTML).join('')}</div>`
        : `<div class="scholar-books">${(s.recommended || []).map((b) => `<span>${esc(b)}</span>`).join('')}</div>`}
    </div>
    <div class="scholar-section">
      <h3>${t('Hakkındaki yorumlar ({n})', { n: s.comments.length })}</h3>
      <div class="scholar-comments">
        ${s.comments.length ? s.comments.map((c) => `
          <article class="scholar-comment">
            <div class="scholar-comment-head">
              <strong>${esc(c.author.display_name)} <small>· ${esc(timeAgo(c.created_at))}</small></strong>
              ${isAdmin ? `<button class="admin-delete" type="button" data-delete-scholar-comment="${c.id}">${t('Yorumu sil')}</button>` : ''}
            </div>
            <p>${esc(c.text)}</p>
          </article>`).join('')
          : `<p class="scholar-empty">${t('Bu âlim hakkında henüz yorum yok. İlk cümleyi sen yazabilirsin.')}</p>`}
      </div>
      <form class="scholar-comment-form" data-slug="${esc(s.slug)}" style="margin-top:12px">
        <div class="admin-reply">
          <input type="text" name="text" placeholder="${t('{n} hakkında ne düşünüyorsun?', { n: esc(s.name) })}" aria-label="${t('Yorumun')}" required />
          <button type="submit">${t('Yorum ekle')}</button>
        </div>
      </form>
    </div>`;
}

/* ---------------- Destek, şikayet ve yönetim ---------------- */

function renderSupport() {
  const targets = state.data.report_targets || [];
  const options = targets.map((u) =>
    `<option value="@${esc(u.username)}">${esc(u.display_name)}</option>`
  ).join('');
  $('#report-user-options').innerHTML = options;
  $('#direct-user-options').innerHTML = options;

  $('#support-list').innerHTML = (state.data.tickets || []).length
    ? state.data.tickets.map((t) => `
        <article class="support-item">
          <div class="support-item-head">
            <strong>${esc(t.subject)} <small class="curriculum-meta">· ${t.kind === 'talep' ? t('Talep / öneri') : t('Şikayet')}</small></strong>
            <span class="status-badge" data-status="${esc(t.status)}">${t.status === 'replied' ? t('Yanıtlandı') : t.status === 'closed' ? t('Kapatıldı') : t('İnceleniyor')}</span>
          </div>
          <p>${esc(t.body)}</p>
          <small class="curriculum-meta">${esc(timeAgo(t.created_at))}</small>
          ${t.replies.map((r) => `
            <div class="support-reply"><strong>⚑ ${esc(r.admin.display_name)} · ${esc(timeAgo(r.created_at))}</strong><p>${esc(r.body)}</p></div>`).join('')}
        </article>`).join('')
    : `<p class="announcement-empty">${t('Henüz bir talebin veya şikayetin yok.')}</p>`;

  $('#report-list').innerHTML = (state.data.reports || []).length
    ? state.data.reports.map((r) => `
        <article class="support-item">
          <div class="support-item-head">
            <strong>${esc(r.reason)}</strong>
            <span class="status-badge" data-status="${esc(r.status)}">${r.status === 'replied' ? t('Yanıtlandı') : r.status === 'closed' ? t('Kapatıldı') : t('İnceleniyor')}</span>
          </div>
          <p>${esc(r.detail || t('Açıklama eklenmedi.'))}</p>
          <small class="curriculum-meta">${esc(timeAgo(r.created_at))}</small>
          ${r.admin_reply ? `<div class="support-reply"><strong>${t('⚑ Yönetici yanıtı')}</strong><p>${esc(r.admin_reply)}</p></div>` : ''}
        </article>`).join('')
    : `<p class="announcement-empty">${t('Henüz kullanıcı şikayetin yok.')}</p>`;
}

function statusLabel(status) {
  return status === 'replied' ? t('Yanıtlandı') : status === 'closed' ? t('Kapatıldı') : t('Bekliyor');
}

function renderAdmin() {
  const admin = state.data.admin;
  if (!admin) return;

  $('#admin-announcements').innerHTML = (state.data.announcements || []).length
    ? state.data.announcements.map((a) => `
        <div class="admin-item">
          <div class="admin-item-head">
            <strong>${esc(a.title)} <small class="curriculum-meta">· ${esc(t(announcementKinds[a.kind] || 'Duyuru'))}</small></strong>
            <button class="admin-delete" type="button" data-delete-announcement="${a.id}">${t('Kaldır')}</button>
          </div>
          <p>${esc(a.body)}</p>
          <small class="curriculum-meta">${esc(a.admin.display_name)} · ${esc(timeAgo(a.created_at))}</small>
        </div>`).join('')
    : `<p class="announcement-empty">${t('Henüz yayınlanmış duyuru yok.')}</p>`;

  $('#admin-tickets').innerHTML = admin.tickets.length
    ? admin.tickets.map((t) => `
        <div class="admin-item">
          <div class="admin-item-head">
            <strong>${esc(t.subject)} <small class="curriculum-meta">· ${t.kind === 'talep' ? t('Talep') : t('Şikayet')} · ${esc(t.owner.display_name)}</small></strong>
            <span class="status-badge" data-status="${esc(t.status)}">${statusLabel(t.status)}</span>
          </div>
          <p>${esc(t.body)}</p>
          <small class="curriculum-meta">${esc(timeAgo(t.created_at))}</small>
          ${t.replies.map((r) => `<div class="support-reply"><strong>⚑ ${esc(r.admin.display_name)}</strong><p>${esc(r.body)}</p></div>`).join('')}
          <form class="admin-reply" data-admin-reply="ticket" data-id="${t.id}">
            <input type="text" name="text" placeholder="${t('Özel yanıtını yaz...')}" aria-label="${t('Yanıt')}" required />
            <button type="submit">${t('Yanıtla')}</button>
          </form>
          <div class="admin-actions">
            ${t.status !== 'closed' ? `<button class="admin-delete" type="button" data-admin-close="ticket" data-id="${t.id}">${t('Kapat')}</button>` : ''}
          </div>
        </div>`).join('')
    : `<p class="announcement-empty">${t('Gelen şikayet veya talep yok.')}</p>`;

  $('#admin-reports').innerHTML = admin.reports.length
    ? admin.reports.map((r) => `
        <div class="admin-item">
          <div class="admin-item-head">
            <strong>${esc(r.reason)}</strong>
            <span class="status-badge" data-status="${esc(r.status)}">${statusLabel(r.status)}</span>
          </div>
          <p><b>${t('Şikayet eden:')}</b> ${esc(r.reporter.display_name)} · <b>${t('Şikayet edilen:')}</b> ${esc(r.reported.display_name)}<br>${esc(r.detail || t('Açıklama eklenmedi.'))}</p>
          <small class="curriculum-meta">${esc(timeAgo(r.created_at))}</small>
          ${r.admin_reply ? `<div class="support-reply"><strong>${t('⚑ Yanıtın')}</strong><p>${esc(r.admin_reply)}</p></div>` : ''}
          <form class="admin-reply" data-admin-reply="report" data-id="${r.id}">
            <input type="text" name="text" placeholder="${t('Şikayet edene yanıt yaz...')}" aria-label="${t('Yanıt')}" required />
            <button type="submit">${t('Yanıtla')}</button>
          </form>
          <div class="admin-actions">
            ${r.status !== 'closed' ? `<button class="admin-delete" type="button" data-admin-close="report" data-id="${r.id}">${t('Kapat')}</button>` : ''}
          </div>
        </div>`).join('')
    : `<p class="announcement-empty">${t('Kullanıcı şikayeti yok.')}</p>`;

  $('#admin-comments').innerHTML = admin.comments.length
    ? admin.comments.map((c) => `
        <div class="admin-item">
          <div class="admin-item-head">
            <strong>${esc(c.author.display_name)} <small class="curriculum-meta">· ${c.kind === 'scholar' ? t('Âlim yorumu') : t('Paylaşım yorumu')} · ${esc(timeAgo(c.created_at))}</small></strong>
            <button class="admin-delete" type="button" data-delete-comment="${esc(c.kind)}" data-id="${c.id}">${t('Yorumu sil')}</button>
          </div>
          <p>${esc(c.text)}</p>
        </div>`).join('')
    : `<p class="announcement-empty">${t('İncelenecek yorum yok.')}</p>`;

  $('#admin-users').innerHTML = admin.users.length
    ? admin.users.map((u) => `
        <div class="admin-item">
          <div class="admin-item-head">
            <strong>${esc(u.display_name)} <small class="curriculum-meta">@${esc(u.username)}${u.is_admin ? t(' · Yönetici') : ''}</small></strong>
            ${u.blocked ? `<span class="status-badge" data-status="closed">${t('Askıda')}</span>` : `<span class="status-badge">${t('Aktif')}</span>`}
          </div>
          ${u.is_admin ? '' : `<div class="admin-actions"><button class="btn btn-outline btn-sm" type="button" data-toggle-block="${u.id}">${u.blocked ? t('Engeli kaldır') : t('Kullanıcıyı engelle')}</button></div>`}
        </div>`).join('')
    : `<p class="announcement-empty">${t('Kullanıcı yok.')}</p>`;

  $('#admin-books').innerHTML = (admin.hidden_books || []).length
    ? admin.hidden_books.map((b) => `
        <div class="admin-item">
          <div class="admin-item-head">
            <strong>${esc(b.title)} <small class="curriculum-meta">· ${esc(b.author || t('Yazar bilinmiyor'))}</small></strong>
          </div>
          <p><b>${t('Gerekçe:')}</b> ${esc(b.hidden_reason || t('Belirtilmedi'))}</p>
          <div class="admin-actions"><button class="btn btn-outline btn-sm" type="button" data-restore-book="${b.id}">${t('Kataloğa geri getir')}</button></div>
        </div>`).join('')
    : `<p class="announcement-empty">${t('Gizlenen kitap yok.')}</p>`;

  $('#admin-book-requests').innerHTML = (admin.book_requests || []).length
    ? admin.book_requests.map((r) => bookRequestCardHTML(r, true)).join('')
    : `<p class="announcement-empty">${t('Gelen kitap önerisi yok.')}</p>`;
}

function renderAccess() {
  const isAdmin = !!(state.user && state.user.is_admin);
  $$('[data-admin-only]').forEach((el) => { el.hidden = !isAdmin; });
  $('#view-admin').hidden = !isAdmin;
  if (!isAdmin && state.currentView === 'admin') switchView('home');
}

function renderDebates() {
  const list = state.data.debates[state.currentBook] || [];
  $('#book-debate').innerHTML = `
    <p class="debate-intro">❖ <strong>${t('Müzakere Masası:')}</strong> ${t('Takıldığın ayet tefsirini, fıkhi meseleyi veya yorumunu sor; okurlar ve rehberler birlikte tartışsın.')}</p>
    <form class="debate-form" data-debate-form>
      <input type="text" placeholder="${t('Bu kitapla ilgili bir soru sor...')}" aria-label="${t('Soru')}" />
      <button type="submit">${t('Sor')}</button>
    </form>
    ${list.length ? list.map((q) => `
      <article class="debate-q">
        <div class="debate-q-head">${avatarHTML(q.author)}
          <div><strong>${esc(q.author.display_name)}</strong><small>${esc(timeAgo(q.created_at))}</small></div></div>
        <p>${esc(q.text)}</p>
        <button class="text-btn" type="button" data-answer-toggle="${q.id}">${t('Yanıt yaz')}</button>
        ${q.answers.length ? `<div class="debate-answers">${q.answers.map((a) => `
          <div class="debate-answer ${a.is_guide ? 'rehber-answer' : ''}"><strong>${esc(a.author.display_name)}${a.is_guide ? ` ${t('✓ Rehber')}` : ''}:</strong> ${esc(a.text)}</div>`).join('')}</div>` : ''}
        <form class="answer-form" data-answer-form="${q.id}" hidden>
          <input type="text" placeholder="${t('Yanıtını yaz...')}" aria-label="${t('Yanıt')}" />
          <button type="submit">${t('Gönder')}</button>
        </form>
      </article>`).join('') : `<div class="overview-card"><p>${t('Henüz soru yok. İlk soruyu sen sorabilirsin.')}</p></div>`}`;
}

function turkishBookDescription(book) {
  const description = String(book?.description || '').trim();
  if (book?.source === 'curated' && description) return description;
  const title = String(book?.title || t('Bu eser'));
  const author = String(book?.author || '').trim();
  const genre = bookGenres(book)[0] || 'ilim ve edebiyat';
  const year = book?.year ? ` ${t('{n} yılında yayımlanmıştır.', { n: book.year })}` : '';
  return `${t('{n}, İlim Halkası kütüphanesinde {m} alanında yer alan bir eserdir.', { n: title, m: genre })}${
    author ? ` ${t('Yazarı:')} ${author}.` : ''
  }${year} ${t('Kapağı, türü ve yayımlanma bilgileri bu sayfada toplanmıştır; alıntılarını ve müzakere sorularını toplulukla paylaşabilirsin.')}`;
}

function shelfEntryFor(book) {
  return (state.data?.shelf || []).find((s) => Number(s.book_id) === Number(book?.id));
}

function bookActionHTML(book) {
  if (!book?.id) return '';
  const entry = shelfEntryFor(book);
  // Toplam sayfa ve cilt sayısı katalogdan; kullanıcı yalnızca güncel sayfayı girer.
  const catalogEntry = {
    page_count: Number(book.page_count) || 0,
    volume_count: Number(book.volume_count) || 1,
    page: Number(entry?.page) || 0,
    volume: Number(entry?.volume) || 1,
    progress: Number(entry?.progress) || 0
  };
  const { total, page, pct, volumes, volume } = shelfProgress(catalogEntry);
  const preview = pageProgressText({ total, page, pct, volumes, volume })
    || t('Bu kitabın toplam sayfası katalogda henüz yok');
  const statuses = [
    ['reading', t('okuyorum')], ['finished', t('okudum')],
    ['wishlist', t('okuyacağım')], ['abandoned', t('yarım bıraktım')]
  ];
  const listOptions = (state.data.lists || []).map((l) =>
    `<option value="${esc(l.id)}">${esc(l.name)}</option>`).join('');
  return `
    <div class="book-actions">
      <div class="book-action-block">
        <h3>${t('Okuma durumun')}</h3>
        <div class="status-buttons">
          ${statuses.map(([value, label]) => `
            <button class="btn btn-sm ${entry?.status === value ? 'btn-gold' : 'btn-outline'}"
              type="button" data-book-status="${value}">${label}</button>`).join('')}
        </div>
      </div>
      <div class="book-action-block">
        <h3>${t('Puanın')}</h3>
        <div class="rating-stars" role="group" aria-label="${t('Kitaba puan ver')}">
          ${[1, 2, 3, 4, 5].map((value) => `
            <button class="rating-star ${entry?.rating >= value ? 'is-active' : ''}" type="button"
              data-book-rating="${value}" aria-label="${t('{n} yıldız', { n: value })}">★</button>`).join('')}
          <small>${entry?.rating ? `${entry.rating}/5` : t('Henüz puan vermedin')}</small>
        </div>
      </div>
      <div class="book-action-block">
        <h3>${t('Sayfa takibi')}</h3>
        <form class="page-form" data-page-form data-total="${total}" data-volumes="${volumes}">
          ${volumes > 1 ? `
          <div class="page-form-row">
            <label>${t('Cilt')}
              <select name="volume" aria-label="${t('Cilt numarası')}">
                ${Array.from({ length: volumes }, (_, i) => i + 1).map((n) =>
                  `<option value="${n}" ${n === volume ? 'selected' : ''}>${n}. ${t('cilt')}</option>`).join('')}
              </select>
            </label>
          </div>` : ''}
          <div class="page-form-row">
            <label>${t('Güncel sayfa')}
              <input type="number" name="page" min="0" step="1" inputmode="numeric" value="${page || 0}" aria-label="${t('Okuduğun sayfa')}" />
            </label>
            ${total > 0 ? `<span class="page-form-total">/ ${total} sayfa</span>` : ''}
          </div>
          <div class="shelf-progress"><span style="width:${pct}%"></span></div>
          <p class="page-preview">${esc(preview)}</p>
          <button class="btn btn-gold btn-sm" type="submit">${t('Sayfayı güncelle')}</button>
        </form>
      </div>
      <div class="book-action-block">
        <h3>${t('Listene ekle')}</h3>
        <form class="book-list-form" data-book-list-form>
          <select name="list_id" aria-label="${t('Liste seç')}">
            <option value="">${t('Liste seç')}</option>
            ${listOptions}
          </select>
          <input type="text" name="name" placeholder="${t('Yeni liste adı (isteğe bağlı)')}" maxlength="80" />
          <button class="btn btn-outline btn-sm" type="submit">${t('Ekle')}</button>
        </form>
      </div>
      <div class="book-action-block">
        <h3>${t('İnceleme yaz')}</h3>
        <form class="review-form" data-review-form>
          <textarea name="text" rows="3" placeholder="${t('Bu kitap hakkında ne düşünüyorsun?')}" required></textarea>
          <div class="review-form-foot">
            <label>${t('Puan')}
              <select name="rating">
                <option value="5">★★★★★</option><option value="4">★★★★</option>
                <option value="3">★★★</option><option value="2">★★</option><option value="1">★</option>
              </select>
            </label>
            <button class="btn btn-gold btn-sm" type="submit">${t('İncelemeyi yayınla')}</button>
          </div>
        </form>
      </div>
    </div>`;
}

function similarBooksHTML(book) {
  const pool = (state.data.books || []).filter((b) => Number(b.id) !== Number(book.id));
  if (!pool.length) return '';
  const score = (other) => {
    let points = 0;
    if (book.genre && other.genre && String(book.genre) === String(other.genre)) points += 3;
    if (book.category && other.category && String(book.category) === String(other.category)) points += 2;
    if (book.author && other.author && String(book.author) === String(other.author)) points += 4;
    return points;
  };
  const matches = pool
    .map((other) => ({ other, points: score(other) }))
    .filter((entry) => entry.points > 0)
    .sort((a, b) => b.points - a.points)
    .slice(0, 4)
    .map((entry) => entry.other);
  if (!matches.length) return '';
  return `
    <section class="similar-books">
      <h3>${t('Benzer Kitaplar')}</h3>
      <div class="similar-books-grid">${matches.map((item) => `
        <button class="similar-book" type="button" data-global-book="${esc(item.id)}">
          ${bookCoverHTML(item)}
          <strong>${esc(item.title)}</strong><small>${esc(item.author || '')}</small>
        </button>`).join('')}</div>
    </section>`;
}

let bookPostsRequest = 0;

function bookPostHTML(post) {
  const isReview = post.type === 'review';
  const author = post.author || {};
  return `
    <article class="book-post-card ${isReview ? 'is-review' : 'is-quote'}">
      <div class="book-post-head">
        <button class="book-post-author" type="button" data-profile-user="${esc(author.id || 0)}">
          ${avatarHTML(author, 'avatar--sm')}
          <span><strong>${esc(author.display_name || author.name || t('Misafir'))}</strong>
          <small>${isReview ? t('İnceleme') : t('Alıntı')} · ${esc(timeAgo(post.created_at))}</small></span>
        </button>
        ${isReview ? starRow(Number(post.rating) || 0) : ''}
      </div>
      <p>${esc(post.text)}</p>
      <div class="book-post-foot">
        <span>♥ ${Number(post.likes) || 0}</span>
        <span>★ ${Number(post.favorites) || 0}</span>
      </div>
    </article>`;
}

function renderBookPosts(posts) {
  const host = $('#book-posts');
  if (!host) return;
  const count = $('#book-post-count');
  if (count) count.textContent = t('{n} paylaşım', { n: posts.length });
  host.innerHTML = posts.length
    ? `<div class="book-post-list">${posts.map(bookPostHTML).join('')}</div>`
    : `<div class="overview-card"><p>${t('Bu kitap için henüz paylaşım yok.')}</p></div>`;
}

async function loadBookPosts(book) {
  const host = $('#book-posts');
  if (!host) return;
  const request = ++bookPostsRequest;
  host.innerHTML = `<div class="overview-card"><p>${t('Paylaşımlar yükleniyor...')}</p></div>`;
  try {
    const result = await api('/api/posts/by-book?book=' + encodeURIComponent(book?.title || ''));
    if (request === bookPostsRequest) renderBookPosts(result.posts || []);
  } catch (error) {
    if (request === bookPostsRequest) {
      host.innerHTML = `<div class="overview-card"><p>${t('Paylaşımlar yüklenemedi.')}</p></div>`;
    }
  }
}

function openBook(key) {
  const scholarBooks = (state.data.scholars || []).flatMap((s) =>
    [...(s.bookItems || []), ...(s.recommendedItems || [])]);
  const book = state.data.books.find((b) => String(b.id) === String(key))
    || scholarBooks.find((b) => String(b.id) === String(key))
    || state.data.books.find((b) => b.title === key)
    || scholarBooks.find((b) => b.title === key)
    || { title: String(key), author: t('Bilinmeyen yazar'), category: t('Genel'), cover: '' };
  const title = book.title;
  state.currentBook = title;
  state.bookDetailBook = book;
  $('#book-detail-title').textContent = title;
  $('#book-hero').innerHTML = `
    <div class="book-hero-detail">
      ${bookCoverHTML(book)}
      <div>
        <h2>${esc(title)}</h2>
        <p>${esc(book.author || t('Yazar bilinmiyor'))} · ${esc(book.category)}${book.year ? ` · ${book.year}` : ''}</p>
        <div>
          <span class="read-status">${t('{n} müzakere sorusu', { n: (state.data.debates[title] || []).length })}</span>
          <span class="read-status" id="book-post-count">${t('{n} paylaşım', { n: 0 })}</span>
        </div>
      </div>
    </div>`;
  const reviews = state.data.posts.filter((p) => p.book === title && p.type === 'review');
  $('#book-overview').innerHTML = `
    <div class="overview-card">
      <h3>${t('Hakkında')}</h3>
      <p>${esc(turkishBookDescription(book))}</p>
      ${book.genre ? `<p><strong>${t('Tür:')}</strong> ${esc(book.genre)}</p>` : ''}
      ${book.year ? `<p><strong>${t('İlk yayın:')}</strong> ${book.year}</p>` : ''}
      ${book.publisher ? `<p><strong>${t('Yayınevi:')}</strong> ${esc(book.publisher)}</p>` : ''}
      ${book.page_count ? `<p><strong>${t('Sayfa sayısı:')}</strong> ${book.page_count}</p>` : ''}
      ${book.rating ? `<p><strong>${t('Veritabanı puanı:')}</strong> ★ ${Number(book.rating).toFixed(1)} / 5${book.rating_count ? ` · ${book.rating_count}${t(' değerlendirme')}` : ''}</p>` : ''}
      ${reviews.length ? `<p><strong>${t('Okur puanı:')}</strong> ★ ${(reviews.reduce((n, r) => n + r.rating, 0) / reviews.length).toFixed(1)} / 5 · ${reviews.length}${t(' inceleme')}</p>` : ''}
      <button class="btn btn-outline btn-sm" type="button" data-open-debate>${t('Müzakere Masası’na git →')}</button>
      ${bookActionHTML(book)}
      ${state.user?.is_admin && book.id ? `<div class="admin-actions"><button class="admin-delete" type="button" data-hide-book="${esc(book.id)}">${t('Kataloğu gizle')}</button></div>` : ''}
      ${similarBooksHTML(book)}
    </div>`;
  $$('.detail-tab').forEach((t) => {
    const active = t.dataset.detailTab === 'overview';
    t.classList.toggle('is-active', active);
    t.setAttribute('aria-selected', String(active));
  });
  $('#book-overview').hidden = false;
  $('#book-debate').hidden = true;
  $('#book-posts').hidden = true;
  renderDebates();
  loadBookPosts(book);
  switchView('book');
}

function renderReviews() {
  const list = myReviews();
  $('#review-list').innerHTML = list.length ? list.map((p) => `
    <article class="journal-card">
      <span class="note-visibility" data-v="public">${t('★ İNCELEME')}</span>
      <h3>${esc(p.book)}</h3>
      <p>${esc(p.text)}</p>
      <small class="curriculum-meta">${esc(p.writer || t('Yazar bilinmiyor'))} · ${esc(timeAgo(p.created_at))}</small>
      ${ownActionsHTML('post', p.id)}
    </article>`).join('') : `<p class="rail-muted">${t('Henüz inceleme paylaşmadın.')}</p>`;
}

function shelfProgress(entry) {
  const total = Math.max(0, Number(entry?.page_count) || 0);
  const volumes = Math.max(1, Number(entry?.volume_count) || 1);
  const volume = Math.max(1, Math.min(volumes, Number(entry?.volume) || 1));
  const page = Math.max(0, Number(entry?.page) || 0);
  const readPages = (volume - 1) * total + page;
  const pct = total > 0
    ? Math.min(100, Math.round((readPages / (total * volumes)) * 100))
    : Math.min(100, Number(entry?.progress) || 0);
  return { total, page, pct, volumes, volume };
}

function pageProgressText({ total, page, pct, volumes = 1, volume = 1 }) {
  const parts = [];
  if (volumes > 1) parts.push(t('{volume}. cilt / {volumes} cilt', { volume, volumes }));
  if (total > 0) parts.push(t('{page} / {total} sayfa', { page, total }), `%${pct}`);
  else if (page > 0) parts.push(t('{page} sayfa', { page }));
  return parts.join(' · ');
}

function shelfBook(entry) {
  const progress = shelfProgress(entry);
  const { pct } = progress;
  let extra;
  let bar = '';
  if (entry.status === 'reading') {
    extra = pageProgressText(progress) || `${t('%{n} tamamlandı', { n: pct })}`;
    bar = `<div class="shelf-progress"><span style="width:${pct}%"></span></div>`;
  } else if (entry.status === 'finished') {
    extra = `★ ${entry.rating || 5}/5 ${t('okudun')}`;
  } else if (entry.status === 'abandoned') {
    extra = t('Yarım bıraktın');
  } else {
    extra = t('Okuyacağım');
  }
  return `
    <div class="shelf-book" data-detail-book="${esc(entry.book_id)}" title="${t('Kitap sayfasını aç')}">
      ${bookCoverHTML(entry)}
      <strong>${esc(entry.title)}</strong><small>${esc(entry.author)}</small>
      <span class="page-badge note-visibility">${extra}</span>
      ${(entry.curricula || []).length ? `<small class="shelf-curriculum">${esc(entry.curricula.join(' · '))}</small>` : ''}
      ${bar}
    </div>`;
}

function listCardHTML(list) {
  const id = Number(list.id);
  const renameLabel = esc(t('Listeyi yeniden adlandır'));
  const deleteLabel = esc(t('Listeyi sil'));
  return `<article class="list-card" data-list-id="${esc(list.id)}">
    <div class="list-card-head">
      <h3>${esc(list.name)} <small>${list.books.length} ${t('kitap')}</small></h3>
      <div class="list-card-actions">
        <button type="button" data-rename-list="${esc(list.id)}" aria-label="${renameLabel}" title="${renameLabel}">✎</button>
        <button type="button" data-delete-list="${esc(list.id)}" aria-label="${deleteLabel}" title="${deleteLabel}">×</button>
      </div>
    </div>
    ${state.renamingListId === id ? `<form class="list-rename-form" data-list-rename="${esc(list.id)}">
      <input type="text" name="name" value="${esc(list.name)}" maxlength="80" aria-label="${esc(t('Yeni liste adı'))}" required />
      <button type="submit">${esc(t('Kaydet'))}</button>
    </form>` : ''}
    ${list.books.length ? `<div class="shelf-grid">${list.books.map((b) => `
      <div class="shelf-book" data-detail-book="${esc(b.id)}" title="${t('Kitap sayfasını aç')}">
        ${bookCoverHTML(b)}
        <strong>${esc(b.title)}</strong><small>${esc(b.author)}</small>
      </div>`).join('')}</div>`
      : `<p class="rail-muted">${t('Bu liste henüz boş.')}</p>`}
  </article>`;
}

function listCreateFormHTML() {
  const label = esc(t('Liste adı'));
  return `<form class="list-create-form" data-list-create>
    <input type="text" class="list-name-input" placeholder="${label}" aria-label="${label}" maxlength="80" />
    <button class="btn btn-gold btn-sm" type="submit">${esc(t('Yeni liste'))}</button>
  </form>`;
}

function renderShelfPanel() {
  if (state.shelfTab === 'lists') {
    const lists = state.data.lists || [];
    $('#shelf-panel').innerHTML = listCreateFormHTML() + (lists.length
      ? `<div class="profile-lists">${lists.map(listCardHTML).join('')}</div>`
      : `<div class="shelf-empty">${esc(t('Henüz listen yok. Yukarıdan yeni bir liste oluşturabilirsin.'))}</div>`);
    return;
  }
  const list = state.data.shelf.filter((s) => s.status === state.shelfTab);
  $('#shelf-panel').innerHTML = list.length
    ? `<div class="shelf-grid">${list.map(shelfBook).join('')}</div>`
    : `<div class="shelf-empty">${t('Eser bulunamadı. Kütüphaneden ilginizi çeken bir eser seçerek başlayabilirsiniz.')}</div>`;
}

function bookKeyForTitle(title) {
  const found = (state.data?.books || []).find((b) => b.title === title);
  return found ? found.id : title;
}

function interactionCardHTML(post) {
  const key = bookKeyForTitle(post.book);
  const text = String(post.text || '');
  const snippet = text.length > 180 ? `${text.slice(0, 180)}…` : text;
  return `<article class="writing-item interaction-item">
    <button class="public-cover-link" type="button" data-global-book="${esc(key)}" title="${esc(t('Kitap detayını aç'))}">${bookCoverHTML({ title: post.book, cover: post.cover })}</button>
    <div>
      <button class="public-book-link" type="button" data-global-book="${esc(key)}">${esc(post.book)}</button>
      <small>${esc(post.writer || '')} · ${esc(timeAgo(post.created_at))}</small>
      <p class="interaction-text">${esc(snippet)}</p>
    </div>
    <span class="interaction-kind">${post.type === 'quote' ? t('Alıntı') : t('İnceleme')}</span>
  </article>`;
}

async function loadInteractions() {
  try {
    state.interactions = await api('/api/me/interactions');
    renderInteractions();
  } catch (error) { toast(error.message); }
}

function renderInteractions() {
  const host = $('#interaction-panel');
  if (!host) return;
  const items = (state.interactions?.[state.interactionTab] || []);
  host.innerHTML = items.length
    ? `<div class="writing-list">${items.map(interactionCardHTML).join('')}</div>`
    : `<div class="shelf-empty">${t('Henüz bir etkileşimin yok.')}</div>`;
}

function requestStatusLabel(status) {
  return status === 'approved' ? t('Onaylandı')
    : status === 'rejected' ? t('Reddedildi') : t('İncelemede');
}

function bookRequestCardHTML(request, admin = false) {
  const status = requestStatusLabel(request.status);
  return `<div class="admin-item book-request-item" data-book-request="${esc(request.id)}">
    <div class="admin-item-head">
      <strong>${esc(request.title)} <small class="curriculum-meta">· ${esc(request.author || t('Yazar bilinmiyor'))}</small></strong>
      <span class="status-badge" data-status="${esc(request.status)}">${status}</span>
    </div>
    <div class="book-request-body">
      ${request.cover ? `<img class="book-request-cover" src="${esc(request.cover)}" alt="" />` : ''}
      <div>
        ${request.page_count ? `<p><b>${t('Sayfa:')}</b> ${Number(request.page_count)}</p>` : ''}
        ${request.about ? `<p>${esc(request.about)}</p>` : ''}
        ${request.status === 'approved' && request.book ? `<p><b>${t('Katalog:')}</b> ${esc(request.book.title)}</p>` : ''}
        ${request.status === 'rejected' && request.reason ? `<p><b>${t('Gerekçe:')}</b> ${esc(request.reason)}</p>` : ''}
        <small class="curriculum-meta">${esc(request.requester?.display_name || t('Kullanıcı'))} · ${esc(timeAgo(request.created_at))}</small>
      </div>
    </div>
    ${admin && request.status === 'pending' ? `
      <div class="admin-actions book-request-actions">
        <button class="btn btn-gold btn-sm" type="button" data-book-request-review="approve" data-id="${esc(request.id)}">${t('Onayla ve ekle')}</button>
        <form class="admin-reply" data-book-request-review="reject" data-id="${esc(request.id)}">
          <input type="text" name="reason" placeholder="${t('Ret gerekçesi')}" aria-label="${t('Ret gerekçesi')}" required />
          <button type="submit">${t('Reddet')}</button>
        </form>
      </div>` : ''}
  </div>`;
}

function renderBookRequests() {
  const requests = state.data?.book_requests || [];
  const head = $('#book-requests-head');
  const panel = $('#book-requests-panel');
  if (head) head.hidden = !requests.length;
  if (!panel) return;
  panel.innerHTML = requests.length
    ? `<div class="admin-list">${requests.map((r) => bookRequestCardHTML(r)).join('')}</div>`
    : '';
}

function renderProfileCurricula() {
  const list = (state.data?.curricula || []).filter((c) => c.followed);
  const head = $('#profile-curricula-head');
  const host = $('#profile-curricula');
  if (head) head.hidden = !list.length;
  if (!host) return;
  host.innerHTML = list.length ? `<div class="profile-curricula-grid">${list.map((c) => `
    <button class="profile-curriculum" type="button" data-view="lists">
      <span class="selection-kind">${t('SEÇKİ')}</span>
      <strong>${esc(c.title)} <span class="status-badge" data-status="approved">${t('Takip ediliyor')}</span></strong>
      <small>${esc(t('{done} / {total} eser', {
        done: c.progress?.completed || 0, total: c.progress?.total || 0
      }))} · %${Number(c.progress?.pct) || 0}</small>
      <span class="tesbih-progress" aria-label="%${Number(c.progress?.pct) || 0}">
        ${Array.from({ length: 5 }, (_, i) => `<span class="${i < Math.round((Number(c.progress?.pct) || 0) / 20) ? 'is-on' : ''}"></span>`).join('')}
      </span>
    </button>`).join('')}</div>` : '';
}

const CURRICULUM_STATUS_OPTIONS = [
  ['', 'Durum seç'],
  ['wishlist', 'Okuyacağım'],
  ['reading', 'Okuyorum'],
  ['finished', 'Okudum']
];

function curriculumStepHTML(step, key) {
  const label = esc(step.label || step.raw);
  const linked = Boolean(step.book_id);
  const bookKey = step.book_id || step.raw;
  const status = step.status || '';
  const pageInfo = step.book?.page_count
    ? t('{page} / {total} sayfa', { page: step.page || 0, total: step.book.page_count })
    : '';
  return `<li class="curriculum-step ${status ? `is-${esc(status)}` : ''}">
    <div class="step-line">
      <button class="step-book-link" type="button" data-global-book="${esc(bookKey)}">${label}</button>
      <span class="step-pct">%${Number(step.pct) || 0}</span>
    </div>
    ${linked ? `
      <div class="step-progress-row">
        <select data-curriculum-progress="${esc(key)}" data-step="${esc(step.index)}" aria-label="${label} ${t('okuma durumu')}">
          ${CURRICULUM_STATUS_OPTIONS.map(([value, text]) => `<option value="${value}" ${value === status ? 'selected' : ''}>${t(text)}</option>`).join('')}
        </select>
        ${pageInfo ? `<small>${esc(pageInfo)}</small>` : ''}
      </div>
      <span class="tesbih-progress" aria-label="%${Number(step.pct) || 0}">
        ${Array.from({ length: 5 }, (_, i) => `<span class="${i < Math.round((Number(step.pct) || 0) / 20) ? 'is-on' : ''}"></span>`).join('')}
      </span>`
    : `<div class="step-progress-row"><small>${t('Katalogda bu eser henüz yok.')}</small><button class="btn btn-outline btn-sm btn-compact" type="button" data-book-request-open>${t('Kitap öner')}</button></div>`}
  </li>`;
}

function curriculumCardHTML(c) {
  const progress = c.progress || { completed: 0, total: c.steps?.length || 0, pct: 0 };
  return `<article class="curriculum-card">
    <span class="verified-seal">✓</span>
    <h3>${esc(c.title)}${c.followed ? ` <span class="status-badge" data-status="approved">${t('Takip ediliyor')}</span>` : ''}</h3>
    <p class="curriculum-meta">${esc(c.meta)}</p>
    <div class="curriculum-progress-summary">
      <span>%${Number(progress.pct) || 0}</span>
      <small>${esc(t('{done} / {total} eser okundu', { done: progress.completed || 0, total: progress.total || 0 }))}</small>
    </div>
    <div class="rehber">${avatarHTML({ avatar: c.avatar, name: c.guide })}
      <div><strong>${esc(c.guide)}</strong><small>${esc(c.guideTitle)}</small></div>
      <button class="text-btn" type="button" data-guide="${esc(c.guide)}">${t('Takip et')}</button>
    </div>
    <ul class="step-list">${(c.steps || []).map((step) => curriculumStepHTML(step, c.key)).join('')}</ul>
    <button class="btn ${c.followed ? 'btn-outline' : 'btn-gold'} btn-sm" type="button" data-follow-curr="${esc(c.key)}">${c.followed ? t('✓ Müfredat takip ediliyor') : t('Bu yolu takip et')}</button>
  </article>`;
}

function renderLibraryPanel() {
  const panel = $('#library-panel');
  const uid = state.user?.id ?? 0;
  if (state.libraryTab === 'quotes') {
    const quotes = myPosts().filter((p) => p.type === 'quote');
    panel.innerHTML = quotes.length ? `<div class="postcard-grid">${quotes.map((p) => `
      <div class="mini-postcard"><span class="quote-mark">“</span><p>${esc(p.text)}</p><small>— ${esc(p.book)}, ${esc(p.writer)}</small>${ownActionsHTML('post', p.id)}</div>`).join('')}</div>`
      : `<div class="shelf-empty">${t('Henüz alıntı paylaşmadın.')}</div>`;
  } else {
    const reviews = myPosts().filter((p) => p.type === 'review');
    const debates = [];
    Object.entries(state.data.debates).forEach(([book, questions]) => {
      questions.forEach((q) => {
        if (q.author.id === uid) {
          debates.push(`<div class="writing-item"><strong>❖ ${t('Müzakere Masası')} · ${esc(book)}</strong><p>${esc(q.text)}</p></div>`);
        }
        q.answers.forEach((a) => {
          if (a.author.id === uid) {
            debates.push(`<div class="writing-item"><strong>✧ ${t('Yanıt')} · ${esc(book)}</strong><p>${esc(a.text)}</p></div>`);
          }
        });
      });
    });
    panel.innerHTML = `<div class="writing-list">
      ${debates.join('')}
      ${reviews.map((r) => {
        const book = state.data.books.find((b) => b.title === r.book)
          || (state.data.scholars || []).flatMap((s) => [...(s.bookItems || []), ...(s.recommendedItems || [])])
            .find((b) => b.title === r.book) || { title: r.book, author: r.writer, cover: '' };
        return `<div class="writing-item review-writing">
          ${bookCoverHTML(book)}
          <div>
            <strong>${esc(r.book)}</strong><small>${esc(r.writer || book.author || '')}</small>
            <p>${esc(r.text)}</p><span class="stars">${'★'.repeat(r.rating)}${'☆'.repeat(5 - (r.rating || 0))}</span>
            ${ownActionsHTML('post', r.id)}
          </div>
        </div>`;
      }).join('')}
      ${debates.length || reviews.length ? '' : `<div class="shelf-empty">${t('Henüz inceleme veya müzakere katkın yok.')}</div>`}
    </div>`;
  }
}

function renderAll() {
  renderIdentity();
  renderRightRail();
  renderNotifications();
  renderFeedTabs();
  renderFeed();
  renderLibrary();
  renderHomeBooks();
  renderCircles();
  renderPostcards();
  renderCircleFeed();
  renderCurricula();
  renderMessages();
  renderAuthors();
  renderSupport();
  renderAdmin();
  renderReviews();
  selectJournalTab(state.journalTab);
  renderShelfPanel();
  renderLibraryPanel();
  renderInteractions();
  renderBookRequests();
  renderProfileCurricula();
  renderDiscoverSections();
  renderListsView();
  renderAccess();
  applySettings();
  if (state.currentView === 'home') {
    $$('#bottom-nav .nav-item[data-view]').forEach((n) =>
      n.classList.toggle('is-active', n.dataset.view === 'home'));
  }
  if (state.currentBook && $('.view.is-active')?.id === 'view-book') renderDebates();
  renderIcons();
}

/* ---------------- Keşfet, listeler ve gezinme ---------------- */

function renderDiscoverSections() {
  const posts = [...(state.data?.posts || [])]
    .sort((a, b) => b.created_at - a.created_at)
    .slice(0, 3);
  const latestHost = $('#discover-latest-posts');
  if (latestHost) {
    latestHost.innerHTML = posts.length
      ? posts.map((p) => `
          <article class="writing-item discover-writing">
            <div class="discover-writing-head">
              ${avatarHTML(p.author, 'avatar--small')}
              <div><strong>${esc(p.author.display_name)}</strong><small>${esc(timeAgo(p.created_at))}</small></div>
            </div>
            <p>${esc(p.text)}</p>
            <small>— ${esc(p.book)}${p.writer ? `, ${esc(p.writer)}` : ''}</small>
          </article>`).join('')
      : `<div class="shelf-empty">${t('Henüz bir paylaşım yok.')}</div>`;
  }

  const bookHost = $('#discover-popular-books');
  if (bookHost) {
    const books = [...(state.data?.books || [])]
      .sort((a, b) => (Number(b.rating) || 0) - (Number(a.rating) || 0))
      .slice(0, 6);
    bookHost.innerHTML = books.length
      ? books.map(miniBook).join('')
      : `<p class="rail-muted">${t('Bu alanda henüz kitap yok.')}</p>`;
  }

  const listHost = $('#discover-curated-lists');
  if (listHost) {
    const curricula = (state.data?.curricula || []).slice(0, 3);
    const items = curricula.map((c) => `<article class="selection-card">
      <span class="selection-kind">${t('REHBER SEÇKİSİ')}</span>
      <h3>${esc(c.title)}</h3>
      <p>${esc(c.meta)}</p>
      <small>${esc(c.guide)} · ${t('{n} adım', { n: c.steps?.length || 0 })}</small>
    </article>`);
    listHost.innerHTML = items.length
      ? items.join('')
      : `<div class="shelf-empty">${t('Henüz hazır bir seçki yok.')}</div>`;
  }
}

function renderListsView() {
  const curricula = state.data?.curricula || [];
  const currHost = $('#list-curricula');
  if (currHost) {
    currHost.innerHTML = curricula.length
      ? curricula.map(curriculumCardHTML).join('')
      : `<div class="shelf-empty">${t('Henüz rehber seçkisi yok.')}</div>`;
  }
}

const AUTHOR_LETTERS = 'ABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ'.split('');
const AUTHOR_COLLATOR = new Intl.Collator('tr', { sensitivity: 'base', numeric: true });

function authorFirstLetter(name) {
  const first = String(name || '').trim().charAt(0).toLocaleUpperCase('tr-TR');
  if (!first) return '';
  if (AUTHOR_LETTERS.includes(first)) return first;
  const base = first.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleUpperCase('tr-TR');
  return AUTHOR_LETTERS.includes(base) ? base : '';
}

function compareCatalogAuthors(a, b) {
  const aBucket = authorFirstLetter(a.name) ? 0 : 1;
  const bBucket = authorFirstLetter(b.name) ? 0 : 1;
  if (aBucket !== bBucket) return aBucket - bBucket;
  return AUTHOR_COLLATOR.compare(String(a.name || ''), String(b.name || ''));
}

const compareCatalogNames = (a, b) => compareCatalogAuthors({ name: a }, { name: b });

async function loadCatalogAuthors() {
  if (state.catalogAuthors) { renderAuthors(); return; }
  $('#author-list').innerHTML = `<p class="rail-muted">${t('Yazarlar yükleniyor…')}</p>`;
  try {
    const result = await api('/api/catalog-authors');
    state.catalogAuthors = result.authors || [];
    renderAuthors();
  } catch (error) {
    state.catalogAuthors = null;
    $('#author-list').innerHTML = `<p class="rail-muted">${t('Yazarlar yüklenemedi. Sayfayı yenileyip tekrar dene.')}</p>`;
    toast(error.message);
  }
}

function renderAuthors() {
  const all = [...(state.catalogAuthors || [])].sort(compareCatalogAuthors);
  if (!$('#author-list') || !all.length) return;
  const letterBox = $('#author-letters');
  if (letterBox) {
    letterBox.innerHTML = `
      <button class="chip ${state.authorLetter === 'all' ? 'is-active' : ''}" type="button" data-author-letter="all">${t('Tümü')}</button>
      ${AUTHOR_LETTERS.map((letter) => `<button class="chip ${state.authorLetter === letter ? 'is-active' : ''}" type="button" data-author-letter="${esc(letter)}">${esc(letter)}</button>`).join('')}
      <button class="chip ${state.authorLetter === 'other' ? 'is-active' : ''}" type="button" data-author-letter="other">${t('Diğer')}</button>`;
  }
  const query = ($('#author-search')?.value || '').trim().toLocaleLowerCase('tr-TR');
  const filtered = all.filter((a) => {
    if (state.authorLetter !== 'all') {
      const first = authorFirstLetter(a.name);
      if (state.authorLetter === 'other') {
        if (first) return false;
      } else if (first !== state.authorLetter) return false;
    }
    return !query || (a.name || '').toLocaleLowerCase('tr-TR').includes(query);
  });
  const limit = state.authorLimit || 200;
  const shown = filtered.slice(0, limit);
  $('#author-list').innerHTML = shown.length
    ? shown.map((a) => `
        <button class="author-card ${a.name === state.selectedAuthor ? 'is-active' : ''}" type="button" data-author="${esc(a.name)}">
          <span class="avatar avatar--small avatar--olive">${esc((a.name || '?').charAt(0).toLocaleUpperCase('tr-TR'))}</span>
          <span><strong>${esc(a.name)}</strong><small>${a.count} ${t('kitap')}</small></span>
        </button>`).join('') +
      (filtered.length > limit ? `<button class="btn btn-ghost btn-sm author-more" type="button" id="author-more">${t('Daha fazla yazar göster ({n})', { n: filtered.length - limit })}</button>` : '')
    : `<p class="scholar-empty">${t('Aramana uyan yazar bulunamadı.')}</p>`;
}

function normalizedAuthorKey(value) {
  return String(value || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en')
    .replace(/[^a-z0-9]+/g, ' ').trim();
}

function findScholarForAuthor(name) {
  const key = normalizedAuthorKey(name);
  if (!key) return null;
  const scholars = state.data?.scholars || [];
  const exact = scholars.find((s) => normalizedAuthorKey(s.name) === key);
  if (exact) return exact;
  return scholars.find((s) => {
    const candidates = [s.name, s.full_name].map(normalizedAuthorKey).filter(Boolean);
    return candidates.some((candidate) =>
      candidate.length >= 5 && (candidate.includes(key) || key.includes(candidate)));
  }) || null;
}

async function openCatalogAuthor(name) {
  state.selectedAuthor = name;
  $$('.author-card').forEach((el) => el.classList.toggle('is-active', el.dataset.author === name));
  const host = $('#author-detail');
  if (!host) return;
  host.innerHTML = `<p class="rail-muted">${t('Eserler yükleniyor…')}</p>`;
  try {
    const params = new URLSearchParams({ author: name, author_exact: '1', limit: '24' });
    const result = await api('/api/books?' + params.toString());
    const total = Number(result.total || 0) || (result.books || []).length;
    const titles = (result.books || []).slice(0, 3).map((b) => b.title).join(' · ');
    const scholar = findScholarForAuthor(name);
    const bio = String(scholar?.bio || '').trim()
      || `${t('{n}, İlim Halkası kataloğunda {m} eseriyle kayıtlı bir yazardır.', { n: name, m: total })}${titles ? ` ${t('Eserlerinden bazıları:')} ${titles}.` : ''} ${t('Hayatına dair ayrıntılı bir kayıt henüz eklenmedi.')}`;
    const importance = String(scholar?.importance || scholar?.contribution || '').trim()
      || t('Kataloğundaki {n} eserle okuyucuların farklı alanlarda karşılaşmasına katkı sağlar; eserleriyle okuma kültürünü zenginleştirir.', { n: total });
    const lifeLine = [scholar?.years, scholar?.era, scholar?.full_name].filter(Boolean).join(' · ');
    host.innerHTML = `
      <div class="author-hero">
        <span class="avatar avatar--olive">${esc(name.charAt(0).toLocaleUpperCase('tr-TR'))}</span>
        <div><h2>${esc(name)}</h2>
          <p>${total} ${t('eser')} · ${t('kütüphanede kayıtlı')}</p></div>
      </div>
      <section class="author-about">
        <h3>${t('Hakkında')}</h3>
        ${lifeLine ? `<p class="author-life">${esc(lifeLine)}</p>` : ''}
        <p>${esc(bio)}</p>
        <h3 class="author-subhead">${t('Önemi')}</h3>
        <p>${esc(importance)}</p>
      </section>
      <div class="page-head page-head--small"><div><h3>${t('Eserleri')}</h3><p>${t('Kitap sayfasına dokunarak inceleyebilirsin.')}</p></div></div>
      <div class="author-books">${(result.books || []).length
        ? result.books.map(miniBook).join('')
        : `<p class="rail-muted">${t('Bu yazara ait kitap bulunamadı.')}</p>`}</div>`;
    renderIcons();
  } catch (error) { host.innerHTML = `<p class="rail-muted">${esc(error.message)}</p>`; }
}

function toggleDiscoverGroup(force) {
  const button = $('#discover-group-toggle');
  const subitems = $('#discover-subitems');
  if (!button || !subitems) return;
  const expanded = typeof force === 'boolean' ? force : button.getAttribute('aria-expanded') !== 'true';
  subitems.hidden = !expanded;
  button.setAttribute('aria-expanded', String(expanded));
  const key = expanded ? 'Keşfet alt bölümlerini kapat' : 'Keşfet alt bölümlerini aç';
  button.setAttribute('aria-label', t(key));
  button.setAttribute('title', t(key));
  button.setAttribute('data-i18n-aria', key);
  button.setAttribute('data-i18n-title', key);
}

function switchView(name, skipHistory = false) {
  if (name === 'admin' && !(state.user && state.user.is_admin)) {
    toast(t('Yönetim paneli yalnızca yöneticiye açık'));
    return;
  }
  const memberViews = new Set(['profile', 'journal', 'stats', 'notifications', 'messages', 'settings', 'support']);
  if (!state.user && memberViews.has(name)) {
    requestAccount();
    switchView('home', true);
    return;
  }
  if (!skipHistory && name !== state.currentView && state.currentView) {
    state.viewHistory.push(state.currentView);
    if (state.viewHistory.length > 20) state.viewHistory.shift();
  }
  state.currentView = name;
  const navKey = name === 'circle-feed' ? 'circles' : name;
  $$('.view').forEach((v) => v.classList.toggle('is-active', v.id === 'view-' + name));
  $$('.nav-item[data-view]').forEach((n) => n.classList.toggle('is-active', n.dataset.view === navKey));
  $$('.footer-links [data-view]').forEach((n) => n.classList.toggle('is-active', n.dataset.view === navKey));
  const inDiscoverGroup = ['users', 'authors', 'lists'].includes(name);
  $('#discover-nav-group .nav-item--group')?.classList.toggle('is-parent-active', inDiscoverGroup);
  if (inDiscoverGroup) toggleDiscoverGroup(true);
  const mobileTabMap = {
    'circle-feed': 'circles',
    'notifications': '',
    'book': 'profile',
    'library': 'profile',
    'public-profile': 'discover',
    'curricula': 'discover',
    'journal': 'profile',
    'settings': 'profile',
    'stats': 'profile',
    'search': '',
    'messages': '',
    'support': '',
    'about': '',
    'admin': ''
  };
  const directMobileTabs = ['home', 'discover', 'library', 'authors', 'users', 'lists', 'circles', 'profile'];
  const mobileTab = directMobileTabs.includes(name) ? name : (mobileTabMap[name] ?? '');
  $$('#bottom-nav .nav-item[data-view]').forEach((n) => n.classList.toggle('is-active', n.dataset.view === mobileTab));
  const discoverTabViews = ['discover', 'authors', 'users', 'lists'];
  const mobileTabs = $('#mobile-discover-tabs');
  if (mobileTabs) mobileTabs.hidden = !discoverTabViews.includes(name);
  $$('#mobile-discover-tabs .md-tab').forEach((n) => {
    const active = n.dataset.view === name;
    n.classList.toggle('is-active', active);
    if (active) n.setAttribute('aria-current', 'page');
    else n.removeAttribute('aria-current');
  });
  if (name === 'users') loadRecommendedUsers();
  if (name === 'profile' && !state.interactions) loadInteractions();
  if (name === 'notifications') {
    markNotificationsSeen('all');
    applyStaticI18n($('#view-notifications') || document);
  }
  if (name === 'discover') renderDiscoverSections();
  if (name === 'lists') renderListsView();
  if (name === 'stats') renderStatsView();
  if (name === 'authors') loadCatalogAuthors();
  $('.sidebar').classList.remove('is-open');
  // Görünüm değişiminde yumuşak kaydırma hareketi istenmiyor; anında üste dön.
  const docEl = document.documentElement;
  const previousBehavior = docEl.style.scrollBehavior;
  docEl.style.scrollBehavior = 'auto';
  window.scrollTo(0, 0);
  docEl.style.scrollBehavior = previousBehavior;
}

// Halka akışı dahil tüm alt sayfalardan bir önceki görünüme döner.
function goBackView() {
  const previous = state.viewHistory.pop();
  if (previous && previous !== state.currentView) {
    switchView(previous, true);
    return true;
  }
  if (state.currentView && state.currentView !== 'home') {
    switchView('home', true);
    return true;
  }
  return false;
}

// Android WebView geri tuşu için: açık panel/modalı kapatır, değilse bir önceki sayfaya döner.
// true döndürürse uygulama olayı yuttu demektir, false ise Activity çıkışı yönetir.
function appBack() {
  const panel = $('#notifications-panel');
  if (panel && !panel.hidden) { toggleNotifications(false); return true; }
  const openModal = document.querySelector('.modal-backdrop:not([hidden])');
  if (openModal) {
    const closeButton = openModal.querySelector('.modal-close');
    if (closeButton) closeButton.click();
    else openModal.hidden = true;
    return true;
  }
  const quickSheet = $('#quick-sheet');
  if (quickSheet && !quickSheet.hidden) { closeQuickSheet(); return true; }
  const sidebar = document.querySelector('.sidebar.is-open');
  if (sidebar) { sidebar.classList.remove('is-open'); return true; }
  if (state.currentView === 'search') { closeMobileSearch(); return true; }
  return goBackView();
}
window.appBack = appBack;
window.goBackView = goBackView;

function selectCommunityTab(name) {
  state.communityTab = name;
  $$('[data-community-tab]').forEach((t) => {
    const active = t.dataset.communityTab === name;
    t.classList.toggle('is-active', active);
    t.setAttribute('aria-selected', String(active));
  });
  $('#community-circles').hidden = name !== 'circles';
  $('#community-meclis').hidden = name !== 'meclis';
  const halkaBtn = $('#create-halka-btn');
  const meclisBtn = $('#create-meclis-btn');
  if (halkaBtn) halkaBtn.hidden = name !== 'circles';
  if (meclisBtn) meclisBtn.hidden = name !== 'meclis';
}

function selectJournalTab(name) {
  state.journalTab = name;
  $$('[data-journal-tab]').forEach((t) => {
    const active = t.dataset.journalTab === name;
    t.classList.toggle('is-active', active);
    t.setAttribute('aria-selected', String(active));
  });
  $('#journal-reviews').hidden = name !== 'reviews';
  $('#journal-quotes').hidden = name !== 'quotes';
  const label = $('#journal-primary-label');
  if (label) {
    const key = name === 'quotes' ? 'Yeni alıntı' : 'Yeni inceleme';
    label.textContent = t(key);
    label.setAttribute('data-i18n', key);
  }
}

/* ---------------- Modallar ---------------- */

const modal = $('#quote-modal');
const editModal = $('#edit-modal');
let shareType = 'quote';

function setShareType(type) {
  shareType = type === 'review' ? 'review' : 'quote';
  const isReview = shareType === 'review';
  $$('[data-share-type]').forEach((btn) => {
    const active = btn.dataset.shareType === shareType;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  const label = $('#quote-text-label');
  if (label) {
    label.textContent = t(isReview ? 'İnceleme' : 'Alıntı');
    label.setAttribute('data-i18n', isReview ? 'İnceleme' : 'Alıntı');
  }
  const text = $('#quote-text');
  if (text) {
    const placeholderKey = isReview
      ? 'Kitap hakkındaki düşüncelerini buraya yaz...'
      : 'Altını çizdiğin cümleyi buraya yaz...';
    text.placeholder = t(placeholderKey);
    text.setAttribute('data-i18n-placeholder', placeholderKey);
    text.maxLength = isReview ? 5000 : 1000;
  }
  const ratingField = $('#quote-rating-field');
  if (ratingField) ratingField.hidden = !isReview;
  const publish = $('#publish-quote span');
  if (publish) {
    publish.textContent = t(isReview ? 'İncelemeyi Yayınla' : 'Paylaşımı Yayınla');
    publish.setAttribute('data-i18n', isReview ? 'İncelemeyi Yayınla' : 'Paylaşımı Yayınla');
  }
  renderIcons();
}

function openModal(type = 'quote', groupId = null) {
  if (!requestAccount(t('Paylaşım yapmak'))) return;
  state.shareGroupId = groupId ? Number(groupId) : null;
  const hint = $('#share-group-hint');
  const group = state.shareGroupId
    ? [...(state.data?.groups || []), ...(state.data?.discover_circles || [])]
        .find((g) => g.id === state.shareGroupId)
    : null;
  if (hint) hint.hidden = !group;
  const name = $('#share-group-name');
  if (name) name.textContent = group?.name || '';
  setShareType(type);
  modal.hidden = false;
  $('#quote-book').focus();
}
function closeModal() {
  modal.hidden = true;
  state.shareGroupId = null;
  const hint = $('#share-group-hint');
  if (hint) hint.hidden = true;
}

/* ---------------- Olaylar ---------------- */

// Alt menüde dokunma/odak nedeniyle oluşan kaymayı engelle.
const bottomNavEl = $('#bottom-nav');
bottomNavEl?.addEventListener('mousedown', (e) => {
  if (e.target.closest('button')) e.preventDefault();
});
bottomNavEl?.addEventListener('click', (e) => {
  const navBtn = e.target.closest('button');
  if (navBtn) navBtn.blur();
}, true);

document.addEventListener('click', async (e) => {
  const expandBtn = e.target.closest('[data-expand-text]');
  if (expandBtn) {
    e.preventDefault();
    const box = expandBtn.closest('.text-collapse');
    if (!box) return;
    const short = box.querySelector('.text-collapse-short');
    const full = box.querySelector('.text-collapse-full');
    const open = full.hidden;
    short.hidden = open;
    full.hidden = !open;
    expandBtn.textContent = t(open ? 'daha az göster' : 'devamını oku');
    expandBtn.setAttribute('aria-expanded', String(open));
    return;
  }

  const view = e.target.closest('[data-view]');
  if (view) {
    e.preventDefault();
    if (view.closest('#bottom-nav')) view.blur();
    switchView(view.dataset.view);
    return;
  }

  const openFollowListBtn = e.target.closest('[data-open-follow-list]');
  if (openFollowListBtn) {
    e.preventDefault();
    openFollowList(openFollowListBtn.dataset.userId, openFollowListBtn.dataset.openFollowList);
    return;
  }

  const profileLink = e.target.closest('[data-profile-user]');
  if (profileLink) {
    e.preventDefault();
    openPublicProfile(Number(profileLink.dataset.profileUser));
    return;
  }

  const globalBook = e.target.closest('[data-global-book]');
  if (globalBook) {
    e.preventDefault();
    hideGlobalSearch();
    const key = String(globalBook.dataset.globalBook || '');
    openBook(/^\d+$/.test(key) ? Number(key) : key);
    return;
  }
  const globalUser = e.target.closest('[data-global-user]');
  if (globalUser) {
    e.preventDefault();
    hideGlobalSearch();
    openPublicProfile(Number(globalUser.dataset.globalUser));
    return;
  }
  const mobileAuthor = e.target.closest('[data-mobile-author]');
  if (mobileAuthor) {
    e.preventDefault();
    switchView('authors');
    openCatalogAuthor(mobileAuthor.dataset.mobileAuthor);
    return;
  }
  const globalCircle = e.target.closest('[data-global-circle]');
  if (globalCircle) {
    e.preventDefault();
    hideGlobalSearch();
    state.activeCircleId = Number(globalCircle.dataset.globalCircle);
    switchView('circle-feed');
    renderCircleFeed();
    return;
  }

  const followUser = e.target.closest('[data-follow-user]');
  if (followUser) {
    e.preventDefault();
    toggleFollowUser(Number(followUser.dataset.followUser), followUser);
    return;
  }

  const openCircle = e.target.closest('[data-open-circle]');
  if (openCircle) {
    state.activeCircleId = Number(openCircle.dataset.openCircle);
    switchView('circle-feed');
    renderCircleFeed();
    return;
  }

  const circleBack = e.target.closest('#circle-feed-back');
  if (circleBack) {
    state.activeCircleId = null;
    switchView('circles');
    return;
  }

  const circleShare = e.target.closest('#circle-feed-share');
  if (circleShare) {
    openModal('quote', circleShare.dataset.openShareCircle || state.activeCircleId);
    return;
  }

  const openGroup = e.target.closest('[data-open-group]');
  if (openGroup) {
    state.activeGroupId = Number(openGroup.dataset.openGroup);
    switchView('messages');
    renderMessages();
    return;
  }

  const join = e.target.closest('[data-join-halka]');
  if (join) {
    try {
      await api(`/api/groups/${join.dataset.joinHalka}/join`, { method: 'POST', body: {} });
      await refresh();
      toast(t('Halkaya katıldın ◈'));
    } catch (error) { toast(error.message); }
    return;
  }

  const leave = e.target.closest('[data-leave-halka]');
  if (leave) {
    try {
      await api(`/api/groups/${leave.dataset.leaveHalka}/leave`, { method: 'POST', body: {} });
      if (state.activeGroupId === Number(leave.dataset.leaveHalka)) state.activeGroupId = null;
      if (state.activeCircleId === Number(leave.dataset.leaveHalka)) {
        state.activeCircleId = null;
        switchView('circles');
      }
      await refresh();
      toast(t('Halkadan ayrıldın'));
    } catch (error) { toast(error.message); }
    return;
  }

  const openHalka = e.target.closest('[data-open-halka]');
  if (openHalka) { openHalkaModal(); return; }
  const openMeclis = e.target.closest('[data-open-meclis]');
  if (openMeclis) { openMeclisModal(); return; }
});

$$('.auth-tab').forEach((tab) => tab.addEventListener('click', () => authTab(tab.dataset.authTab)));

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await api('/api/login', {
      method: 'POST',
      body: { email: $('#login-email').value.trim(), password: $('#login-password').value }
    });
    clearGuestReminder();
    await initAppSession();
    toast(t('Tekrar hoş geldin ✧'));
  } catch (error) { showAuthError('login', error.message); }
});

$('#register-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const result = await api('/api/register', {
      method: 'POST',
      body: {
        email: $('#register-email').value.trim(),
        username: $('#register-username').value.trim(),
        display_name: $('#register-name').value.trim(),
        password: $('#register-password').value
      }
    });
    clearGuestReminder();
    if (!result.user) {
      // E-posta doğrulaması açık: oturum açılmadı, önce bağlantı onaylanmalı.
      $('#register-error').hidden = true;
      authTab('login');
      $('#login-email').value = $('#register-email').value.trim();
      toast(result.message || t('E-postana doğrulama bağlantısı gönderildi.'));
      return;
    }
    await initAppSession();
    toast(t('Halkaya hoş geldin ✧'));
  } catch (error) { showAuthError('register', error.message); }
});

$('#resend-verification-link')?.addEventListener('click', async () => {
  const email = $('#login-email').value.trim();
  if (!email) { showAuthError('login', t('Doğrulama için e-posta adresini gir')); return; }
  try {
    const result = await api('/api/resend-verification', { method: 'POST', body: { email } });
    $('#auth-error').hidden = true;
    toast(result.message || t('Doğrulama bağlantısı yeniden gönderildi.'));
  } catch (error) { showAuthError('login', error.message); }
});

async function logout() {
  try { await api('/api/logout', { method: 'POST', body: {} }); } catch { /* yoksay */ }
  state.data = null;
  state.user = null;
  state.lastPostPollTs = 0;
  state.serverTime = 0;
  state.activeGroupId = null;
  state.activeCircleId = null;
  state.shareGroupId = null;
  phoneNotifiedIds = null;
  state.viewHistory = [];
  state.currentView = 'home';
  rememberGuestVisit();
  await initAppSession();
  toast(t('Çıkış yaptın. Keşfetmeye devam edebilirsin.'));
}
$('#logout-btn').addEventListener('click', logout);
$('#top-logout-btn').addEventListener('click', logout);

/* ---------------- Şifremi unuttum / sıfırlama ---------------- */

const passwordModal = $('#password-modal');
let activeResetToken = null;

function openForgotStage() {
  activeResetToken = null;
  $('#forgot-stage').hidden = false;
  $('#reset-stage').hidden = true;
  $('#password-modal-title').textContent = t('Şifremi unuttum');
  $('#password-modal-desc').textContent = t('E-posta adresine şifre sıfırlama bağlantısı göndereceğiz.');
  $('#forgot-error').hidden = true;
  $('#forgot-dev-hint').hidden = true;
  $('#forgot-email').value = $('#login-email')?.value.trim() || '';
  passwordModal.hidden = false;
  $('#forgot-email').focus();
}

function openResetStage(token) {
  activeResetToken = token;
  $('#forgot-stage').hidden = true;
  $('#reset-stage').hidden = false;
  $('#password-modal-title').textContent = t('Yeni şifre belirle');
  $('#password-modal-desc').textContent = t('Yeni şifreni iki kez yazarak onayla.');
  $('#reset-error').hidden = true;
  $('#reset-password').value = '';
  $('#reset-confirm').value = '';
  passwordModal.hidden = false;
  $('#reset-password').focus();
}

function closePasswordModal() {
  passwordModal.hidden = true;
  activeResetToken = null;
  if (location.search.includes('reset=')) stripQueryParams(['reset']);
}

function showPasswordError(selector, message) {
  const el = $(selector);
  el.textContent = message;
  el.hidden = false;
}

document.addEventListener('click', (e) => {
  const toggle = e.target.closest?.('[data-password-toggle]');
  if (!toggle) return;
  const input = document.getElementById(toggle.dataset.passwordToggle);
  if (!input) return;
  let start = null;
  let end = null;
  try { start = input.selectionStart; end = input.selectionEnd; } catch {}
  input.type = input.type === 'password' ? 'text' : 'password';
  syncPasswordToggles();
  input.focus();
  if (start !== null) {
    try { input.setSelectionRange(start, end); } catch {}
  }
});

$('#forgot-password-link')?.addEventListener('click', openForgotStage);
$$('[data-close-password-modal]').forEach((el) => el.addEventListener('click', closePasswordModal));
passwordModal?.addEventListener('click', (e) => { if (e.target === passwordModal) closePasswordModal(); });

$('#forgot-submit')?.addEventListener('click', async () => {
  const email = $('#forgot-email').value.trim();
  if (!email) { showPasswordError('#forgot-error', t('E-posta adresini gir')); return; }
  try {
    const result = await api('/api/forgot-password', { method: 'POST', body: { email } });
    $('#forgot-error').hidden = true;
    const hint = $('#forgot-dev-hint');
    if (hint) hint.hidden = true;
    toast(result.message || t('E-posta kayıtlıysa sıfırlama bağlantısı gönderildi.'));
    closePasswordModal();
  } catch (error) { showPasswordError('#forgot-error', error.message); }
});

$('#reset-submit')?.addEventListener('click', async () => {
  const password = $('#reset-password').value;
  const confirm = $('#reset-confirm').value;
  if (password.length < 8) { showPasswordError('#reset-error', t('Yeni şifre en az 8 karakter olmalı')); return; }
  if (password !== confirm) { showPasswordError('#reset-error', t('Şifreler eşleşmiyor')); return; }
  if (!activeResetToken) { showPasswordError('#reset-error', t('Sıfırlama bağlantısı geçersiz')); return; }
  try {
    const result = await api('/api/reset-password', {
      method: 'POST', body: { token: activeResetToken, password }
    });
    closePasswordModal();
    showAuth(true);
    authTab('login');
    $('#login-email').value = '';
    $('#login-password').value = '';
    toast(result.message);
  } catch (error) { showPasswordError('#reset-error', error.message); }
});

$('.side-user')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); switchView('profile'); }
});

/* Üst marka: her ekranda ana sayfaya götürür. */
$('#top-brand')?.addEventListener('click', (e) => {
  e.preventDefault();
  e.stopPropagation();
  e.currentTarget.blur();
  switchView('home');
});

/* Görünür Menü butonu: mobilde sol menü çekmecesini açar/kapatır. */
$('#menu-btn')?.addEventListener('click', (e) => {
  e.preventDefault();
  e.stopPropagation();
  $('.sidebar').classList.toggle('is-open');
});

/* Keşfet satırı sayfayı açar; yanındaki ok alt kategorileri açıp kapatır. */
$('#discover-group-toggle')?.addEventListener('click', (e) => {
  e.preventDefault();
  e.stopPropagation();
  toggleDiscoverGroup();
});

/* Menü: masaüstünde daraltılabilir, tablette açılır şerit */
function syncSidebarMode() {
  const shell = $('.app-shell');
  const width = window.innerWidth;
  if (width <= 640) shell.classList.remove('nav-mini');
  else if (width <= 900) shell.classList.add('nav-mini');
  else shell.classList.remove('nav-mini');
}
syncSidebarMode();
window.addEventListener('resize', syncSidebarMode);
$('#sidebar-toggle').addEventListener('click', () => {
  const shell = $('.app-shell');
  if (window.innerWidth <= 640) {
    $('.sidebar').classList.remove('is-open');
  } else {
    shell.classList.toggle('nav-mini');
    const toggle = $('#sidebar-toggle');
    toggle.innerHTML = `<i data-lucide="${shell.classList.contains('nav-mini') ? 'panel-left-open' : 'panel-left-close'}"></i>`;
    renderIcons();
  }
});

$('.feed-controls .tabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.tab[data-tab]');
  if (!tab) return;
  $$('.feed-controls .tabs .tab[data-tab]').forEach((t) => {
    t.classList.remove('is-active'); t.setAttribute('aria-selected', 'false');
  });
  tab.classList.add('is-active');
  tab.setAttribute('aria-selected', 'true');
  state.tab = tab.dataset.tab;
  renderFeed();
});

$$('[data-community-tab]').forEach((tab) => tab.addEventListener('click', () => selectCommunityTab(tab.dataset.communityTab)));
$$('[data-journal-tab]').forEach((tab) => tab.addEventListener('click', () => selectJournalTab(tab.dataset.journalTab)));

function handleNotificationClick(e) {
  const item = e.target.closest('[data-notification-view]');
  if (!item) return;
  toggleNotifications(false);
  const actorId = Number(item.dataset.notificationActor || 0);
  if (item.dataset.notificationKind === 'follow' && actorId) {
    openPublicProfile(actorId);
    return;
  }
  switchView(item.dataset.notificationView);
  const target = item.dataset.notificationTarget;
  if (target) {
    const el = document.getElementById(target);
    if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), 120);
  }
}

$('#notifications-btn')?.addEventListener('click', (e) => {
  e.stopPropagation();
  e.preventDefault();
  e.currentTarget.blur();
  toggleNotifications();
});
$('#notifications-close')?.addEventListener('click', () => toggleNotifications(false));
$('#notifications-mark-read')?.addEventListener('click', () => markNotificationsSeen('announcement'));
$('#notifications-view-mark-read')?.addEventListener('click', () => markNotificationsSeen('all'));
$('#notifications-list')?.addEventListener('click', handleNotificationClick);
$('#notifications-view-list')?.addEventListener('click', handleNotificationClick);

document.addEventListener('click', (e) => {
  if (!e.target.closest('#notifications-panel') && !e.target.closest('#notifications-btn')) {
    toggleNotifications(false);
  }
});

$$('.chip[data-filter]').forEach((chip) => chip.addEventListener('click', () => {
  $$('.chip[data-filter]').forEach((c) => c.classList.remove('is-active'));
  chip.classList.add('is-active');
  state.filter = chip.dataset.filter;
  renderFeed();
}));

$('#sort-select').addEventListener('change', (e) => { state.sort = e.target.value; renderFeed(); });
$('#refresh-feed').addEventListener('click', async () => { await refresh(); toast(t('Akış güncellendi')); });

/* Akış etkileşimleri */
['#feed', '#circle-feed'].forEach((sel) => $(sel)?.addEventListener('click', async (e) => {
  const btn = e.target.closest('.action, .follow-btn, .comment-meta button');
  if (!btn) return;
  const postEl = btn.closest('.post');
  const post = findPost(postEl.dataset.id);
  if (!post) return;
  const act = btn.dataset.act;
  if (!state.user && ['like', 'favorite', 'follow', 'comment-like'].includes(act)) {
    const label = act === 'follow' ? t('Takip etmek')
      : act === 'like' ? t('Beğenmek')
        : act === 'favorite' ? t('Kaydetmek') : t('Yorumu beğenmek');
    requestAccount(label);
    return;
  }

  if (act === 'like' || act === 'favorite') {
    const result = await api(`/api/posts/${post.id}/${act}`, { method: 'POST', body: {} });
    post.liked = result.active && act === 'like' ? true : act === 'like' ? false : post.liked;
    if (act === 'like') post.liked = result.active;
    else post.favorited = result.active;
    const countKey = act === 'like' ? 'likes' : 'favorites';
    post[countKey] = result.count;
    btn.classList.toggle('is-on', result.active);
    btn.setAttribute('aria-pressed', String(result.active));
    $('[data-count="' + countKey + '"]', postEl).textContent = result.count;
    return;
  }

  if (act === 'comment') {
    if (state.openComments.has(post.id)) state.openComments.delete(post.id);
    else state.openComments.add(post.id);
    const panel = $('.comments', postEl);
    panel.classList.toggle('is-open');
    btn.setAttribute('aria-expanded', String(panel.classList.contains('is-open')));
    if (panel.classList.contains('is-open')) $('.comment-form input', panel).focus();
    return;
  }

  if (act === 'share') {
    const text = post.type === 'quote'
      ? `“${post.text}” — ${post.book}, ${post.writer}`
      : `${post.book} — ${post.writer} | ${post.rating}/5: ${post.text}`;
    if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
    toast(t('Paylaşım için kopyalandı · Kartpostal hazır ✧'));
    return;
  }

  if (act === 'follow') {
    await api(`/api/follows/${btn.dataset.user}`, { method: 'POST', body: {} });
    post.followed = true;
    btn.remove();
    toast(`${post.author.display_name}${t(' artık takip ediliyor')}`);
    return;
  }

  if (act === 'comment-like') {
    const comment = findComment(post, btn.dataset.comment);
    const result = await api(`/api/comments/${btn.dataset.comment}/like`, { method: 'POST', body: {} });
    comment.liked = result.active;
    comment.likes = result.count;
    btn.textContent = `${result.active ? '♥' : '♡'} ${result.count}`;
    return;
  }

  if (act === 'reply') {
    const form = $(`.reply-form[data-reply-to="${btn.dataset.comment}"]`, postEl);
    form.hidden = !form.hidden;
    if (!form.hidden) $('input', form).focus();
  }
}));

['#feed', '#circle-feed'].forEach((sel) => $(sel)?.addEventListener('submit', async (e) => {
  const feedRoot = e.currentTarget;
  const form = e.target.closest('.comment-form, .reply-form');
  if (!form) return;
  e.preventDefault();
  if (!requestAccount(t('Yorum yazmak'))) return;
  const input = $('input', form);
  const text = input.value.trim();
  if (!text) return;
  const body = { text };
  if (form.classList.contains('reply-form')) body.reply_to = Number(form.dataset.replyTo);
  await api(`/api/posts/${form.dataset.post}/comments`, { method: 'POST', body });
  const postId = Number(form.dataset.post);
  state.openComments.add(postId);
  await refresh();
  toast(form.classList.contains('reply-form') ? t('Cevabın eklendi') : t('Yorumun eklendi'));
  const el = $(`.post[data-id="${postId}"]`, feedRoot);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}));

/* Alıntı / kartpostal modalı */
$('#share-quote-btn')?.addEventListener('click', () => openModal('quote'));

const quickSheet = $('#quick-sheet');
function openQuickSheet() {
  if (!requestAccount(t('Paylaşım yapmak'))) return;
  if (quickSheet) quickSheet.hidden = false;
}
function closeQuickSheet() { if (quickSheet) quickSheet.hidden = true; }
$('#quick-add-btn')?.addEventListener('click', openQuickSheet);

/* Beğeni ve ortadaki ekleme düğmesinde mürekkep yayılması. */
document.addEventListener('pointerdown', (e) => {
  const likeBtn = e.target.closest('[data-act="like"]');
  const quickBtn = e.target.closest('#quick-add-btn');
  const host = likeBtn || quickBtn?.querySelector('.nav-add-circle');
  if (!host) return;
  const rect = host.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const size = Math.max(rect.width, rect.height) * 2.2;
  const ripple = document.createElement('span');
  ripple.className = 'ink-ripple';
  ripple.style.width = ripple.style.height = size + 'px';
  ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
  ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
  host.appendChild(ripple);
  ripple.addEventListener('animationend', () => ripple.remove(), { once: true });
});

$('#quick-sheet-close')?.addEventListener('click', closeQuickSheet);
quickSheet?.addEventListener('click', (e) => { if (e.target === quickSheet) closeQuickSheet(); });
$('#quick-add-quote')?.addEventListener('click', () => { closeQuickSheet(); openModal('quote'); });
$('#quick-add-circle')?.addEventListener('click', () => { closeQuickSheet(); switchView('circles'); openHalkaModal(); });
$('#journal-primary-btn')?.addEventListener('click', () => openModal(state.journalTab === 'quotes' ? 'quote' : 'review'));
$$('[data-share-type]').forEach((btn) => btn.addEventListener('click', () => setShareType(btn.dataset.shareType)));
$$('[data-close-modal]').forEach((el) => el.addEventListener('click', closeModal));
modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

function closeEditModal() {
  editModal.hidden = true;
  state.editing = null;
}

function openEditModal(kind, id) {
  const item = (state.data.posts || []).find((entry) => Number(entry.id) === Number(id));
  if (!item) return;
  const isReview = item.type === 'review';
  state.editing = { kind, id: Number(id) };
  $('#edit-modal-title').textContent = isReview ? t('İncelemeni düzenle') : t('Alıntını düzenle');
  $('#edit-writer-field').hidden = false;
  $('#edit-rating-field').hidden = !isReview;
  $('#edit-book').value = item.book || '';
  $('#edit-writer').value = item.writer || '';
  $('#edit-rating').value = String(item.rating || 5);
  $('#edit-text').maxLength = isReview ? 5000 : 1000;
  $('#edit-text').value = item.text || '';
  editModal.hidden = false;
  $('#edit-text').focus();
}

async function deleteOwnItem(kind, id) {
  const item = myPosts().find((entry) => Number(entry.id) === Number(id));
  const label = item?.type === 'review' ? t('bu incelemeyi') : t('bu alıntıyı');
  if (!window.confirm(`${label}${t(' kalıcı olarak silinsin mi?')}`)) return;
  try {
    await api(`/api/posts/${id}/delete`, { method: 'POST', body: {} });
    await refresh();
    toast(t('Silindi.'));
  } catch (error) { toast(error.message); }
}

$$('[data-close-edit-modal]').forEach((el) => el.addEventListener('click', closeEditModal));
editModal.addEventListener('click', (e) => { if (e.target === editModal) closeEditModal(); });

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-own-action]');
  if (!btn) return;
  e.preventDefault();
  const { ownAction, ownKind, id } = btn.dataset;
  if (ownAction === 'edit') openEditModal(ownKind, id);
  else if (ownAction === 'delete') await deleteOwnItem(ownKind, id);
});

$('#edit-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const editing = state.editing;
  if (!editing) return;
  const text = $('#edit-text').value.trim();
  const book = $('#edit-book').value.trim();
  if (!text || !book) { toast(t('Kitap ve metin alanlarını doldur ♡')); return; }
  const editedPost = (state.data.posts || []).find((p) => Number(p.id) === Number(editing.id));
  if (editedPost?.type === 'quote' && text.length > 1000) {
    toast(t('Bir alıntı en fazla 1000 karakter olabilir.'));
    return;
  }
  try {
    await api(`/api/posts/${editing.id}/update`, {
      method: 'POST',
      body: {
        book,
        writer: $('#edit-writer').value.trim(),
        text,
        rating: Number($('#edit-rating').value) || 5
      }
    });
    closeEditModal();
    await refresh();
    toast(t('Değişiklikler kaydedildi ✎'));
  } catch (error) { toast(error.message); }
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  closeModal();
  editModal.hidden = true;
  toggleNotifications(false);
  if (!passwordModal.hidden) closePasswordModal();
  $('#book-search-form').hidden = true;
});

$('#publish-quote').addEventListener('click', async () => {
  const book = $('#quote-book').value.trim();
  const writer = $('#quote-author').value.trim();
  const text = $('#quote-text').value.trim();
  const isReview = shareType === 'review';
  if (!text || !book) {
    toast(isReview ? t('Kitap ve inceleme alanlarını doldur ♡') : t('Kitap ve alıntı alanlarını doldur ♡'));
    return;
  }
  if (!isReview && text.length > 1000) {
    toast(t('Bir alıntı en fazla 1000 karakter olabilir.'));
    return;
  }
  const body = {
    type: shareType,
    book,
    writer: writer || t('Bilinmeyen yazar'),
    text
  };
  if (state.shareGroupId) body.group_id = state.shareGroupId;
  if (isReview) {
    body.rating = Number($('#quote-rating').value) || 5;
    body.status = 'Okudum';
  }
  const postedToCircle = Boolean(state.shareGroupId);
  await api('/api/posts', { method: 'POST', body });
  ['#quote-book', '#quote-author', '#quote-text'].forEach((s) => { $(s).value = ''; });
  closeModal();
  if (!postedToCircle) {
    state.tab = 'following'; state.filter = 'all'; state.sort = 'recent';
    $('.tab[data-tab="following"]').click();
    $('#sort-select').value = 'recent';
  }
  await refresh();
  toast(postedToCircle
    ? t('Paylaşımın halkada yayında ✧')
    : isReview ? t('İncelemen akışta yayında ✎') : t('Kartpostalın akışta yayında ✧'));
});

/* Kitap detayı ve müzakere */
['#book-grid', '#home-islamic-books', '#home-classic-books'].forEach((sel) => {
  $(sel).addEventListener('click', (e) => {
    const more = e.target.closest('[data-load-more]');
    if (more) { loadCatalog(false); return; }
    const card = e.target.closest('[data-book]');
    if (card) openBook(card.dataset.book);
  });
});
['#shelf-panel', '#library-panel'].forEach((sel) => $(sel).addEventListener('click', (e) => {
  const card = e.target.closest('[data-book]');
  if (card) openBook(card.dataset.book);
}));

$$('.detail-tab').forEach((tab) => tab.addEventListener('click', () => {
  $$('.detail-tab').forEach((t) => { t.classList.remove('is-active'); t.setAttribute('aria-selected', 'false'); });
  tab.classList.add('is-active');
  tab.setAttribute('aria-selected', 'true');
  const tabKey = tab.dataset.detailTab;
  $('#book-overview').hidden = tabKey !== 'overview';
  $('#book-debate').hidden = tabKey !== 'debate';
  $('#book-posts').hidden = tabKey !== 'posts';
}));

$('#book-overview').addEventListener('click', (e) => {
  if (e.target.closest('[data-open-debate]')) {
    $('.detail-tab[data-detail-tab="debate"]').click();
  }
});

function openHideBookModal(bookId, title) {
  state.pendingHideBookId = Number(bookId);
  $('#hide-book-modal-desc').textContent = t('“{n}” tüm kullanıcıların kataloğundan kaldırılacak. Şeffaf bir gerekçe yaz.', { n: title || t('Bu kitap') });
  $('#hide-book-reason').value = '';
  $('#hide-book-error').textContent = '';
  $('#hide-book-modal').hidden = false;
  $('#hide-book-reason').focus();
}
function closeHideBookModal() {
  $('#hide-book-modal').hidden = true;
  state.pendingHideBookId = null;
}

document.addEventListener('click', (e) => {
  const hide = e.target.closest('[data-hide-book]');
  if (!hide) return;
  e.preventDefault();
  const card = hide.closest('.admin-hide-result, .book-detail, .admin-item');
  const title = card?.querySelector('strong')?.textContent?.split('·')[0]?.trim()
    || $('#book-detail-title')?.textContent || t('Bu kitap');
  openHideBookModal(hide.dataset.hideBook, title);
});

$('#hide-book-confirm')?.addEventListener('click', async () => {
  const id = state.pendingHideBookId;
  const reason = $('#hide-book-reason')?.value?.trim();
  if (!id || !reason) {
    $('#hide-book-error').textContent = t('Gizleme gerekçesi zorunludur.');
    return;
  }
  try {
    await api(`/api/admin/books/${id}/moderate`, {
      method: 'POST', body: { hidden: true, reason }
    });
    closeHideBookModal();
    toast(t('Kitap katalogdan gizlendi'));
    await refresh();
    await loadCatalog(true);
    if (state.currentView === 'admin') {
      renderAdmin();
      renderAccess();
      await runAdminBookHideSearch($('#admin-hide-book-input')?.value || '');
    } else if (state.currentView === 'book') {
      switchView('library');
    }
  } catch (error) {
    $('#hide-book-error').textContent = error.message || t('Kitap gizlenemedi.');
  }
});
$$('[data-close-hide-book-modal]').forEach((el) => el.addEventListener('click', closeHideBookModal));
$('#hide-book-modal')?.addEventListener('click', (e) => {
  if (e.target === $('#hide-book-modal')) closeHideBookModal();
});

$('#book-debate').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-answer-toggle]');
  if (!btn) return;
  const form = $(`[data-answer-form="${btn.dataset.answerToggle}"]`);
  form.hidden = !form.hidden;
  if (!form.hidden) $('input', form).focus();
});

$('#book-debate').addEventListener('submit', async (e) => {
  const form = e.target.closest('[data-debate-form], [data-answer-form]');
  if (!form) return;
  e.preventDefault();
  const input = $('input', form);
  const text = input.value.trim();
  if (!text) return;
  if (form.dataset.debateForm !== undefined) {
    await api('/api/debates', { method: 'POST', body: { book_title: state.currentBook, text } });
    toast(t('Sorun müzakere masasında yayında ❖'));
  } else {
    await api(`/api/debates/${form.dataset.answerForm}/answers`, { method: 'POST', body: { text } });
    toast(t('Yanıtın eklendi'));
  }
  await refresh();
  renderDebates();
});

/* Kitap detayı: durum, puan, liste ve inceleme */
async function updateBookDetail(action) {
  const book = state.bookDetailBook;
  if (!book?.id) return;
  try {
    await action();
    await refresh();
    openBook(book.id);
  } catch (error) {
    toast(error.message);
  }
}

$('#book-overview').addEventListener('click', (e) => {
  const statusBtn = e.target.closest('[data-book-status]');
  if (statusBtn) {
    const status = statusBtn.dataset.bookStatus;
    const labels = {
      reading: t('Okuyorsun'), finished: t('Okudun'), wishlist: t('Okuma listene eklendi'), abandoned: t('Yarım bıraktın')
    };
    updateBookDetail(async () => {
      await api('/api/shelf', { method: 'POST', body: { book_id: state.bookDetailBook.id, status } });
      toast(labels[status] || t('Raf güncellendi ✓'));
    });
    return;
  }
  const star = e.target.closest('[data-book-rating]');
  if (star) {
    const rating = Number(star.dataset.bookRating);
    const status = shelfEntryFor(state.bookDetailBook)?.status || 'reading';
    updateBookDetail(async () => {
      await api('/api/shelf', {
        method: 'POST',
        body: { book_id: state.bookDetailBook.id, status, rating }
      });
      toast(`${t('{n} yıldız verdin ★', { n: rating })}`);
    });
  }
});

function updatePagePreview(form) {
  const total = Number(form.dataset.total) || 0;
  const volumes = Math.max(1, Number(form.dataset.volumes) || 1);
  const volume = Math.max(1, Math.min(volumes, Number(form.querySelector('[name="volume"]')?.value) || 1));
  const page = Math.max(0, Number(form.querySelector('[name="page"]')?.value) || 0);
  const progress = shelfProgress({ page, page_count: total, volume, volume_count: volumes });
  const bar = form.querySelector('.shelf-progress span');
  if (bar) bar.style.width = `${progress.pct}%`;
  const preview = form.querySelector('.page-preview');
  if (preview) preview.textContent = pageProgressText(progress)
    || t('Bu kitabın toplam sayfası katalogda henüz yok');
}

$('#book-overview').addEventListener('input', (e) => {
  const form = e.target.closest('[data-page-form]');
  if (form) updatePagePreview(form);
});
$('#book-overview').addEventListener('change', (e) => {
  const form = e.target.closest('[data-page-form]');
  if (form) updatePagePreview(form);
});

$('#book-overview').addEventListener('submit', (e) => {
  const listForm = e.target.closest('[data-book-list-form]');
  if (listForm) {
    e.preventDefault();
    const data = new FormData(listForm);
    const listId = String(data.get('list_id') || '');
    const name = String(data.get('name') || '').trim();
    if (!listId && !name) { toast(t('Bir liste seç veya yeni liste adı yaz')); return; }
    updateBookDetail(async () => {
      await api('/api/lists/add', {
        method: 'POST',
        body: { book_id: state.bookDetailBook.id, list_id: Number(listId) || 0, name }
      });
      toast(name ? `“${name}${t(' listesine eklendi ✧')}` : t('Listeye eklendi ✧'));
    });
    return;
  }
  const pageForm = e.target.closest('[data-page-form]');
  if (pageForm) {
    e.preventDefault();
    const data = new FormData(pageForm);
    const page = Number(data.get('page'));
    const volume = Number(data.get('volume')) || 1;
    const total = Number(pageForm.dataset.total) || 0;
    if (!Number.isFinite(page) || page < 0) { toast(t('Geçerli bir sayfa gir')); return; }
    if (total > 0 && page > total) { toast(t('Güncel sayfa toplam sayfadan fazla olamaz')); return; }
    const status = shelfEntryFor(state.bookDetailBook)?.status || 'reading';
    const progress = shelfProgress({
      page, page_count: total, volume, volume_count: Number(pageForm.dataset.volumes) || 1
    });
    updateBookDetail(async () => {
      await api('/api/shelf', {
        method: 'POST',
        body: { book_id: state.bookDetailBook.id, status, page, volume }
      });
      toast(pageProgressText(progress)
        ? `${t('Sayfa güncellendi · ')}${pageProgressText(progress)}`
        : t('Sayfa güncellendi ✓'));
    });
    return;
  }
  const reviewForm = e.target.closest('[data-review-form]');
  if (reviewForm) {
    e.preventDefault();
    const data = new FormData(reviewForm);
    const text = String(data.get('text') || '').trim();
    if (!text) return;
    const book = state.bookDetailBook;
    updateBookDetail(async () => {
      await api('/api/posts', {
        method: 'POST',
        body: {
          type: 'review', book: book.title, writer: book.author || '', text,
          rating: Number(data.get('rating')) || 5, status: 'Okudum',
          cover: String(book.cover || '').slice(0, 30)
        }
      });
      toast(t('İncelemen yayınlandı ve profiline eklendi ✎'));
    });
  }
});

/* Kitap filtreleri mobilde düğmeyle açılır; seçili durum aynı yerde görünür. */
$('#filter-toggle')?.addEventListener('click', () => {
  const filters = $('#book-filters');
  const button = $('#filter-toggle');
  if (!filters || !button) return;
  const open = filters.classList.toggle('is-open');
  button.setAttribute('aria-expanded', String(open));
  if (open) filters.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

$('#circle-feed-back')?.addEventListener('click', () => goBackView());

/* Kitap arama, rafa ekleme ve kullanıcı kitap önerisi */
$('#catalog-search-toggle')?.addEventListener('click', () => {
  const form = $('#book-search-form');
  form.hidden = !form.hidden;
  if (!form.hidden) $('#book-search-input').focus();
});

$('#book-add-btn')?.addEventListener('click', openBookRequestModal);

$('#book-search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = $('#book-search-input').value.trim();
  if (q.length < 2) { toast(t('En az 2 karakter yaz')); return; }
  const submit = $('#book-search-form button[type="submit"]');
  submit.disabled = true;
  submit.textContent = t('Aranıyor…');
  try {
    const result = await api('/api/books/search?q=' + encodeURIComponent(q));
    for (const found of result.books) {
      const index = state.data.books.findIndex((b) => b.id === found.id);
      if (index >= 0) state.data.books[index] = found;
      else state.data.books.push(found);
    }
    await loadCatalog(true);
    const box = $('#book-search-results');
    box.hidden = false;
    box.innerHTML = result.books.length
      ? `<p class="curriculum-meta">${t('{n} kitap bulundu.', { n: result.books.length })}</p>` +
        result.books.map((b) => {
          const meta = bookMetaHTML(b);
          const turkishInfo = turkishBookDescription(b);
          const snippet = `${turkishInfo.slice(0, 130)}${turkishInfo.length > 130 ? '…' : ''}`;
          return `
          <div class="search-result-row">
            ${bookCoverHTML(b)}
            <div>
              <strong>${esc(b.title)}</strong>
              <small>${esc(b.author || t('Yazar bilinmiyor'))}${meta ? ` · ${meta}` : ''}</small>
              ${snippet ? `<small>${esc(snippet)}</small>` : ''}
            </div>
            <div class="search-result-actions">
              <button class="search-detail-btn" type="button" data-detail-book="${b.id}">${t('Hakkında')}</button>
              <button class="shelf-add-btn" type="button" data-add-book="${b.id}">${t('Rafa ekle')}</button>
            </div>
          </div>`;
        }).join('')
      : `<p class="rail-muted">${t('Sonuç bulunamadı.')}</p>`;
  } catch (error) {
    toast(error.message);
  } finally {
    submit.disabled = false;
    submit.textContent = t('Ara');
  }
});

$('#book-search-results').addEventListener('click', async (e) => {
  const detail = e.target.closest('[data-detail-book]');
  if (detail) {
    openBook(detail.dataset.detailBook);
    return;
  }
  const btn = e.target.closest('[data-add-book]');
  if (!btn) return;
  await api('/api/shelf', { method: 'POST', body: { book_id: Number(btn.dataset.addBook), status: 'wishlist' } });
  await refresh();
  toast(t('Kitap okuma listene eklendi ✧'));
});

/* Müfredatlar */
async function handleCurriculumClick(e) {
  const follow = e.target.closest('[data-follow-curr]');
  if (follow) {
    const result = await api(`/api/curricula/${follow.dataset.followCurr}/follow`, { method: 'POST', body: {} });
    await refresh();
    toast(result.active ? t('Müfredat okuma planına eklendi ☷') : t('Müfredat takibi bırakıldı'));
    return;
  }
  const guide = e.target.closest('[data-guide]');
  if (guide) { guide.textContent = t('✓ Takiptesin'); toast(`${guide.dataset.guide}${t(' artık takip ediliyor')}`); }
}

$('#curriculum-grid').addEventListener('click', handleCurriculumClick);
$('#list-curricula')?.addEventListener('click', handleCurriculumClick);

async function handleCurriculumProgress(e) {
  const select = e.target.closest('[data-curriculum-progress]');
  if (!select) return;
  const status = select.value;
  if (!status) return;
  try {
    await api(`/api/curricula/${encodeURIComponent(select.dataset.curriculumProgress)}/steps/${select.dataset.step}/progress`, {
      method: 'POST', body: { status }
    });
    await refresh();
    toast(t('Okuma durumu güncellendi ✧'));
  } catch (error) {
    toast(error.message);
    await refresh();
  }
}
$('#curriculum-grid').addEventListener('change', handleCurriculumProgress);
$('#list-curricula')?.addEventListener('change', handleCurriculumProgress);

$('#shelf-panel').addEventListener('click', (e) => {
  const card = e.target.closest('[data-detail-book]');
  if (card) openBook(card.dataset.detailBook);
});

/* Profil sekmeleri */
$$('[data-profile-tab]').forEach((tab) => tab.addEventListener('click', () => {
  $$('[data-profile-tab]').forEach((t) => { t.classList.remove('is-active'); t.setAttribute('aria-selected', 'false'); });
  tab.classList.add('is-active');
  tab.setAttribute('aria-selected', 'true');
  state.shelfTab = tab.dataset.profileTab;
  renderShelfPanel();
}));

$$('[data-interaction-tab]').forEach((tab) => tab.addEventListener('click', () => {
  $$('[data-interaction-tab]').forEach((t) => { t.classList.remove('is-active'); t.setAttribute('aria-selected', 'false'); });
  tab.classList.add('is-active');
  tab.setAttribute('aria-selected', 'true');
  state.interactionTab = tab.dataset.interactionTab;
  loadInteractions();
}));

$$('[data-library-tab]').forEach((tab) => tab.addEventListener('click', () => {
  $$('[data-library-tab]').forEach((t) => { t.classList.remove('is-active'); t.setAttribute('aria-selected', 'false'); });
  tab.classList.add('is-active');
  tab.setAttribute('aria-selected', 'true');
  state.libraryTab = tab.dataset.libraryTab;
  renderLibraryPanel();
}));

/* Liste oluşturma: profil ve Listelerim */
document.addEventListener('submit', async (e) => {
  const form = e.target.closest('[data-list-create]');
  if (!form) return;
  e.preventDefault();
  const input = form.querySelector('.list-name-input');
  const name = input?.value.trim();
  if (!name) {
    toast(t('Liste adı gerekli'));
    input?.focus();
    return;
  }
  try {
    await api('/api/lists', { method: 'POST', body: { name } });
    if (input) input.value = '';
    await refresh();
    toast(t('“{name}” listesi oluşturuldu ✧', { name }));
  } catch (error) {
    toast(error.message);
  }
});

/* Liste yeniden adlandırma ve silme */
document.addEventListener('click', (e) => {
  const rename = e.target.closest('[data-rename-list]');
  if (rename) {
    e.preventDefault();
    state.renamingListId = Number(rename.dataset.renameList);
    renderShelfPanel();
    return;
  }
  const remove = e.target.closest('[data-delete-list]');
  if (remove) {
    e.preventDefault();
    deleteList(Number(remove.dataset.deleteList));
  }
});

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('[data-list-rename]');
  if (!form) return;
  e.preventDefault();
  const name = form.querySelector('input')?.value.trim();
  if (!name) { toast(t('Liste adı gerekli')); return; }
  try {
    await api('/api/lists/update', {
      method: 'POST',
      body: { list_id: Number(form.dataset.listRename), name }
    });
    state.renamingListId = null;
    await refresh();
    toast(t('Liste güncellendi'));
  } catch (error) {
    toast(error.message);
  }
});

async function deleteList(id) {
  const list = (state.data?.lists || []).find((l) => Number(l.id) === id);
  if (!list) return;
  if (!window.confirm(t('“{name}” listesi silinsin mi?', { name: list.name }))) return;
  try {
    await api('/api/lists/delete', { method: 'POST', body: { list_id: id } });
    if (state.renamingListId === id) state.renamingListId = null;
    await refresh();
    toast(t('Liste silindi'));
  } catch (error) {
    toast(error.message);
  }
}

/* Profil düzenleme */
const profileModal = $('#profile-modal');
const profilePhoto = photoUploader({
  input: '#photo-input',
  button: '#photo-upload-btn',
  remove: '#photo-remove-btn',
  preview: '#photo-preview',
  onChange: (value) => { state.profileAvatarImage = value; }
});

function selectAvatar(avatar) {
  state.profileAvatar = avatar;
  $$('.avatar-choice').forEach((btn) => {
    const active = btn.dataset.avatar === avatar;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-checked', String(active));
  });
}

function openProfileModal() {
  if (!requestAccount(t('Profilini düzenlemek'))) return;
  $('#edit-display-name').value = state.user.display_name || '';
  $('#edit-username').value = state.user.username || '';
  $('#edit-bio').value = state.user.bio || '';
  $('#profile-error').textContent = '';
  state.profileAvatarImage = state.user.avatar_image || '';
  profilePhoto.set(state.profileAvatarImage);
  const avatarPreview = $('#photo-preview-avatar');
  if (avatarPreview) avatarPreview.textContent = initial(state.user.display_name);
  selectAvatar(state.user.avatar || 'olive');
  profileModal.hidden = false;
  $('#edit-display-name').focus();
}

function closeProfileModal() { profileModal.hidden = true; }

$('#edit-profile-btn').addEventListener('click', openProfileModal);
$$('[data-close-profile-modal]').forEach((el) => el.addEventListener('click', closeProfileModal));
profileModal.addEventListener('click', (e) => { if (e.target === profileModal) closeProfileModal(); });
$('#avatar-choices').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-avatar]');
  if (btn) selectAvatar(btn.dataset.avatar);
});

$('#profile-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    display_name: $('#edit-display-name').value.trim(),
    username: $('#edit-username').value.trim().toLowerCase(),
    avatar: state.profileAvatar,
    avatar_image: state.profileAvatarImage,
    bio: $('#edit-bio').value.trim()
  };
  if (!body.username.match(/^[a-z0-9_]{3,24}$/)) {
    $('#profile-error').textContent = t('Kullanıcı adı 3–24 karakter; yalnızca küçük harf, rakam ve alt çizgi.');
    return;
  }
  try {
    await api('/api/profile', { method: 'POST', body });
    closeProfileModal();
    await refresh();
    toast(t('Profilin güncellendi ✎'));
  } catch (error) {
    $('#profile-error').textContent = error.message;
  }
});

/* ---------------- Halka, meclis ve özel mesajlar ---------------- */

const halkaModal = $('#halka-modal');
const meclisModal = $('#meclis-modal');
const directModal = $('#direct-modal');
const bookRequestModal = $('#book-request-modal');
const bookRequestCover = photoUploader({
  input: '#book-request-cover-input',
  button: '#book-request-cover-btn',
  remove: '#book-request-cover-remove',
  preview: '#book-request-cover-preview',
  crop: cropBookCover,
  message: 'Kapak görseli hazır ✧'
});

function openBookRequestModal() {
  if (!bookRequestModal) return;
  $('#book-request-title-input').value = '';
  $('#book-request-author').value = '';
  $('#book-request-pages').value = '';
  $('#book-request-about').value = '';
  $('#book-request-error').textContent = '';
  bookRequestCover.set('');
  bookRequestModal.hidden = false;
  $('#book-request-title-input').focus();
}
function closeBookRequestModal() {
  if (bookRequestModal) bookRequestModal.hidden = true;
}
$$('[data-close-book-request-modal]').forEach((el) => el.addEventListener('click', closeBookRequestModal));
bookRequestModal?.addEventListener('click', (e) => {
  if (e.target === bookRequestModal) closeBookRequestModal();
});
document.addEventListener('click', (e) => {
  const open = e.target.closest('[data-book-request-open]');
  if (!open) return;
  e.preventDefault();
  openBookRequestModal();
});

$('#book-request-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const error = $('#book-request-error');
  error.textContent = '';
  const body = {
    title: $('#book-request-title-input').value.trim(),
    author: $('#book-request-author').value.trim(),
    page_count: Number($('#book-request-pages').value || 0),
    about: $('#book-request-about').value.trim(),
    cover: bookRequestCover.get()
  };
  if (body.title.length < 2 || !body.author) {
    error.textContent = t('Kitap adı ve yazarı gerekli');
    return;
  }
  try {
    await api('/api/book-requests', { method: 'POST', body });
    closeBookRequestModal();
    await refresh();
    toast(t('Kitap önerin yönetici incelemesine gönderildi ✧'));
  } catch (err) { error.textContent = err.message || t('Öneri gönderilemedi'); }
});

const halkaPhoto = photoUploader({
  input: '#halka-photo-input',
  button: '#halka-photo-btn',
  remove: '#halka-photo-remove',
  preview: '#halka-photo-preview'
});
const meclisPhoto = photoUploader({
  input: '#meclis-photo-input',
  button: '#meclis-photo-btn',
  remove: '#meclis-photo-remove',
  preview: '#meclis-photo-preview'
});

function openHalkaModal() {
  if (!requestAccount(t('Halka kurmak'))) return;
  $('#halka-name').value = '';
  $('#halka-description').value = '';
  $('#halka-error').textContent = '';
  halkaPhoto.set('');
  halkaModal.hidden = false;
  $('#halka-name').focus();
}
function closeHalkaModal() { halkaModal.hidden = true; }
$$('[data-close-halka-modal]').forEach((el) => el.addEventListener('click', closeHalkaModal));
halkaModal.addEventListener('click', (e) => { if (e.target === halkaModal) closeHalkaModal(); });

$('#halka-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = $('#halka-name').value.trim();
  if (name.length < 3) { $('#halka-error').textContent = t('Halka adı en az 3 karakter olmalı'); return; }
  try {
    const result = await api('/api/groups/halka', {
      method: 'POST',
      body: { name, description: $('#halka-description').value.trim(), avatar_image: halkaPhoto.get() }
    });
    closeHalkaModal();
    await refresh();
    state.activeGroupId = result.id;
    renderMessages();
    switchView('messages');
    toast(t('Halka kuruldu ◈'));
  } catch (error) { $('#halka-error').textContent = error.message; }
});

function renderMeclisMembers(query = '') {
  const targets = state.data.report_targets || [];
  const q = query.trim().toLocaleLowerCase('tr-TR');
  const list = targets.filter((u) =>
    !q || u.display_name.toLocaleLowerCase('tr-TR').includes(q) || u.username.includes(q)
  );
  $('#meclis-members').innerHTML = list.length ? list.map((u) => `
    <label class="member-option">
      <input type="checkbox" value="${u.id}" ${state.meclisMembers.has(u.id) ? 'checked' : ''} />
      ${avatarHTML(u, 'avatar--small')}
      <span><strong>${esc(u.display_name)}</strong><small>@${esc(u.username)}</small></span>
    </label>`).join('') : `<p class="rail-muted">${t('Kullanıcı bulunamadı.')}</p>`;
}

function openMeclisModal() {
  if (!requestAccount(t('Meclis kurmak'))) return;
  $('#meclis-name').value = '';
  $('#meclis-description').value = '';
  $('#meclis-member-search').value = '';
  $('#meclis-error').textContent = '';
  state.meclisMembers = new Set();
  meclisPhoto.set('');
  renderMeclisMembers();
  meclisModal.hidden = false;
  $('#meclis-name').focus();
}
function closeMeclisModal() { meclisModal.hidden = true; }
$$('[data-close-meclis-modal]').forEach((el) => el.addEventListener('click', closeMeclisModal));
meclisModal.addEventListener('click', (e) => { if (e.target === meclisModal) closeMeclisModal(); });
$('#meclis-member-search').addEventListener('input', (e) => renderMeclisMembers(e.target.value));
$('#meclis-members').addEventListener('change', (e) => {
  const box = e.target.closest('input[type="checkbox"]');
  if (!box) return;
  const id = Number(box.value);
  if (box.checked) state.meclisMembers.add(id);
  else state.meclisMembers.delete(id);
});

$('#meclis-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = $('#meclis-name').value.trim();
  if (name.length < 3) { $('#meclis-error').textContent = t('Meclis adı en az 3 karakter olmalı'); return; }
  if (state.meclisMembers.size < 2) {
    $('#meclis-error').textContent = t('Meclis için en az 2 başka üye seçmelisin (toplam 3 kişi)');
    return;
  }
  try {
    const result = await api('/api/groups/meclis', {
      method: 'POST',
      body: {
        name,
        description: $('#meclis-description').value.trim(),
        avatar_image: meclisPhoto.get(),
        member_ids: [...state.meclisMembers]
      }
    });
    closeMeclisModal();
    await refresh();
    state.activeGroupId = result.id;
    renderMessages();
    switchView('messages');
    toast(t('Meclis kuruldu ❖'));
  } catch (error) { $('#meclis-error').textContent = error.message; }
});

function openDirectModal() {
  if (!requestAccount(t('Mesaj göndermek'))) return;
  $('#direct-username').value = '';
  $('#direct-error').textContent = '';
  directModal.hidden = false;
  $('#direct-username').focus();
}
function closeDirectModal() { directModal.hidden = true; }
$('#new-direct-btn').addEventListener('click', openDirectModal);
$$('[data-close-direct-modal]').forEach((el) => el.addEventListener('click', closeDirectModal));
directModal.addEventListener('click', (e) => { if (e.target === directModal) closeDirectModal(); });

$('#direct-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = $('#direct-username').value.trim();
  if (!username) { $('#direct-error').textContent = t('Kullanıcı adı gerekli'); return; }
  try {
    const result = await api('/api/groups/direct', { method: 'POST', body: { username } });
    closeDirectModal();
    await refresh();
    state.activeGroupId = result.id;
    renderMessages();
    toast(t('Sohbet hazır ✆'));
  } catch (error) { $('#direct-error').textContent = error.message; }
});

$('#message-chat-close').addEventListener('click', () => {
  state.activeGroupId = null;
  renderMessages();
});

$('#message-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = $('#message-input');
  const text = input.value.trim();
  if (!text || !state.activeGroupId) return;
  try {
    await api(`/api/groups/${state.activeGroupId}/messages`, { method: 'POST', body: { text } });
    input.value = '';
    await refresh();
    renderMessages();
  } catch (error) { toast(error.message); }
});

$('#new-circle-btn').addEventListener('click', () => { switchView('circles'); openHalkaModal(); });

/* Yazarlar · kütüphane kataloğundan */
$('#author-list')?.addEventListener('click', (e) => {
  const more = e.target.closest('#author-more');
  if (more) {
    state.authorLimit = (state.authorLimit || 200) + 200;
    renderAuthors();
    return;
  }
  const card = e.target.closest('[data-author]');
  if (card) openCatalogAuthor(card.dataset.author);
});

$('#author-letters')?.addEventListener('click', (e) => {
  const chip = e.target.closest('[data-author-letter]');
  if (!chip) return;
  state.authorLetter = chip.dataset.authorLetter;
  state.authorLimit = 200;
  renderAuthors();
});

$('#author-search')?.addEventListener('input', () => {
  state.authorLimit = 200;
  renderAuthors();
});

$('#author-search-btn')?.addEventListener('click', () => {
  state.authorLimit = 200;
  renderAuthors();
});

$('#author-detail')?.addEventListener('click', (e) => {
  const book = e.target.closest('[data-detail-book], [data-book]');
  if (book) openBook(book.dataset.detailBook || book.dataset.book);
});

$('[data-community-jump="meclis"]')?.addEventListener('click', () => selectCommunityTab('meclis'));

/* Şikayet ve talepler */
$('#support-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    kind: $('#support-kind').value,
    subject: $('#support-subject').value.trim(),
    body: $('#support-body').value.trim()
  };
  if (!body.subject || !body.body) { toast(t('Konu ve mesaj alanlarını doldur')); return; }
  try {
    await api('/api/support', { method: 'POST', body });
    $('#support-subject').value = '';
    $('#support-body').value = '';
    await refresh();
    toast(t('Mesajın yöneticiye ulaştı ✉'));
  } catch (error) { toast(error.message); }
});

$('#report-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = $('#report-username').value.trim();
  if (!username) { toast(t('Şikayet edilecek kullanıcı adını yaz')); return; }
  try {
    await api('/api/reports', {
      method: 'POST',
      body: {
        username,
        reason: $('#report-reason').value,
        detail: $('#report-detail').value.trim()
      }
    });
    $('#report-username').value = '';
    $('#report-detail').value = '';
    await refresh();
    toast(t('Kullanıcı şikayetin yönetime iletildi'));
  } catch (error) { toast(error.message); }
});

/* Yönetim paneli */
$('#announcement-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    kind: $('#announcement-kind').value,
    title: $('#announcement-title').value.trim(),
    body: $('#announcement-body').value.trim()
  };
  if (!body.title || !body.body) { toast(t('Duyuru başlığı ve metni gerekli')); return; }
  try {
    await api('/api/admin/announcements', { method: 'POST', body });
    $('#announcement-title').value = '';
    $('#announcement-body').value = '';
    await refresh();
    toast(t('Duyuru yayınlandı ⚑'));
  } catch (error) { toast(error.message); }
});

$('#view-admin').addEventListener('submit', async (e) => {
  const requestReview = e.target.closest('[data-book-request-review="reject"]');
  if (requestReview) {
    e.preventDefault();
    const reason = $('input[name="reason"]', requestReview)?.value.trim() || '';
    if (!reason) return;
    try {
      await api(`/api/admin/book-requests/${requestReview.dataset.id}/review`, {
        method: 'POST', body: { approve: false, reason }
      });
      await refresh();
      toast(t('Kitap önerisi reddedildi'));
    } catch (error) { toast(error.message); }
    return;
  }
  const form = e.target.closest('[data-admin-reply]');
  if (!form) return;
  e.preventDefault();
  const input = $('input', form);
  const text = input.value.trim();
  if (!text) return;
  const plural = form.dataset.adminReply === 'report' ? 'reports' : 'tickets';
  try {
    await api(`/api/admin/${plural}/${form.dataset.id}/reply`, { method: 'POST', body: { body: text } });
    input.value = '';
    await refresh();
    toast(t('Özel yanıtın gönderildi ✉'));
  } catch (error) { toast(error.message); }
});

$('#view-admin').addEventListener('click', async (e) => {
  const announce = e.target.closest('[data-delete-announcement]');
  const close = e.target.closest('[data-admin-close]');
  const comment = e.target.closest('[data-delete-comment]');
  const block = e.target.closest('[data-toggle-block]');
  const restoreBook = e.target.closest('[data-restore-book]');
  const bookRequestApprove = e.target.closest('[data-book-request-review="approve"]');
  let path = '';
  let message = '';
  let body = {};
  if (bookRequestApprove) {
    path = `/api/admin/book-requests/${bookRequestApprove.dataset.id}/review`;
    body = { approve: true };
    message = t('Kitap önerisi onaylandı ve kataloğa eklendi');
  } else if (announce) {
    path = `/api/admin/announcements/${announce.dataset.deleteAnnouncement}/delete`;
    message = t('Duyuru kaldırıldı');
  } else if (close) {
    const plural = close.dataset.adminClose === 'report' ? 'reports' : 'tickets';
    path = `/api/admin/${plural}/${close.dataset.id}/close`;
    message = t('Kayıt kapatıldı');
  } else if (comment) {
    path = `/api/admin/comments/${comment.dataset.deleteComment}/${comment.dataset.id}/delete`;
    message = t('Yorum silindi');
  } else if (block) {
    path = `/api/admin/users/${block.dataset.toggleBlock}/block`;
    message = t('Kullanıcı durumu güncellendi');
  } else if (restoreBook) {
    path = `/api/admin/books/${restoreBook.dataset.restoreBook}/moderate`;
    body = { hidden: false, reason: '' };
    message = t('Kitap kataloğa geri getirildi');
  }
  if (!path) return;
  try {
    await api(path, { method: 'POST', body });
    await refresh();
    if (restoreBook || bookRequestApprove) await loadCatalog(true);
    toast(message);
  } catch (error) { toast(error.message); }
});

/* ---------------- Keşfet, kullanıcı profilleri, davet ve bildirim ---------------- */

const shelfStatusLabels = {
  reading: 'Okuyorum', finished: 'Okudum',
  wishlist: 'Okuyacağım', abandoned: 'Yarım bıraktım'
};

function followButtonHTML(user) {
  const following = Boolean(user.following)
    || (state.data?.follows || []).some((id) => Number(id) === Number(user.id));
  return `<button class="btn ${following ? 'btn-outline' : 'btn-gold'} btn-sm"
    type="button" data-follow-user="${esc(user.id)}">${following ? t('✓ Takip ediliyor') : t('Takip Et')}</button>`;
}

function userCardHTML(user) {
  const interests = (user.shared || user.interests || []).slice(0, 3);
  const chips = interests.length
    ? interests.map((name) => `<span>${esc(name)}</span>`).join('')
    : `<span>${t('İlgi etiketi yok')}</span>`;
  return `
    <article class="user-card">
      ${avatarHTML(user, 'avatar--small')}
      <div class="user-card-body">
        <button class="user-card-name" type="button" data-profile-user="${esc(user.id)}">${esc(user.display_name)}</button>
        <button class="user-card-handle" type="button" data-profile-user="${esc(user.id)}">@${esc(user.username)}</button>
        <div class="user-interest-line">${chips}</div>
      </div>
      ${followButtonHTML(user)}
    </article>`;
}

function renderUserSearchResults(users, query) {
  const box = $('#user-search-results');
  if (!box) return;
  if (String(query || '').trim().length < 2) {
    box.innerHTML = `<p class="rail-muted">${t('Kullanıcı adı veya görünen ad için en az iki karakter yaz.')}</p>`;
    return;
  }
  box.innerHTML = users.length
    ? `<div class="user-card-grid">${users.map(userCardHTML).join('')}</div>`
    : `<p class="rail-muted">${t('Bu aramayla eşleşen kullanıcı bulunamadı.')}</p>`;
}

async function runUserSearch(value) {
  const query = String(value || '').trim();
  const box = $('#user-search-results');
  if (!box) return;
  if (query.length < 2) { renderUserSearchResults([], query); return; }
  try {
    const result = await api(`/api/users/search?q=${encodeURIComponent(query)}`);
    if ($('#user-search-input')?.value.trim() !== query) return;
    state.userSearchUsers = result.users || [];
    renderUserSearchResults(state.userSearchUsers, query);
  } catch (error) {
    box.innerHTML = `<p class="rail-muted">${esc(error.message)}</p>`;
  }
}

function renderRecommendedUsers() {
  const host = $('#recommended-users');
  if (!host) return;
  host.innerHTML = state.recommendedUsers.length
    ? state.recommendedUsers.map(userCardHTML).join('')
    : `<div class="shelf-empty">${t('Şimdilik önerilen kullanıcı yok. Kitaplığın büyüdükçe öneriler de şekillenecek.')}</div>`;
}

async function loadRecommendedUsers() {
  const host = $('#recommended-users');
  if (!host) return;
  host.innerHTML = `<div class="shelf-empty">${t('Öneriler hazırlanıyor...')}</div>`;
  try {
    const result = await api('/api/users/recommended');
    state.recommendedUsers = result.users || [];
    renderRecommendedUsers();
  } catch (error) {
    host.innerHTML = `<div class="shelf-empty">${esc(error.message)}</div>`;
  }
}

function publicWritingHTML(post) {
  const commentCount = (post.comments || []).reduce(
    (n, c) => n + 1 + (c.replies ? c.replies.length : 0), 0
  );
  const bookLink = `<button class="public-book-link" type="button" data-global-book="${esc(post.book)}" title="${esc(t('Kitap detayını aç'))}">${esc(post.book)}</button>`;
  const cover = `<button class="public-cover-link" type="button" data-global-book="${esc(post.book)}" title="${esc(t('Kitap detayını aç'))}">${bookCoverHTML({ title: post.book, cover: post.cover })}</button>`;
  const actions = `
    <div class="writing-actions" data-public-post="${esc(post.id)}">
      <button class="action ${post.liked ? 'is-on' : ''}" type="button" data-act="like" aria-pressed="${Boolean(post.liked)}">
        <span class="ico">♥</span><span data-count="likes">${Number(post.likes) || 0}</span> ${t('Beğeni')}
      </button>
      <button class="action ${post.favorited ? 'is-on' : ''}" type="button" data-act="favorite" aria-pressed="${Boolean(post.favorited)}">
        <span class="ico">★</span><span data-count="favorites">${Number(post.favorites) || 0}</span> ${t('Kaydet')}
      </button>
      <button class="action" type="button" data-act="public-comment" aria-expanded="false">
        <span class="ico">❍</span><span data-count="comments">${commentCount}</span> ${t('Yorum')}
      </button>
      <form class="public-comment-form" data-post="${esc(post.id)}" hidden>
        <input type="text" placeholder="${t('Düşünceni paylaş...')}" aria-label="${t('Yorum yaz')}" />
        <button type="submit">${t('Gönder')}</button>
      </form>
    </div>`;

  if (post.type === 'quote') {
    return `<article class="writing-item public-quote">
      <span class="quote-mark">“</span>
      ${collapsibleTextHTML(post.text, 'public-quote-text')}
      <small>— ${bookLink}, ${esc(post.writer || '')}</small>
      ${actions}
    </article>`;
  }
  return `<article class="writing-item review-writing">
    ${cover}
    <div>
      ${bookLink}<small>${esc(post.writer || '')} · ${esc(timeAgo(post.created_at))}</small>
      ${collapsibleTextHTML(post.text, 'public-review-text')}
      ${post.rating ? starRow(post.rating) : ''}
    </div>
    ${actions}
  </article>`;
}

function renderPublicProfile() {
  const user = state.publicProfile;
  if (!user) return;
  (user.shelf || []).forEach(rememberBook);

  const avatar = $('#public-avatar');
  avatar.innerHTML = user.avatar_image ? `<img src="${esc(user.avatar_image)}" alt="" />` : initial(user.display_name);
  avatar.className = `avatar avatar--xl avatar--${esc(user.avatar || 'olive')}`;
  $('#public-profile-title').textContent = user.display_name;
  const pubFinished = Number(user.stats?.finished_books || 0);
  const pubPosts = (user.posts || []).filter((p) => p.author?.id === user.id).length;
  const pubLevel = pubFinished >= 6 && pubPosts >= 3 ? 3 : pubFinished >= 4 || pubPosts >= 3 ? 2 : pubPosts >= 1 ? 1 : 0;
  $('#public-title-badge').innerHTML = `${levelIconHTML(levels[pubLevel].icon)} ${esc(t(levels[pubLevel].name))}`;
  $('#public-handle-line').textContent = `@${user.username}${user.year ? ` · ${t('{n} yılından beri', { n: user.year })}` : ''}`;

  const bio = $('#public-bio');
  bio.textContent = user.bio || '';
  bio.hidden = !user.bio;

  $('#public-follow-counts').innerHTML = `
    <button type="button" data-open-follow-list="followers" data-user-id="${esc(user.id)}"><b>${Number(user.stats?.followers || 0)}</b>${t(' takipçi')}</button>
    <button type="button" data-open-follow-list="following" data-user-id="${esc(user.id)}"><b>${Number(user.stats?.following || 0)}</b>${t(' takip edilen')}</button>`;

  const followBtn = $('#public-follow-btn');
  followBtn.textContent = user.following ? t('✓ Takip ediliyor') : t('Takip Et');
  followBtn.className = `btn btn-compact ${user.following ? 'btn-outline' : 'btn-gold'}`;
  const canMessage = !user.blocked && Boolean(user.mutual);
  $('#public-message-btn').disabled = !canMessage;
  $('#public-message-btn').title = user.blocked ? t('Bu kullanıcı engelli')
    : canMessage ? '' : t('Mesaj göndermek için karşılıklı takip etmen gerekir');
  $('#public-block-btn').textContent = user.blocked ? t('Engeli kaldır') : t('Engelle');

  $('#public-shelf').innerHTML = (user.shelf || []).length ? user.shelf.map((item) => {
    const progress = shelfProgress(item);
    const { pct } = progress;
    let detail = esc(t(shelfStatusLabels[item.status] || item.status));
    let bar = '';
    if (item.status === 'reading') {
      detail = esc(pageProgressText(progress) || `${t('%{n} tamamlandı', { n: pct })}`);
      bar = `<div class="shelf-progress"><span style="width:${pct}%"></span></div>`;
    }
    return `
    <button class="shelf-book" type="button" data-global-book="${esc(item.book_id)}">
      ${bookCoverHTML(item)}
      <strong>${esc(item.title)}</strong><small>${esc(item.author || '')}</small>
      <span class="page-badge">${detail}</span>
      ${item.rating ? `<span class="stars">${'★'.repeat(Number(item.rating))}${'☆'.repeat(5 - Number(item.rating))}</span>` : ''}
      ${bar}
    </button>`;
  }).join('') : `<div class="shelf-empty">${t('Eser bulunamadı. Kütüphaneden ilginizi çeken bir eser seçerek başlayabilirsiniz.')}</div>`;

  const posts = user.posts || [];
  $('#public-posts').innerHTML = posts.length
    ? posts.map(publicWritingHTML).join('')
    : `<div class="shelf-empty">${t('Henüz inceleme veya alıntı paylaşmadı.')}</div>`;

  renderIcons();
}

function findPublicPost(id) {
  return (state.publicProfile?.posts || []).find((p) => Number(p.id) === Number(id));
}

$('#public-posts')?.addEventListener('click', async (e) => {
  const action = e.target.closest('[data-act]');
  if (!action) return;
  const holder = action.closest('[data-public-post]');
  if (!holder) return;
  e.preventDefault();
  const post = findPublicPost(holder.dataset.publicPost);
  if (!post) return;
  const kind = action.dataset.act;
  if (kind === 'public-comment') {
    const form = holder.querySelector('.public-comment-form');
    if (!form) return;
    form.hidden = !form.hidden;
    action.setAttribute('aria-expanded', String(!form.hidden));
    if (!form.hidden) form.querySelector('input')?.focus();
    return;
  }
  if (kind !== 'like' && kind !== 'favorite') return;
  const endpoint = kind === 'like' ? 'like' : 'favorite';
  const flag = kind === 'like' ? 'liked' : 'favorited';
  try {
    const result = await api(`/api/posts/${post.id}/${endpoint}`, { method: 'POST', body: {} });
    post[flag] = Boolean(result.active);
    post[kind === 'like' ? 'likes' : 'favorites'] = Number(result.count) || 0;
    action.classList.toggle('is-on', post[flag]);
    action.setAttribute('aria-pressed', String(post[flag]));
    const countEl = action.querySelector('[data-count]');
    if (countEl) countEl.textContent = String(post[kind === 'like' ? 'likes' : 'favorites']);
  } catch (error) { toast(error.message); }
});

$('#public-posts')?.addEventListener('submit', async (e) => {
  const form = e.target.closest('.public-comment-form');
  if (!form) return;
  e.preventDefault();
  const input = form.querySelector('input');
  const text = input?.value.trim() || '';
  if (!text) return;
  const post = findPublicPost(form.dataset.post);
  if (!post) return;
  try {
    const result = await api(`/api/posts/${post.id}/comments`, { method: 'POST', body: { text } });
    post.comments = post.comments || [];
    post.comments.push(result.comment);
    const countEl = form.closest('[data-public-post]')?.querySelector('[data-count="comments"]');
    if (countEl) countEl.textContent = String(post.comments.reduce(
      (n, c) => n + 1 + (c.replies ? c.replies.length : 0), 0
    ));
    input.value = '';
    form.hidden = true;
    toast(t('Yorum eklendi ✧'));
  } catch (error) { toast(error.message); }
});

async function openPublicProfile(userId) {
  const id = Number(userId);
  if (!id) return;
  closeFollowListModal();
  if (state.user && id === Number(state.user.id)) {
    switchView('profile');
    return;
  }
  if (state.currentView !== 'public-profile') state.publicReturnView = state.currentView || 'discover';
  try {
    const result = await api(`/api/users/${id}`);
    state.publicProfile = result.user;
    renderPublicProfile();
    switchView('public-profile');
  } catch (error) {
    toast(error.message);
  }
}

function closePublicMoreMenu() {
  $('#public-more-menu').hidden = true;
  $('#public-more-btn').setAttribute('aria-expanded', 'false');
}

function renderOwnFollowCounts() {
  if (!state.user || !state.data?.stats) return;
  const el = $('#follow-counts');
  if (!el) return;
  const stats = state.data.stats;
  el.innerHTML = `
    <button type="button" data-open-follow-list="followers" data-user-id="${esc(state.user.id)}"><b>${stats.followers || 0}</b>${t(' takipçi')}</button>
    <button type="button" data-open-follow-list="following" data-user-id="${esc(state.user.id)}"><b>${stats.following || 0}</b>${t(' takip edilen')}</button>
    <span><b>${stats.circles || 0}</b>${t(' ilim halkası')}</span>`;
}

function applyFollowUI(id, following, followers) {
  const userId = Number(id);
  state.data.follows = state.data.follows || [];
  const index = state.data.follows.findIndex((value) => Number(value) === userId);
  if (following && index < 0) state.data.follows.push(userId);
  if (!following && index >= 0) state.data.follows.splice(index, 1);
  state.data.stats = state.data.stats || {};
  state.data.stats.following = state.data.follows.length;

  if (state.publicProfile && Number(state.publicProfile.id) === userId) {
    state.publicProfile.following = following;
    state.publicProfile.mutual = following && Boolean(state.publicProfile.followed_by);
    if (typeof followers === 'number') state.publicProfile.stats.followers = followers;
    renderPublicProfile();
  }
  if (!(state.publicProfile && Number(state.publicProfile.id) === userId)) {
    renderOwnFollowCounts();
  }
  state.recommendedUsers.forEach((user) => {
    if (Number(user.id) === userId) user.following = following;
  });
  (state.userSearchUsers || []).forEach((user) => {
    if (Number(user.id) === userId) user.following = following;
  });
  $$(`[data-follow-user="${userId}"]`).forEach((button) => {
    button.textContent = following ? t('✓ Takip ediliyor') : t('Takip Et');
    button.className = `btn btn-sm ${following ? 'btn-outline' : 'btn-gold'}`;
  });
}

async function toggleFollowUser(userId) {
  const id = Number(userId);
  if (!id) return;
  if (!requestAccount(t('Takip etmek'))) return;
  try {
    const result = await api('/api/follow', { method: 'POST', body: { user_id: id } });
    applyFollowUI(id, result.following, result.followers);
    toast(result.following ? t('Kullanıcı takip ediliyor ✧') : t('Takip bırakıldı'));
    if (result.following) await openPublicProfile(id);
  } catch (error) { toast(error.message); }
}

function openInviteModal() {
  if (!requestAccount(t('Davet etmek'))) return;
  const link = `${location.origin}/?invite=${encodeURIComponent(state.user?.username || '')}`;
  $('#invite-link').value = link;
  $('#invite-error').textContent = '';
  $('#invite-modal').hidden = false;
  $('#invite-link').focus();
  $('#invite-link').select();
}
function closeInviteModal() { $('#invite-modal').hidden = true; }

async function copyInviteLink() {
  const input = $('#invite-link');
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(input.value);
    } else {
      input.focus();
      input.select();
      if (!document.execCommand('copy')) throw new Error(t('Kopyalanamadı'));
    }
    toast(t('Davet bağlantısı kopyalandı ✉'));
  } catch {
    $('#invite-error').textContent = t('Otomatik kopyalanamadı; bağlantıyı seçip kopyalayabilirsin.');
    input.focus();
    input.select();
  }
}

function openReportUserModal() {
  const user = state.publicProfile;
  if (!user) return;
  $('#report-user-desc').textContent = t('@{n} adlı kullanıcının profilini bildiriyorsun.', { n: user.username });
  $('#report-user-reason').value = t('Uygunsuz içerik');
  $('#report-user-detail').value = '';
  $('#report-user-error').textContent = '';
  $('#report-user-modal').hidden = false;
  closePublicMoreMenu();
}
function closeReportUserModal() { $('#report-user-modal').hidden = true; }

async function toggleBlockUser() {
  const user = state.publicProfile;
  if (!user) return;
  const action = user.blocked ? 'unblock' : 'block';
  try {
    const result = await api('/api/block', { method: 'POST', body: { user_id: user.id, action } });
    user.blocked = result.blocked;
    state.data.blocked = state.data.blocked || [];
    if (result.blocked) {
      state.data.blocked = [...new Set([...state.data.blocked, Number(user.id)])];
      applyFollowUI(user.id, false, Math.max(0, Number(user.stats?.followers || 0) - 1));
    } else {
      state.data.blocked = state.data.blocked.filter((id) => Number(id) !== Number(user.id));
    }
    renderPublicProfile();
    toast(result.blocked ? t('Kullanıcı engellendi') : t('Kullanıcının engeli kaldırıldı'));
  } catch (error) { toast(error.message); }
}

async function messagePublicUser() {
  const user = state.publicProfile;
  if (!user) return;
  if (!user.mutual) {
    toast(t('Mesaj göndermek için karşılıklı takip etmen gerekir'));
    return;
  }
  try {
    const result = await api('/api/groups/direct', {
      method: 'POST', body: { username: user.username }
    });
    await refresh();
    state.activeGroupId = result.id;
    renderMessages();
    switchView('messages');
    toast(t('Sohbet hazır ✆'));
  } catch (error) { toast(error.message); }
}

function closeFollowListModal() {
  const modal = $('#follow-list-modal');
  if (modal) modal.hidden = true;
}

async function openFollowList(userId, mode) {
  const id = Number(userId);
  if (!id || (mode !== 'followers' && mode !== 'following')) return;
  const modal = $('#follow-list-modal');
  const title = $('#follow-list-title');
  const body = $('#follow-list-body');
  if (!modal || !title || !body) return;
  const isFollowers = mode === 'followers';
  state.followListMode = mode;
  title.textContent = isFollowers ? t('Takipçiler') : t('Takip edilenler');
  body.innerHTML = `<p class="rail-muted">${t('Yükleniyor…')}</p>`;
  modal.hidden = false;

  try {
    const result = await api(`/api/users/${id}/${mode}`);
    const users = result.users || [];
    body.innerHTML = users.length
      ? `<div class="user-card-grid">${users.map(userCardHTML).join('')}</div>`
      : `<p class="follow-list-empty">${isFollowers ? t('Henüz takipçi yok.') : t('Henüz takip edilen kimse yok.')}</p>`;
  } catch (error) {
    body.innerHTML = `<p class="follow-list-empty">${esc(error.message || t('Liste yüklenemedi.'))}</p>`;
  }
}

async function runAdminBookHideSearch(query) {
  const box = $('#admin-hide-book-results');
  if (!box) return;
  const q = String(query || '').trim();
  if (q.length < 2) {
    box.innerHTML = `<p class="announcement-empty">${t('Gizlemek istediğin kitabı bulmak için en az iki karakter yaz.')}</p>`;
    return;
  }
  try {
    const result = await api(`/api/books?${new URLSearchParams({ q, limit: '20' }).toString()}`);
    const books = result.books || [];
    box.innerHTML = books.length
      ? books.map((b) => `
        <div class="admin-item admin-hide-result">
          <div>
            <strong>${esc(b.title)} <small class="curriculum-meta">· ${esc(b.author || t('Yazar bilinmiyor'))}</small></strong>
            <p>${esc([b.category, b.genre].filter(Boolean).join(' · ') || t('Katalog kitabı'))}</p>
          </div>
          <div class="admin-actions">
            <button class="admin-delete" type="button" data-hide-book="${esc(b.id)}">${t('Kataloğu gizle')}</button>
          </div>
        </div>`).join('')
      : `<p class="announcement-empty">${t('Bu aramayla eşleşen görünür kitap bulunamadı.')}</p>`;
  } catch (error) {
    box.innerHTML = `<p class="announcement-empty">${esc(error.message || t('Arama yapılamadı.'))}</p>`;
  }
}

/* Üst arama, Keşfet ve herkese açık profil olayları */
const globalSearchInput = $('#global-search');
globalSearchInput?.addEventListener('input', (e) => {
  clearTimeout(state.globalSearchTimer);
  state.globalSearchTimer = setTimeout(() => runGlobalSearch(e.target.value), 220);
});
globalSearchInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { hideGlobalSearch(); e.target.blur(); }
  if (e.key === 'Enter') {
    e.preventDefault();
    clearTimeout(state.globalSearchTimer);
    runGlobalSearch(e.target.value);
  }
});

$('#search-open-btn')?.addEventListener('click', openMobileSearch);
$('#search-close-btn')?.addEventListener('click', closeMobileSearch);
$('#mobile-search-form')?.addEventListener('submit', (e) => {
  e.preventDefault();
  clearTimeout(state.mobileSearchTimer);
  runMobileSearch();
});
const mobileSearchInput = $('#mobile-search-input');
mobileSearchInput?.addEventListener('input', (e) => {
  clearTimeout(state.mobileSearchTimer);
  state.mobileSearchTimer = setTimeout(runMobileSearch, 220);
});
mobileSearchInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.preventDefault(); closeMobileSearch(); }
});
$$('#mobile-search-filters [data-search-filter]').forEach((chip) => {
  chip.addEventListener('click', () => {
    state.mobileSearchFilter = chip.dataset.searchFilter;
    $$('#mobile-search-filters [data-search-filter]').forEach((button) => {
      button.classList.toggle('is-active', button === chip);
    });
    clearTimeout(state.mobileSearchTimer);
    runMobileSearch();
  });
});

$('#user-search-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  await runUserSearch($('#user-search-input').value);
});
$('#user-search-input')?.addEventListener('input', (e) => {
  clearTimeout(state.userSearchTimer);
  state.userSearchTimer = setTimeout(() => runUserSearch(e.target.value), 260);
});

$('#invite-btn')?.addEventListener('click', openInviteModal);
$('#users-invite-btn')?.addEventListener('click', openInviteModal);
$$('[data-close-invite-modal]').forEach((el) => el.addEventListener('click', closeInviteModal));
$('#invite-modal')?.addEventListener('click', (e) => {
  if (e.target === $('#invite-modal')) closeInviteModal();
});
$('#invite-copy')?.addEventListener('click', copyInviteLink);

$$('[data-close-follow-list-modal]').forEach((el) => el.addEventListener('click', closeFollowListModal));
$('#follow-list-modal')?.addEventListener('click', (e) => {
  if (e.target === $('#follow-list-modal')) closeFollowListModal();
});

$('#admin-hide-book-input')?.addEventListener('input', (e) => {
  clearTimeout(state.adminHideBookTimer);
  state.adminHideBookTimer = setTimeout(() => runAdminBookHideSearch(e.target.value), 260);
});
$('#admin-hide-book-form')?.addEventListener('submit', (e) => {
  e.preventDefault();
  clearTimeout(state.adminHideBookTimer);
  runAdminBookHideSearch($('#admin-hide-book-input')?.value);
});

$$('[data-close-report-user-modal]').forEach((el) => el.addEventListener('click', closeReportUserModal));
$('#report-user-modal')?.addEventListener('click', (e) => {
  if (e.target === $('#report-user-modal')) closeReportUserModal();
});
$('#report-user-submit')?.addEventListener('click', async () => {
  const user = state.publicProfile;
  if (!user) return;
  const reason = $('#report-user-reason').value;
  const detail = $('#report-user-detail').value.trim();
  try {
    await api('/api/reports', {
      method: 'POST', body: { reported_id: user.id, reason, detail }
    });
    closeReportUserModal();
    toast(t('Bildirimin yönetime iletildi'));
  } catch (error) { $('#report-user-error').textContent = error.message; }
});

$('#public-back-btn')?.addEventListener('click', () => switchView(state.publicReturnView || 'discover'));
$('#public-message-btn')?.addEventListener('click', messagePublicUser);
$('#public-follow-btn')?.addEventListener('click', () => {
  if (state.publicProfile) toggleFollowUser(state.publicProfile.id);
});
$('#public-more-btn')?.addEventListener('click', (e) => {
  e.stopPropagation();
  const menu = $('#public-more-menu');
  menu.hidden = !menu.hidden;
  $('#public-more-btn').setAttribute('aria-expanded', String(!menu.hidden));
});
$('#public-block-btn')?.addEventListener('click', toggleBlockUser);
$('#public-report-btn')?.addEventListener('click', openReportUserModal);

document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrap')) hideGlobalSearch();
  if (!e.target.closest('.more-wrap')) closePublicMoreMenu();
  const sidebar = $('.sidebar');
  if (sidebar?.classList.contains('is-open')
    && !e.target.closest('.sidebar')
    && !e.target.closest('#menu-btn')
    && !e.target.closest('#top-brand')) {
    sidebar.classList.remove('is-open');
  }
});

/* Ayarlar */
$$('[data-setting]').forEach((el) => el.addEventListener('change', () => {
  const key = el.dataset.setting;
  state.settings[key] = el.type === 'checkbox' ? el.checked : el.value;
  if (key === 'yearlyGoal') {
    const current = String(new Date().getFullYear());
    state.settings.yearlyGoals = {
      ...(state.settings.yearlyGoals || {}),
      [current]: Math.min(100000, Math.floor(yearlyGoal()))
    };
  }
  saveSettings();
  if (key.startsWith('notify')) syncPhoneNotificationPrefs();
  if (key === 'language' && state.data) renderAll();
  if (key === 'yearlyGoal' && state.data) { renderIdentity(); renderStatsView(); }
}));
$('#settings-save')?.addEventListener('click', () => saveSettings());
$('#settings-reset')?.addEventListener('click', () => {
  state.settings = { ...DEFAULT_SETTINGS, yearlyGoals: {} };
  saveSettings(t('Varsayılan tercihler geri yüklendi'));
  if (state.data) renderAll();
});

/* KVKK aydınlatma metni ve kişisel veri dışa aktarma */
const PRIVACY_SECTIONS = [
  {
    title: 'Toplanan veriler',
    body: 'Profil bilgilerin; görünen adın, kullanıcı adın, e-posta adresin, biyografin ve profil fotoğrafındır. Paylaşımların, kitap rafların, okuma durumların, yorumların, beğenilerin, kaydettiklerin, takiplerin, engellerin, halka ve meclis mesajların, bildirimlerin ile destek taleplerin de işlenir.'
  },
  {
    title: 'İşleme amacı',
    body: 'Verilerin uygulamayı sunmak, profilini ve istatistiklerini oluşturmak, paylaşımlarını ve etkileşimlerini göstermek, bildirim göndermek ve güvenliği sağlamak için işlenir.'
  },
  {
    title: 'Paylaşım ve üçüncü taraflar',
    body: 'Reklam ağı, analitik veya harici yazı tipi/ikon kullanılmaz; fontlar ve ikonlar uygulamayla birlikte sunulur. Oturumun yalnızca bu sunucunun HttpOnly çerezinde tutulur. İçerikler bu uygulamanın sunucusunda tutulur; yalnızca katalog kaydında bağlantı bulunan kitap kapakları Open Library / Archive.org üzerinden yüklenir. Üretim modunda e-posta doğrulama ve şifre sıfırlama bağlantıları SMTP sağlayıcısı aracılığıyla gönderilir. Halkalara açık paylaşımlar diğer üyeler tarafından okunabilir.'
  },
  {
    title: 'Saklama süreleri',
    body: 'Oturumlar 30 gün, şifre sıfırlama ve e-posta doğrulama bağlantıları 1 saat geçerlidir. Süresi dolan oturum ve bağlantılar açılışta ve bakım sırasında temizlenir. Akışa sığmayan en eski paylaşımlar akıştan çıkar, silinmez; silme kaydı 90 gün tutulur. Yedekler günlük alınır ve son 7 gün saklanır; hesabını sildikten sonra verilerin yedeklerden en fazla 7 gün içinde kaldırılır. Paylaşımların, yorumların, rafların ve mesajların hesabını silene kadar kalır; hesap silme işlemiyle kaldırılır.'
  },
  {
    title: 'Hakların',
    body: 'Verilerine erişme, düzeltme, silme, dışa aktarma ve işlemeye itiraz etme hakkın vardır. Dışa aktarma ve hesap silme işlemlerini Ayarlar bölümünden yapabilirsin.'
  },
  {
    title: 'Başvuru',
    body: 'Diğer KVKK taleplerin için {contact} adresine yazabilirsin. Veri sorumlusu: {controller}.'
  }
];

const privacyModal = $('#privacy-modal');

function renderPrivacyNotice(notice) {
  const host = $('#privacy-content');
  if (!host) return;
  const vars = { contact: notice?.contact || '', controller: notice?.controller || '' };
  host.innerHTML = PRIVACY_SECTIONS.map((section) => `
    <section class="privacy-section">
      <h3>${t(section.title)}</h3>
      <p>${esc(t(section.body, vars))}</p>
    </section>`).join('');
}

async function openPrivacyModal() {
  if (!privacyModal) return;
  privacyModal.hidden = false;
  const host = $('#privacy-content');
  if (host) host.innerHTML = `<p>${t('Bilgi yükleniyor...')}</p>`;
  try {
    renderPrivacyNotice(await api('/api/privacy'));
  } catch (error) {
    toast(error.message);
  }
}

function closePrivacyModal() {
  if (privacyModal) privacyModal.hidden = true;
}

$('#privacy-open-btn')?.addEventListener('click', openPrivacyModal);
$$('[data-close-privacy]').forEach((el) => el.addEventListener('click', closePrivacyModal));
privacyModal?.addEventListener('click', (e) => {
  if (e.target === privacyModal) closePrivacyModal();
});

async function exportMyData() {
  if (!state.user) {
    requestAccount(t('Verilerimi dışa aktarmak'));
    return;
  }
  const button = $('#export-data-btn');
  if (button) button.disabled = true;
  try {
    const result = await api('/api/me/export');
    const data = result.data || {};
    // Tema, dil ve yazı boyutu gibi cihaz tercihleri tarayıcıda tutulur.
    data.preferences = { ...state.settings };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ilimhalkasi-verilerim-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(t('Verilerin JSON olarak indirildi'));
  } catch (error) {
    toast(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

$('#export-data-btn')?.addEventListener('click', exportMyData);

/* Hesap silme */
const deleteAccountModal = $('#delete-account-modal');

function openDeleteAccountModal() {
  if (!deleteAccountModal || !state.user) return;
  $('#delete-password').value = '';
  $('#delete-confirm').value = '';
  $('#delete-account-error').textContent = '';
  $('#delete-username-hint').textContent = state.user.username;
  deleteAccountModal.hidden = false;
  $('#delete-password').focus();
}

function closeDeleteAccountModal() {
  if (deleteAccountModal) deleteAccountModal.hidden = true;
}

$('#delete-account-btn')?.addEventListener('click', openDeleteAccountModal);
$$('[data-close-delete-account]').forEach((el) => el.addEventListener('click', closeDeleteAccountModal));
deleteAccountModal?.addEventListener('click', (e) => { if (e.target === deleteAccountModal) closeDeleteAccountModal(); });

$('#delete-account-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const button = e.submitter || e.target.querySelector('[type="submit"]');
  if (button) button.disabled = true;
  try {
    await api('/api/account/delete', {
      method: 'POST',
      body: {
        password: $('#delete-password').value,
        confirmation: $('#delete-confirm').value
      }
    });
    closeDeleteAccountModal();
    state.user = null;
    state.activeGroupId = null;
    rememberGuestVisit();
    await initAppSession();
    toast(t('Hesabın kalıcı olarak silindi. İstersen yeniden kayıt olabilirsin.'));
  } catch (error) {
    $('#delete-account-error').textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
});

/* Manevi İklim */
$$('[data-theme-choice]').forEach((btn) => btn.addEventListener('click', () => {
  state.settings.theme = btn.dataset.themeChoice;
  saveSettings(`${t(THEMES.find((t) => t.key === state.settings.theme).label)}${t(' iklimine geçildi')}`);
}));
/* Alt menü */
$('#footer-logout-btn')?.addEventListener('click', logout);
$('#footer-new-circle-btn')?.addEventListener('click', () => { switchView('circles'); openHalkaModal(); });

/* Hesap daveti: üye işlemi isteyen misafir önce burayı görür. */
$('#account-create-btn')?.addEventListener('click', openRegisterScreen);
$('#account-login-btn')?.addEventListener('click', () => {
  closeAccountSheet();
  showAuth(true);
  authTab('login');
});
$('#account-later-btn')?.addEventListener('click', closeAccountSheet);
$('#account-sheet-close')?.addEventListener('click', closeAccountSheet);
$('#account-sheet')?.addEventListener('click', (e) => {
  if (e.target === $('#account-sheet')) closeAccountSheet();
});
$$('[data-guest-auth-btn]').forEach((btn) => btn.addEventListener('click', openRegisterScreen));

initEmblems();
initWatermarks();
renderIcons();
boot();

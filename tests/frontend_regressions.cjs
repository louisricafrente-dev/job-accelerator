const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('src/static/app.js', 'utf8');
const storage = new Map();
const token = (role, id) => Buffer.from(JSON.stringify({ role, id })).toString('base64url') + '.test';
const requests = [];
const elements = new Map();
const context = vm.createContext({
  console, URLSearchParams, atob,
  currentSessionToken: token('guest', 'guest-a'), currentUserRole: 'guest',
  localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
  window: { fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => ({ success: true }) }; } },
  document: { getElementById: id => { if (!elements.has(id)) elements.set(id, { style: {}, innerHTML: '' }); return elements.get(id); } },
  currentStatus: 'new', currentRole: 'All', currentLevel: 'All', searchQuery: '', currentDateFilter: 'all',
  hasSalaryOnly: false, remoteOnly: false, hideSenior: false, vaTrainingEnabled: false, currentPlatform: 'All',
  selectedLevels: new Set(), filterBySkillsOnly: false, userStack: 'Junior / Entry',
  jobsList: [], selectedIndex: 0, renderJobs() {}, updateSummaryText() {},
});
vm.runInContext(code.slice(code.indexOf('const LOCAL_STATUS_KEY ='), code.indexOf("document.addEventListener('visibilitychange'")), context);
vm.runInContext(code.slice(code.indexOf('function getSkillsMatch(job)'), code.indexOf('// Chip & Stack helpers')), context);
vm.runInContext(code.slice(code.indexOf('let loadJobsSequence ='), code.indexOf('// Skills matching calculator')), context);

async function main() {
  for (const title of ['Software Engineer III', 'Senior Software Engineer, Backend (Identity International)']) {
    assert.equal(context.getSkillsMatch({ title, experience_level: 'Senior / Lead' }).count, 0);
  }
  assert.equal(context.getSkillsMatch({ title: 'Junior Android Developer', experience_level: 'Junior / Entry' }).count, 1);

  context.saveLocalStatusOverride(1, { status: 'applied', notes: 'guest note' });
  context.currentSessionToken = token('admin', 'admin');
  context.currentUserRole = 'admin';
  await context.syncLocalOverridesToServer();
  assert.equal(requests.length, 0, 'guest queue must never replay as admin');
  context.saveLocalStatusOverride(1, { notes: 'admin note' });
  context.currentSessionToken = token('guest', 'guest-a');
  context.currentUserRole = 'guest';
  await context.syncLocalOverridesToServer();
  assert.equal(requests.length, 1);
  assert.equal(JSON.parse(requests[0].options.body).notes, 'guest note');
  context.currentSessionToken = token('admin', 'admin');
  assert.equal(context.getLocalStatusOverrides()['1'].notes, 'admin note');
  await context.syncLocalOverridesToServer();

  const jobs = Array.from({ length: 207 }, (_, i) => ({ id: i + 1, status: 'new', title: 'Developer' }));
  context.resilientFetchWithRetry = async url => {
    const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset'));
    const page = jobs.slice(offset, offset + 200);
    return { ok: true, json: async () => ({ jobs: page, has_more: offset + page.length < jobs.length }) };
  };
  await context.loadJobs();
  assert.equal(context.jobsList.length, 207, 'feed must load every page');

  let release;
  context.resilientFetchWithRetry = () => new Promise(resolve => { release = resolve; });
  const oldRequest = context.loadJobs();
  context.resilientFetchWithRetry = async () => ({ ok: true, json: async () => ({ jobs: [{ id: 999, status: 'new' }], has_more: false }) });
  await context.loadJobs();
  release({ ok: true, json: async () => ({ jobs: [{ id: 1, status: 'new' }], has_more: false }) });
  await oldRequest;
  assert.equal(context.jobsList[0].id, 999, 'an old response must not overwrite newer filters');

  vm.runInContext(code.slice(code.indexOf('async function triggerSync()'), code.indexOf('function startSyncPoller()')), context);
  const matrix = vm.runInNewContext(code.slice(code.indexOf('const PRESET_CATEGORIES ='), code.indexOf('const PRESET_SKILLS =')) + ';PRESET_CATEGORIES.flatMap(c=>c.skills)');
  const classes = { contains: () => false, add() {}, remove() {} };
  elements.set('sync-btn', { classList: classes });
  elements.set('sync-spinner', { classList: classes });
  elements.set('user-stack-input', { value: matrix.join(', ') });
  const toasts = [];
  context.currentUserRole = 'admin';
  context.showToast = message => toasts.push(message);
  context.stopSyncIndicator = () => {};
  context.startSyncPoller = () => {};
  context.loadStats = async () => {};
  let sent;
  context.fetch = async (_, options) => {
    sent = JSON.parse(options.body);
    return { ok: true, json: async () => ({ status: 'ok', added: 0 }) };
  };
  await context.triggerSync();
  assert.equal(sent.keywords.length, matrix.length, 'Sync must send the entire selected matrix');
  assert.ok(toasts.at(-1).startsWith('Sync complete!'));
  context.fetch = async () => ({ ok: false, status: 400, json: async () => ({ status: 'error', error: 'Keyword matrix is too long' }) });
  await context.triggerSync();
  assert.ok(toasts.at(-1).includes('Keyword matrix is too long'));
  context.fetch = async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError('HTML response'); } });
  await context.triggerSync();
  assert.ok(toasts.at(-1).includes('Sync failed (502)'));
  console.log('Frontend regressions passed: seniority, account isolation, replay, pagination, response ordering, full-matrix sync, API errors');
}
main().catch(error => { console.error(error); process.exitCode = 1; });

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('src/static/app.js', 'utf8');
const storage = new Map();
const token = (role, id) => Buffer.from(JSON.stringify({ role, id })).toString('base64url') + '.test';
const requests = [];
const elements = new Map();
const context = vm.createContext({
  console, URLSearchParams, atob, setTimeout, clearTimeout, AbortController,
  currentSessionToken: token('guest', 'guest-a'), currentUserRole: 'guest',
  localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
  window: { fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async () => ({ success: true }) }; } },
  document: { querySelector: () => null, getElementById: id => { if (!elements.has(id)) elements.set(id, { style: {}, innerHTML: '', dataset: {}, classList: {add() {}, remove() {}, toggle() {}} }); return elements.get(id); } },
  currentViewMode: 'tech', currentStatus: 'new', currentRole: 'All', currentLevel: 'All', searchQuery: '', currentDateFilter: 'all',
  hasSalaryOnly: false, remoteOnly: false, hideSenior: false, vaTrainingEnabled: false, currentPlatform: 'All',
  selectedLevels: new Set(), filterBySkillsOnly: false, userStack: 'Junior / Entry',
  jobsList: [], selectedIndex: 0, renderJobs() {}, updateSummaryText() {},
});
vm.runInContext(code.slice(code.indexOf('const LOCAL_STATUS_KEY ='), code.indexOf("document.addEventListener('visibilitychange'")), context);
vm.runInContext(code.slice(code.indexOf('const ROLE_OPTIONS ='), code.indexOf('let currentPlatform =')), context);
vm.runInContext(code.slice(code.indexOf('function getSkillsMatch(job)'), code.indexOf('// Chip & Stack helpers')), context);
vm.runInContext(code.slice(code.indexOf('let loadJobsSequence ='), code.indexOf('// Skills matching calculator')), context);

async function main() {
  context.userStack = 'React';
  assert.equal(context.getSkillsMatch({title: 'Software Developer', description: 'Build applications using React.'}).count, 1);
  assert.equal(context.getSkillsMatch({title: 'Software Developer', description: 'Build applications using PHP.'}).count, 0);
  context.userStack = 'Junior / Entry';
  context.currentStats = {};
  context.MONITORED_BOARDS = [{key: 'LinkedIn', label: 'LinkedIn', domain: 'linkedin.com', type: 'Feed'}];
  context.escapeHtml = value => String(value);
  vm.runInContext(code.slice(code.indexOf('function renderTelemetry(data)'), code.indexOf('function copySyncLogs()')), context);
  context.renderTelemetry({is_syncing: true, progress: {completed_searches: 10, total_searches: 100}, telemetry: {LinkedIn: {status: 'error', error: 'HTTP 429', count: 5}}});
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /RETRY LATER/);
  assert.doesNotMatch(elements.get('telemetry-boards-grid').innerHTML, /SCANNING/);
  assert.match(elements.get('telemetry-sync-state').textContent, /10\/100/);
  context.renderTelemetry({is_syncing: true,
    local_request: {id: 'run-1', status: 'running'}, local_worker: {online: true, heartbeat_at: Date.now() / 1000},
    run_totals: {request_id: 'run-1', total_fetched: 42, sent: 20, added: 5, platforms: {LinkedIn: 42}},
    progress: {completed_searches: 10, total_searches: 100, has_more: true, can_continue: false,
      next_run_at: Date.now() / 1000 + 300, boards: {LinkedIn: {next_at: Date.now() / 1000 + 300}}},
    telemetry: {LinkedIn: {status: 'cooldown', error: 'HTTP 403', count: 0, route: 'WEBSHARE', connection_retries: 1}}});
  assert.match(elements.get('telemetry-sync-state').textContent, /Waiting for retry.*Resumes automatically/);
  assert.match(elements.get('telemetry-sync-state').textContent, /42 fetched.*20 uploaded.*5 new/);
  assert.doesNotMatch(elements.get('telemetry-sync-state').textContent, /Syncing/);
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /HTTP 403.*Retry allowed after/);
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /42 fetched/);
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /WEBSHARE \(fallback\)/);
  assert.doesNotMatch(elements.get('telemetry-boards-grid').innerHTML, /STANDBY|SYNCED|Ready/);
  context.renderTelemetry({is_syncing: false, progress: {completed_searches: 10, total_searches: 100, has_more: true}});
  assert.equal(elements.get('sync-text').textContent, 'Sync now');
  assert.equal(elements.get('resume-sync-btn').hidden, false);

  for (const legacy of [false, true]) {
    const warning = 'Coverage limited: public feed only';
    context.renderTelemetry({is_syncing: false, progress: {completed_searches: 100, total_searches: 100, unfinished: false, has_more: false,
      coverage_issues: [{platform: 'LinkedIn', reason: warning}], boards: {'LinkedIn': {next_at: Date.now()/1000+3600}}},
      telemetry: {'LinkedIn': legacy ? {error: warning, status: 'error'} : {coverage_warning: warning, error: ''}}});
    const cards = elements.get('telemetry-boards-grid').innerHTML;
    assert.match(cards, /LIMITED COVERAGE/);
    assert.doesNotMatch(cards, /Eligible after|Retry allowed|DEFERRED/);
    assert.match(elements.get('progress-headline').textContent, /limited coverage/);
  }
  for (const [error, label] of [['HTTP 403', 'BLOCKED'], ['Cloudflare challenge; requires verification', 'VERIFY ACCESS'],
    ['HTTP 429', 'RETRY LATER'], ['Configuration required: authorized feed', 'SETUP REQUIRED']]) {
    context.renderTelemetry({is_syncing: false, telemetry: {'LinkedIn': {error, status: 'error'}}});
    assert.ok(elements.get('telemetry-boards-grid').innerHTML.includes(label), label);
  }
  context.renderTelemetry({is_syncing: true, telemetry: {'LinkedIn': {error: 'HTTP 403', status: 'fetching'}}});
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /SCANNING/);

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

  context.currentStatus = 'saved';
  context.currentRole = 'Mobile';
  context.currentDateFilter = 'all';
  context.currentLevel = 'All';
  context.saveLocalStatusOverride(555, { status: 'saved', job: { id: 555, title: 'Data Scientist', status: 'saved' } });
  context.resilientFetchWithRetry = async () => ({ ok: true, json: async () => ({ jobs: [], has_more: false }) });
  await context.loadJobs();
  assert.equal(context.jobsList.length, 0, 'local Saved jobs must not bypass a role filter');
  context.currentRole = 'All';
  await context.loadJobs();
  assert.equal(context.jobsList[0].id, 555, 'unfiltered Saved must retain pending local jobs');
  context.removeLocalStatusOverride(555);
  context.currentStatus = 'new';

  vm.runInContext(code.slice(code.indexOf('async function triggerSync('), code.indexOf('function startSyncPoller()')), context);
  const matrix = vm.runInNewContext(code.slice(code.indexOf('const PRESET_CATEGORIES ='), code.indexOf('const PRESET_SKILLS =')) + ';PRESET_CATEGORIES.flatMap(c=>c.skills)');
  const classes = { contains: () => false, add() {}, remove() {}, toggle() {} };
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
  let batches = 0;
  context.fetch = async (_, options) => {
    sent = JSON.parse(options.body);
    batches++;
    return { ok: true, json: async () => ({ status: 'ok', added: 1,
      progress: { has_more: batches < 3, can_continue: batches < 3, completed_searches: batches, total_searches: 3 } }) };
  };
  context.batchSyncMessage = () => 'Sync complete';
  await context.triggerSync();
  assert.equal(batches, 3, 'One click must continue available cloud batches');
  batches = 0;
  context.fetch = async () => {
    batches++;
    return { ok: true, json: async () => ({ status: 'partial', progress: { has_more: true, can_continue: false } }) };
  };
  await context.triggerSync();
  assert.equal(batches, 1, 'Cooldown-only work must not produce an infinite continuation loop');
  const originalSyncToken = context.currentSessionToken;
  let switchedRequests = 0;
  context.fetch = async () => {
    switchedRequests++;
    context.currentSessionToken = token('admin', 'other-session');
    return { ok: true, json: async () => ({ status: 'ok', progress: { has_more: true, can_continue: true } }) };
  };
  await context.triggerSync();
  assert.equal(switchedRequests, 1, 'A changed session must stop automatic continuation');
  context.currentSessionToken = originalSyncToken;

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
  vm.runInContext(code.slice(code.indexOf('function batchSyncMessage('), code.indexOf('function stopSyncIndicator(')), context);
  context.fetch = async () => ({ ok: true, json: async () => ({ status: 'ok', added: 12, progress: {completed_searches: 2, total_searches: 295, has_more: true} }) });
  await context.triggerSync();
  assert.ok(toasts.at(-1).includes('2/295'));
  assert.ok(toasts.at(-1).includes('Continuing available searches'));
  console.log('Frontend regressions passed: seniority, account isolation, replay, pagination, response ordering, full-matrix sync, API errors');
}
main().catch(error => { console.error(error); process.exitCode = 1; });

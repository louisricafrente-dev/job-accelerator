const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('src/static/app.js', 'utf8');
// Compile the whole entry point before tests evaluate isolated helpers.
new vm.Script(code, { filename: 'src/static/app.js' });
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
vm.runInContext(code.slice(code.indexOf('function filterByTag('), code.indexOf('function handleTagFilterChange(')), context);

async function main() {
  const retryStart = code.indexOf('async function resilientFetchWithRetry(');
  const retryEnd = code.indexOf('// LOCAL-FIRST PERSISTENCE ENGINE', retryStart);
  vm.runInContext(code.slice(retryStart, retryEnd), context);
  const originalFetch = context.window.fetch;
  let retryCalls = 0;
  context.window.fetch = async () => {
    retryCalls++;
    return retryCalls <= 3 ? { ok: false, status: 503 } : new Promise(() => {});
  };
  try {
    const outcome = await Promise.race([
      context.resilientFetchWithRetry('/api/jobs', {}, 3, 0),
      new Promise(resolve => setTimeout(() => resolve({ timedOut: true }), 100))
    ]);
    assert.equal(retryCalls, 3, 'fetch retries must not issue an unbounded fourth request');
    assert.equal(outcome.status, 503, 'retry exhaustion must return the final HTTP response');
  } finally {
    context.window.fetch = originalFetch;
  }

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
    schedule: {next_check_at: Date.now() / 1000 + 3600},
    local_request: {id: 'run-1', status: 'running'}, local_worker: {online: true, heartbeat_at: Date.now() / 1000},
    run_totals: {request_id: 'run-1', total_fetched: 42, sent: 20, added: 5, platforms: {LinkedIn: 42}},
    progress: {completed_searches: 10, total_searches: 100, has_more: true, can_continue: false,
      next_run_at: Date.now() / 1000 + 300, boards: {LinkedIn: {next_at: Date.now() / 1000 + 300,
        yield_counts: {android: {new: 2}, kotlin: {new: 1}}}}},
    telemetry: {LinkedIn: {status: 'cooldown', error: 'HTTP 403', count: 0, route: 'WEBSHARE', connection_retries: 1}}});
  assert.match(elements.get('telemetry-sync-state').textContent, /Waiting for retry.*Resumes automatically/);
  assert.match(elements.get('telemetry-sync-state').textContent, /Next scheduled check.*Manila/);
  assert.match(elements.get('telemetry-sync-state').textContent, /42 fetched.*20 uploaded.*5 new/);
  assert.doesNotMatch(elements.get('telemetry-sync-state').textContent, /Syncing/);
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /HTTP 403.*Retry allowed after/);
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /42 fetched.*3 new in checkpoint/);
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /WEBSHARE \(fallback\)/);
  assert.doesNotMatch(elements.get('telemetry-boards-grid').innerHTML, /STANDBY|SYNCED|Ready/);
  context.renderTelemetry({is_syncing: false, schedule: {paused: true}, progress: {completed_searches: 10, total_searches: 100, has_more: true}});
  assert.match(elements.get('telemetry-sync-state').textContent, /Auto-sync paused/);
  assert.doesNotMatch(elements.get('telemetry-sync-state').textContent, /Next scheduled check/);
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

  context.MONITORED_BOARDS = [{key: 'SmartRecruiters', label: 'SmartRecruiters', domain: 'api.smartrecruiters.com', type: 'Employer API'}];
  context.renderTelemetry({is_syncing: true,
    execution: {id: 'database-run', status: 'running', totals: {platforms: {SmartRecruiters: 3}}},
    last_result: {platforms: {}},
    telemetry: {SmartRecruiters: {status: 'complete', count: 0}}});
  assert.match(elements.get('telemetry-boards-grid').innerHTML, /3 fetched/);

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
    const params = new URL(url, 'http://localhost').searchParams;
    const offset = Number(params.get('offset'));
    const limit = Number(params.get('limit')) || 20;
    const page = jobs.slice(offset, offset + limit);
    return { ok: true, json: async () => ({ jobs: page, total: jobs.length, has_more: offset + page.length < jobs.length }) };
  };
  await context.loadJobs();
  assert.equal(context.jobsList.length, 20, 'initial load must fetch only the first 20-job batch');
  while (vm.runInContext('feedHasMore', context)) {
    await context.fetchNextJobsPage();
  }
  assert.equal(context.jobsList.length, 207, 'infinite scroll must fetch remaining 20-job batches until complete');

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
  elements.get('tag-filter').value = 'CAPTCHA';
  context.resilientFetchWithRetry = async () => ({ ok: true, json: async () => ({ jobs: [
    { id: 1, status: context.currentStatus, notes: '[TAG: CLOUDFLARE_CHALLENGE]' },
    { id: 2, status: context.currentStatus, notes: '[TAG: SCREENING_QUESTION]' }
  ], has_more: false }) });
  await context.loadJobs();
  assert.equal(elements.get('tag-filter-row').style.display, '');
  assert.deepEqual(Array.from(context.jobsList, job => job.id), [1]);
  context.currentStatus = 'new';
  await context.loadJobs();
  assert.equal(elements.get('tag-filter-row').style.display, 'none');
  assert.equal(context.jobsList.length, 2, 'Saved tags must not filter Inbox');
  elements.get('tag-filter').value = 'all';

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

  const originalPrefetchFetch = context.resilientFetchWithRetry;
  const originalSetTimeout = context.setTimeout;
  const originalRequestAnimationFrame = context.window.requestAnimationFrame;
  const prefetchRequests = [];
  let prefetchTask;
  vm.runInContext('serverQueryCache.clear()', context);
  context.currentStatus = 'new';
  context.window.requestAnimationFrame = () => {};
  context.resilientFetchWithRetry = async url => {
    const params = new URL(url, 'http://localhost').searchParams;
    const status = params.get('status');
    const offset = Number(params.get('offset'));
    prefetchRequests.push({ status, offset });
    const jobs = offset === 0
      ? Array.from({ length: 20 }, (_, index) => ({ id: index + 1, status }))
      : [{ id: `${status}-next`, status }];
    return { ok: true, json: async () => ({ jobs, total: 21, has_more: offset === 0 }) };
  };
  context.setTimeout = callback => { prefetchTask = callback(); return 0; };
  try {
    context.prefetchSiblingStatusTabs(context.currentSessionToken);
    await prefetchTask;
    assert.deepEqual(prefetchRequests, [
      { status: 'saved', offset: 0 },
      { status: 'applied', offset: 0 }
    ], 'background tab warming must fetch one preview page per sibling tab');
  } finally {
    context.resilientFetchWithRetry = originalPrefetchFetch;
    context.setTimeout = originalSetTimeout;
    context.window.requestAnimationFrame = originalRequestAnimationFrame;
  }

  const originalLoadFetch = context.resilientFetchWithRetry;
  const refreshedOffsets = [];
  context.currentStatus = 'saved';
  context.currentRole = 'All';
  context.currentLevel = 'All';
  context.currentDateFilter = 'all';
  context.currentPlatform = 'All';
  context.searchQuery = '';
  context.resilientFetchWithRetry = async url => {
    const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset'));
    refreshedOffsets.push(offset);
    const jobs = offset === 0
      ? Array.from({ length: 20 }, (_, index) => ({ id: index + 1, status: 'saved', title: 'Developer' }))
      : Array.from({ length: 5 }, (_, index) => ({ id: 21 + index, status: 'saved', title: 'Developer' }));
    return { ok: true, json: async () => ({ jobs, total: 25, has_more: offset === 0 }) };
  };
  try {
    await context.loadJobs();
    assert.deepEqual(refreshedOffsets, [0], 'initial tab open must fetch only the first 20-item page');
    assert.equal(context.jobsList.length, 20);
    await context.fetchNextJobsPage();
    assert.deepEqual(refreshedOffsets, [0, 20], 'scrolling must fetch the next 20-item page');
    assert.equal(context.jobsList.length, 25);
    const params = new URLSearchParams({ status: 'saved', role: 'All', experience_level: 'All', search: '', date_filter: 'all' });
    params.set('include_va', '1');
    const savedCacheKey = `${context.currentSessionToken}::${params.toString()}`;
    assert.equal(vm.runInContext(`serverQueryCacheComplete.has(${JSON.stringify(savedCacheKey)})`, context), true,
      'the full refresh must mark the cache complete');
  } finally {
    context.resilientFetchWithRetry = originalLoadFetch;
  }

  // 1. Abort without retry in resilientFetchWithRetry
  const prevResilientFetch = context.resilientFetchWithRetry;
  vm.runInContext(code.slice(retryStart, retryEnd), context);
  const originalAbortWindowFetch = context.window.fetch;
  let abortedFetchCalls = 0;
  context.window.fetch = (url, opts) => {
    abortedFetchCalls++;
    return new Promise((_, reject) => {
      const onAbort = () => reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
      if (opts?.signal?.aborted) onAbort();
      else opts?.signal?.addEventListener('abort', onAbort, { once: true });
    });
  };
  try {
    const ctrl = new AbortController();
    const pending = context.resilientFetchWithRetry('/api/jobs?abort_test=1', { signal: ctrl.signal }, 3, 0);
    ctrl.abort();
    let caught = null;
    try {
      await pending;
    } catch (err) {
      caught = err;
    }
    assert.ok(caught, 'aborted fetch must reject');
    assert.equal(caught.name, 'AbortError');
    assert.equal(abortedFetchCalls, 1, 'aborted fetch must not retry');
  } finally {
    context.window.fetch = originalAbortWindowFetch;
    context.resilientFetchWithRetry = prevResilientFetch;
  }

  // 2. Superseded loadJobs cancels the previous in-flight request
  const originalSupersededFetch = context.resilientFetchWithRetry;
  let firstSignal = null;
  let callIndex = 0;
  vm.runInContext('serverQueryCache.clear(); serverQueryCacheComplete.clear();', context);
  context.currentStatus = 'new';
  context.currentRole = 'All';
  context.currentLevel = 'All';
  context.currentDateFilter = '7days';
  context.currentPlatform = 'All';
  context.searchQuery = '';
  context.resilientFetchWithRetry = (url, opts) => {
    callIndex++;
    if (callIndex === 1) {
      firstSignal = opts?.signal || null;
      return new Promise((_, reject) => {
        const onAbort = () => reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
        if (firstSignal?.aborted) onAbort();
        else firstSignal?.addEventListener('abort', onAbort, { once: true });
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ jobs: [{ id: 999, status: 'new', title: 'Frontend Engineer' }], total: 1, has_more: false })
    });
  };
  try {
    const firstLoad = context.loadJobs();
    context.currentRole = 'Frontend';
    await context.loadJobs();
    await firstLoad;
    assert.equal(firstSignal?.aborted, true, 'superseded loadJobs must abort the previous request');
    assert.deepEqual(Array.from(context.jobsList, j => j.id), [999]);
    assert.doesNotMatch(elements.get('job-feed').innerHTML, /Error retrieving/);
  } finally {
    context.resilientFetchWithRetry = originalSupersededFetch;
  }

  // 3. Row-budget LRU cache eviction and zero-clone storage
  vm.runInContext('serverQueryCache.clear(); serverQueryCacheComplete.clear();', context);
  const rows5kA = Array.from({ length: 5000 }, (_, i) => ({ id: i + 1 }));
  const rows5kB = Array.from({ length: 5000 }, (_, i) => ({ id: i + 5001 }));
  const rows9kBig = Array.from({ length: 9000 }, (_, i) => ({ id: i + 10001 }));
  context.cacheServerQuery('a', rows5kA, true);
  context.cacheServerQuery('b', rows5kB, true);
  assert.equal(vm.runInContext(`serverQueryCache.has('a')`, context), false, 'oldest entry must evict when row budget exceeded');
  assert.equal(vm.runInContext(`serverQueryCache.has('b')`, context), true);
  assert.equal(vm.runInContext(`serverQueryCache.get('b')`, context), rows5kB, 'cacheServerQuery must store array directly without cloning');
  context.cacheServerQuery('big', rows9kBig, true);
  assert.equal(vm.runInContext(`serverQueryCache.size`, context), 1, 'latest entry must remain even if it exceeds row budget alone');
  assert.equal(vm.runInContext(`serverQueryCache.has('big')`, context), true);

  console.log('Frontend regressions passed: seniority, account isolation, replay, pagination, response ordering, full-matrix sync, API errors');
}
main().catch(error => { console.error(error); process.exitCode = 1; });

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('src/static/app.js', 'utf8');

function harness() {
  const timers = new Map();
  const listeners = new Map();
  const toasts = [];
  let nextTimer = 0;
  let reads = 0;
  let refreshes = 0;
  let renderCount = 0;
  let state = { is_syncing: false };
  let response = null;
  const context = vm.createContext({
    currentUserRole: 'admin', currentSessionToken: 'session', AbortSignal,
    document: {
      visibilityState: 'visible',
      addEventListener: (name, callback) => listeners.set(name, callback),
      getElementById: () => null,
    },
    setTimeout: (callback, delay) => { timers.set(++nextTimer, { callback, delay }); return nextTimer; },
    clearTimeout: id => timers.delete(id),
    fetch: async () => {
      reads++;
      if (response) await response;
      return { ok: true, json: async () => state };
    },
    renderTelemetry: () => renderCount++,
    stopSyncIndicator() {}, showToast: message => toasts.push(message),
    loadStats: () => refreshes++, loadJobs: () => refreshes++,
    syncLocalOverridesToServer() {}, flushPendingSettings() {},
    batchSyncMessage: () => 'partial progress',
  });
  vm.runInContext('let syncCompletionPending = false;', context);
  vm.runInContext(code.slice(code.indexOf('function startSyncPoller()'), code.indexOf('function batchSyncMessage(')), context);
  vm.runInContext(code.slice(code.indexOf('let telemetryTimer ='), code.indexOf('function renderTelemetry(data)')), context);
  vm.runInContext(code.slice(code.indexOf("document.addEventListener('visibilitychange'"), code.indexOf("window.addEventListener('online'")), context);
  return {
    context, timers, toasts,
    setState: value => state = value,
    setResponse: value => response = value,
    reads: () => reads, refreshes: () => refreshes, renderCount: () => renderCount,
    visibility: value => { context.document.visibilityState = value; listeners.get('visibilitychange')(); },
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));
async function tick(h) {
  assert.equal(h.timers.size, 1);
  const [id, timer] = [...h.timers][0];
  h.timers.delete(id);
  timer.callback();
  await settle();
}
async function main() {
  let h = harness();
  h.context.startTelemetryPolling();
  await settle();
  assert.equal([...h.timers.values()][0].delay, 60000);
  assert.equal(h.reads(), 1);
  h.setState({ is_syncing: true });
  h.context.startSyncPoller();
  await tick(h);
  assert.equal(h.timers.size, 1);
  assert.equal([...h.timers.values()][0].delay, 5000);
  h.setState({ is_syncing: false, last_result: { added: 3, skipped: 2 } });
  await tick(h);
  assert.match(h.toasts[0], /3 new jobs.*2 existing/);
  assert.equal(h.refreshes(), 2);
  assert.equal([...h.timers.values()][0].delay, 60000);
  await tick(h);
  assert.equal(h.toasts.length, 1, 'completion fires once');

  h.setState({ is_syncing: false, last_result: { status: 'error', error: 'failed ingestion' } });
  h.context.startSyncPoller();
  await tick(h);
  assert.equal(h.toasts.at(-1), 'Sync failed: failed ingestion');
  h.setState({ is_syncing: false, last_result: { status: 'partial' } });
  h.context.startSyncPoller();
  await tick(h);
  assert.match(h.toasts.at(-1), /Some sites were unavailable/);

  h.visibility('hidden');
  assert.equal(h.timers.size, 0);
  const reads = h.reads();
  h.context.startTelemetryPolling();
  await settle();
  assert.equal(h.reads(), reads, 'hidden tabs make no new poll requests');
  h.visibility('visible');
  await settle();
  assert.equal(h.reads(), reads + 1);
  assert.equal(h.timers.size, 1);

  h = harness();
  let release;
  h.setResponse(new Promise(resolve => release = resolve));
  h.context.startTelemetryPolling();
  h.context.startSyncPoller();
  h.context.startTelemetryPolling();
  assert.equal(h.reads(), 1, 'overlapping callers share the in-flight request');
  release();
  await settle();
  assert.equal(h.timers.size, 1, 'overlapping callers schedule one timer');

  h = harness();
  h.setResponse(new Promise(resolve => release = resolve));
  h.context.startTelemetryPolling();
  h.context.startSyncPoller();
  release();
  await settle();
  assert.equal(h.toasts.length, 0, 'a pre-command status response cannot report completion');
  assert.equal([...h.timers.values()][0].delay, 5000);
  h.setState({ is_syncing: true });
  await tick(h);
  assert.equal(h.toasts.length, 0);

  h = harness();
  h.setResponse(new Promise(resolve => release = resolve));
  h.context.startTelemetryPolling();
  h.visibility('hidden');
  release();
  await settle();
  assert.equal(h.timers.size, 0, 'an in-flight response cannot resume hidden polling');
  h.visibility('visible');
  await settle();
  h.context.currentUserRole = null;
  h.context.startTelemetryPolling();
  assert.equal(h.timers.size, 0, 'sign-out cancels polling');
  console.log('Polling regressions passed: cadence, single timer, completion/error/partial, visibility, in-flight races, sign-out.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });

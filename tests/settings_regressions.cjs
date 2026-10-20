const fs = require('node:fs');
const harness = fs.readFileSync('tests/frontend_regressions.cjs', 'utf8').split('async function main()')[0];
eval(harness + `
(async () => {
  context.viewFilters = {};
  context.currentUserRole = 'admin';
  context.currentSessionToken = token('admin', 'settings-a');
  context.console = { ...console, warn() {} };
  const section = code.slice(code.indexOf('const viewFilterKeys ='), code.indexOf('// Load persistent user settings'))
    .replace('const SETTINGS_TIMEOUT_MS = 10000;', 'const SETTINGS_TIMEOUT_MS = 20;');
  vm.runInContext(section, context);
  const requests = [];
  let releaseOld;
  context.fetch = (url, options) => {
    requests.push(JSON.parse(options.body));
    if (requests.length === 1) return new Promise(resolve => { releaseOld = resolve; });
    return Promise.resolve({ok: true});
  };
  context.persistSetting('view_filters', 'old');
  await new Promise(resolve => setImmediate(resolve));
  context.persistSetting('view_filters', 'latest');
  await vm.runInContext('settingWriteQueue', context);
  assert.equal(requests.length, 2, 'a hung request must time out and let the latest snapshot retry');
  assert.equal(requests[1].view_filters, 'latest');
  assert.ok(requests[1].__revisions.view_filters > requests[0].__revisions.view_filters);
  assert.equal(Object.keys(context.pendingSettings()).length, 0);
  releaseOld({ok: true});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(Object.keys(context.pendingSettings()).length, 0);

  context.fetch = async () => { throw new Error('offline'); };
  context.persistSetting('view_filters', 'keep after reload');
  await vm.runInContext('settingWriteQueue', context);
  assert.equal(context.pendingSettings().view_filters.value, 'keep after reload');
  vm.runInContext('clearTimeout(settingRetryTimer)', context);
  const persisted = storage.get(context.pendingSettingsKey());
  const key = context.pendingSettingsKey();
  assert.equal(JSON.parse(persisted).view_filters.value, 'keep after reload');
  context.currentSessionToken = token('admin', 'settings-b');
  assert.equal(Object.keys(context.pendingSettings()).length, 0, 'pending preferences are identity scoped');
  context.currentSessionToken = token('admin', 'settings-a');
  storage.set(key, persisted);
  context.fetch = async (url, options) => {
    assert.equal(JSON.parse(options.body).view_filters, 'keep after reload');
    return {ok: true};
  };
  await context.flushPendingSettings();
  assert.equal(Object.keys(context.pendingSettings()).length, 0);
  console.log('Settings regressions passed: timeout, latest retry, late acknowledgment, durable pending values, identity isolation, recovery');
})().catch(error => { console.error(error); process.exitCode = 1; });
`);

const fs = require('node:fs');
const harness = fs.readFileSync('tests/frontend_regressions.cjs', 'utf8').split('async function main()')[0];
eval(harness + `
(async () => {
 vm.runInContext(code.slice(code.indexOf('function applicationHandlingLabel('), code.indexOf('// Update status via API')), context);
 assert.equal(context.applicationHandlingLabel({status: 'saved'}), '');
 assert.equal(context.applicationHandlingLabel({status: 'applied'}), 'Applied by me / human');
 assert.equal(context.applicationHandlingLabel({status: 'saved', application_handling: 'needs_human'}), 'Needs human verification');
 assert.equal(context.applicationHandlingLabel({status: 'saved', application_handling: 'in_progress'}), 'In progress');
 context.saveLocalStatusOverride(42, {application_handling: 'needs_human'});
 await context.flushJobOverride(42);
 assert.equal(JSON.parse(requests[requests.length - 1].options.body).application_handling, 'needs_human');
 context.saveLocalStatusOverride(43, {application_handling: 'in_progress'});
 await context.flushJobOverride(43);
 assert.equal(JSON.parse(requests[requests.length - 1].options.body).application_handling, 'in_progress');
 console.log('Application handling regressions passed');
})().catch(e => {console.error(e);process.exitCode=1;});
`);

'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../assets/site.js'), 'utf8');
const target = Date.parse('2027-08-27T14:00:00+02:00');
let now = target - (86400 + 7200 + 180 + 4) * 1000;
const units = Object.fromEntries(['days', 'hours', 'minutes', 'seconds'].map(k => [k, {}]));
const countdown = {dataset: {countdown: '2027-08-27T14:00:00+02:00'},
  querySelector: s => units[s.match(/"(\w+)"/)[1]]};
let tick, visibility, cleared = 0, observed = 0, revealed = 0, callback;
const section = {getBoundingClientRect: () => ({top: 1200}),
  classList: {add: c => { assert.equal(c, 'is-revealed'); revealed++; }}};
const document = {
  hidden: false,
  querySelector: s => s === '[data-countdown]' ? countdown : null,
  querySelectorAll: s => s === '[data-reveal]' ? [section] : [],
  getElementById: () => null,
  addEventListener: (name, cb) => { assert.equal(name, 'visibilitychange'); visibility = cb; },
};
const window = {addEventListener() {}, innerHeight: 900, IntersectionObserver: true,
  matchMedia: () => ({matches: false})};
class Observer {
  constructor(cb) { callback = cb; }
  observe(s) { assert.equal(s, section); observed++; }
  unobserve(s) { assert.equal(s, section); observed--; }
}
vm.runInNewContext(source, {document, window, IntersectionObserver: Observer,
  Date: class extends Date { static now() { return now; } },
  setInterval: cb => { tick = cb; return 1; }, clearInterval: () => cleared++});
assert.deepEqual(Object.values(units).map(e => e.textContent), ['01', '02', '03', '04']);
now = target + 10000; tick();
assert.deepEqual(Object.values(units).map(e => e.textContent), ['00', '00', '00', '00']);
document.hidden = true; visibility(); assert.equal(cleared, 1);
document.hidden = false; now = target - 1000; visibility(); assert.equal(units.seconds.textContent, '01');
assert.equal(observed, 1);
callback([{isIntersecting: false, target: section}]); assert.equal(revealed, 0);
callback([{isIntersecting: true, target: section}]); assert.equal(revealed, 1); assert.equal(observed, 0);
// Missing API and reduced-motion each leave sections visible and unobserved.
for (const reduced of [false, true]) {
  window.matchMedia = () => ({matches: reduced});
  if (!reduced) delete window.IntersectionObserver;
  else window.IntersectionObserver = true;
  vm.runInNewContext(source, {document: {...document, querySelector: () => null}, window});
}
console.log('Countdown: timezone, rollover, expiry, visibility; reveal and fallbacks OK');

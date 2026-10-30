'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/site.js'), 'utf8');

function fixture(saved, blocked = false) {
  const attributes = {};
  const colors = {};
  const handlers = {};
  const writes = [];
  const root = {dataset: {}};
  const button = {hidden: true,
    setAttribute: (key, value) => { attributes[key] = value; },
    addEventListener: (type, fn) => { handlers[type] = fn; }};
  const storage = {
    getItem(key) { assert.equal(key, 'wedding-theme'); if (blocked) throw Error('Blocked'); return saved; },
    setItem(key, value) { if (blocked) throw Error('Blocked'); writes.push([key, value]); },
  };
  const document = {
    documentElement: root, getElementById: () => null, querySelectorAll: () => [],
    querySelector: (selector) => selector === '[data-theme-toggle]' ? button
      : selector === 'meta[name="theme-color"]' ? {setAttribute: (key, value) => { colors[key] = value; }} : null,
  };
  vm.runInNewContext(source, {document, window: {localStorage: storage, addEventListener() {}}});
  return {root, button, attributes, colors, writes, click: () => handlers.click()};
}

for (const saved of [null, '', 'invalid', '<script>']) {
  const f = fixture(saved);
  assert.equal(f.root.dataset.theme, 'light');
  assert.equal(f.button.hidden, false);
  assert.equal(f.attributes['aria-pressed'], 'false');
  assert.deepEqual(f.writes, []);
}
const f = fixture('dark');
assert.equal(f.root.dataset.theme, 'dark');
assert.equal(f.colors.content, '#141c18');
assert.equal(f.attributes['aria-pressed'], 'true');
f.click();
assert.equal(f.root.dataset.theme, 'light');
assert.equal(f.colors.content, '#faf7f2');
assert.equal(f.attributes['aria-pressed'], 'false');
f.click();
assert.equal(f.root.dataset.theme, 'dark');
assert.deepEqual(f.writes, [['wedding-theme', 'light'], ['wedding-theme', 'dark']]);
const unavailable = fixture(null, true);
unavailable.click();
assert.equal(unavailable.root.dataset.theme, 'dark');
unavailable.click();
assert.equal(unavailable.root.dataset.theme, 'light');
console.log('Theme preference: default, restore, toggle, safe storage fallback OK');

'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/site.js'), 'utf8');

for (const [dialog, expected] of [[null, 0], [{}, 0], [{showModal() {}}, 1]]) {
  const listeners = [];
  const form = {
    addEventListener(type, handler) { listeners.push([type, handler]); },
  };
  const document = {
    documentElement: {lang: 'en'},
    getElementById: () => null,
    querySelector: selector => selector === '[data-media-confirm]' ? dialog : null,
    querySelectorAll: selector => selector === '[data-media-delete]' ? [form] : [],
  };
  vm.runInNewContext(source, {document, window: {addEventListener() {}}});
  assert.equal(listeners.length, expected, 'Only intercept deletion when native dialog works');
  if (expected) assert.equal(listeners[0][0], 'submit');
}
console.log('Media confirmation: missing dialog support preserves ordinary form submission OK');

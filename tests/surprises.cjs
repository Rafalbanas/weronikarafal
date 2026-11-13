'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/site.js'), 'utf8');
const messages = {star: {hidden: true}, heart: {hidden: true}};
const buttons = ['star', 'heart', 'missing'].map((id) => ({
  dataset: {surprise: id}, hidden: true, attributes: {},
  setAttribute(key, value) { this.attributes[key] = value; },
  addEventListener(type, fn) { assert.equal(type, 'click'); this.click = fn; },
}));
const document = {
  querySelector: () => null,
  querySelectorAll: (selector) => selector === '[data-surprise]' ? buttons : [],
  getElementById: (id) => messages[id] || null,
};
vm.runInNewContext(source, {document, window: {addEventListener() {}}});
for (const [index, id] of ['star', 'heart'].entries()) {
  const button = buttons[index];
  assert.equal(button.hidden, false);
  button.click();
  assert.equal(messages[id].hidden, false);
  assert.equal(button.attributes['aria-expanded'], 'true');
  button.click();
  assert.equal(messages[id].hidden, true);
  assert.equal(button.attributes['aria-expanded'], 'false');
  // Reopening the hidden scene restarts its CSS animation without new handlers.
  button.click();
  assert.equal(messages[id].hidden, false);
  assert.equal(button.attributes['aria-expanded'], 'true');
  const other = id === 'star' ? 'heart' : 'star';
  assert.equal(messages[other].hidden, true);
  button.click();
  assert.equal(messages[id].hidden, true);
}
assert.equal(buttons[2].hidden, true);
assert.equal(buttons[2].click, undefined);
console.log('Surprises: opt-in reveal, hide, independent controls, absent target OK');

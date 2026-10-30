'use strict';
// Exercise the shipped script in a minimal DOM, without a browser or dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../assets/site.js'), 'utf8');

class Element {
  constructor(dataset = {}) {
    this.dataset = dataset;
    this.listeners = new Map();
    this.children = {};
    this.textContent = '';
    this.isConnected = true;
    this.focused = false;
    this.hidden = true;
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  emit(type, props = {}) {
    const event = {target: this, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, ...props};
    for (const handler of this.listeners.get(type) || []) handler(event);
    return event;
  }
  querySelector(selector) { return this.children[selector] || null; }
  removeAttribute(name) { delete this[name]; }
  focus() { this.focused = true; }
}

function gallery(count, template = 'Zdjęcie {current} z {total}', supported = true) {
  const dialog = new Element({counterTemplate: template});
  dialog.open = false;
  dialog.showModal = supported ? function () { this.open = true; } : undefined;
  dialog.close = function () { this.open = false; this.emit('close'); };
  const nodes = {};
  for (const name of ['image', 'caption', 'counter', 'navigation', 'prev', 'next']) {
    nodes[name] = new Element();
    dialog.children[`[data-media-${name === 'image' ? 'lightbox-image' : name}]`] = nodes[name];
  }
  const photos = Array.from({length: count}, (_, index) => new Element({
    mediaSrc: `/media/photo${index}`, mediaAlt: `<img src=x onerror=alert(1)> photo ${index}`,
  }));
  const document = {
    getElementById: () => null,
    querySelector: (selector) => selector === '[data-media-lightbox]' ? dialog : null,
    querySelectorAll: (selector) => selector === '[data-media-open]' ? photos : [],
  };
  vm.runInNewContext(source, {document, window: {addEventListener() {}}});
  return {dialog, photos, ...nodes};
}

// Opening a middle photo, controls, keyboard, wrapping, and text-only filenames.
const g = gallery(3);
assert.equal(g.navigation.hidden, false);
g.photos[1].emit('click');
assert.equal(g.dialog.open, true);
assert.equal(g.image.src, '/media/photo1');
assert.equal(g.counter.textContent, 'Zdjęcie 2 z 3');
assert.equal(g.caption.textContent, g.photos[1].dataset.mediaAlt);
assert.equal(g.image.alt, g.photos[1].dataset.mediaAlt);
g.next.emit('click');
assert.equal(g.image.src, '/media/photo2');
g.next.emit('click');
assert.equal(g.counter.textContent, 'Zdjęcie 1 z 3');
g.prev.emit('click');
assert.equal(g.image.src, '/media/photo2');
assert.equal(g.dialog.emit('keydown', {key: 'ArrowLeft'}).defaultPrevented, true);
assert.equal(g.image.src, '/media/photo1');
g.dialog.emit('keydown', {key: 'ArrowRight'});
assert.equal(g.image.src, '/media/photo2');
for (const modifier of ['ctrlKey', 'altKey', 'metaKey']) {
  assert.equal(g.dialog.emit('keydown', {key: 'ArrowLeft', [modifier]: true}).defaultPrevented, false);
}
assert.equal(g.image.src, '/media/photo2');
g.dialog.emit('click', {target: g.image});
assert.equal(g.dialog.open, true); // Image/control clicks do not dismiss the modal.
g.dialog.emit('click'); // Backdrop closes and restores focus to the original opener.
assert.equal(g.dialog.open, false);
assert.equal(g.image.src, undefined);
assert.equal(g.counter.textContent, '');
assert.equal(g.caption.textContent, '');
assert.equal(g.photos[1].focused, true);
g.next.emit('click');
g.dialog.emit('keydown', {key: 'ArrowRight'});
assert.equal(g.image.src, undefined); // Closed dialogs ignore navigation.
g.photos[0].emit('click');
assert.equal(g.counter.textContent, 'Zdjęcie 1 z 3');
const escape = g.dialog.emit('keydown', {key: 'Escape'});
assert.equal(escape.defaultPrevented, false); // Native Escape remains enabled.
g.dialog.close(); // Model the native dialog close event after Escape / close button.
assert.equal(g.photos[0].focused, true);

const single = gallery(1, 'Photo {current} of {total}');
single.photos[0].emit('click');
assert.equal(single.navigation.hidden, true);
assert.equal(single.counter.textContent, 'Photo 1 of 1');
assert.equal(single.dialog.emit('keydown', {key: 'ArrowLeft'}).defaultPrevented, false);
assert.equal(single.image.src, '/media/photo0');
single.photos[0].isConnected = false;
single.dialog.close(); // Detached openers are not focused.
assert.equal(single.photos[0].focused, false);

const empty = gallery(0);
assert.equal(empty.navigation.hidden, true);
assert.equal(empty.dialog.open, false);
const unsupported = gallery(1, '', false);
unsupported.photos[0].emit('click');
assert.equal(unsupported.dialog.open, false);
const english = gallery(3, 'Photo {current} of {total}');
english.photos[2].emit('click');
assert.equal(english.counter.textContent, 'Photo 3 of 3');
english.next.emit('click');
assert.equal(english.counter.textContent, 'Photo 1 of 3');
console.log('Lightbox navigation: controls, keyboard, counter, focus and empty states OK');

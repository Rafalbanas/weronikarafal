'use strict';

const copyCode = document.getElementById('copy-code');
if (copyCode && navigator.clipboard) {
  copyCode.hidden = false;
  copyCode.addEventListener('click', async () => {
    const input = document.getElementById('new-code');
    const status = document.getElementById('copy-status');
    try {
      await navigator.clipboard.writeText(input.value);
      status.textContent = document.documentElement.lang === 'en' ? 'Code copied.' : 'Kod skopiowany.';
    } catch {
      input.select();
      status.textContent = document.documentElement.lang === 'en' ? 'Code selected — please copy it manually.' : 'Zaznaczono kod — skopiuj go ręcznie.';
    }
  });
}

const countdown = document.querySelector('[data-countdown]');
if (countdown) {
  const target = new Date(countdown.dataset.countdown).getTime();
  const update = () => {
    let seconds = Math.max(0, Math.floor((target - Date.now()) / 1000));
    const values = {days: Math.floor(seconds / 86400), hours: Math.floor(seconds / 3600) % 24,
      minutes: Math.floor(seconds / 60) % 60, seconds: seconds % 60};
    Object.entries(values).forEach(([key, value]) => {
      const output = countdown.querySelector(`[data-unit="${key}"]`);
      if (output) output.textContent = String(value).padStart(2, '0');
    });
  };
  update();
  setInterval(update, 1000);
}

// All authorization and RSVP validation live on the server. JavaScript is optional.
const rsvpForm = document.getElementById('rsvpForm');
if (rsvpForm) {
  rsvpForm.addEventListener('submit', () => {
    const button = rsvpForm.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = document.documentElement.lang === 'en' ? 'Saving…' : 'Zapisywanie…';
  });
}
window.addEventListener('pageshow', (event) => {
  // The response never comes from shared HTTP caches; refresh a restored private page
  // so a revoked or logged-out session is checked again by the server.
  if (event.persisted || performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
    window.location.reload();
  }
});

// Password visibility is local to this page; passwords are never saved by this control.
document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  const field = document.getElementById(button.dataset.passwordToggle);
  if (!field) return;
  button.hidden = false;
  button.addEventListener('click', () => {
    const visible = field.type === 'password';
    field.type = visible ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(visible));
    button.textContent = visible ? button.dataset.hide : button.dataset.show;
  });
});

// Household controls enhance ordinary form fields; the server validates them all.
document.querySelectorAll('[data-household]').forEach((group) => {
  const kind = group.querySelector('[data-household-kind]');
  const partner = group.querySelector('[data-partner-fields]');
  const partnerInput = partner.querySelector('input');
  const updateKind = () => {
    const namedCouple = kind.value === 'couple';
    partner.hidden = !namedCouple;
    partnerInput.disabled = !namedCouple;
    partnerInput.required = namedCouple;
  };
  kind.addEventListener('change', updateKind);
  updateKind();
  const editor = group.querySelector('[data-children-editor]');
  const count = editor.querySelector('[data-children-count]');
  const list = editor.querySelector('[data-children-list]');
  const plus = editor.querySelector('[data-child-plus]');
  const minus = editor.querySelector('[data-child-minus]');
  plus.hidden = minus.hidden = false;
  const names = () => [...list.querySelectorAll('[data-child-name]')].map((field) => field.value);
  const render = (values) => {
    count.value = String(values.length);
    list.replaceChildren();
    values.forEach((value, index) => {
      const row = document.createElement('div');
      row.className = 'child-row';
      const field = document.createElement('div');
      field.className = 'child-field';
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.id = `child-${editor.dataset.prefix}-${index + 1}`;
      label.htmlFor = input.id;
      label.textContent = `${editor.dataset.childLabel} ${index + 1} (${editor.dataset.optional})`;
      input.name = 'children';
      input.value = value;
      input.maxLength = 120;
      input.autocomplete = 'off';
      input.dataset.childName = '';
      field.append(label, input);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'button button-small button-outline';
      remove.textContent = '−';
      remove.setAttribute('aria-label', `${editor.dataset.remove} ${index + 1}`);
      remove.addEventListener('click', () => {
        const values = names();
        values.splice(index, 1);
        render(values);
      });
      row.append(field, remove);
      list.append(row);
    });
    plus.disabled = values.length >= 20;
    minus.disabled = values.length === 0;
  };
  const resize = (length) => {
    const values = names();
    length = Math.min(20, Math.max(0, Math.trunc(length) || 0));
    while (values.length < length) values.push('');
    render(values.slice(0, length));
  };
  plus.addEventListener('click', () => resize(Number(count.value) + 1));
  minus.addEventListener('click', () => resize(Number(count.value) - 1));
  count.addEventListener('change', () => resize(Number(count.value)));
  render(names());
});

'use strict';

const copyCode = document.getElementById('copy-code');
if (copyCode && navigator.clipboard) {
  copyCode.hidden = false;
  copyCode.addEventListener('click', async () => {
    const input = document.getElementById('new-code');
    const status = document.getElementById('copy-status');
    try {
      await navigator.clipboard.writeText(input.value);
      status.textContent = 'Kod skopiowany.';
    } catch {
      input.select();
      status.textContent = 'Zaznaczono kod — skopiuj go ręcznie.';
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
    button.textContent = 'Zapisywanie…';
  });
}
window.addEventListener('pageshow', (event) => {
  // The response never comes from shared HTTP caches; refresh a restored private page
  // so a revoked or logged-out session is checked again by the server.
  if (event.persisted || performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
    window.location.reload();
  }
});

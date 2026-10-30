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

// Media library: dropzone, per-file upload progress, lightbox and delete confirmation.
const mediaUpload = document.querySelector('[data-media-upload]');
if (mediaUpload) {
  const form = mediaUpload.querySelector('[data-media-form]');
  const input = mediaUpload.querySelector('[data-media-input]');
  const dropzone = mediaUpload.querySelector('[data-dropzone]');
  const pending = mediaUpload.querySelector('[data-media-pending]');
  const submit = mediaUpload.querySelector('[data-media-submit]');
  const statusOutput = mediaUpload.querySelector('[data-media-status]');
  const maxBytes = Number(mediaUpload.dataset.maxBytes) || 0;
  const isEnglish = document.documentElement.lang === 'en';
  const messages = {
    tooLarge: mediaUpload.dataset.msgTooLarge,
    choose: mediaUpload.dataset.msgChoose,
    error: mediaUpload.dataset.msgError,
    uploading: mediaUpload.dataset.msgUploading,
    done: mediaUpload.dataset.msgDone,
    failed: mediaUpload.dataset.msgFailed,
  };
  const rows = new Map();
  let queue = [];
  let uploading = false;

  const setStatus = (text, failed = false) => {
    statusOutput.textContent = text || '';
    statusOutput.classList.toggle('notice-error', failed);
  };

  const renderPending = () => {
    pending.replaceChildren();
    rows.clear();
    queue.forEach((file) => {
      const row = document.createElement('li');
      row.className = 'media-pending-item';
      row.dataset.state = 'ready';
      const name = document.createElement('span');
      name.className = 'media-pending-name';
      name.textContent = file.name;
      const bar = document.createElement('progress');
      bar.max = 100;
      bar.value = 0;
      const label = document.createElement('span');
      label.className = 'media-pending-status';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'media-pending-remove';
      remove.setAttribute('aria-label', `${isEnglish ? 'Remove file' : 'Usuń plik'}: ${file.name}`);
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        if (uploading) return;
        queue = queue.filter((item) => item !== file);
        renderPending();
      });
      row.append(name, bar, label, remove);
      pending.append(row);
      rows.set(file, { row, bar, label });
    });
    pending.hidden = queue.length === 0;
    submit.disabled = uploading || queue.length === 0;
  };

  const addFiles = (fileList) => {
    if (uploading) return;
    let tooLarge = false;
    Array.from(fileList).forEach((file) => {
      if (maxBytes && file.size > maxBytes) {
        tooLarge = true;
        return;
      }
      if (queue.some((item) => item.name === file.name && item.size === file.size
          && item.lastModified === file.lastModified)) return;
      queue.push(file);
    });
    if (tooLarge) setStatus(messages.tooLarge, true);
    renderPending();
  };

  input.addEventListener('change', () => {
    addFiles(input.files);
    input.value = '';
  });
  ['dragenter', 'dragover'].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add('is-dragging');
    });
  });
  ['dragleave', 'drop'].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove('is-dragging');
    });
  });
  dropzone.addEventListener('drop', (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  });
  dropzone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      input.click();
    }
  });

  const uploadFile = (file) => new Promise((resolve) => {
    const row = rows.get(file);
    const xhr = new XMLHttpRequest();
    const finish = (ok, message) => {
      if (row) {
        row.row.dataset.state = ok ? 'done' : 'error';
        if (ok) row.bar.value = 100;
        row.label.textContent = ok ? messages.done : (message || messages.failed);
      }
      resolve(ok);
    };
    xhr.open('POST', form.action);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    if (row) {
      row.row.dataset.state = 'uploading';
      row.label.textContent = messages.uploading;
    }
    xhr.upload.addEventListener('progress', (event) => {
      if (row && event.lengthComputable) row.bar.value = Math.round(event.loaded / event.total * 100);
    });
    xhr.addEventListener('load', () => {
      let payload = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      finish(xhr.status >= 200 && xhr.status < 300 && payload && payload.ok === true,
        payload && payload.error);
    });
    xhr.addEventListener('error', () => finish(false));
    xhr.addEventListener('timeout', () => finish(false));
    const body = new FormData();
    body.append('csrf_token', form.querySelector('[name="csrf_token"]').value);
    body.append('files', file, file.name);
    xhr.send(body);
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (uploading) return;
    if (!queue.length) {
      setStatus(messages.choose, true);
      return;
    }
    uploading = true;
    input.disabled = true;
    submit.disabled = true;
    setStatus('');
    const finished = new Set();
    let failed = false;
    for (const file of queue.slice()) {
      if (await uploadFile(file)) finished.add(file);
      else failed = true;
    }
    uploading = false;
    input.disabled = false;
    if (!failed) {
      window.location.reload();
      return;
    }
    queue = queue.filter((file) => !finished.has(file));
    finished.forEach((file) => {
      rows.get(file).row.remove();
      rows.delete(file);
    });
    submit.disabled = queue.length === 0;
    setStatus(messages.error, true);
  });

  renderPending();
}

const mediaConfirm = document.querySelector('[data-media-confirm]');
if (mediaConfirm) {
  document.querySelectorAll('[data-media-delete]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.confirmed === '1') return;
      event.preventDefault();
      const text = mediaConfirm.querySelector('[data-media-confirm-text]');
      if (text) text.textContent = form.dataset.confirm || '';
      mediaConfirm.returnValue = '';
      mediaConfirm.showModal();
      mediaConfirm.addEventListener('close', () => {
        if (mediaConfirm.returnValue !== 'confirm') return;
        form.dataset.confirmed = '1';
        form.submit();
      }, { once: true });
    });
  });
}

function setupMediaLightbox() {
  const dialog = document.querySelector('[data-media-lightbox]');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  // Only previewable photos on this rendered page; videos and downloads are excluded.
  const photos = [...document.querySelectorAll('[data-media-open]')];
  if (!photos.length) return;
  const image = dialog.querySelector('[data-media-lightbox-image]');
  const caption = dialog.querySelector('[data-media-caption]');
  const counter = dialog.querySelector('[data-media-counter]');
  const navigation = dialog.querySelector('[data-media-navigation]');
  let current = -1;
  let opener = null;

  const showPhoto = (index) => {
    current = (index + photos.length) % photos.length;
    const photo = photos[current];
    image.src = photo.dataset.mediaSrc;
    image.alt = photo.dataset.mediaAlt || '';
    caption.textContent = image.alt;
    counter.textContent = dialog.dataset.counterTemplate
      .replace('{current}', String(current + 1)).replace('{total}', String(photos.length));
  };
  const move = (delta) => {
    if (dialog.open && current >= 0 && photos.length > 1) showPhoto(current + delta);
  };
  navigation.hidden = photos.length < 2;
  dialog.querySelector('[data-media-prev]').addEventListener('click', () => move(-1));
  dialog.querySelector('[data-media-next]').addEventListener('click', () => move(1));
  photos.forEach((button, index) => {
    button.addEventListener('click', () => {
      opener = button;
      showPhoto(index);
      if (!dialog.open) dialog.showModal();
    });
  });
  dialog.addEventListener('keydown', (event) => {
    if (!dialog.open || photos.length < 2 || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      move(event.key === 'ArrowLeft' ? -1 : 1);
    }
    // Escape is deliberately left to the native dialog's cancel/close behavior.
  });
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    image.removeAttribute('src');
    image.alt = '';
    caption.textContent = '';
    counter.textContent = '';
    current = -1;
    if (opener?.isConnected) opener.focus();
    opener = null;
  });
}
setupMediaLightbox();

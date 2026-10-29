const gmailTypes = {
  INTERVIEW: ['Interview', 'interview'], ASSESSMENT: ['Assessment', 'assessment'],
  REQUIREMENT: ['Documents / forms', 'requirement'], OFFER: ['Offer', 'offer'],
  REJECTED: ['Rejection', 'rejected'], RECEIVED: ['Acknowledgment', 'other'], OTHER: ['Other / unclear', 'other']
};
let gmailListController = null;
let gmailSearchTimer = null;
let gmailReturnFocus = null;
let gmailViewerRecord = null;

function originalGmailLink(message) {
  return `https://mail.google.com/mail/u/michael18ricafrente@gmail.com/#all/${message.id}`;
}

async function gmailRequest(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Gmail Hub request failed.');
  return data;
}

async function loadGmailHub(append = false) {
  const feed = document.getElementById('gmail-messages-feed');
  if (!feed) return;
  if (gmailListController) gmailListController.abort();
  const controller = new AbortController();
  gmailListController = controller;
  const value = id => document.getElementById(id)?.value || '';
  const params = new URLSearchParams({limit: '40', offset: String(append ? gmailMessages.length : 0),
    category: value('gmail-category-filter'), read: value('gmail-read-filter'),
    match: value('gmail-match-filter'), search: value('gmail-search-input')});
  feed.setAttribute('aria-busy', 'true');
  const more = document.getElementById('gmail-load-more');
  more.disabled = true;
  try {
    const data = await gmailRequest('/api/gmail/messages?' + params, {signal: controller.signal});
    gmailMessages = append ? [...gmailMessages, ...data.messages] : data.messages;
    const stats = data.stats || {};
    document.getElementById('gmail-stats-strip').innerHTML = [
      ['Messages', stats.total], ['Unread in Hub', stats.unread], ['Needs action', stats.action_required],
      ['Pipeline updated', stats.updated], ['Unchanged / review', stats.review]
    ].map(([label, count]) => `<div><strong>${Number(count || 0)}</strong><span>${label}</span></div>`).join('');
    const scan = data.scan || {};
    const result = scan.result || {};
    const timestamp = scan.completed_at ? new Date(scan.completed_at * 1000).toLocaleString() : '';
    const statuses = {
      queued: 'Cloud scan queued. Reload saved inbox to check progress.',
      running: 'Cloud scan running. Existing messages remain available.',
      complete: `Last scan ${timestamp}: ${Number(result.imported || 0)} new messages; ${Number(result.pipeline_updated || 0)} Pipeline updates.`,
      error: scan.error || 'Last scan failed. Your saved messages are still available.'
    };
    const status = document.getElementById('gmail-scan-status');
    status.textContent = statuses[scan.status] || 'No cloud scan yet. Choose a range and scan Gmail.';
    status.dataset.state = scan.status || 'empty';
    document.getElementById('gmail-result-count').textContent = `${gmailMessages.length} of ${data.total} matching messages · newest first`;
    const badge = document.getElementById('stat-gmail');
    if (badge) badge.textContent = stats.unread || 0;
    more.hidden = !data.has_more;
    renderGmailMessages();
  } catch (error) {
    if (error.name !== 'AbortError') {
      document.getElementById('gmail-scan-status').textContent = error.message;
      if (!gmailMessages.length) feed.innerHTML = '<p class="gh-empty">Inbox unavailable. Use Reload saved inbox to try again.</p>';
    }
  } finally {
    if (gmailListController === controller) {
      feed.setAttribute('aria-busy', 'false');
      more.disabled = false;
    }
  }
}

function filterGmailCategory(category) {
  const select = document.getElementById('gmail-category-filter');
  select.value = category === 'ALL' ? '' : category;
  loadGmailHub();
}

function handleGmailSearch() {
  clearTimeout(gmailSearchTimer);
  gmailSearchTimer = setTimeout(() => loadGmailHub(), 350);
}

function renderGmailMessages() {
  const feed = document.getElementById('gmail-messages-feed');
  if (!gmailMessages.length) {
    feed.innerHTML = '<div class="gh-empty"><h3>No messages in this view</h3><p>Change your filters, or scan a wider date range. Uncertain messages are kept without changing your Pipeline.</p></div>';
    return;
  }
  feed.innerHTML = gmailMessages.map(message => {
    const [label, type] = gmailTypes[message.category] || gmailTypes.OTHER;
    return `<article class="gh-message ${message.is_read ? 'is-read' : 'is-unread'}">
      <div class="gh-message-meta"><span class="gh-tag gh-${type}">${label}</span>
        <span class="gh-read-label">${message.is_read ? 'Read' : 'Unread'}</span>
        <time datetime="${new Date(message.received_at * 1000).toISOString()}">${escapeHtml(new Date(message.received_at * 1000).toLocaleString())}</time></div>
      <h3><button type="button" class="gh-subject" data-open="${message.id}">${escapeHtml(message.subject || '(No subject)')}</button></h3>
      <p class="gh-sender">${escapeHtml(message.sender)}</p>
      <p class="gh-preview">${escapeHtml(message.snippet)}</p>
      <div class="gh-message-bottom"><span class="gh-pipeline ${message.stage_applied ? 'gh-updated' : ''}">${escapeHtml(message.pipeline_result)}${message.job_id ? ` · Job #${Number(message.job_id)}` : ''}</span>
        <div class="gh-message-actions"><button type="button" data-read="${message.id}">${message.is_read ? 'Mark unread' : 'Mark read'}</button>
        <a href="${originalGmailLink(message)}" target="_blank" rel="noopener noreferrer">Open in Gmail <span aria-hidden="true">↗</span></a></div></div>
    </article>`;
  }).join('');
  feed.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => openGmailMessageViewer(button.dataset.open)));
  feed.querySelectorAll('[data-read]').forEach(button => button.addEventListener('click', () => {
    const message = gmailMessages.find(item => item.id === button.dataset.read);
    setGmailRead(message.id, !message.is_read, button);
  }));
}

async function setGmailRead(id, value, button) {
  if (button) button.disabled = true;
  try {
    await gmailRequest(`/api/gmail/messages/${id}/read`, {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({is_read: value})});
    const message = gmailMessages.find(item => item.id === id);
    if (message) message.is_read = value ? 1 : 0;
    await loadGmailHub();
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function triggerGmailScan(button) {
  button = button || document.getElementById('btn-gmail-scan');
  button.disabled = true;
  button.textContent = 'Queuing scan…';
  try {
    const data = await gmailRequest('/api/gmail/scan', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({window: document.getElementById('gmail-scan-window').value})});
    if (!data.success) throw new Error(data.error || 'Scan could not be queued.');
    await loadGmailHub();
  } catch (error) {
    document.getElementById('gmail-scan-status').textContent = error.message;
    showToast(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'Scan Gmail';
  }
}

function renderGmailViewerContent(message) {
  const [label, type] = gmailTypes[message.category] || gmailTypes.OTHER;
  const body = (message.body_text || '').split(/(https?:\/\/[^\s<>"']+)/g).map(part =>
    /^https?:\/\//.test(part) ? `<a href="${escapeHtml(part)}" target="_blank" rel="noopener noreferrer">${escapeHtml(part)}</a>` : escapeHtml(part)).join('');
  return `<div class="gh-reader">
    <span class="gh-tag gh-${type}">${label}</span>
    <h2 id="gmail-modal-subject">${escapeHtml(message.subject)}</h2>
    <p>${escapeHtml(message.sender)}</p><p class="gh-muted">${escapeHtml(new Date(message.received_at * 1000).toLocaleString())}</p>
    <div class="gh-reader-result"><strong>${escapeHtml(message.pipeline_result)}</strong><p>${escapeHtml(message.match_reason)}</p></div>
    <div class="gh-message-actions"><a href="${originalGmailLink(message)}" target="_blank" rel="noopener noreferrer">Open original in Gmail ↗</a>
      <button type="button" id="gmail-viewer-unread">Mark unread &amp; close</button></div>
    <p class="gh-muted">Original message text. Remote images and attachments are not loaded.</p>
    <pre class="gh-body">${body}</pre>
  </div>`;
}

async function openGmailMessageViewer(id) {
  if (!currentViewerMessageId) gmailReturnFocus = document.activeElement;
  currentViewerMessageId = id;
  const modal = document.getElementById('gmail-message-modal');
  const content = document.getElementById('gmail-viewer-content');
  content.innerHTML = '<h2 id="gmail-modal-subject">Loading message…</h2>';
  modal.style.display = 'flex';
  document.body.classList.add('modal-open');
  modal.querySelector('.btn-viewer-close').focus();
  try {
    const message = await gmailRequest('/api/gmail/messages/' + id);
    if (currentViewerMessageId !== id) return;
    gmailViewerRecord = message;
    const index = gmailMessages.findIndex(item => item.id === id);
    if (index >= 0) gmailMessages[index] = {...gmailMessages[index], ...message};
    content.innerHTML = renderGmailViewerContent(message);
    content.scrollTop = 0;
    document.getElementById('gmail-viewer-counter').textContent = `${index + 1} of ${gmailMessages.length} loaded`;
    document.getElementById('btn-gmail-prev').disabled = index <= 0;
    document.getElementById('btn-gmail-next').disabled = index < 0 || index >= gmailMessages.length - 1;
    document.getElementById('gmail-viewer-unread').onclick = async event => {
      await setGmailRead(id, false, event.currentTarget);
      closeGmailMessageViewer();
    };
    if (!message.is_read) await setGmailRead(id, true);
  } catch (error) {
    if (currentViewerMessageId === id) content.innerHTML = `<h2 id="gmail-modal-subject">Cannot open message</h2><p>${escapeHtml(error.message)}</p>`;
  }
}

function closeGmailMessageViewer() {
  document.getElementById('gmail-message-modal').style.display = 'none';
  document.body.classList.remove('modal-open');
  const id = currentViewerMessageId;
  currentViewerMessageId = null;
  const target = gmailReturnFocus?.isConnected ? gmailReturnFocus : document.querySelector(`[data-open="${id}"]`);
  (target || document.getElementById('btn-gmail-scan')).focus();
}

function handleGmailModalOverlayClick(event) {
  if (event.target.id === 'gmail-message-modal') closeGmailMessageViewer();
}

function navigateGmailMessage(delta) {
  const index = gmailMessages.findIndex(message => message.id === currentViewerMessageId) + delta;
  if (index >= 0 && index < gmailMessages.length) openGmailMessageViewer(gmailMessages[index].id);
}

async function copyCurrentGmailMessage() {
  const message = gmailViewerRecord;
  if (!message) return;
  try {
    await navigator.clipboard.writeText(`${message.subject}\n${message.sender}\n\n${message.body_text || ''}`);
    showToast('Message copied.', 'success');
  } catch {
    showToast('Clipboard unavailable. Select and copy the message text.', 'error');
  }
}

document.addEventListener('keydown', event => {
  const modal = document.getElementById('gmail-message-modal');
  if (modal.style.display === 'none' || event.key !== 'Tab') return;
  const controls = [...modal.querySelectorAll('button:not(:disabled),a[href]')];
  const first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

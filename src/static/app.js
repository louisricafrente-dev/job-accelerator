// State management
let currentStatus = 'new';
let currentLevel = 'All';
let currentRole = 'All';
let currentDateFilter = 'all';
let hideSenior = false;
let searchQuery = '';
let jobsList = [];
let selectedIndex = 0;
let searchDebounceTimer = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadJobs();
  setupKeyboardNavigation();
});

// Load stats from server
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('stat-new').textContent = data.new || 0;
    document.getElementById('stat-saved').textContent = data.saved || 0;
    document.getElementById('stat-applied').textContent = data.applied || 0;
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

// Load jobs with current filters
async function loadJobs() {
  const feed = document.getElementById('job-feed');
  feed.innerHTML = '<div class="loading-state">Loading job postings...</div>';

  try {
    const params = new URLSearchParams({
      status: currentStatus,
      role: currentRole,
      experience_level: currentLevel,
      search: searchQuery,
      date_filter: currentDateFilter
    });

    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    let jobs = data.jobs || [];

    // Client-side Senior suppression if checkbox active and not explicitly viewing senior
    if (hideSenior && currentLevel !== 'Senior / Lead') {
      jobs = jobs.filter(j => j.experience_level !== 'Senior / Lead');
    }

    jobsList = jobs;
    selectedIndex = 0;
    renderJobs();
    updateSearchCount(jobs.length);
  } catch (err) {
    feed.innerHTML = `<div class="empty-state">Error loading jobs: ${err.message}</div>`;
  }
}

// Render cards
function renderJobs() {
  const feed = document.getElementById('job-feed');
  if (jobsList.length === 0) {
    feed.innerHTML = `
      <div class="empty-state">
        <p>No job postings found for the current filters.</p>
        <p style="margin-top: 8px; font-size: 0.88rem; color: #64748b;">Try changing the level filter or click "Sync Latest".</p>
      </div>`;
    return;
  }

  feed.innerHTML = jobsList.map((job, idx) => {
    const isSelected = idx === selectedIndex ? 'selected' : '';
    
    // Level badge class
    let levelClass = 'badge-level-mid';
    if (job.experience_level.includes('Junior') || job.experience_level.includes('Entry')) {
      levelClass = 'badge-level-junior';
    } else if (job.experience_level.includes('Senior') || job.experience_level.includes('Lead')) {
      levelClass = 'badge-level-senior';
    }

    // Tier badge class
    const tierClass = `badge-tier${job.tier || 1}`;

    return `
      <div class="job-card ${isSelected}" id="job-card-${idx}" onclick="selectCard(${idx})">
        <div class="job-main">
          <div class="job-header-row">
            <span class="job-title">${escapeHtml(job.title)}</span>
            <span class="company-name">@ ${escapeHtml(job.company)}</span>
          </div>

          <div class="meta-row">
            <span class="badge badge-platform">${escapeHtml(job.platform)}</span>
            <span class="badge ${tierClass}">Tier ${job.tier}</span>
            <span class="badge ${levelClass}">${escapeHtml(job.experience_level)}</span>
            <span class="job-location">📍 ${escapeHtml(job.location || 'Remote')}</span>
            ${job.salary ? `<span class="job-salary">💰 ${escapeHtml(job.salary)}</span>` : ''}
            ${formatPostingDate(job.date_posted)}
          </div>
        </div>

        <div class="job-actions">
          <a href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer" 
             class="btn-apply" onclick="handleApplyClick(event, ${job.id}, '${escapeHtml(job.job_url)}')">
            🚀 Apply Now
          </a>
          <button class="btn-action-icon ${job.status === 'applied' ? 'btn-applied' : ''}" 
                  title="Mark Applied" onclick="updateJobStatus(${job.id}, 'applied')">
            ✅
          </button>
          <button class="btn-action-icon" title="Save Job" onclick="updateJobStatus(${job.id}, 'saved')">
            ⭐
          </button>
          <button class="btn-action-icon" title="Ignore Job" onclick="updateJobStatus(${job.id}, 'ignored')">
            ✕
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// Select card by index
function selectCard(idx) {
  if (idx < 0 || idx >= jobsList.length) return;
  const oldCard = document.getElementById(`job-card-${selectedIndex}`);
  if (oldCard) oldCard.classList.remove('selected');

  selectedIndex = idx;
  const newCard = document.getElementById(`job-card-${selectedIndex}`);
  if (newCard) {
    newCard.classList.add('selected');
    newCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// 1-Click Apply click handler
function handleApplyClick(e, jobId, url) {
  // Allow default opening in new tab
  // Prompt or auto-update status to applied
  setTimeout(() => {
    if (confirm('Mark this job as "Applied" in your tracking system?')) {
      updateJobStatus(jobId, 'applied');
    }
  }, 400);
}

// Update status via API
async function updateJobStatus(jobId, status) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    if (res.ok) {
      loadStats();
      loadJobs();
    }
  } catch (err) {
    alert(`Failed to update status: ${err.message}`);
  }
}

// Trigger Sync
async function triggerSync() {
  const btn = document.getElementById('sync-btn');
  const spinner = document.getElementById('sync-spinner');
  const txt = document.getElementById('sync-text');

  btn.disabled = true;
  spinner.style.animation = 'spin 1s linear infinite';
  txt.textContent = 'Syncing...';

  try {
    const res = await fetch('/api/sync', { method: 'POST' });
    const data = await res.json();
    alert(`Sync completed! Added: ${data.added} new jobs (Skipped ${data.skipped} duplicates).`);
    loadStats();
    loadJobs();
  } catch (err) {
    alert(`Sync failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    spinner.style.animation = '';
    txt.textContent = 'Sync Latest';
  }
}

// Keyboard navigation
function setupKeyboardNavigation() {
  document.addEventListener('keydown', (e) => {
    // If typing in search box, ignore navigation keys
    if (document.activeElement === document.getElementById('search-input')) {
      if (e.key === 'Escape') {
        document.getElementById('search-input').blur();
      }
      return;
    }

    if (e.key === '/') {
      e.preventDefault();
      document.getElementById('search-input').focus();
      return;
    }

    if (jobsList.length === 0) return;
    const selectedJob = jobsList[selectedIndex];

    if (e.key === 'j' || e.key === 'ArrowDown') {
      e.preventDefault();
      selectCard(Math.min(selectedIndex + 1, jobsList.length - 1));
    } else if (e.key === 'k' || e.key === 'ArrowUp') {
      e.preventDefault();
      selectCard(Math.max(selectedIndex - 1, 0));
    } else if (e.key === 'a' || e.key === 'Enter') {
      if (selectedJob) {
        e.preventDefault();
        window.open(selectedJob.job_url, '_blank');
        if (confirm(`Mark "${selectedJob.title}" as Applied?`)) {
          updateJobStatus(selectedJob.id, 'applied');
        }
      }
    } else if (e.key === 's') {
      if (selectedJob) {
        e.preventDefault();
        updateJobStatus(selectedJob.id, 'saved');
      }
    } else if (e.key === 'x') {
      if (selectedJob) {
        e.preventDefault();
        updateJobStatus(selectedJob.id, 'ignored');
      }
    }
  });
}

// Filter button handlers
function setStatus(status, elem) {
  currentStatus = status;
  updatePillActive('status-group', elem);
  loadJobs();
}

function setLevel(level, elem) {
  currentLevel = level;
  updatePillActive('level-group', elem);
  loadJobs();
}

function setRole(role, elem) {
  currentRole = role;
  updatePillActive('role-group', elem);
  loadJobs();
}

function setDateFilter(filter, elem) {
  currentDateFilter = filter;
  updatePillActive('date-group', elem);
  loadJobs();
}

function formatPostingDate(dateStr) {
  if (!dateStr) return '<span class="badge badge-date-older">📅 Recently</span>';
  const todayStr = new Date().toISOString().slice(0, 10);
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const yesterdayStr = d.toISOString().slice(0, 10);

  if (dateStr.startsWith(todayStr)) {
    return `<span class="badge badge-date-today">🔥 Today (${escapeHtml(dateStr.slice(0, 10))})</span>`;
  } else if (dateStr.startsWith(yesterdayStr)) {
    return `<span class="badge badge-date-recent">🕒 Yesterday (${escapeHtml(dateStr.slice(0, 10))})</span>`;
  }
  return `<span class="badge badge-date-older">📅 ${escapeHtml(dateStr.slice(0, 10))}</span>`;
}

function toggleHideSenior(checkbox) {
  hideSenior = checkbox.checked;
  loadJobs();
}

function handleSearchInput() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    searchQuery = document.getElementById('search-input').value.trim();
    loadJobs();
  }, 250);
}

function updatePillActive(groupId, elem) {
  document.querySelectorAll(`#${groupId} .pill`).forEach(p => p.classList.remove('active'));
  elem.classList.add('active');
}

function updateSearchCount(count) {
  document.getElementById('search-count').textContent = `${count} jobs`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

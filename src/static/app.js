// --------------------------------------------------------------------------
// JOB APPLICATION ACCELERATOR - CLIENT WORKSTATION
// State Management, Live Filter Engine, Keyboard Controls, Pitch Generator
// --------------------------------------------------------------------------

// State management
let currentViewMode = 'tech'; // 'tech' or 'va'
let currentStatus = 'new';
let viewFilters = {};
let selectedLevels = new Set(['All']);
let currentLevel = 'All';
let currentRole = 'All';
let currentPlatform = 'All';
let currentDateFilter = '7days';
let hasSalaryOnly = false;
let remoteOnly = false;
let hideSenior = false;
let filterBySkillsOnly = false;
let vaTrainingEnabled = localStorage.getItem('job_accel_va_training_enabled') === 'true';
let autoSyncEnabled = localStorage.getItem('job_accel_auto_sync_enabled') !== 'false';
let searchQuery = '';
let jobsList = [];
let selectedIndex = 0;
let searchDebounceTimer = null;
let currentStats = {};
const CANDIDATE_DEFAULT_STACK = 'Kotlin, Jetpack Compose, React, Next.js, TypeScript, Node.js, Express, MySQL, Tailwind CSS, Junior / Entry';
let userStack = localStorage.getItem('job_accel_user_stack') || CANDIDATE_DEFAULT_STACK;

// Categorized preset skills for developer clarity & fast discovery (Comprehensive Taxonomy A-M)
const PRESET_CATEGORIES = [
  {
    category: "Virtual Assistant (Entry/Trainee Matrix)",
    skills: [
      "Virtual Assistant", "VA", "Executive Assistant", "Administrative Assistant",
      "Remote Assistant", "Training Provided", "Paid Training", "Will Train",
      "No Experience", "Entry Level", "Trainee", "Cyberbacker", "Athena",
      "Virtudesk", "Pineapple Staffing", "Data Entry", "Email Management",
      "Calendar Management", "Customer Support", "Research Assistant"
    ]
  },
  {
    category: "Job Titles & Seniority (Priority 1)",
    skills: [
      "Junior / Entry", "Software Engineer", "Software Developer", "Application Developer",
      "Associate Software Engineer", "Junior Software Engineer", "Graduate Software Engineer",
      "Entry Level Software Engineer", "Software Engineer I", "Software Development Engineer",
      "SDE I", "Programmer", "Computer Programmer", "Application Engineer", "Product Engineer",
      "Platform Engineer", "Systems Developer", "Systems Engineer", "Web Developer",
      "Mobile Developer", "Android Developer", "iOS Developer", "Frontend Developer",
      "Backend Developer", "Full Stack Developer", "API Developer", "Integration Developer",
      "DevOps Engineer", "QA Automation Engineer", "Software Development Intern",
      "Android Developer Intern", "Web Developer Intern", "Mobile Developer Intern",
      "Trainee Software Developer", "Graduate Developer", "Remote Software Developer"
    ]
  },
  {
    category: "Android & Mobile Engineering (Priority 2)",
    skills: [
      "Android / Kotlin", "Kotlin Coroutines", "Kotlin Flow", "StateFlow", "SharedFlow",
      "Jetpack Compose", "Android Media3", "ExoPlayer", "Jetpack Navigation", "Android SDK",
      "Android Studio", "MVVM", "MVI", "Clean Architecture", "Hilt", "Dagger", "Koin",
      "Dependency Injection", "Retrofit", "OkHttp", "REST API Integration", "Room DB",
      "Room Persistence Library", "DataStore", "WorkManager", "Paging 3", "Jetpack Lifecycle",
      "ViewModel", "LiveData", "Material Design 3", "Android UI Testing", "Espresso",
      "Compose UI Testing", "JUnit", "MockK", "Gradle", "Kotlin DSL", "Compose Multiplatform",
      "Kotlin Multiplatform", "KMP", "KMM", "Kotlin Native", "Flutter", "Dart",
      "React Native", "Expo", "iOS / Swift", "SwiftUI", "iOS SDK", "Objective-C",
      "Xamarin", ".NET MAUI", "Ionic", "Capacitor", "NativeScript", "Appium",
      "Firebase Cloud Messaging", "Push Notifications", "Deep Linking", "Offline-First Architecture"
    ]
  },
  {
    category: "Frontend & Web Development (Priority 3)",
    skills: [
      "React", "Next.js", "TypeScript", "JavaScript", "HTML / CSS", "Tailwind CSS",
      "Angular", "Vue.js", "Nuxt.js", "Svelte", "SvelteKit", "Astro", "Remix", "Gatsby",
      "Vite", "Webpack", "Babel", "Redux", "Redux Toolkit", "Zustand", "TanStack Query",
      "React Query", "Jotai", "Recoil", "Pinia", "Vuex", "RxJS", "jQuery", "Bootstrap",
      "Sass", "SCSS", "Less", "CSS Modules", "Styled Components", "Emotion", "Shadcn UI",
      "Radix UI", "Material UI", "MUI", "Chakra UI", "Ant Design", "Storybook",
      "Responsive Web Design", "Web Accessibility", "WCAG", "Progressive Web Apps", "PWA",
      "Server-Side Rendering", "SSR", "Static Site Generation", "SSG",
      "Web Performance Optimization", "WebSockets", "Web Components", "Figma to React"
    ]
  },
  {
    category: "Backend, API & Server-Side (Priority 3 & 4)",
    skills: [
      "Node.js", "Express", "Python", "Django", "Django REST Framework", "Flask",
      "FastAPI", "Spring Boot", "Spring Framework", "Spring MVC", "Hibernate", "JPA",
      "ASP.NET Core", "ASP.NET MVC", "Entity Framework Core", "Blazor", "PHP / Laravel",
      "Laravel", "Symfony", "CodeIgniter", "Ruby on Rails", "Ruby", "Go / Golang",
      "Rust", "Actix Web", "Axum", "C++", "C", "NestJS", "Hono", "AdonisJS", "Bun",
      "Deno", "Fastify", "Koa.js", "Ktor", "Prisma ORM", "Drizzle ORM", "Sequelize",
      "TypeORM", "SQLAlchemy", "Pydantic", "REST API", "RESTful API", "GraphQL API",
      "gRPC", "Webhooks", "Microservices", "Monolithic Architecture", "Event-Driven Architecture",
      "Message Queues", "RabbitMQ", "Apache Kafka", "Celery", "BullMQ", "OAuth 2.0",
      "OpenID Connect", "JWT Authentication", "API Authentication", "API Integration",
      "API Design", "API Documentation", "Swagger", "OpenAPI Specification", "Postman", "Insomnia"
    ]
  },
  {
    category: "Databases, Caching & Search (Section E)",
    skills: [
      "MySQL", "PostgreSQL", "SQLite", "MongoDB", "SQL", "MariaDB", "Microsoft SQL Server",
      "SQL Server", "Oracle Database", "Oracle SQL", "PL/SQL", "CockroachDB", "Supabase",
      "PlanetScale", "Neon", "DynamoDB", "Amazon RDS", "Amazon Aurora", "Firestore",
      "Cloud Firestore", "Cassandra", "Apache Cassandra", "CouchDB", "Elasticsearch",
      "OpenSearch", "Meilisearch", "Neo4j", "InfluxDB", "TimescaleDB", "ClickHouse",
      "Redis", "Memcached", "Valkey", "Database Design", "Database Administration",
      "Database Optimization", "Query Optimization", "Database Migration", "ORM",
      "NoSQL", "Relational Database", "Data Modeling"
    ]
  },
  {
    category: "Cloud, DevOps & Infrastructure (Priority 5)",
    skills: [
      "Google Cloud Platform", "GCP", "Microsoft Azure", "AWS", "AWS Lambda", "Amazon ECS",
      "Amazon EKS", "Amazon S3", "CloudFront", "API Gateway", "Firebase Hosting",
      "Firebase", "Vercel", "Netlify", "Render", "Railway", "Fly.io", "Cloudflare",
      "Cloudflare Workers", "Kubernetes", "Helm", "Terraform", "Pulumi", "Ansible",
      "Jenkins", "GitHub Actions", "GitLab CI/CD", "Bitbucket Pipelines", "CircleCI",
      "Argo CD", "Continuous Integration", "Continuous Deployment", "CI/CD",
      "Infrastructure as Code", "Linux", "Ubuntu", "Bash", "Shell Scripting",
      "Nginx", "Apache HTTP Server", "Docker", "Docker Compose", "Containerization",
      "Serverless Architecture", "Monitoring", "Prometheus", "Grafana", "Datadog",
      "Sentry", "OpenTelemetry", "ELK Stack", "Log Management", "Production Deployment",
      "Release Engineering", "Site Reliability Engineering", "SRE"
    ]
  },
  {
    category: "Software Testing, QA & Automation (Priority 5)",
    skills: [
      "Software QA Engineer", "Software Test Engineer", "QA Automation Engineer",
      "Test Automation Engineer", "SDET", "Software Development Engineer in Test",
      "Quality Engineer", "Automation Tester", "Manual Tester", "API Tester",
      "Performance Tester", "Security Tester", "JUnit", "TestNG", "Mockito", "Jest",
      "Vitest", "Mocha", "Chai", "Playwright", "Cypress", "Selenium", "WebdriverIO",
      "Puppeteer", "Robot Framework", "Pytest", "unittest", "JMeter", "k6", "Gatling",
      "REST Assured", "Detox", "Maestro", "XCTest", "Unit Testing", "Integration Testing",
      "End-to-End Testing", "E2E Testing", "Regression Testing", "Smoke Testing",
      "Performance Testing", "Load Testing", "Accessibility Testing", "CI Test Automation",
      "Test-Driven Development", "TDD", "Behavior-Driven Development", "BDD",
      "Code Coverage", "Bug Tracking", "Jira", "Exploratory Testing"
    ]
  },
  {
    category: "Languages & Computer Science Fundamentals (Section H)",
    skills: [
      "C", "C++", "Python", "Ruby", "Rust", "Dart", "Swift", "Objective-C", "Java",
      "Kotlin", "JavaScript", "TypeScript", "PHP", "Go / Golang", "C#", ".NET",
      "Scala", "Clojure", "Elixir", "Erlang", "Haskell", "Perl", "R", "MATLAB",
      "Assembly Language", "PowerShell", "Object-Oriented Programming", "OOP",
      "Functional Programming", "Data Structures", "Algorithms", "Design Patterns",
      "System Design", "Distributed Systems", "Concurrency", "Multithreading",
      "Memory Management", "Compiler Design", "Code Review", "Refactoring", "Debugging",
      "Git", "GitHub", "GitLab", "Bitbucket", "Version Control", "Agile Development",
      "Scrum", "Kanban", "SDLC", "Software Development Life Cycle"
    ]
  },
  {
    category: "AI, Machine Learning & LLMs (Priority 6)",
    skills: [
      "AI Engineer", "Machine Learning Engineer", "Applied AI Engineer",
      "AI Application Developer", "Generative AI Engineer", "LLM Engineer", "MLOps Engineer",
      "Artificial Intelligence", "Machine Learning", "Deep Learning",
      "Natural Language Processing", "NLP", "Computer Vision", "PyTorch", "TensorFlow",
      "scikit-learn", "Hugging Face", "LangChain", "LangGraph", "LlamaIndex", "RAG",
      "Retrieval-Augmented Generation", "Vector Database", "Pinecone", "Weaviate",
      "ChromaDB", "FAISS", "Embeddings", "LLM API Integration", "OpenAI API",
      "Prompt Engineering", "AI Agents", "Model Deployment", "MLflow", "Jupyter Notebook"
    ]
  },
  {
    category: "Game Development (Priority 6)",
    skills: [
      "Game Developer", "Gameplay Programmer", "Game Programmer", "Unity Developer",
      "Unreal Engine Developer", "Game Software Engineer", "Unity", "Unreal Engine",
      "Godot", "C# Game Development", "C++ Game Development", "GDScript", "Game Physics",
      "Game AI", "Multiplayer Game Development", "Game Backend Developer",
      "Game Tools Programmer", "Game UI Programmer", "Game Testing", "PlayFab",
      "Photon Engine", "Mirror Networking", "Game Server Development"
    ]
  },
  {
    category: "Data Engineering & Platforms (Priority 6)",
    skills: [
      "Data Engineer", "Analytics Engineer", "Data Platform Engineer", "ETL Developer",
      "Database Developer", "Big Data Engineer", "Data Infrastructure Engineer",
      "Apache Spark", "PySpark", "Apache Airflow", "dbt", "Apache Flink", "Apache Beam",
      "Databricks", "Snowflake", "BigQuery", "Amazon Redshift", "Azure Data Factory",
      "Google Dataflow", "Data Pipelines", "ETL", "ELT", "Data Warehousing", "Data Lake",
      "Data Lakehouse", "Data Orchestration", "Stream Processing", "Data Quality",
      "Python Data Engineering", "SQL Developer"
    ]
  },
  {
    category: "Security, Systems & Architecture (Section L)",
    skills: [
      "Application Security Engineer", "Product Security Engineer", "Security Software Engineer",
      "DevSecOps Engineer", "Embedded Software Engineer", "Firmware Engineer", "IoT Developer",
      "IoT Engineer", "Robotics Software Engineer", "Systems Programmer",
      "Systems Software Engineer", "Infrastructure Engineer", "Solutions Engineer",
      "Solutions Architect", "Software Architect", "Technical Lead", "Integration Engineer",
      "Middleware Developer", "ERP Developer", "Salesforce Developer", "ServiceNow Developer",
      "SAP Developer", "WordPress Developer", "Shopify Developer", "Low-Code Developer",
      "OutSystems Developer", "Mendix Developer", "Blockchain Developer",
      "Smart Contract Developer", "Web3 Developer", "Solidity Developer"
    ]
  }
];

const PRESET_SKILLS = PRESET_CATEGORIES.flatMap(c => c.skills);

const PIPELINE_STAGES = [
  { key: 'applied', label: 'Applied', short: 'Applied' },
  { key: 'hr_screening', label: 'HR Screening', short: 'Screening' },
  { key: 'tech_exam', label: 'Tech Assessment', short: 'Tech Exam' },
  { key: 'final_interview', label: 'Final Interview', short: 'Final' },
  { key: 'offer', label: 'Job Offer', short: 'Offer' },
  { key: 'rejected', label: 'Archived / Rejected', short: 'Rejected' }
];

// SVG Icon Helpers
const ICONS = {
  check: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  star: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  dismiss: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  pitch: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`,
  external: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`,
  saveDisk: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>`
};

// --------------------------------------------------------------------------
// SECURITY GATEWAY & MULTI-TENANT ACCESS CONTROL (ADMIN / GUEST SANDBOX)
// --------------------------------------------------------------------------
let currentUserRole = null; // 'admin' | 'guest'
let currentSessionToken = localStorage.getItem('job_accel_session_token') || '';
let isDashboardBootstrapped = false;

// Universal fetch interceptor to attach bearer token and intercept 401s
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  options = options || {};
  options.headers = options.headers || {};
  if (currentSessionToken) {
    if (options.headers instanceof Headers) {
      if (!options.headers.has('Authorization')) {
        options.headers.set('Authorization', `Bearer ${currentSessionToken}`);
      }
    } else if (Array.isArray(options.headers)) {
      options.headers.push(['Authorization', `Bearer ${currentSessionToken}`]);
    } else {
      if (!options.headers['Authorization']) {
        options.headers['Authorization'] = `Bearer ${currentSessionToken}`;
      }
    }
  }
  return originalFetch(url, options).then(response => {
    const urlStr = typeof url === 'string' ? url : (url.url || '');
    if (response.status === 401 && !urlStr.includes('/api/auth/')) {
      currentUserRole = null;
      updateAuthUI();
      showAuthGate();
    }
    return response;
  });
};

// Resilient fetch with exponential backoff and timeout guard for serverless cold starts & wake-from-sleep
async function resilientFetchWithRetry(url, options = {}, retries = 3, backoff = 500) {
  let attempt = 0;
  while (attempt < retries) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 12000); // 12s timeout
      const fetchOpts = { ...options, signal: controller.signal };
      const res = await window.fetch(url, fetchOpts);
      clearTimeout(timeoutId);
      if (res.ok || res.status === 401 || res.status === 404) {
        return res;
      }
      attempt++;
      if (attempt < retries) {
        await new Promise(r => setTimeout(r, backoff * Math.pow(2, attempt - 1)));
      }
    } catch (err) {
      attempt++;
      if (attempt >= retries) {
        console.warn(`Resilient fetch warning for ${url}:`, err);
        throw err;
      }
      await new Promise(r => setTimeout(r, backoff * Math.pow(2, attempt - 1)));
    }
  }
  return window.fetch(url, options);
}

// --------------------------------------------------------------------------
// LOCAL-FIRST PERSISTENCE ENGINE (OFFLINE & IDLE-PROOF CLIENT ARCHITECTURE)
// --------------------------------------------------------------------------
const LOCAL_STATUS_KEY = 'job_accel_status_overrides';

function overrideStorageKey(token = currentSessionToken) {
  try {
    const raw = token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
    const session = JSON.parse(atob(raw.padEnd(Math.ceil(raw.length / 4) * 4, '=')));
    return `${LOCAL_STATUS_KEY}:${session.role}:${session.id}`;
  } catch (_) {
    return `${LOCAL_STATUS_KEY}:locked`;
  }
}

function getLocalStatusOverrides() {
  try {
    const raw = localStorage.getItem(overrideStorageKey());
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    return {};
  }
}

function saveLocalStatusOverride(jobId, updates) {
  try {
    const overrides = getLocalStatusOverrides();
    const idKey = String(jobId);
    overrides[idKey] = {
      ...(overrides[idKey] || {}),
      ...updates,
      revision: `${Date.now()}:${Math.random()}`,
      save_state: 'pending',
      updated_at: new Date().toISOString()
    };
    localStorage.setItem(overrideStorageKey(), JSON.stringify(overrides));
  } catch (e) {
    console.error('Failed to save local status override:', e);
  }
}

function removeLocalStatusOverride(jobId, storageKey = overrideStorageKey()) {
  try {
    const overrides = JSON.parse(localStorage.getItem(storageKey) || '{}');
    delete overrides[String(jobId)];
    localStorage.setItem(storageKey, JSON.stringify(overrides));
  } catch (e) {}
}

const pendingStatusWrites = new Map();

function renderNoteSaveState(jobId) {
  const el = document.getElementById(`note-save-${jobId}`);
  if (!el) return;
  const ov = getLocalStatusOverrides()[String(jobId)];
  const state = ov ? (ov.save_state || 'pending') : 'saved';
  el.textContent = state === 'failed' ? 'Failed - retry' : state === 'pending' ? 'Pending' : 'Saved';
  el.dataset.state = state;
  el.disabled = state !== 'failed';
}

function flushJobOverride(jobId, token = currentSessionToken) {
  const storageKey = overrideStorageKey(token);
  const key = `${storageKey}:${jobId}`;
  if (pendingStatusWrites.has(key)) return pendingStatusWrites.get(key);
  const task = (async () => {
    while (token === currentSessionToken) {
      const ov = JSON.parse(localStorage.getItem(storageKey) || '{}')[String(jobId)];
      if (!ov) return true;
      if (ov.save_state === 'failed') {
        const overrides = JSON.parse(localStorage.getItem(storageKey) || '{}');
        overrides[String(jobId)].save_state = 'pending';
        localStorage.setItem(storageKey, JSON.stringify(overrides));
        if (token === currentSessionToken) renderNoteSaveState(jobId);
      }
      const payload = {};
      for (const field of ['status', 'notes', 'stage', 'follow_up_date']) {
        if (ov[field] !== undefined && ov[field] !== null) payload[field] = ov[field];
      }
      try {
        const res = await window.fetch(`/api/jobs/${jobId}/status`, {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify(payload)
        });
        if (!res.ok || !(await res.json()).success) throw new Error('Save failed');
        const latest = JSON.parse(localStorage.getItem(storageKey) || '{}')[String(jobId)];
        if (latest && latest.revision === ov.revision) removeLocalStatusOverride(jobId, storageKey);
        if (token === currentSessionToken) renderNoteSaveState(jobId);
      } catch (_) {
        const latest = JSON.parse(localStorage.getItem(storageKey) || '{}');
        if (latest[String(jobId)]) {
          latest[String(jobId)].save_state = 'failed';
          localStorage.setItem(storageKey, JSON.stringify(latest));
        }
        if (token === currentSessionToken) renderNoteSaveState(jobId);
        return false;
      }
    }
    return false;
  })();
  const tracked = task.finally(() => pendingStatusWrites.delete(key));
  pendingStatusWrites.set(key, tracked);
  return tracked;
}

async function syncLocalOverridesToServer() {
  if (!currentUserRole || !currentSessionToken) return;
  const token = currentSessionToken;
  for (const id of Object.keys(getLocalStatusOverrides())) {
    if (token !== currentSessionToken) return;
    await flushJobOverride(id, token);
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    startTelemetryPolling();
    syncLocalOverridesToServer();
    flushPendingSettings();
    loadStats();
  }
});

window.addEventListener('online', () => {
  syncLocalOverridesToServer();
  flushPendingSettings();
  loadStats();
  loadJobs();
});

async function checkAuthStatus() {
  try {
    const res = await originalFetch('/api/auth/status', {
      headers: currentSessionToken ? { 'Authorization': `Bearer ${currentSessionToken}` } : {}
    });
    if (!res.ok) {
      currentUserRole = null;
      updateAuthUI();
      return false;
    }
    const data = await res.json();
    if (data.authenticated) {
      currentUserRole = data.role;
      updateAuthUI();
      return true;
    }
    currentUserRole = null;
    updateAuthUI();
    return false;
  } catch (err) {
    currentUserRole = null;
    updateAuthUI();
    return false;
  }
}

function updateAuthUI() {
  const pill = document.getElementById('auth-mode-pill');
  const pillText = document.getElementById('auth-pill-text');
  const btn2fa = document.getElementById('btn-2fa-setup');
  const btnAction = document.getElementById('btn-auth-action');
  const actionText = document.getElementById('auth-action-text');

  const syncBtn = document.getElementById('sync-btn');
  const syncTxt = document.getElementById('sync-text');
  const digestBtn = document.getElementById('btn-daily-digest');

  if (currentUserRole === 'admin') {
    if (pill) {
      pill.className = 'auth-pill admin-pill';
      pill.title = 'Admin session active — master database (data/jobs.db) unlocked';
    }
    if (pillText) pillText.textContent = 'Admin';
    if (btn2fa) btn2fa.style.display = 'inline-flex';
    if (actionText) actionText.textContent = 'Logout';
    if (btnAction) {
      btnAction.title = 'Log out from Admin session & lock workstation';
      btnAction.className = 'btn-logout';
    }
    if (syncBtn) {
      syncBtn.title = 'Search connected job sites for recent postings';
      syncBtn.classList.remove('btn-locked');
    }
    if (syncTxt) syncTxt.textContent = 'Sync Job Sites';
    if (digestBtn) digestBtn.style.opacity = '1';
  } else if (currentUserRole === 'guest') {
    if (pill) {
      pill.className = 'auth-pill guest-pill';
      pill.title = 'Guest Sandbox active — private temporary database in use';
    }
    if (pillText) pillText.textContent = 'Guest Sandbox';
    if (btn2fa) btn2fa.style.display = 'none';
    if (actionText) actionText.textContent = 'Exit';
    if (btnAction) {
      btnAction.title = 'Exit Guest Sandbox';
      btnAction.className = 'btn-logout';
    }
    if (syncBtn) {
      syncBtn.title = '🔒 Only Admin can harvest and add new data to the system.';
      syncBtn.classList.add('btn-locked');
    }
    if (syncTxt) syncTxt.textContent = 'Sync (Admin Only)';
    if (digestBtn) digestBtn.style.opacity = '0.5';
  } else {
    if (pill) pill.className = 'auth-pill';
    if (pillText) pillText.textContent = 'Locked';
    if (btn2fa) btn2fa.style.display = 'none';
    if (actionText) actionText.textContent = 'Unlock';
  }
}


function showAuthGate() {
  const modal = document.getElementById('auth-gate-modal');
  if (modal) {
    modal.style.display = 'flex';
    const errBox = document.getElementById('auth-error-msg');
    if (errBox) errBox.style.display = 'none';
    setTimeout(() => {
      const pwd = document.getElementById('admin-password');
      if (pwd) {
        pwd.focus();
        pwd.select();
      }
    }, 120);
  }
}

function hideAuthGate() {
  const modal = document.getElementById('auth-gate-modal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function switchAuthTab(tab) {
  if (tab === 'guest') return;
  const tabAdmin = document.getElementById('tab-admin');
  const tabGuest = document.getElementById('tab-guest');
  const panelAdmin = document.getElementById('auth-panel-admin');
  const panelGuest = document.getElementById('auth-panel-guest');
  const errBox = document.getElementById('auth-error-msg');
  if (errBox) errBox.style.display = 'none';

  if (tab === 'admin') {
    tabAdmin?.classList.add('active');
    tabGuest?.classList.remove('active');
    if (panelAdmin) panelAdmin.style.display = 'flex';
    if (panelGuest) panelGuest.style.display = 'none';
    const pwd = document.getElementById('admin-password');
    if (pwd) { pwd.focus(); pwd.select(); }
  } else {
    tabGuest?.classList.add('active');
    tabAdmin?.classList.remove('active');
    if (panelGuest) panelGuest.style.display = 'flex';
    if (panelAdmin) panelAdmin.style.display = 'none';
  }
}

function handleAdminLoginKeyDown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    submitAdminLogin();
  }
}

function togglePasswordVisibility() {
  const pwd = document.getElementById('admin-password');
  const icon = document.getElementById('eye-icon');
  if (!pwd) return;
  if (pwd.type === 'password') {
    pwd.type = 'text';
    if (icon) {
      icon.innerHTML = `
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
        <line x1="1" y1="1" x2="23" y2="23"/>
      `;
    }
  } else {
    pwd.type = 'password';
    if (icon) {
      icon.innerHTML = `
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
        <circle cx="12" cy="12" r="3"/>
      `;
    }
  }
}

async function submitAdminLogin() {
  const usernameInput = document.getElementById('admin-username');
  const passwordInput = document.getElementById('admin-password');
  const btn = document.getElementById('btn-unlock-admin');
  const errBox = document.getElementById('auth-error-msg');

  const username = usernameInput ? usernameInput.value.trim().toLowerCase() : '';
  const password = passwordInput ? passwordInput.value.trim() : '';

  if (!username) {
    if (errBox) {
      errBox.textContent = 'Please enter your username.';
      errBox.style.display = 'block';
    }
    usernameInput?.focus();
    return;
  }

  if (!password) {
    if (errBox) {
      errBox.textContent = 'Please enter your password.';
      errBox.style.display = 'block';
    }
    passwordInput?.focus();
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="loading-spinner" style="width:14px;height:14px;border-width:2px;margin-right:6px;"></span> Signing in...`;
  }
  if (errBox) errBox.style.display = 'none';

  try {
    const res = await originalFetch('/api/auth/login-admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      currentUserRole = 'admin';
      currentSessionToken = data.token;
      // Persistent login session: stored in localStorage and cookie
      localStorage.setItem('job_accel_session_token', data.token);
      hideAuthGate();
      updateAuthUI();
      showToast('👑 Welcome back! Master database unlocked.');
      await bootstrapDashboard();
    } else {
      if (errBox) {
        errBox.textContent = data.error || 'Invalid username or password.';
        errBox.style.display = 'block';
      }
      passwordInput?.select();
      passwordInput?.focus();
    }
  } catch (err) {
    if (errBox) {
      errBox.textContent = `Connection error: ${err.message}`;
      errBox.style.display = 'block';
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
        <span>Sign In as Admin</span>
      `;
    }
  }
}


async function submitGuestAccess() {
  const btn = document.getElementById('btn-enter-guest');
  if (btn) btn.disabled = true;
  try {
    const res = await originalFetch('/api/auth/login-guest', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      currentUserRole = 'guest';
      currentSessionToken = data.token;
      localStorage.setItem('job_accel_session_token', data.token);
      hideAuthGate();
      updateAuthUI();
      showToast('🧪 Guest Sandbox initialized! Your edits are saved to your private local database.');
      await bootstrapDashboard();
    } else {
      showToast('Could not initialize sandbox: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    showToast(`Error initializing guest workspace: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function resetGuestSandbox() {
  if (!confirm('Are you sure you want to reset your Guest Sandbox? This will re-initialize your temporary database with clean demo opportunities.')) {
    return;
  }
  try {
    const res = await fetch('/api/auth/reset-sandbox', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast('Guest Sandbox re-initialized to clean state.');
      await loadStats();
      await loadJobs();
    } else {
      showToast(data.error || 'Reset error');
    }
  } catch (err) {
    showToast(`Reset error: ${err.message}`);
  }
}

async function lockSession() {
  try {
    await originalFetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {}
  localStorage.removeItem('job_accel_session_token');
  currentSessionToken = '';
  currentUserRole = null;
  clearTimeout(telemetryTimer);
  clearInterval(syncPollTimer);
  syncPollTimer = null;
  stopSyncIndicator();
  document.getElementById('telemetry-log-stream').textContent = 'Sign in to view sync activity.';
  isDashboardBootstrapped = false;
  jobsList = [];
  loadJobsSequence++;
  updateAuthUI();
  showAuthGate();
  showToast('Dashboard locked.');
}

function handleAuthAction() {
  if (currentUserRole === 'admin') {
    lockSession();
  } else {
    switchAuthTab('admin');
    showAuthGate();
  }
}

async function bootstrapDashboard() {
  await loadAllUserSettings();
  flushPendingSettings();
  startTelemetryPolling();
  if (isDashboardBootstrapped) {
    await loadStats();
    await loadJobs();
    return;
  }
  isDashboardBootstrapped = true;
  renderSkillChips();
  updateActiveSkillsBadge();
  const isTelemetryCollapsed = localStorage.getItem('job_accel_telemetry_collapsed') !== '0';
  toggleTelemetryCollapse(isTelemetryCollapsed);
  await loadStats();
  await loadJobs();
}

// Lifecycle Bootstrap
document.addEventListener('DOMContentLoaded', async () => {
  const isAuthenticated = await checkAuthStatus();
  if (isAuthenticated) {
    hideAuthGate();
    await bootstrapDashboard();
  } else {
    showAuthGate();
  }
  setupKeyboardNavigation();
});


const viewFilterKeys = new Set(['date_filter', 'role', 'experience_levels', 'platform', 'remote_only', 'hide_senior', 'has_salary_only', 'filter_skills_only']);
function filterViewKey() { return currentViewMode === 'va' ? 'va' : currentStatus; }
function rememberViewFilters() {
  viewFilters[filterViewKey()] = { date: currentDateFilter, role: currentRole, level: currentLevel,
    platform: currentPlatform, remote: remoteOnly, senior: hideSenior, salary: hasSalaryOnly,
    skills: filterBySkillsOnly, search: searchQuery };
  persistSetting('view_filters', JSON.stringify(viewFilters));
}
function restoreViewFilters() {
  const f = viewFilters[filterViewKey()] || {};
  currentDateFilter = f.date || (['saved', 'applied'].includes(currentStatus) ? 'all' : '7days');
  currentRole = f.role || 'All'; currentLevel = f.level || 'All';
  selectedLevels = new Set(currentLevel.split(',')); currentPlatform = f.platform || 'All';
  remoteOnly = Boolean(f.remote); hideSenior = Boolean(f.senior);
  hasSalaryOnly = Boolean(f.salary); filterBySkillsOnly = Boolean(f.skills);
  searchQuery = f.search || '';
  const input = document.getElementById('search-input');
  if (input) input.value = searchQuery;
}

// Universal persistence helper (saves to both localStorage & server SQLite)
let settingWriteQueue = Promise.resolve();
let settingRetryTimer = null;
const SETTINGS_TIMEOUT_MS = 10000;

function pendingSettingsKey(token = currentSessionToken) {
  return `${overrideStorageKey(token)}:settings`;
}
function pendingSettings(token = currentSessionToken) {
  try { return JSON.parse(localStorage.getItem(pendingSettingsKey(token)) || '{}'); }
  catch (_) { return {}; }
}

async function sendSettings(body, token) {
  const controller = new AbortController();
  let timeout;
  try {
    return await Promise.race([
      fetch('/api/settings', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(body), signal: controller.signal }),
      new Promise((_, reject) => {
        timeout = setTimeout(() => { controller.abort(); reject(new Error('Settings save timed out')); }, SETTINGS_TIMEOUT_MS);
      })
    ]);
  } finally { clearTimeout(timeout); }
}

function flushPendingSettings(token = currentSessionToken) {
  settingWriteQueue = settingWriteQueue.catch(() => {}).then(async () => {
    for (let attempt = 0; attempt < 2; attempt++) {
      if (token !== currentSessionToken || !currentUserRole) return;
      const snapshot = pendingSettings(token);
      if (!Object.keys(snapshot).length) return;
      const body = { __revisions: {} };
      for (const [key, entry] of Object.entries(snapshot)) {
        body[key] = entry.value;
        body.__revisions[key] = entry.revision;
      }
      try {
        const response = await sendSettings(body, token);
        if (!response.ok) throw new Error(`Settings save failed (${response.status})`);
        const latest = pendingSettings(token);
        for (const [key, entry] of Object.entries(snapshot)) {
          if (latest[key]?.revision === entry.revision) delete latest[key];
        }
        localStorage.setItem(pendingSettingsKey(token), JSON.stringify(latest));
      } catch (error) { console.warn('Settings remain pending:', error.message); }
    }
    if (token === currentSessionToken && currentUserRole && Object.keys(pendingSettings(token)).length) {
      clearTimeout(settingRetryTimer);
      settingRetryTimer = setTimeout(() => flushPendingSettings(token), 5000);
    }
  });
  return settingWriteQueue;
}

function persistSetting(key, value) {
  if (viewFilterKeys.has(key)) rememberViewFilters();
  try {
    const token = currentSessionToken;
    localStorage.setItem('job_accel_' + key, String(value));
    const pending = pendingSettings(token);
    const clockKey = `${pendingSettingsKey(token)}:revision`;
    const revision = Math.max(Date.now() * 1000, Number(localStorage.getItem(clockKey) || 0) + 1);
    localStorage.setItem(clockKey, String(revision));
    pending[key] = { value: String(value), revision };
    localStorage.setItem(pendingSettingsKey(token), JSON.stringify(pending));
    flushPendingSettings(token);
  } catch (error) { console.warn('Could not queue setting:', error); }
}

// Load persistent user settings and filter toggle states from server SQLite (with localStorage fallback)
async function loadAllUserSettings() {
  let settings = {};

  // 1. Immediate hydration from localStorage to prevent visual flicker
  try {
    settings = {
      target_stack: localStorage.getItem('job_accel_target_stack') || localStorage.getItem('job_accel_user_stack') || CANDIDATE_DEFAULT_STACK,
      filter_skills_only: localStorage.getItem('job_accel_filter_skills_only'),
      has_salary_only: localStorage.getItem('job_accel_has_salary_only'),
      remote_only: localStorage.getItem('job_accel_remote_only'),
      hide_senior: localStorage.getItem('job_accel_hide_senior'),
      date_filter: localStorage.getItem('job_accel_date_filter'),
      role: localStorage.getItem('job_accel_role'),
      experience_levels: localStorage.getItem('job_accel_experience_levels'),
      view_filters: localStorage.getItem('job_accel_view_filters'),
      status: localStorage.getItem('job_accel_status'),
      auto_sync_enabled: localStorage.getItem('job_accel_auto_sync_enabled'),
      proxy_list: localStorage.getItem('job_accel_proxy_list'),
      proxy_mode: localStorage.getItem('job_accel_proxy_mode')
    };
  } catch (e) {}

  // 2. Fetch authoritative settings from server SQLite
  try {
    const res = await fetch('/api/settings');
    if (res.ok) {
      const serverSettings = await res.json();
      if (serverSettings && typeof serverSettings === 'object') {
        settings = { ...settings, ...serverSettings };
      }
    }
  } catch (err) {
    console.warn('Could not load settings from server SQLite, using localStorage fallback:', err);
  }

  for (const [key, entry] of Object.entries(pendingSettings())) settings[key] = entry.value;

  // 3. Hydrate state variables
  if (settings.target_stack && settings.target_stack.trim()) {
    userStack = settings.target_stack.trim();
  } else {
    userStack = CANDIDATE_DEFAULT_STACK;
  }
  localStorage.setItem('job_accel_target_stack', userStack);
  localStorage.setItem('job_accel_user_stack', userStack);

  const stackInput = document.getElementById('user-stack-input');
  if (stackInput) stackInput.value = userStack;

  // On/off filter toggles
  if (settings.filter_skills_only !== undefined && settings.filter_skills_only !== null) {
    filterBySkillsOnly = settings.filter_skills_only === '1' || settings.filter_skills_only === true || settings.filter_skills_only === 'true';
  }
  if (settings.has_salary_only !== undefined && settings.has_salary_only !== null) {
    hasSalaryOnly = settings.has_salary_only === '1' || settings.has_salary_only === true || settings.has_salary_only === 'true';
  }
  if (settings.remote_only !== undefined && settings.remote_only !== null) {
    remoteOnly = settings.remote_only === '1' || settings.remote_only === true || settings.remote_only === 'true';
  }
  if (settings.hide_senior !== undefined && settings.hide_senior !== null) {
    hideSenior = settings.hide_senior === '1' || settings.hide_senior === true || settings.hide_senior === 'true';
  }
  if (settings.va_training_enabled !== undefined && settings.va_training_enabled !== null) {
    vaTrainingEnabled = settings.va_training_enabled === '1' || settings.va_training_enabled === true || settings.va_training_enabled === 'true';
  }
  if (settings.auto_sync_enabled !== undefined && settings.auto_sync_enabled !== null) {
    autoSyncEnabled = settings.auto_sync_enabled === '1' || settings.auto_sync_enabled === true || settings.auto_sync_enabled === 'true';
  }

  if (settings.date_filter) {
    currentDateFilter = settings.date_filter;
  }
  if (settings.role && settings.role !== 'Virtual Assistant') {
    currentRole = settings.role;
  } else {
    currentRole = 'All';
  }
  if (settings.platform) {
    currentPlatform = settings.platform;
  }
  if (settings.status === 'va') {
    currentViewMode = 'va';
    currentStatus = 'new';
  } else if (settings.status) {
    currentStatus = settings.status;
  }

  if (settings.experience_levels) {
    const levels = settings.experience_levels.split(',').map(s => s.trim()).filter(Boolean);
    if (levels.length > 0) {
      selectedLevels = new Set(levels);
      currentLevel = selectedLevels.has('All') ? 'All' : Array.from(selectedLevels).join(',');
    }
  }

  try { viewFilters = JSON.parse(settings.view_filters || '{}'); } catch (_) { viewFilters = {}; }
  if (!viewFilters || typeof viewFilters !== 'object' || Array.isArray(viewFilters)) viewFilters = {};
  restoreViewFilters();
  // 4. Update UI elements to reflect restored toggles & selections
  syncFilterControlsUI();
}

function syncFilterControlsUI() {
  const salaryCb = document.getElementById('salary-only-checkbox');
  if (salaryCb) salaryCb.checked = hasSalaryOnly;

  const remoteCb = document.getElementById('remote-only-checkbox');
  if (remoteCb) remoteCb.checked = remoteOnly;

  const seniorCb = document.getElementById('hide-senior-checkbox');
  if (seniorCb) seniorCb.checked = hideSenior;

  const skillsCb = document.getElementById('skills-only-checkbox');
  if (skillsCb) skillsCb.checked = filterBySkillsOnly;

  const vaTrainingCb = document.getElementById('va-training-checkbox');
  if (vaTrainingCb) vaTrainingCb.checked = vaTrainingEnabled;
  const vaTrainingBtn = document.getElementById('toggle-va-training-btn');
  if (vaTrainingBtn) {
    vaTrainingBtn.classList.toggle('va-active', vaTrainingEnabled);
  }
  const autoSyncCb = document.getElementById('auto-sync-checkbox');
  if (autoSyncCb) autoSyncCb.checked = autoSyncEnabled;

  updateFilterButtonState();

  // Status navigation tabs
  const isVA = currentViewMode === 'va';
  document.querySelectorAll('.status-nav .status-tab').forEach(tab => {
    const val = tab.getAttribute('data-val');
    if (isVA) {
      tab.classList.toggle('active', val === 'va');
    } else {
      tab.classList.toggle('active', val === currentStatus);
    }
  });

  // When in VA mode, dim Role Focus chips because all listings in this view are VA
  const roleGroupCell = document.getElementById('role-group')?.closest('.filter-cell');
  if (roleGroupCell) {
    roleGroupCell.style.opacity = isVA ? '0.45' : '1';
    roleGroupCell.style.pointerEvents = isVA ? 'none' : 'auto';
  }

  // Date filter chips
  document.querySelectorAll('#date-group .filter-chip').forEach(chip => {
    const val = chip.getAttribute('data-val');
    chip.classList.toggle('active', val === currentDateFilter);
  });

  // Role focus chips
  document.querySelectorAll('#role-group .filter-chip').forEach(chip => {
    const val = chip.getAttribute('data-val');
    chip.classList.toggle('active', val === currentRole);
  });

  const platformSelect = document.getElementById('platform-select');
  if (platformSelect) {
    if ([...platformSelect.options].some(option => option.value === currentPlatform)) {
      platformSelect.value = currentPlatform;
    } else {
      currentPlatform = 'All';
      platformSelect.value = 'All';
    }
  }

  // Seniority chips
  document.querySelectorAll('#level-group .filter-chip').forEach(chip => {
    const val = chip.getAttribute('data-val');
    chip.classList.toggle('active', selectedLevels.has(val));
  });
}

// Backward-compatible alias
async function loadStackSettings() {
  return loadAllUserSettings();
}

// Load stats from server
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    currentStats = data;

    const setNum = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val || 0;
    };

    setNum('stat-new', data.new);
    setNum('stat-saved', data.saved);
    setNum('stat-applied', data.applied);
    setNum('stat-ignored', data.ignored);
    setNum('stat-va', data.va);

    renderPipelineSummary(data.by_stage || {});
  } catch (err) {
    console.error('Failed to load telemetry stats:', err);
  }
}

// Render pipeline summary badges in the Applications hub header
function renderPipelineSummary(byStage) {
  const container = document.getElementById('pipeline-stages-summary');
  if (!container) return;
  container.innerHTML = PIPELINE_STAGES.map(s => {
    const count = byStage[s.key] || 0;
    return `
      <div class="stage-stat-pill stage-${s.key}">
        <span class="stage-stat-label">${s.label}</span>
        <span class="stage-stat-num">${count}</span>
      </div>
    `;
  }).join('');
}

// Drawer Toggle
function toggleStackDrawer() {
  const drawer = document.getElementById('stack-drawer');
  if (!drawer) return;
  if (drawer.style.display === 'none' || !drawer.style.display) {
    drawer.style.display = 'block';
    renderSkillMatrix();
    const input = document.getElementById('manual-keyword-input');
    if (input) setTimeout(() => input.focus(), 60);
  } else {
    drawer.style.display = 'none';
  }
}

function updateActiveSkillsBadge() {
  const active = getActiveSkills();
  const headerBadge = document.getElementById('active-skills-count');
  if (headerBadge) {
    headerBadge.textContent = active.length;
  }
  const drawerBadge = document.getElementById('matrix-active-count-badge');
  if (drawerBadge) {
    drawerBadge.textContent = `${active.length} Active`;
  }
}

// Load jobs with current filters
let loadJobsSequence = 0;
async function loadJobs() {
  const sequence = ++loadJobsSequence;
  const token = currentSessionToken;
  const feed = document.getElementById('job-feed');
  feed.innerHTML = `
    <div class="state-loading">
      <div class="loading-spinner"></div>
      <p>Scanning job opportunities across platforms...</p>
    </div>
  `;

  const pipelineHeader = document.getElementById('pipeline-hub-header');
  const activeView = typeof currentViewMode !== 'undefined' ? currentViewMode : 'tech';
  if (pipelineHeader) {
    pipelineHeader.style.display = (activeView === 'tech' && currentStatus === 'applied') ? 'block' : 'none';
  }

  try {
    const isVA = activeView === 'va';
    const params = new URLSearchParams({
      status: isVA ? 'all' : currentStatus,
      role: isVA ? 'Virtual Assistant' : currentRole,
      experience_level: isVA ? 'All' : currentLevel,
      search: searchQuery,
      date_filter: currentDateFilter
    });
    if (hasSalaryOnly) params.set('has_salary', '1');
    if (isVA || remoteOnly) params.set('remote_only', '1');
    if (!isVA && hideSenior) params.set('hide_senior', '1');
    if (isVA || vaTrainingEnabled || currentRole === 'Virtual Assistant') {
      params.set('include_va', '1');
    }
    if (currentPlatform && currentPlatform !== 'All') {
      params.set('platform', currentPlatform);
    }

    params.set('limit', '500');
    let jobs = [];
    let hasMore = true;
    while (hasMore) {
      if (sequence !== loadJobsSequence || token !== currentSessionToken) return;
      params.set('offset', String(jobs.length));
      const res = await resilientFetchWithRetry(`/api/jobs?${params.toString()}`, {}, 3);
      if (!res.ok) throw new Error(`Unable to load jobs (${res.status})`);
      const data = await res.json();
      const page = data.jobs || [];
      jobs.push(...page);
      hasMore = Boolean(data.has_more) && page.length > 0;
    }
    if (sequence !== loadJobsSequence || token !== currentSessionToken) return;

    // Local-First Overrides Overlay
    const overrides = getLocalStatusOverrides();
    jobs.forEach(j => {
      const ov = overrides[String(j.id)];
      if (ov) {
        if (ov.status !== undefined && ov.status !== null) j.status = ov.status;
        if (ov.notes !== undefined && ov.notes !== null) j.notes = ov.notes;
        if (ov.stage !== undefined && ov.stage !== null) j.pipeline_stage = ov.stage;
        if (ov.follow_up_date !== undefined && ov.follow_up_date !== null) j.follow_up_date = ov.follow_up_date;
        if (ov.applied_at) j.applied_at = ov.applied_at;
      }
    });

    // Filter out jobs whose overridden status doesn't match currentStatus
    if (!isVA && currentStatus !== 'all') {
      jobs = jobs.filter(j => (j.status || 'new') === currentStatus);
    } else if (isVA) {
      if (currentStatus === 'ignored') {
        jobs = jobs.filter(j => j.status === 'ignored');
      } else {
        jobs = jobs.filter(j => j.status !== 'ignored');
      }
    }

    // Inject any locally saved/applied jobs that the server might not have yet (e.g. serverless cold start / lag)
    if (currentStatus === 'applied' || currentStatus === 'saved') {
      const existingIds = new Set(jobs.map(j => j.id));
      for (const [idStr, ov] of Object.entries(overrides)) {
        const idNum = parseInt(idStr, 10);
        if (!existingIds.has(idNum) && ov.status === currentStatus && ov.job) {
          const injectedJob = { ...ov.job };
          injectedJob.status = ov.status;
          if (ov.notes) injectedJob.notes = ov.notes;
          if (ov.stage) injectedJob.pipeline_stage = ov.stage;
          if (ov.follow_up_date) injectedJob.follow_up_date = ov.follow_up_date;
          if (ov.applied_at) injectedJob.applied_at = ov.applied_at;
          jobs.unshift(injectedJob);
        }
      }
    }

    // Client-side Senior suppression
    if (hideSenior && !selectedLevels.has('Senior / Lead')) {
      const seniorRegex = /\b(senior|sr\.?|lead|principal|staff|architect|director|manager)\b/i;
      jobs = jobs.filter(j => j.experience_level !== 'Senior / Lead' && !seniorRegex.test(j.title));
    }

    // Client-side Filter by Selected Skills
    if (filterBySkillsOnly && userStack.trim()) {
      jobs = jobs.filter(j => getSkillsMatch(j).count > 0);
    }

    jobsList = jobs;
    selectedIndex = 0;
    renderJobs();
    updateSummaryText(jobs.length);
  } catch (err) {
    if (sequence !== loadJobsSequence || token !== currentSessionToken) return;
    feed.innerHTML = `
      <div class="state-empty">
        <p>Error retrieving opportunities: ${escapeHtml(err.message)}</p>
        <span class="sub-text">Check server connectivity on localhost:8000</span>
      </div>`;
  }
}

// Skills matching calculator
function getSkillsMatch(job) {
  if (!userStack || !userStack.trim()) return { count: 0, matched: [] };
  const tokens = userStack.split(',').map(s => s.trim()).filter(Boolean);
  const targetText = `${job.title} ${job.company || ''} ${job.location || ''} ${job.role_category || ''} ${job.experience_level || ''} ${job.notes || ''}`.toLowerCase();

  const matched = [];
  for (const token of tokens) {
    const subParts = token.includes('/') ? token.split('/').map(p => p.trim()) : [token];
    let isMatch = false;

    for (const part of subParts) {
      if (!part) continue;
      const cleanPart = part.toLowerCase();
      if (cleanPart === 'junior' || cleanPart === 'entry' || cleanPart === 'junior / entry') {
        isMatch = job.experience_level === 'Junior / Entry';
        if (!job.experience_level || job.experience_level === 'Unspecified') {
          isMatch = /\b(junior|jr\.?|entry[- ]level|associate|intern(?:ship)?|trainee|fresh grad|early career|ojt)\b/i.test(job.title || '');
        }
        if (isMatch) break;
        continue;
      }
      if (cleanPart === 'full stack' && (targetText.includes('fullstack') || targetText.includes('full stack'))) {
        isMatch = true;
        break;
      }
      if (cleanPart === 'node.js' && (targetText.includes('node.js') || targetText.includes('nodejs') || targetText.includes('node '))) {
        isMatch = true;
        break;
      }
      if ((cleanPart === 'c#' || cleanPart === '.net' || cleanPart === 'c# / .net') &&
          (targetText.includes('c#') || targetText.includes('.net') || targetText.includes('dotnet') || targetText.includes('csharp'))) {
        isMatch = true;
        break;
      }
      if (cleanPart === 'c++' && (targetText.includes('c++') || targetText.includes('cpp'))) {
        isMatch = true;
        break;
      }
      if ((cleanPart === 'kmp' || cleanPart === 'kmm' || cleanPart === 'compose multiplatform' || cleanPart === 'kotlin multiplatform') &&
          (targetText.includes('kmp') || targetText.includes('kmm') || targetText.includes('compose multiplatform') || targetText.includes('kotlin multiplatform'))) {
        isMatch = true;
        break;
      }
      if ((cleanPart === 'android media3' || cleanPart === 'media3' || cleanPart === 'exoplayer') &&
          (targetText.includes('media3') || targetText.includes('exoplayer'))) {
        isMatch = true;
        break;
      }
      if ((cleanPart === 'ci/cd' || cleanPart === 'cicd') &&
          (targetText.includes('ci/cd') || targetText.includes('cicd') || targetText.includes('continuous integration'))) {
        isMatch = true;
        break;
      }
      if ((cleanPart === 'qa' || cleanPart === 'sdet' || cleanPart === 'qa automation') &&
          (targetText.includes('qa') || targetText.includes('sdet') || targetText.includes('quality assurance') || targetText.includes('testing'))) {
        isMatch = true;
        break;
      }
      const escaped = part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(^|\\W)${escaped}(\\W|$)`, 'i');
      if (regex.test(targetText)) {
        isMatch = true;
        break;
      }
    }

    if (isMatch) {
      matched.push(token);
    }
  }
  return { count: matched.length, matched };
}

// Chip & Stack helpers
function getActiveSkills() {
  if (!userStack || !userStack.trim()) return [];
  return userStack.split(',').map(s => s.trim()).filter(Boolean);
}

function renderSkillMatrix() {
  renderActiveStackStrip();
  const activeContainer = document.getElementById('active-tags-container');
  const categoriesContainer = document.getElementById('preset-categories-container');
  const activeList = getActiveSkills();
  const activeSet = new Set(activeList.map(s => s.toLowerCase()));

  // 1. Render active tags flex with 1-click remove
  if (activeContainer) {
    if (activeList.length === 0) {
      activeContainer.innerHTML = `<span class="empty-tags-hint">No active keywords. Type a custom skill above or click quick-add presets below.</span>`;
    } else {
      activeContainer.innerHTML = activeList.map(skill => `
        <span class="active-tag-pill">
          <span>${escapeHtml(skill)}</span>
          <button type="button" class="btn-remove-tag" data-skill="${escapeHtml(skill)}" onclick="removeSkill(this.dataset.skill)" title="Remove ${escapeHtml(skill)}" aria-label="Remove ${escapeHtml(skill)}">&times;</button>
        </span>
      `).join('');
    }
  }

  // 2. Render categorized presets grid
  if (categoriesContainer) {
    categoriesContainer.innerHTML = PRESET_CATEGORIES.map(cat => `
      <div class="preset-category-block">
        <span class="preset-category-title">${escapeHtml(cat.category)}</span>
        <div class="preset-chips-flex">
          ${cat.skills.map(skill => {
            const isActive = activeSet.has(skill.toLowerCase());
            return `
              <button type="button"
                      class="preset-chip ${isActive ? 'active' : ''}"
                      onclick="toggleSkill('${escapeHtml(skill)}')"
                      title="${isActive ? 'Remove ' + skill : 'Add ' + skill}">
                <span>${escapeHtml(skill)}</span>
                <span class="chip-symbol">${isActive ? '✓' : '+'}</span>
              </button>
            `;
          }).join('')}
        </div>
      </div>
    `).join('');
  }

  updateFilterButtonState();
  updateActiveSkillsBadge();
}

let isMatrixCollapsed = localStorage.getItem('job_accel_matrix_collapsed') !== '0';

function toggleActiveMatrixCollapse() {
  isMatrixCollapsed = !isMatrixCollapsed;
  localStorage.setItem('job_accel_matrix_collapsed', isMatrixCollapsed ? '1' : '0');
  updateMatrixCollapsedState();
}

function updateMatrixCollapsedState() {
  const strip = document.getElementById('active-stack-strip');
  const label = document.getElementById('strip-collapse-label');
  const activeList = getActiveSkills();

  if (strip) {
    strip.classList.toggle('is-collapsed', isMatrixCollapsed);
  }
  if (label) {
    label.textContent = isMatrixCollapsed ? `Show Chips (${activeList.length})` : 'Collapse';
  }
}

// Render dashboard active stack strip (with collapsible support)
function renderActiveStackStrip() {
  const chipsContainer = document.getElementById('strip-active-chips');
  const countBadge = document.getElementById('strip-active-count');
  const previewContainer = document.getElementById('strip-preview-inline');
  const activeList = getActiveSkills();

  if (countBadge) {
    countBadge.textContent = `${activeList.length} Active`;
  }

  if (previewContainer) {
    if (activeList.length === 0) {
      previewContainer.innerHTML = `<span class="strip-preview-empty" style="color: var(--text-tertiary); font-size: 0.72rem;">(No active skills)</span>`;
    } else {
      const topFew = activeList.slice(0, 4);
      const remaining = activeList.length - topFew.length;
      previewContainer.innerHTML = topFew.map(s => `<span class="strip-preview-pill">${escapeHtml(s)}</span>`).join('') +
        (remaining > 0 ? `<span class="strip-preview-more">+${remaining} more</span>` : '');
    }
  }

  updateMatrixCollapsedState();

  if (!chipsContainer) return;

  if (activeList.length === 0) {
    chipsContainer.innerHTML = `
      <div class="strip-empty-prompt">
        <span>No keywords active in stack matrix. Opportunities cannot be scored.</span>
        <button type="button" class="btn-strip-action" onclick="resetToCandidateProfile()">Load Candidate Stack</button>
      </div>
    `;
    return;
  }

  chipsContainer.innerHTML = activeList.map(skill => `
    <span class="strip-tag-pill">
      <span>${escapeHtml(skill)}</span>
      <button type="button" class="btn-strip-remove-tag" data-skill="${escapeHtml(skill)}" onclick="removeSkill(this.dataset.skill)" title="Remove ${escapeHtml(skill)}" aria-label="Remove ${escapeHtml(skill)}">&times;</button>
    </span>
  `).join('');
}

// Backward-compatible alias
function renderSkillChips() {
  renderSkillMatrix();
}

function addManualKeyword() {
  const input = document.getElementById('manual-keyword-input');
  if (!input) return;
  const raw = input.value.trim();
  if (!raw) return;

  const tokens = raw.split(',').map(s => s.trim()).filter(Boolean);
  let activeList = getActiveSkills();
  let addedCount = 0;

  for (const token of tokens) {
    if (!activeList.some(s => s.toLowerCase() === token.toLowerCase())) {
      activeList.push(token);
      addedCount++;
    }
  }

  if (addedCount > 0) {
    saveActiveSkills(activeList);
    showToast(`Added ${addedCount === 1 ? `"${tokens[0]}"` : `${addedCount} keywords`} to target stack.`);
  } else {
    showToast(`Keyword "${tokens[0]}" is already active in your stack.`);
  }

  input.value = '';
  input.focus();
}

function handleManualKeywordKeyDown(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    addManualKeyword();
  } else if (event.key === ',' && !event.shiftKey) {
    event.preventDefault();
    addManualKeyword();
  }
}

function removeSkill(skill) {
  let activeList = getActiveSkills();
  const lower = skill.toLowerCase();
  activeList = activeList.filter(s => s.toLowerCase() !== lower);
  saveActiveSkills(activeList);
  showToast(`Removed "${skill}".`);
}

function saveActiveSkills(activeList) {
  userStack = activeList.join(', ');
  const hiddenInput = document.getElementById('user-stack-input');
  if (hiddenInput) hiddenInput.value = userStack;
  persistSetting('target_stack', userStack);

  renderSkillMatrix();
  if (filterBySkillsOnly) {
    loadJobs();
  } else {
    renderJobs();
    updateSummaryText(jobsList.length);
  }
}

function toggleSkill(skill) {
  let activeList = getActiveSkills();
  const lower = skill.toLowerCase();
  const existingIdx = activeList.findIndex(s => s.toLowerCase() === lower);

  if (existingIdx >= 0) {
    activeList.splice(existingIdx, 1);
  } else {
    activeList.push(skill);
  }

  saveActiveSkills(activeList);
}

function resetToCandidateProfile() {
  const verifiedStack = [
    'Kotlin', 'Jetpack Compose', 'Android Media3', 'React', 'Next.js',
    'TypeScript', 'Node.js', 'Express', 'MySQL', 'Tailwind CSS', 'Junior / Entry'
  ];
  saveActiveSkills(verifiedStack);
  showToast('Reset to candidate verified stack profile (Louis Michael Ricafrente).');
}

function selectAllSkills() {
  const all = [...PRESET_SKILLS];
  saveActiveSkills(all);
  showToast('All preset skills selected.');
}

function clearAllSkills() {
  saveActiveSkills([]);
  showToast('All keywords cleared from stack matrix.');
}

function toggleFilterBySkills() {
  filterBySkillsOnly = !filterBySkillsOnly;
  persistSetting('filter_skills_only', filterBySkillsOnly ? '1' : '0');
  updateFilterButtonState();
  loadJobs();
}

function toggleSkillsOnly(checkbox) {
  filterBySkillsOnly = checkbox.checked;
  persistSetting('filter_skills_only', filterBySkillsOnly ? '1' : '0');
  updateFilterButtonState();
  loadJobs();
}

function updateFilterButtonState() {
  const btn = document.getElementById('filter-by-skills-btn');
  const cb = document.getElementById('skills-only-checkbox');
  if (cb) cb.checked = filterBySkillsOnly;
  if (btn) {
    if (filterBySkillsOnly) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  }
}

function toggleVaTraining() {
  vaTrainingEnabled = !vaTrainingEnabled;
  localStorage.setItem('job_accel_va_training_enabled', vaTrainingEnabled.toString());
  persistSetting('va_training_enabled', vaTrainingEnabled ? '1' : '0');
  syncFilterControlsUI();
  showToast(vaTrainingEnabled ? 'VA jobs will appear in the main inbox.' : 'VA jobs stay in the Remote VA tab.');
  loadJobs();
}

function toggleVaTrainingCheckbox(checkbox) {
  vaTrainingEnabled = checkbox.checked;
  localStorage.setItem('job_accel_va_training_enabled', vaTrainingEnabled.toString());
  persistSetting('va_training_enabled', vaTrainingEnabled ? '1' : '0');
  syncFilterControlsUI();
  showToast(vaTrainingEnabled ? 'VA jobs will appear in the main inbox.' : 'VA jobs stay in the Remote VA tab.');
  loadJobs();
}

function toggleAutoSync(checkbox) {
  autoSyncEnabled = checkbox.checked;
  localStorage.setItem('job_accel_auto_sync_enabled', String(autoSyncEnabled));
  persistSetting('auto_sync_enabled', autoSyncEnabled ? '1' : '0');
  showToast(autoSyncEnabled ? 'Automatic cloud sync enabled. It runs on the server schedule.' : 'Automatic job sync paused.');
}

// Calculate days since a given date string
function getDaysSince(dateStr) {
  if (!dateStr) return 0;
  try {
    const target = new Date(dateStr.slice(0, 10));
    const now = new Date();
    const diff = Math.max(0, Math.floor((now - target) / (1000 * 60 * 60 * 24)));
    return isNaN(diff) ? 0 : diff;
  } catch {
    return 0;
  }
}

// 1-Click Tailored Pitch Generator (Strictly Anti-Slop: No generic buzzwords, no em dashes)
function generateTailoredPitch(job) {
  const match = getSkillsMatch(job);
  const techTokens = match.matched.filter(t => !/^(junior|senior|mid|entry|lead|intern|full stack|developer|engineer)$/i.test(t));
  const titleLower = (job.title || '').toLowerCase();

  let techSummary = 'modern full-stack web engineering and scalable backend architecture';
  if (techTokens.length > 0) {
    techSummary = techTokens.slice(0, 3).join(', ');
  } else if (titleLower.includes('android') || titleLower.includes('mobile') || titleLower.includes('kotlin') || job.role_category === 'Mobile') {
    techSummary = 'Kotlin Android development, Jetpack Compose, and modern mobile architecture';
  } else if (titleLower.includes('frontend') || titleLower.includes('react') || job.role_category === 'Frontend') {
    techSummary = 'React, TypeScript, Next.js, and responsive frontend systems';
  } else if (titleLower.includes('backend') || titleLower.includes('node') || job.role_category === 'Backend') {
    techSummary = 'Node.js, Express, REST APIs, and relational databases';
  } else if (job.role_category === 'Data/AI/ML' || titleLower.includes('data') || titleLower.includes('ai')) {
    techSummary = 'Python data processing, ML pipeline automation, and analytics';
  }

  return `Hi ${job.company} Team,\n\nI am reaching out regarding the ${job.title} role. With hands-on software development experience across ${techSummary}, I focus on writing reliable code and delivering clean user experiences. I would welcome an opportunity to discuss how my background aligns with your engineering goals.\n\nBest regards,\nLouis Michael Ricafrente`;
}

// Copy pitch to clipboard
function copyTailoredPitch(jobId, event) {
  if (event) event.stopPropagation();
  const job = jobsList.find(j => j.id === jobId);
  if (!job) return;

  const pitch = generateTailoredPitch(job);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(pitch).then(() => {
      showToast(`Tailored pitch copied for ${job.company}.`);
    }).catch(() => {
      fallbackCopy(pitch, job.company);
    });
  } else {
    fallbackCopy(pitch, job.company);
  }
}

function fallbackCopy(text, company) {
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  showToast(`Tailored pitch copied for ${company}.`);
}

// Show toast notification with optional Undo / action button
function showToast(message, actionText = null, onAction = null) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast-item';

  const textSpan = document.createElement('span');
  textSpan.textContent = message;
  toast.appendChild(textSpan);

  if (actionText && typeof onAction === 'function') {
    const btn = document.createElement('button');
    btn.className = 'toast-undo-btn';
    btn.type = 'button';
    btn.textContent = actionText;
    btn.onclick = (e) => {
      e.stopPropagation();
      toast.remove();
      onAction();
    };
    toast.appendChild(btn);
  }

  container.appendChild(toast);
  const duration = actionText ? 5000 : 2800;
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Render cards
function renderJobs() {
  const feed = document.getElementById('job-feed');
  let headerHtml = '';
  if (currentViewMode === 'va') {
    headerHtml = `
      <div class="va-view-header">
        <div class="va-view-info">
          <span class="va-view-badge">Remote VA Feed</span>
          <span class="va-view-text">Showing <strong>${jobsList.length}</strong> Virtual Assistant &amp; remote support opportunities.</span>
        </div>
        <button type="button" class="btn-return-tech" onclick="switchToTechMode()" title="Return to Software &amp; Tech Engineering jobs">
          ← Back to Tech Jobs
        </button>
      </div>
    `;
  }

  if (jobsList.length === 0) {
    feed.innerHTML = headerHtml + renderEmptyStateHtml();
    return;
  }

  feed.innerHTML = headerHtml + jobsList.map((job, idx) => {
    const isSelected = idx === selectedIndex ? 'selected' : '';

    // Level badge class
    let levelClass = 'badge-level-mid';
    if (job.experience_level.includes('Junior') || job.experience_level.includes('Entry')) {
      levelClass = 'badge-level-junior';
    } else if (job.experience_level.includes('Senior') || job.experience_level.includes('Lead')) {
      levelClass = 'badge-level-senior';
    }

    const skillsMatch = getSkillsMatch(job);

    // Follow-up indicator logic
    const currentStage = job.pipeline_stage || 'applied';
    const appliedDays = getDaysSince(job.applied_at || job.date_posted || job.created_at);
    let followUpBadge = '';
    if (job.status === 'applied') {
      if (currentStage === 'applied' && appliedDays >= 5) {
        followUpBadge = `<span class="badge-followup-due" title="Applied ${appliedDays} days ago without status update">Follow-up due (${appliedDays}d)</span>`;
      } else if (currentStage === 'offer') {
        followUpBadge = `<span class="badge-offer-stage">Offer Received</span>`;
      } else if (currentStage !== 'rejected') {
        followUpBadge = `<span class="badge-date date-recent">${appliedDays}d in pipeline</span>`;
      }
    }

    const isAppliedView = currentStatus === 'applied';

    return `
      <div class="job-card ${isSelected}" id="job-card-${idx}" onclick="selectCard(${idx})">
        <div class="job-main-block">
          <div class="job-headline">
            <a href="${escapeHtml(safeJobUrl(job.job_url))}" target="_blank" rel="noopener noreferrer"
               class="job-title-link" onclick="event.stopPropagation()">
              ${escapeHtml(job.title)}
            </a>
            <span class="company-identifier">@ ${escapeHtml(job.company)}</span>
            ${followUpBadge}
          </div>

          <div class="job-meta-row">
            ${(() => {
              const sources = Array.isArray(job.sources) && job.sources.length > 0
                ? job.sources
                : [{ platform: job.platform, url: job.job_url }];

              if (sources.length > 1) {
                return `
                  <div class="multi-platform-group" title="Available on ${sources.length} job boards">
                    <span class="multi-platform-label">Available on:</span>
                    ${sources.map(s => `
                      <a href="${escapeHtml(safeJobUrl(s.url))}" target="_blank" rel="noopener noreferrer"
                         class="badge-platform badge-source-link multi-source-badge"
                         onclick="event.stopPropagation()"
                         title="Open on ${escapeHtml(s.platform)}">
                        ${escapeHtml(s.platform)} ↗
                      </a>
                    `).join('')}
                  </div>
                `;
              }
              const single = sources[0];
              return `
                <a href="${escapeHtml(safeJobUrl(single.url || job.job_url))}" target="_blank" rel="noopener noreferrer"
                   class="badge-platform badge-source-link"
                   onclick="event.stopPropagation()"
                   title="Open on ${escapeHtml(single.platform || job.platform)}">
                  ${escapeHtml(single.platform || job.platform)} ↗
                </a>
              `;
            })()}
            <span class="badge-level ${levelClass}">${escapeHtml(job.experience_level)}</span>
            <span class="job-location-tag">${escapeHtml((!job.location || job.location.toLowerCase() === 'nan' || job.location === 'None') ? 'Remote / Philippines' : job.location)}</span>
            ${(job.salary && job.salary.toLowerCase() !== 'nan' && job.salary !== 'None') ? `<span class="job-salary-tag">${escapeHtml(job.salary)}</span>` : ''}
            ${skillsMatch.count > 0 ? `<span class="job-skills-matched">Match: ${escapeHtml(skillsMatch.matched.join(', '))}</span>` : ''}
            ${formatPostingDate(job.date_posted)}
          </div>

          ${job.description ? `<details class="job-description" onclick="event.stopPropagation()">
              <summary>Read saved job details</summary>
              <p class="job-description-note">Source-provided text; some sites supply only a preview.</p>
              <div class="job-description-body">${escapeHtml(job.description)}</div>
            </details>` : ''}

            ${isAppliedView ? `
            <div class="pipeline-card-controls" onclick="event.stopPropagation()">
              <div class="stage-select-wrapper">
                <label class="stage-label-text">Stage:</label>
                <select class="stage-dropdown" onchange="changeJobStage(${job.id}, this.value)">
                  ${PIPELINE_STAGES.map(s => `
                    <option value="${s.key}" ${currentStage === s.key ? 'selected' : ''}>${s.label}</option>
                  `).join('')}
                </select>
              </div>
              <div class="followup-input-wrapper" title="Set follow-up reminder date">
                <label class="stage-label-text">Follow Up:</label>
                <input type="date" class="followup-date-input"
                       value="${escapeHtml(job.follow_up_date ? job.follow_up_date.slice(0, 10) : '')}"
                       onchange="saveJobFollowUp(${job.id}, this.value)">
              </div>
              <div class="notes-input-wrapper">
                <input type="text" class="notes-text-input" placeholder="Recruiter notes or assessment deadline..."
                       value="${escapeHtml(job.notes || '')}" onblur="saveJobNotes(${job.id}, this.value)"
                       onkeydown="if(event.key==='Enter')this.blur()">
                <button type="button" id="note-save-${job.id}" class="note-save-state" aria-live="polite"
                        ${getLocalStatusOverrides()[String(job.id)]?.save_state === 'failed' ? '' : 'disabled'}
                        onclick="retryNoteSave(${job.id})">${getLocalStatusOverrides()[String(job.id)]?.save_state === 'failed' ? 'Failed - retry' : getLocalStatusOverrides()[String(job.id)] ? 'Pending' : 'Saved'}</button>
              </div>
            </div>
          ` : ''}
        </div>

        <div class="card-actions-cluster" onclick="event.stopPropagation()">
          <a href="${escapeHtml(safeJobUrl(job.job_url))}" target="_blank" rel="noopener noreferrer"
             class="btn-card-apply" onclick="handleApplyClick(event, ${job.id})">
            <span>${isAppliedView ? 'Open' : 'Apply'}</span>
            ${ICONS.external}
          </a>

          <button class="btn-icon-action ${job.status === 'applied' ? 'is-applied' : ''}"
                  title="Mark as Applied" onclick="updateJobStatus(${job.id}, 'applied')">
            ${ICONS.check}
          </button>

          <button class="btn-icon-action ${job.status === 'saved' ? 'is-saved' : ''}"
                  title="Save Opportunity" onclick="updateJobStatus(${job.id}, 'saved')">
            ${ICONS.star}
          </button>

          <button class="btn-icon-action action-dismiss"
                  title="Archive Opportunity" onclick="updateJobStatus(${job.id}, 'ignored')">
            ${ICONS.dismiss}
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

// Apply button handler (Instant non-blocking local-first update with 1-click Undo)
function handleApplyClick(e, jobId) {
  const job = jobsList.find(j => j.id === jobId);
  if (!job) return;

  // In applied view, simply let the external link open
  if (currentStatus === 'applied' || job.status === 'applied') {
    return;
  }

  updateJobStatus(jobId, 'applied');
}

// Stage change handler
function changeJobStage(jobId, stage) {
  updateJobStatus(jobId, 'applied', null, stage);
}

// Save inline notes
function saveJobNotes(jobId, newNotes) {
  const job = jobsList.find(j => j.id === jobId);
  if (job && (job.notes || '') !== newNotes) {
    updateJobStatus(jobId, null, newNotes);
  }
}

// Save follow-up reminder date
function saveJobFollowUp(jobId, newDate) {
  const job = jobsList.find(j => j.id === jobId);
  if (job) {
    job.follow_up_date = newDate;
    updateJobStatus(jobId, null, null, null, newDate).then(() => {
      showToast(newDate ? `Follow-up set for ${newDate}.` : 'Follow-up date cleared.');
    });
  }
}

// Interactive & Actionable Empty State
function renderEmptyStateHtml() {
  const isVa = currentViewMode === 'va';
  const activeFilters = [];

  if (searchQuery && searchQuery.trim()) {
    activeFilters.push({ label: `Search: "${searchQuery}"`, action: 'clearSearchInput()' });
  }
  if (currentRole && currentRole !== 'All') {
    activeFilters.push({ label: `Role: ${currentRole}`, action: `setRole('All', document.querySelector('#role-group button[data-val="All"]'))` });
  }
  if (selectedLevels && !selectedLevels.has('All') && selectedLevels.size > 0) {
    const levelsStr = Array.from(selectedLevels).join(', ');
    activeFilters.push({ label: `Seniority: ${levelsStr}`, action: `setLevel('All', document.querySelector('#level-group button[data-val="All"]'))` });
  }
  if (currentDateFilter && currentDateFilter !== '15days' && currentDateFilter !== 'all') {
    const dateLabels = { today: 'Today', '3days': 'Past 3 days', '7days': 'Past 7 days' };
    activeFilters.push({ label: `Date: ${dateLabels[currentDateFilter] || currentDateFilter}`, action: `setDateFilter('15days', document.querySelector('#date-group button[data-val="15days"]'))` });
  }
  if (currentPlatform && currentPlatform !== 'All') {
    activeFilters.push({ label: `Site: ${currentPlatform}`, action: `setPlatform('All', document.getElementById('platform-select'))` });
  }
  if (filterBySkillsOnly) {
    activeFilters.push({ label: 'Match Stack Only', action: 'toggleFilterBySkills()' });
  }

  const chipsHtml = activeFilters.map(f => `
    <button type="button" class="empty-filter-pill" onclick="${f.action}" title="Click to remove this filter">
      <span>${escapeHtml(f.label)}</span>
      <span class="pill-remove">&times;</span>
    </button>
  `).join('');

  return `
    <div class="state-empty enhanced-empty-state">
      <div class="empty-state-icon-wrap">
        <svg class="empty-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/>
          <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          <line x1="8" y1="11" x2="14" y2="11"/>
        </svg>
      </div>
      <h3 class="empty-state-title">${isVa ? 'No Virtual Assistant opportunities match active filters' : 'No job opportunities match active criteria'}</h3>
      <p class="empty-state-desc">
        ${activeFilters.length > 0
          ? 'Your active filters narrowed the view to 0 results. You can remove individual filters below or reset everything to explore the full inventory.'
          : 'No postings are currently indexed for this view. Click "Sync Job Sites" to scan connected boards.'}
      </p>

      ${activeFilters.length > 0 ? `
        <div class="empty-active-filters">
          <span class="empty-filters-label">Active constraints</span>
          <div class="empty-pills-row">
            ${chipsHtml}
          </div>
        </div>
      ` : ''}

      <div class="empty-actions-row">
        <button type="button" class="btn-primary" onclick="resetAllFeedFilters()">
          <svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          <span>Reset All Filters</span>
        </button>
        ${currentDateFilter !== '15days' && currentDateFilter !== 'all' ? `
          <button type="button" class="btn-secondary" onclick="setDateFilter('15days', document.querySelector('#date-group button[data-val=\\'15days\\']'))">
            <span>Expand to Past 15d</span>
          </button>
        ` : ''}
        ${selectedLevels && !selectedLevels.has('All') ? `
          <button type="button" class="btn-secondary" onclick="setLevel('All', document.querySelector('#level-group button[data-val=\\'All\\']'))">
            <span>All Experience Levels</span>
          </button>
        ` : ''}
        <button type="button" class="btn-secondary" onclick="triggerSync()">
          <svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
            <path d="M16 21h5v-5"/>
          </svg>
          <span>Sync Job Sites</span>
        </button>
      </div>
    </div>
  `;
}

function resetAllFeedFilters() {
  searchQuery = '';
  const searchInput = document.getElementById('search-input');
  if (searchInput) searchInput.value = '';
  const clearBtn = document.getElementById('clear-search-btn');
  if (clearBtn) clearBtn.style.display = 'none';

  currentRole = 'All';
  document.querySelectorAll('#role-group .filter-chip').forEach(c => {
    c.classList.toggle('active', c.dataset.val === 'All');
  });

  selectedLevels.clear();
  selectedLevels.add('All');
  document.querySelectorAll('#level-group .filter-chip').forEach(c => {
    c.classList.toggle('active', c.dataset.val === 'All');
  });

  currentDateFilter = '15days';
  document.querySelectorAll('#date-group .filter-chip').forEach(c => {
    c.classList.toggle('active', c.dataset.val === '15days');
  });

  currentPlatform = 'All';
  const platformSelect = document.getElementById('platform-select');
  if (platformSelect) platformSelect.value = 'All';

  if (filterBySkillsOnly) {
    filterBySkillsOnly = false;
    const btn = document.getElementById('filter-by-skills-btn');
    if (btn) btn.classList.remove('active');
  }

  rememberViewFilters();
  persistSetting('date_filter', '15days');
  persistSetting('level', 'All');
  persistSetting('role', 'All');
  persistSetting('platform', 'All');
  loadJobs();
  showToast('Filters reset to full 15-day inventory.', 'info');
}

// Update status via API (Optimistic in-place update with Local-First persistence & auto-retry)
async function updateJobStatus(jobId, status = null, notes = null, stage = null, followUp = null) {
  const token = currentSessionToken;
  const storageKey = overrideStorageKey(token);
  const jobIdx = jobsList.findIndex(j => j.id === jobId);
  let targetJob = jobIdx >= 0 ? jobsList[jobIdx] : null;

  // Fallback to locally cached job object
  if (!targetJob) {
    const overrides = getLocalStatusOverrides();
    if (overrides[String(jobId)] && overrides[String(jobId)].job) {
      targetJob = overrides[String(jobId)].job;
    }
  }

  // 1. Save immediately to Local-First storage (Instant offline/idle durability)
  const overrideUpdate = {};
  if (status !== null) overrideUpdate.status = status;
  if (notes !== null) overrideUpdate.notes = notes;
  if (stage !== null) overrideUpdate.stage = stage;
  if (followUp !== null) overrideUpdate.follow_up_date = followUp;
  if (status === 'applied') overrideUpdate.applied_at = (targetJob && targetJob.applied_at) || new Date().toISOString();
  if (targetJob) overrideUpdate.job = { ...targetJob, ...overrideUpdate };

  saveLocalStatusOverride(jobId, overrideUpdate);

  // 2. In-place Optimistic UI Updates
  if (status === 'ignored') {
    const cardEl = document.getElementById(`job-card-${jobIdx}`);
    if (cardEl) {
      cardEl.classList.add('card-dismissing');
    }
    showToast('Opportunity archived.');

    if (jobIdx >= 0) {
      jobsList.splice(jobIdx, 1);
    }
    updateSummaryText(jobsList.length);

    setTimeout(() => {
      renderJobs();
      if (selectedIndex >= jobsList.length) {
        selectedIndex = Math.max(0, jobsList.length - 1);
      }
      selectCard(selectedIndex);
    }, 220);
  } else if (status === 'saved') {
    if (targetJob) {
      if (currentStatus === 'saved') {
        status = 'new';
        targetJob.status = 'new';
        overrideUpdate.status = 'new';
        if (targetJob) overrideUpdate.job = { ...targetJob, status: 'new' };
        saveLocalStatusOverride(jobId, overrideUpdate);

        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        showToast('Opportunity unstarred and moved back to Inbox.');
        if (jobIdx >= 0) jobsList.splice(jobIdx, 1);
        updateSummaryText(jobsList.length);
        setTimeout(() => {
          renderJobs();
          if (selectedIndex >= jobsList.length) {
            selectedIndex = Math.max(0, jobsList.length - 1);
          }
          selectCard(selectedIndex);
        }, 220);
      } else {
        targetJob.status = 'saved';
        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        showToast('Opportunity saved! Moved to Saved tab.');
        if (jobIdx >= 0) jobsList.splice(jobIdx, 1);
        updateSummaryText(jobsList.length);
        setTimeout(() => {
          renderJobs();
          if (selectedIndex >= jobsList.length) {
            selectedIndex = Math.max(0, jobsList.length - 1);
          }
          selectCard(selectedIndex);
        }, 220);
      }
    }
  } else if (status === 'applied') {
    if (targetJob) {
      if (currentStatus === 'applied') {
        // Toggle back from Pipeline to Inbox
        targetJob.status = 'new';
        overrideUpdate.status = 'new';
        if (targetJob) overrideUpdate.job = { ...targetJob, status: 'new' };
        saveLocalStatusOverride(jobId, overrideUpdate);

        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        showToast(`Moved ${targetJob.company} back to Inbox.`, 'Undo', () => {
          updateJobStatus(jobId, 'applied');
        });
        if (jobIdx >= 0) jobsList.splice(jobIdx, 1);
        updateSummaryText(jobsList.length);
        setTimeout(() => {
          renderJobs();
          if (selectedIndex >= jobsList.length) {
            selectedIndex = Math.max(0, jobsList.length - 1);
          }
          selectCard(selectedIndex);
        }, 220);
      } else {
        // Mark as applied from new or saved feed
        targetJob.status = 'applied';
        targetJob.applied_at = targetJob.applied_at || new Date().toISOString();
        const prevStatus = currentStatus === 'saved' ? 'saved' : 'new';
        showToast(`Marked ${targetJob.company} as Applied! Moved to Pipeline.`, 'Undo', () => {
          updateJobStatus(jobId, prevStatus);
        });

        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        if (jobIdx >= 0) jobsList.splice(jobIdx, 1);
        updateSummaryText(jobsList.length);
        setTimeout(() => {
          renderJobs();
          if (selectedIndex >= jobsList.length) {
            selectedIndex = Math.max(0, jobsList.length - 1);
          }
          selectCard(selectedIndex);
        }, 220);
      }
    }
  } else if (status === 'new') {
    if (targetJob) {
      targetJob.status = 'new';
      if (currentStatus === 'applied' || currentStatus === 'saved') {
        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        if (jobIdx >= 0) jobsList.splice(jobIdx, 1);
        updateSummaryText(jobsList.length);
        setTimeout(() => {
          renderJobs();
          if (selectedIndex >= jobsList.length) {
            selectedIndex = Math.max(0, jobsList.length - 1);
          }
          selectCard(selectedIndex);
        }, 220);
      }
    }
  } else if (stage !== null && targetJob) {
    targetJob.pipeline_stage = stage;
    showToast(`Stage updated to ${stage.replace('_', ' ')}.`);
  } else if (notes !== null && targetJob) {
    targetJob.notes = notes;
  } else if (followUp !== null && targetJob) {
    targetJob.follow_up_date = followUp;
  }

  renderNoteSaveState(jobId);
  const saved = await flushJobOverride(jobId, token);
  if (saved && token === currentSessionToken) loadStats();
}

async function retryNoteSave(jobId) {
  const overrides = getLocalStatusOverrides();
  if (!overrides[String(jobId)]) return;
  overrides[String(jobId)].save_state = 'pending';
  localStorage.setItem(overrideStorageKey(), JSON.stringify(overrides));
  renderNoteSaveState(jobId);
  await flushJobOverride(jobId);
}

let syncPollTimer = null;

// Trigger Sync (Non-blocking Background Execution with Live Polling)
async function triggerSync() {
  if (currentUserRole !== 'admin') {
    showToast('🔒 Only Admin can harvest and add new opportunities to the system. As a guest, you can explore, filter, and save opportunities!');
    return;
  }
  const btn = document.getElementById('sync-btn');
  const spinner = document.getElementById('sync-spinner');
  const txt = document.getElementById('sync-text');
  const stackInput = document.getElementById('user-stack-input');
  const rawKws = stackInput ? stackInput.value.trim() : '';
  const keywords = rawKws ? rawKws.split(',').map(s => s.trim()).filter(Boolean) : null;

  if (btn && btn.classList.contains('is-running')) {
    showToast('Job site sync is already running in the background.');
    return;
  }

  if (btn) btn.classList.add('is-running');
  if (spinner) spinner.classList.add('is-spinning');
  if (txt) txt.textContent = 'Syncing...';

  const syncToken = currentSessionToken;
  let sessionAdded = 0;
  try {
    while (syncToken === currentSessionToken && currentUserRole === 'admin') {
      const res = await fetch('/api/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keywords, background: true })
      });
      let data;
      try {
        data = await res.json();
      } catch (_) {
        throw new Error(`Sync failed (${res.status}): the server did not return a valid response.`);
      }

      if (!res.ok || data.status === 'error') {
        throw new Error(data.error || `Sync failed (${res.status})`);
      }
      if (syncToken !== currentSessionToken || currentUserRole !== 'admin') return;
      if (data.local_request && ['queued', 'running'].includes(data.local_request.status)) {
        showToast('Sync accepted by the local worker on this PC. Keep the PC awake while it runs.');
        startSyncPoller();
        return;
      }
      if (data.cloud_run && ['queued', 'running', 'waiting'].includes(data.cloud_run.status)) {
        showToast('Cloud sync accepted. You can close this tab or laptop.');
        startSyncPoller();
        return;
      }
      if (data.progress) {
        sessionAdded += data.added || 0;
        if (typeof renderTelemetry === 'function') renderTelemetry(data);
        await loadStats();
        await loadJobs();
        if (data.progress.has_more && data.progress.can_continue === true) {
          if (txt) txt.textContent = 'Continuing sync...';
          continue;
        }
        stopSyncIndicator();
        showToast(batchSyncMessage({ ...data, added: sessionAdded }));
        return;
      }
      if (data.status === 'ok') {
        stopSyncIndicator();
        showToast(`Sync complete! +${data.added || 0} new jobs.`);
        await loadStats();
        await loadJobs();
        return;
      }
      if (data.status === 'already_syncing') {
        showToast('Job site sync is already running in the background.');
      } else {
        showToast('Job site sync started in the background.');
      }

      startSyncPoller();
      return;
    }
  } catch (err) {
    showToast(`Could not trigger sync: ${err.message}`);
    stopSyncIndicator();
  }
}

function startSyncPoller() {
  if (syncPollTimer) clearInterval(syncPollTimer);
  syncPollTimer = setInterval(async () => {
    try {
      const data = await fetchSyncTelemetry();
      if (!data) return;

      // Live update telemetry modal if open
      const modal = document.getElementById('sync-activity');
      if (modal && modal.style.display !== 'none' && typeof renderTelemetry === 'function') {
        renderTelemetry(data);
      }

      if (!data.is_syncing) {
        clearInterval(syncPollTimer);
        syncPollTimer = null;
        stopSyncIndicator();
        if (data.last_result?.status === 'error') {
          showToast(`Sync failed: ${data.last_result.error || 'Database ingestion failed'}`);
          return;
        }
        const added = (data.last_result && data.last_result.added !== undefined) ? data.last_result.added : 0;
        const skipped = (data.last_result && data.last_result.skipped !== undefined) ? data.last_result.skipped : 0;
        if (data.last_result?.progress) {
          showToast(batchSyncMessage(data.last_result));
        } else if (data.last_result?.status === 'partial') {
          showToast(`Sync finished: ${added} new jobs found. Some sites were unavailable; check Logs.`);
        } else {
          showToast(`Sync complete: ${added} new jobs found, ${skipped} existing listings updated.`);
        }
        loadStats();
        loadJobs();
        if (modal && modal.style.display !== 'none' && typeof renderTelemetry === 'function') {
          renderTelemetry(data);
        }
      }
    } catch (e) {
      clearInterval(syncPollTimer);
      syncPollTimer = null;
      stopSyncIndicator();
    }
  }, 1800);
}

function batchSyncMessage(result) {
  const progress = result.progress;
  const coverage = `${progress.completed_searches}/${progress.total_searches} keyword-board searches saved`;
  const next = !progress.has_more ? 'Current search cycle complete.' : progress.can_continue === false ? 'Remaining boards are paused by cooldowns; sync again after they clear.' : 'Next run continues; board cooldowns still apply.';
  return `Batch saved: +${result.added || 0} jobs. ${coverage}. ${next}${result.status === 'partial' ? ' Some searches need retry; check Logs.' : ''}`;
}

function stopSyncIndicator() {
  const btn = document.getElementById('sync-btn');
  const spinner = document.getElementById('sync-spinner');
  const txt = document.getElementById('sync-text');
  if (btn) btn.classList.remove('is-running');
  if (spinner) spinner.classList.remove('is-spinning');
  if (txt) txt.textContent = 'Sync Job Sites';
}

// Keyboard navigation
function setupKeyboardNavigation() {
  document.addEventListener('keydown', (e) => {
    const tag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      if (e.key === 'Escape') {
        document.activeElement.blur();
        const drawer = document.getElementById('stack-drawer');
        if (drawer && drawer.style.display !== 'none') drawer.style.display = 'none';
      }
      return;
    }

    if (e.key === 'Escape') {
      const drawer = document.getElementById('stack-drawer');
      if (drawer && drawer.style.display !== 'none') drawer.style.display = 'none';
      return;
    }

    if (e.key === '/') {
      e.preventDefault();
      const s = document.getElementById('search-input');
      if (s) s.focus();
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
        window.open(safeJobUrl(selectedJob.job_url), '_blank', 'noopener,noreferrer');
        if (currentStatus !== 'applied' && selectedJob.status !== 'applied') {
          const prevStatus = selectedJob.status || 'new';
          updateJobStatus(selectedJob.id, 'applied');
          showToast(`Marked ${selectedJob.company} as Applied. Moved to Pipeline.`, 'Undo', () => {
            updateJobStatus(selectedJob.id, prevStatus);
          });
        }
      }
    } else if (e.key === 'p') {
      if (selectedJob) {
        e.preventDefault();
        copyTailoredPitch(selectedJob.id);
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
  if (status === 'va') {
    switchToVAMode(elem);
    return;
  }
  rememberViewFilters();
  currentViewMode = 'tech';
  currentStatus = status;
  restoreViewFilters();
  persistSetting('status', status);
  document.querySelectorAll('.status-nav .status-tab').forEach(t => t.classList.remove('active'));
  if (elem) elem.classList.add('active');

  syncFilterControlsUI();
  loadJobs();
}

function setLevel(level, elem) {
  if (level === 'All') {
    selectedLevels.clear();
    selectedLevels.add('All');
  } else {
    selectedLevels.delete('All');
    if (selectedLevels.has(level)) {
      selectedLevels.delete(level);
      if (selectedLevels.size === 0) {
        selectedLevels.add('All');
      }
    } else {
      selectedLevels.add(level);
    }
  }

  // Update active UI classes on chips
  document.querySelectorAll('#level-group .filter-chip').forEach(c => {
    const val = c.getAttribute('data-val');
    if (selectedLevels.has(val)) {
      c.classList.add('active');
    } else {
      c.classList.remove('active');
    }
  });

  if (selectedLevels.has('All')) {
    currentLevel = 'All';
  } else {
    currentLevel = Array.from(selectedLevels).join(',');
  }

  persistSetting('experience_levels', currentLevel);
  loadJobs();
}

function setRole(role, elem) {
  if (role === 'Virtual Assistant') {
    switchToVAMode();
    return;
  }
  currentViewMode = 'tech';
  currentRole = role;
  persistSetting('role', role);
  document.querySelectorAll('#role-group .filter-chip').forEach(c => c.classList.remove('active'));
  if (elem) elem.classList.add('active');
  syncFilterControlsUI();
  loadJobs();
}

function setPlatform(platform, elem) {
  currentPlatform = platform;
  persistSetting('platform', platform);
  document.querySelectorAll('#platform-group .filter-chip').forEach(c => c.classList.remove('active'));
  if (elem) elem.classList.add('active');
  showToast(`Filtered feed to ${platform === 'All' ? 'All connected job sites' : platform}.`);
  loadJobs();
}

function filterByPlatformDirect(platform, event) {
  if (event) event.stopPropagation();
  currentPlatform = platform;
  persistSetting('platform', platform);
  syncFilterControlsUI();
  showToast(`Filtered feed to ${platform}.`);
  loadJobs();
}

function setDateFilter(filter, elem) {
  currentDateFilter = filter;
  persistSetting('date_filter', filter);
  document.querySelectorAll('#date-group .filter-chip').forEach(c => c.classList.remove('active'));
  elem.classList.add('active');
  loadJobs();
}

function formatPostingDate(dateStr) {
  if (!dateStr || !dateStr.trim()) return '<span class="badge-date">Recently</span>';
  const clean = dateStr.slice(0, 10);
  const todayStr = new Date().toISOString().slice(0, 10);
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const yesterdayStr = d.toISOString().slice(0, 10);

  if (clean === todayStr) {
    return `<span class="badge-date date-today">Today</span>`;
  } else if (clean === yesterdayStr) {
    return `<span class="badge-date date-recent">Yesterday</span>`;
  }

  try {
    const postDate = new Date(clean + 'T00:00:00');
    const now = new Date();
    const diffDays = Math.floor((now - postDate) / (1000 * 60 * 60 * 24));
    if (diffDays >= 2 && diffDays <= 7) {
      return `<span class="badge-date date-recent">${diffDays}d ago</span>`;
    } else if (diffDays > 7 && diffDays <= 30) {
      return `<span class="badge-date">${diffDays}d ago</span>`;
    }
  } catch (e) {}

  return `<span class="badge-date">${escapeHtml(clean)}</span>`;
}

function toggleHideSenior(checkbox) {
  hideSenior = checkbox.checked;
  persistSetting('hide_senior', hideSenior ? '1' : '0');
  loadJobs();
}

function toggleSalaryOnly(checkbox) {
  hasSalaryOnly = checkbox.checked;
  persistSetting('has_salary_only', hasSalaryOnly ? '1' : '0');
  loadJobs();
}

function toggleRemoteOnly(checkbox) {
  remoteOnly = checkbox.checked;
  persistSetting('remote_only', remoteOnly ? '1' : '0');
  loadJobs();
}

function updateClearSearchBtn() {
  const btn = document.getElementById('clear-search-btn');
  const input = document.getElementById('search-input');
  if (btn && input) {
    btn.style.display = input.value.trim() ? 'block' : 'none';
  }
}

function clearSearchInput() {
  const input = document.getElementById('search-input');
  if (input) {
    input.value = '';
    searchQuery = '';
    rememberViewFilters();
    updateClearSearchBtn();
    input.focus();
    loadJobs();
  }
}

function handleSearchInput() {
  updateClearSearchBtn();
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    searchQuery = document.getElementById('search-input').value.trim();
    rememberViewFilters();
    loadJobs();
  }, 220);
}

function updateSummaryText(count) {
  const countEl = document.getElementById('search-count');
  const ctxEl = document.getElementById('summary-context');
  if (countEl) {
    countEl.textContent = `${count} opportunities found`;
  }
  if (ctxEl) {
    if (currentViewMode === 'va') {
      ctxEl.textContent = 'Track: Remote Virtual Assistant';
    } else {
      const filters = [];
      if (currentRole !== 'All') filters.push(currentRole);
      if (currentLevel !== 'All') filters.push(currentLevel);
      if (currentDateFilter !== 'all') filters.push(`Date: ${currentDateFilter}`);
      if (filterBySkillsOnly) filters.push('Matching Target Stack');
      if (vaTrainingEnabled) filters.push('VA Included');
      ctxEl.textContent = filters.length > 0 ? `Filtered by: ${filters.join(' • ')}` : '';
    }
  }
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

function safeJobUrl(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : '#';
  } catch (_) {
    return '#';
  }
}

// --------------------------------------------------------------------------
// TELEMETRY & SYNC LOGS MODAL ENGINE
// --------------------------------------------------------------------------
const MONITORED_BOARDS = [
  { key: 'JobStreet', label: 'JobStreet PH', domain: 'jobstreet.com.ph', type: 'HTML/Live' },
  { key: 'OnlineJobs.ph', label: 'OnlineJobs.ph', domain: 'onlinejobs.ph', type: 'Direct Client PH' },
  { key: 'Indeed', label: 'Indeed PH', domain: 'ph.indeed.com', type: 'Live Feed' },
  { key: 'LinkedIn', label: 'LinkedIn PH', domain: 'linkedin.com/jobs', type: 'Guest Feed' },
  { key: 'Glassdoor', label: 'Glassdoor', domain: 'glassdoor.com', type: 'Feed/Direct' },
  { key: 'Kalibrr', label: 'Kalibrr PH', domain: 'kalibrr.com', type: 'Direct Portal' },
  { key: 'Bossjob', label: 'Bossjob PH', domain: 'bossjob.ph', type: 'Chat/Direct' },
  { key: 'Remotive', label: 'Remotive', domain: 'remotive.com/api', type: 'Verified API' },
  { key: 'Himalayas', label: 'Himalayas Remote', domain: 'himalayas.app/api', type: 'JSON API' },
  { key: 'Remote OK', label: 'Remote OK', domain: 'remoteok.com/api', type: 'JSON API' },
  { key: 'We Work Remotely', label: 'We Work Remotely', domain: 'weworkremotely.com', type: 'RSS/Atom' },
  { key: 'Arc', label: 'Arc Dev', domain: 'arc.dev', type: 'Global Remote' },
  { key: 'Jobicy', label: 'Jobicy', domain: 'jobicy.com/api', type: 'Remote jobs API' },
  { key: 'ZipRecruiter', label: 'ZipRecruiter', domain: 'ziprecruiter.com', type: 'JobSpy' },
  { key: 'Freelancer', label: 'Freelancer', domain: 'freelancer.com', type: 'Direct Contract' },
  { key: 'Upwork', label: 'Upwork', domain: 'upwork.com', type: 'Direct Contract' },
  { key: 'Wellfound', label: 'Wellfound', domain: 'wellfound.com', type: 'Tech Startups' },
  { key: 'Contra', label: 'Contra', domain: 'contra.com', type: 'Direct Freelance' },
  { key: 'FlexJobs', label: 'FlexJobs', domain: 'flexjobs.com', type: 'Screened Remote' }
];

let telemetryTimer = null;
let telemetryRequest = null;

function toggleSyncLogModal() {
  const activitySec = document.getElementById('sync-activity');
  if (activitySec && activitySec.classList.contains('is-collapsed')) {
    toggleTelemetryCollapse(false);
  }
  activitySec?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  fetchSyncTelemetry();
}

function startTelemetryPolling() {
  clearTimeout(telemetryTimer);
  if (!currentUserRole || document.visibilityState === 'hidden') return;
  fetchSyncTelemetry().then(data => {
    if (currentUserRole && document.visibilityState !== 'hidden') {
      telemetryTimer = setTimeout(startTelemetryPolling, data?.is_syncing ? 2000 : 10000);
    }
  });
}

async function fetchSyncTelemetry() {
  if (!currentUserRole) return;
  if (telemetryRequest) return telemetryRequest;
  const token = currentSessionToken;
  telemetryRequest = (async () => {
    const hint = document.getElementById('telemetry-update-status');
    try {
      const res = await fetch('/api/sync/status', { signal: AbortSignal.timeout(10000) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Could not read sync status');
      if (token !== currentSessionToken) return;
      renderTelemetry(data);
      if (hint) hint.textContent = `Updated ${new Date().toLocaleTimeString()} · Refreshes every ${data.is_syncing ? '2' : '10'} seconds`;
      return data;
    } catch (err) {
      if (token === currentSessionToken && hint) hint.textContent = `Live updates unavailable: ${err.message}. Retrying automatically.`;
    } finally {
      telemetryRequest = null;
    }
  })();
  return telemetryRequest;
}

function renderTelemetry(data) {
  if (!data) return;
  const progress = data.progress || data.last_result?.progress;
  const runTotals = data.run_totals?.request_id === data.local_request?.id ? data.run_totals : null;
  const waiting = data.is_syncing && progress?.has_more && progress.can_continue === false && progress.next_run_at > Date.now() / 1000;
  const retryTime = timestamp => new Date(timestamp * 1000).toLocaleTimeString();

  // 1. Status overview bar
  const syncStateEl = document.getElementById('telemetry-sync-state');
  if (syncStateEl) {
    syncStateEl.textContent = progress ? `${progress.completed_searches}/${progress.total_searches} searches saved` : 'No saved search progress';
    if (waiting) {
      const seconds = Math.max(1, Math.ceil(progress.next_run_at - Date.now() / 1000));
      syncStateEl.textContent += ` · Waiting for retry at ${retryTime(progress.next_run_at)} (in ${Math.ceil(seconds / 60)} min) · Resumes automatically`;
    } else if (data.is_syncing) {
      syncStateEl.textContent += ' · Syncing';
    } else if (data.local_request?.status === 'interrupted') {
      syncStateEl.textContent += ' · Interrupted · Saved progress will resume when the worker reconnects';
    } else if (progress?.has_more) {
      syncStateEl.textContent += ' · Unfinished · Click Resume sync to continue saved progress';
    } else {
      syncStateEl.textContent += ' · Idle';
    }
    if (['queued', 'running'].includes(data.local_request?.status)) {
      syncStateEl.textContent += data.local_request.status === 'running' ? ' · Running on this PC' : ' · Queued on this PC';
    } else if (data.local_worker) {
      syncStateEl.textContent += data.local_worker.online ? ' · Local worker online' : ' · Local worker offline';
    }
    if (data.cloud_run?.status === 'waiting') {
      syncStateEl.textContent += ` · Cloud retry ${new Date(data.cloud_run.next_at * 1000).toLocaleTimeString()}`;
    } else if (data.cloud_run?.status === 'queued') {
      syncStateEl.textContent += ' · Queued in cloud';
    } else if (data.cloud_run?.status === 'stalled') {
      syncStateEl.textContent += ' · Cloud stalled - click Sync to resume';
    } else if (data.cloud_run?.status === 'partial') {
      syncStateEl.textContent += ' · Cloud run ended - click Sync to resume';
    }
    if (runTotals) syncStateEl.textContent += ` · ${runTotals.total_fetched || 0} fetched · ${runTotals.sent || 0} uploaded · ${runTotals.added || 0} new`;
    if (data.local_worker?.online && data.local_worker.heartbeat_at) syncStateEl.textContent += ` · Worker heartbeat ${retryTime(data.local_worker.heartbeat_at)}`;
    syncStateEl.style.color = data.is_syncing ? 'var(--accent-blue)' : '#3fb950';
  }
  const syncText = document.getElementById('sync-text');
  if (syncText) syncText.textContent = waiting ? 'Waiting for retry...' : data.is_syncing ? 'Syncing...' : progress?.has_more ? 'Resume sync' : 'Sync Job Sites';

  const dbJobsEl = document.getElementById('telemetry-total-db-jobs');
  if (dbJobsEl) {
    const total = currentStats.total || ((currentStats.new || 0) + (currentStats.saved || 0) + (currentStats.applied || 0) + (currentStats.ignored || 0));
    dbJobsEl.textContent = total ? `${total} listings` : `${jobsList.length} loaded`;
  }

  const activeBoardsEl = document.getElementById('telemetry-active-boards');
  if (activeBoardsEl) {
    activeBoardsEl.textContent = `${data.total_boards || MONITORED_BOARDS.length} connected job sites`;
  }

  const lastRunEl = document.getElementById('telemetry-last-run-time');
  if (lastRunEl) {
    if (data.last_sync_time && data.last_sync_time > 0) {
      const d = new Date(data.last_sync_time * 1000);
      lastRunEl.textContent = d.toLocaleTimeString();
    } else {
      lastRunEl.textContent = 'Not recorded yet';
    }
  }

  // 2. Render boards grid
  const grid = document.getElementById('telemetry-boards-grid');
  if (grid) {
    const telem = data.telemetry || {};
    const platformCounts = runTotals?.platforms || (data.last_result && data.last_result.platforms) || data.platforms || {};

    grid.innerHTML = MONITORED_BOARDS.map(b => {
      const boardInfo = telem[b.key] || telem[b.label] || {};
      const boardProgress = progress?.boards?.[b.key] || progress?.boards?.[b.label] || {};
      const boardError = boardInfo.error || boardProgress.last_error || '';
      const count = platformCounts[b.key] !== undefined ? platformCounts[b.key] : (boardInfo.count || 0);
      const isRunning = data.is_syncing;

      let badgeClass = 'status-idle';
      let badgeLabel = 'READY';
      if (boardError || boardInfo.status === 'error') {
        badgeClass = 'status-error';
        badgeLabel = 'RETRY';
      } else if (isRunning && boardInfo.status === 'fetching') {
        badgeClass = 'status-running';
        badgeLabel = 'SCANNING';
      } else if (boardInfo.status === 'complete') {
        badgeClass = 'status-success';
        badgeLabel = 'DONE';
      } else if (count > 0 || boardInfo.status === 'active') {
        badgeClass = 'status-success';
        badgeLabel = `${count} JOBS`;
      } else if (boardInfo.status === 'cooldown') {
        const isFeed = b.type && (b.type.includes('API') || b.type.includes('Feed') || b.type.includes('RSS'));
        badgeClass = isFeed ? 'status-synced' : 'status-idle';
        badgeLabel = isFeed ? 'SYNCED' : 'STANDBY';
      }
      const nextRetry = boardError && boardProgress.next_at > Date.now() / 1000 ? `Retry at ${retryTime(boardProgress.next_at)}` : boardError ? 'Retry pending' : '';

      return `
        <div class="telemetry-board-card">
          <div class="board-header-row">
            <span class="board-name" title="${escapeHtml(b.domain)}">${escapeHtml(b.label)}</span>
            <span class="board-status-badge ${badgeClass}" title="${escapeHtml(boardError)}">${badgeLabel}</span>
          </div>
          <div class="board-meta-row">
            <span>${escapeHtml(b.type)}${boardInfo.route ? ` · ${escapeHtml(boardInfo.route)}${boardInfo.connection_retries ? ' (fallback)' : ''}` : ''}</span>
            <span class="board-count-pill">${count} fetched</span>
          </div>
          ${boardError ? `<div class="board-error" role="status">${escapeHtml(boardError)} · ${escapeHtml(nextRetry)}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  // 3. Render terminal logs
  const stream = document.getElementById('telemetry-log-stream');
  if (stream) {
    const logs = data.logs || [];
    if (logs.length === 0) {
      stream.textContent = `[${new Date().toLocaleTimeString()}] Ready. Start a sync to search connected job sites.`;
    } else {
      stream.textContent = logs.join('\n');
    }

    const autoscroll = document.getElementById('telemetry-autoscroll');
    if (!autoscroll || autoscroll.checked) {
      stream.scrollTop = stream.scrollHeight;
    }
  }
}

function copySyncLogs() {
  const stream = document.getElementById('telemetry-log-stream');
  if (!stream) return;
  const text = stream.textContent || '';
  navigator.clipboard.writeText(text).then(() => {
    showToast('Telemetry logs copied to clipboard.');
  }).catch(() => {
    showToast('Failed to copy logs to clipboard.');
  });
}

function toggleTelemetryCollapse(forceState) {
  const activitySec = document.getElementById('sync-activity');
  const label = document.getElementById('telemetry-toggle-text');
  if (!activitySec) return;

  const isCurrentlyCollapsed = activitySec.classList.contains('is-collapsed');
  const willCollapse = typeof forceState === 'boolean' ? forceState : !isCurrentlyCollapsed;

  activitySec.classList.toggle('is-collapsed', willCollapse);
  if (label) label.textContent = willCollapse ? 'Expand' : 'Minimize';

  try {
    localStorage.setItem('job_accel_telemetry_collapsed', willCollapse ? '1' : '0');
  } catch (e) {}
}

// --------------------------------------------------------------------------
// VIRTUAL ASSISTANT & REMOTE FREELANCE HUB
// --------------------------------------------------------------------------
function toggleVaHub() {
  const hub = document.getElementById('va-hub-section');
  if (!hub) return;
  const isHidden = hub.style.display === 'none' || !hub.style.display;
  hub.style.display = isHidden ? 'flex' : 'none';
  if (isHidden) {
    hub.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    showToast('Virtual Assistant & Remote Freelance Hub opened.');
  }
}

function switchToVAMode(elem) {
  rememberViewFilters();
  currentViewMode = 'va';
  restoreViewFilters();
  document.querySelectorAll('.status-nav .status-tab').forEach(t => t.classList.remove('active'));
  const vaTab = elem || document.getElementById('va-feed-tab');
  if (vaTab) vaTab.classList.add('active');

  syncFilterControlsUI();
  showToast('Viewing Remote Virtual Assistant & Freelance opportunities.');
  loadJobs();
}

function switchToTechMode(targetStatus = 'new') {
  const tab = document.querySelector(`.status-nav [data-val="${targetStatus}"]`);
  setStatus(targetStatus, tab);
}

function filterRemoteVAJobs() {
  switchToVAMode();
}

// --------------------------------------------------------------------------
// AUTOMATED DAILY EMAIL DIGEST
// --------------------------------------------------------------------------
async function triggerEmailDigest() {
  if (currentUserRole !== 'admin') {
    showToast('🔒 Daily email digest is reserved for Admin.');
    return;
  }
  const btn = document.getElementById('btn-daily-digest');
  if (btn) btn.disabled = true;
  showToast('Compiling and dispatching daily job digest to michael18ricafrente@gmail.com...');
  try {
    const res = await fetch('/api/notify/daily', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`Daily digest dispatched to ${data.recipient}! (${data.new_jobs} new jobs summarized)`);
    } else {
      showToast(data.message || `Digest compiled (${data.new_jobs || 0} jobs)! Check server logs.`);
    }
  } catch (err) {
    showToast(`Digest error: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}


// --------------------------------------------------------------------------
// RESIDENTIAL PROXY & HYBRID ROUTING MANAGER
// --------------------------------------------------------------------------
const DEFAULT_WEBSHARE_PROXIES = `45.38.107.97:6014:qbpwgfwy:5h0usxx7tj71
64.137.96.74:6641:qbpwgfwy:5h0usxx7tj71
198.23.243.226:6361:qbpwgfwy:5h0usxx7tj71
38.154.185.97:6370:qbpwgfwy:5h0usxx7tj71
84.247.60.125:6095:qbpwgfwy:5h0usxx7tj71
191.96.254.138:6185:qbpwgfwy:5h0usxx7tj71
198.46.161.42:5092:qbpwgfwy:5h0usxx7tj71
64.137.10.153:5803:qbpwgfwy:5h0usxx7tj71
104.164.49.38:7693:qbpwgfwy:5h0usxx7tj71
23.26.71.145:5628:qbpwgfwy:5h0usxx7tj71`;

function toggleProxyModal() {
  const modal = document.getElementById('proxy-modal');
  if (!modal) return;
  const isHidden = modal.style.display === 'none';
  modal.style.display = isHidden ? 'flex' : 'none';
  if (isHidden) {
    loadProxyStatus();
  }
}

function handleProxyOverlayClick(event) {
  if (event.target === document.getElementById('proxy-modal')) {
    toggleProxyModal();
  }
}

async function loadProxyStatus() {
  try {
    const res = await fetch('/api/proxy/status');
    if (!res.ok) return;
    const data = await res.json();
    const modeSelect = document.getElementById('proxy-mode-select');
    const listInput = document.getElementById('proxy-list-input');
    const badge = document.getElementById('proxy-modal-badge');
    const pill = document.getElementById('proxy-status-pill');

    if (modeSelect) modeSelect.value = data.mode || 'hybrid';
    if (listInput) {
      const activeRaw = (data.raw && data.raw.trim()) ? data.raw : DEFAULT_WEBSHARE_PROXIES;
      listInput.value = activeRaw;
    }
    if (badge) badge.textContent = `${data.count || 0} Configured`;
    if (pill) {
      pill.textContent = (data.mode || 'hybrid').toUpperCase();
      pill.className = `proxy-status-pill ${data.mode || 'hybrid'}`;
    }
    updateProxyHint(data.mode || 'hybrid');
  } catch (err) {
    console.warn('Could not load proxy status:', err);
  }
}

function onProxyModeChange() {
  const select = document.getElementById('proxy-mode-select');
  if (select) updateProxyHint(select.value);
}

function updateProxyHint(mode) {
  const hint = document.getElementById('proxy-mode-hint');
  if (!hint) return;
  if (mode === 'hybrid') {
    hint.textContent = 'Hybrid mode automatically routes requests through residential proxies on Vercel Cloud to prevent anti-bot blocks, but turns them OFF when running on your laptop to save bandwidth.';
  } else if (mode === 'always') {
    hint.textContent = 'Always Active routes all scraping requests through the residential proxy pool regardless of environment.';
  } else {
    hint.textContent = 'Disabled turns off all proxies. Requests will connect directly from your current network.';
  }
}

function resetToDefaultProxies() {
  const listInput = document.getElementById('proxy-list-input');
  if (listInput) {
    listInput.value = DEFAULT_WEBSHARE_PROXIES;
    showToast('Reset to verified Webshare 10-proxy pool.', 'info');
  }
}

async function runProxyLiveTest() {
  const listInput = document.getElementById('proxy-list-input');
  const resultsGrid = document.getElementById('proxy-test-results');
  const btn = document.getElementById('btn-test-proxies');
  const btnText = document.getElementById('btn-test-proxies-text');

  if (!resultsGrid) return;
  const rawText = listInput ? listInput.value.trim() : '';
  if (!rawText) {
    resultsGrid.innerHTML = '<div class="test-empty-state" style="color:#ef4444;">Please enter at least one proxy before testing.</div>';
    return;
  }

  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = 'Testing...';
  resultsGrid.innerHTML = '<div class="test-empty-state">Pinging proxy nodes across global regions...</div>';

  try {
    const res = await fetch('/api/proxy/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxies: rawText })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Test request failed');

    const results = data.results || [];
    if (!results.length) {
      resultsGrid.innerHTML = '<div class="test-empty-state">No valid proxies tested.</div>';
      return;
    }

    resultsGrid.innerHTML = results.map(r => {
      const isOk = r.status === 'ok';
      return `
        <div class="proxy-result-chip ${isOk ? 'ok' : 'error'}">
          <div class="chip-info">
            <span class="chip-proxy">${escapeHtml(r.proxy || '')}</span>
            <span class="chip-meta" style="color:var(--text-secondary); font-size:10px; display:block;">
              ${isOk ? `${escapeHtml(r.country || '')} (${escapeHtml(r.city || '')}) ? ${r.latency_ms}ms` : escapeHtml(r.error || 'Failed')}
            </span>
          </div>
          <span class="proxy-result-status ${isOk ? 'ok' : 'error'}">
            ${isOk ? '? OK' : '? FAIL'}
          </span>
        </div>
      `;
    }).join('');

    const okCount = results.filter(r => r.status === 'ok').length;
    showToast(`Tested ${results.length} proxies: ${okCount} working.`, okCount > 0 ? 'success' : 'error');
  } catch (err) {
    resultsGrid.innerHTML = `<div class="test-empty-state" style="color:#ef4444;">Test error: ${escapeHtml(err.message)}</div>`;
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = 'Test Proxies Live';
  }
}

async function saveProxyConfiguration() {
  const modeSelect = document.getElementById('proxy-mode-select');
  const listInput = document.getElementById('proxy-list-input');
  const feedback = document.getElementById('proxy-save-feedback');
  const btn = document.getElementById('btn-save-proxy-config');

  const mode = modeSelect ? modeSelect.value : 'hybrid';
  const rawList = listInput ? listInput.value.trim() : '';

  if (btn) btn.disabled = true;
  if (feedback) feedback.textContent = 'Saving...';

  try {
    persistSetting('proxy_mode', mode);
    persistSetting('proxy_list', rawList);

    const pill = document.getElementById('proxy-status-pill');
    if (pill) {
      pill.textContent = mode.toUpperCase();
      pill.className = `proxy-status-pill ${mode}`;
    }

    const badge = document.getElementById('proxy-modal-badge');
    const lines = rawList.split('\n').filter(l => l.trim() && !l.startsWith('#')).length;
    if (badge) badge.textContent = `${lines} Configured`;

    if (feedback) feedback.textContent = 'Settings saved successfully';
    showToast('Proxy settings saved & synchronized.', 'success');
    setTimeout(() => {
      if (feedback) feedback.textContent = '';
      toggleProxyModal();
    }, 1200);
  } catch (err) {
    if (feedback) feedback.textContent = `Error: ${err.message}`;
    showToast(`Failed to save proxies: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

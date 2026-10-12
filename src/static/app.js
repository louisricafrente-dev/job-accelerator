// --------------------------------------------------------------------------
// JOB APPLICATION ACCELERATOR - CLIENT WORKSTATION
// State Management, Live Filter Engine, Keyboard Controls, Pitch Generator
// --------------------------------------------------------------------------

// State management
let currentStatus = 'new';
let selectedLevels = new Set(['All']);
let currentLevel = 'All';
let currentRole = 'All';
let currentDateFilter = '7days';
let hasSalaryOnly = false;
let remoteOnly = false;
let hideSenior = false;
let filterBySkillsOnly = false;
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

// Lifecycle Bootstrap
document.addEventListener('DOMContentLoaded', async () => {
  await loadAllUserSettings();
  renderSkillChips();
  updateActiveSkillsBadge();
  loadStats();
  loadJobs();
  setupKeyboardNavigation();
});

// Universal persistence helper (saves to both localStorage & server SQLite)
function persistSetting(key, value) {
  try {
    localStorage.setItem('job_accel_' + key, String(value));
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: String(value) })
    }).catch(err => console.warn(`Could not persist setting "${key}":`, err));
  } catch (err) {
    console.warn(`Local save error for "${key}":`, err);
  }
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
      status: localStorage.getItem('job_accel_status')
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

  if (settings.date_filter) {
    currentDateFilter = settings.date_filter;
  }
  if (settings.role) {
    currentRole = settings.role;
  }
  if (settings.status) {
    currentStatus = settings.status;
  }

  if (settings.experience_levels) {
    const levels = settings.experience_levels.split(',').map(s => s.trim()).filter(Boolean);
    if (levels.length > 0) {
      selectedLevels = new Set(levels);
      currentLevel = selectedLevels.has('All') ? 'All' : Array.from(selectedLevels).join(',');
    }
  }

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

  updateFilterButtonState();

  // Status navigation tabs
  document.querySelectorAll('.status-nav .status-tab').forEach(tab => {
    const val = tab.getAttribute('data-val');
    tab.classList.toggle('active', val === currentStatus);
  });

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
async function loadJobs() {
  const feed = document.getElementById('job-feed');
  feed.innerHTML = `
    <div class="state-loading">
      <div class="loading-spinner"></div>
      <p>Scanning job opportunities across platforms...</p>
    </div>
  `;

  const pipelineHeader = document.getElementById('pipeline-hub-header');
  if (pipelineHeader) {
    pipelineHeader.style.display = currentStatus === 'applied' ? 'block' : 'none';
  }

  try {
    const params = new URLSearchParams({
      status: currentStatus,
      role: currentRole,
      experience_level: currentLevel,
      search: searchQuery,
      date_filter: currentDateFilter
    });
    if (hasSalaryOnly) params.set('has_salary', '1');
    if (remoteOnly) params.set('remote_only', '1');
    if (hideSenior) params.set('hide_senior', '1');

    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    let jobs = data.jobs || [];

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
      if ((cleanPart === 'junior' || cleanPart === 'entry' || cleanPart === 'junior / entry') && 
          (targetText.includes('junior') || targetText.includes('jr') || targetText.includes('entry') || 
           targetText.includes('associate') || targetText.includes('intern') || targetText.includes('trainee') || 
           targetText.includes('fresh grad') || targetText.includes('early career') || targetText.includes('ojt') || 
           targetText.includes('0-2 year') || targetText.includes('engineer i') || targetText.includes('developer i') || 
           job.experience_level === 'Junior / Entry')) {
        isMatch = true;
        break;
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
          <button type="button" class="btn-remove-tag" onclick="removeSkill('${escapeHtml(skill)}')" title="Remove ${escapeHtml(skill)}" aria-label="Remove ${escapeHtml(skill)}">&times;</button>
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
      <button type="button" class="btn-strip-remove-tag" onclick="removeSkill('${escapeHtml(skill)}')" title="Remove ${escapeHtml(skill)}" aria-label="Remove ${escapeHtml(skill)}">&times;</button>
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

// Show toast notification
function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast-item';
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 300);
  }, 2600);
}

// Render cards
function renderJobs() {
  const feed = document.getElementById('job-feed');
  if (jobsList.length === 0) {
    feed.innerHTML = `
      <div class="state-empty">
        <p>No job postings match the active filter criteria.</p>
        <span class="sub-text">Broaden your search or click "Sync 12 Boards" to refresh opportunities.</span>
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
            <a href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer" 
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
                      <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" 
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
                <a href="${escapeHtml(single.url || job.job_url)}" target="_blank" rel="noopener noreferrer" 
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
            ${skillsMatch.count > 0 ? `<span class="job-skills-matched">Match: ${skillsMatch.matched.join(', ')}</span>` : ''}
            ${formatPostingDate(job.date_posted)}
          </div>

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
              </div>
            </div>
          ` : ''}
        </div>

        <div class="card-actions-cluster" onclick="event.stopPropagation()">
          <a href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer" 
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

// Apply button handler
function handleApplyClick(e, jobId) {
  setTimeout(() => {
    if (confirm('Mark this position as "Applied" in your tracking pipeline?')) {
      updateJobStatus(jobId, 'applied');
    }
  }, 400);
}

// Stage change handler
function changeJobStage(jobId, stage) {
  updateJobStatus(jobId, 'applied', null, stage);
}

// Save inline notes
function saveJobNotes(jobId, newNotes) {
  const job = jobsList.find(j => j.id === jobId);
  if (job && (job.notes || '') !== newNotes) {
    updateJobStatus(jobId, null, newNotes).then(() => {
      showToast('Application notes updated.');
    });
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

// Update status via API (Optimistic in-place update without reloading the web page or feed)
async function updateJobStatus(jobId, status = null, notes = null, stage = null, followUp = null) {
  const jobIdx = jobsList.findIndex(j => j.id === jobId);
  const targetJob = jobIdx >= 0 ? jobsList[jobIdx] : null;

  // 1. In-place Optimistic UI Updates
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
        targetJob.status = 'new';
        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        showToast('Opportunity unstarred and moved back to Inbox.');
        jobsList.splice(jobIdx, 1);
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
        jobsList.splice(jobIdx, 1);
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
      targetJob.status = 'applied';
      if (currentStatus === 'new' || currentStatus === 'saved') {
        const cardEl = document.getElementById(`job-card-${jobIdx}`);
        if (cardEl) cardEl.classList.add('card-dismissing');
        showToast('Marked as Applied! Moved to Pipeline.');
        jobsList.splice(jobIdx, 1);
        updateSummaryText(jobsList.length);
        setTimeout(() => {
          renderJobs();
          if (selectedIndex >= jobsList.length) {
            selectedIndex = Math.max(0, jobsList.length - 1);
          }
          selectCard(selectedIndex);
        }, 220);
      } else {
        targetJob.pipeline_stage = stage || targetJob.pipeline_stage || 'applied';
        renderJobs();
        selectCard(selectedIndex);
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

  // 2. Background Persistence to Server
  try {
    const payload = {};
    if (status === 'saved') {
      payload.status = targetJob ? targetJob.status : 'saved';
    } else if (status !== null) {
      payload.status = status;
    }
    if (notes !== null) payload.notes = notes;
    if (stage !== null) payload.stage = stage;
    if (followUp !== null) payload.follow_up_date = followUp;

    const res = await fetch(`/api/jobs/${jobId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      loadStats(); // Silently update telemetry badges without reloading feed
    }
  } catch (err) {
    console.error('Failed to persist status change:', err);
    showToast(`Sync warning: ${err.message}`);
  }
}

let syncPollTimer = null;

// Trigger Sync (Non-blocking Background Execution with Live Polling)
async function triggerSync() {
  const btn = document.getElementById('sync-btn');
  const spinner = document.getElementById('sync-spinner');
  const txt = document.getElementById('sync-text');
  const stackInput = document.getElementById('user-stack-input');
  const rawKws = stackInput ? stackInput.value.trim() : '';
  const keywords = rawKws ? rawKws.split(',').map(s => s.trim()).filter(Boolean) : null;

  if (btn && btn.classList.contains('is-running')) {
    showToast('Sync is already actively scanning 15 boards in the background.');
    return;
  }

  if (btn) btn.classList.add('is-running');
  if (spinner) spinner.classList.add('is-spinning');
  if (txt) txt.textContent = 'Syncing...';

  try {
    const res = await fetch('/api/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keywords, background: true })
    });
    const data = await res.json();

    if (data.status === 'already_syncing') {
      showToast('Sync is already running across 15 boards in background.');
    } else {
      showToast('Sync launched in background! 15 boards scanning.');
    }

    startSyncPoller();
  } catch (err) {
    showToast(`Could not trigger sync: ${err.message}`);
    stopSyncIndicator();
  }
}

function startSyncPoller() {
  if (syncPollTimer) clearInterval(syncPollTimer);
  syncPollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/sync/status');
      const data = await res.json();

      // Live update telemetry modal if open
      const modal = document.getElementById('sync-log-modal');
      if (modal && modal.style.display !== 'none' && typeof renderTelemetry === 'function') {
        renderTelemetry(data);
      }

      if (!data.is_syncing) {
        clearInterval(syncPollTimer);
        syncPollTimer = null;
        stopSyncIndicator();
        const added = (data.last_result && data.last_result.added !== undefined) ? data.last_result.added : 0;
        const skipped = (data.last_result && data.last_result.skipped !== undefined) ? data.last_result.skipped : 0;
        showToast(`Sync complete! +${added} new jobs, ${skipped} existing updated across 15 boards.`);
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

function stopSyncIndicator() {
  const btn = document.getElementById('sync-btn');
  const spinner = document.getElementById('sync-spinner');
  const txt = document.getElementById('sync-text');
  if (btn) btn.classList.remove('is-running');
  if (spinner) spinner.classList.remove('is-spinning');
  if (txt) txt.textContent = 'Sync 15 Boards';
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
        window.open(selectedJob.job_url, '_blank');
        if (confirm(`Mark "${selectedJob.title}" as Applied?`)) {
          updateJobStatus(selectedJob.id, 'applied');
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
  currentStatus = status;
  persistSetting('status', status);
  document.querySelectorAll('.status-tab').forEach(t => t.classList.remove('active'));
  elem.classList.add('active');
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
  currentRole = role;
  persistSetting('role', role);
  document.querySelectorAll('#role-group .filter-chip').forEach(c => c.classList.remove('active'));
  elem.classList.add('active');
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
    const filters = [];
    if (currentRole !== 'All') filters.push(currentRole);
    if (currentLevel !== 'All') filters.push(currentLevel);
    if (currentDateFilter !== 'all') filters.push(`Date: ${currentDateFilter}`);
    if (filterBySkillsOnly) filters.push('Matching Target Stack');
    ctxEl.textContent = filters.length > 0 ? `Filtered by: ${filters.join(' • ')}` : '';
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
  { key: 'Wellfound', label: 'Wellfound', domain: 'wellfound.com', type: 'Startup Hub' },
  { key: 'Arc', label: 'Arc Dev', domain: 'arc.dev', type: 'Global Remote' },
  { key: 'Foundit', label: 'Foundit APAC', domain: 'foundit.com.ph', type: 'Regional' },
  { key: 'Upwork', label: 'Upwork Remote', domain: 'upwork.com', type: 'Contract / Dev' }
];

function toggleSyncLogModal() {
  const modal = document.getElementById('sync-log-modal');
  if (!modal) return;
  const isHidden = modal.style.display === 'none' || !modal.style.display;
  modal.style.display = isHidden ? 'flex' : 'none';
  if (isHidden) {
    fetchSyncTelemetry();
  }
}

function handleModalBackdropClick(event) {
  if (event.target && event.target.id === 'sync-log-modal') {
    toggleSyncLogModal();
  }
}

async function fetchSyncTelemetry() {
  try {
    const res = await fetch('/api/sync/status');
    const data = await res.json();
    renderTelemetry(data);
  } catch (err) {
    console.error('Failed to fetch sync telemetry:', err);
    const stream = document.getElementById('telemetry-log-stream');
    if (stream) stream.textContent = `Error fetching telemetry: ${err.message}`;
  }
}

function renderTelemetry(data) {
  if (!data) return;

  // 1. Status overview bar
  const syncStateEl = document.getElementById('telemetry-sync-state');
  if (syncStateEl) {
    syncStateEl.textContent = data.is_syncing ? 'Scanning...' : 'Idle / Standby';
    syncStateEl.style.color = data.is_syncing ? 'var(--accent-blue)' : '#3fb950';
  }

  const dbJobsEl = document.getElementById('telemetry-total-db-jobs');
  if (dbJobsEl) {
    const total = currentStats.total || ((currentStats.new || 0) + (currentStats.saved || 0) + (currentStats.applied || 0) + (currentStats.ignored || 0));
    dbJobsEl.textContent = total ? `${total} listings` : `${jobsList.length} loaded`;
  }

  const activeBoardsEl = document.getElementById('telemetry-active-boards');
  if (activeBoardsEl) {
    activeBoardsEl.textContent = `${data.total_boards || 15} / 15 Boards`;
  }

  const lastRunEl = document.getElementById('telemetry-last-run-time');
  if (lastRunEl) {
    if (data.last_sync_time && data.last_sync_time > 0) {
      const d = new Date(data.last_sync_time * 1000);
      lastRunEl.textContent = d.toLocaleTimeString();
    } else {
      lastRunEl.textContent = 'Ready';
    }
  }

  // 2. Render boards grid
  const grid = document.getElementById('telemetry-boards-grid');
  if (grid) {
    const telem = data.telemetry || {};
    const platformCounts = (data.last_result && data.last_result.platforms) || data.platforms || {};

    grid.innerHTML = MONITORED_BOARDS.map(b => {
      const boardInfo = telem[b.key] || telem[b.label] || {};
      const count = platformCounts[b.key] !== undefined ? platformCounts[b.key] : (boardInfo.count || 0);
      const isRunning = data.is_syncing;
      
      let badgeClass = 'status-idle';
      let badgeLabel = 'STANDBY';
      if (isRunning) {
        badgeClass = 'status-running';
        badgeLabel = 'SCANNING';
      } else if (boardInfo.status === 'active' || count > 0) {
        badgeClass = 'status-success';
        badgeLabel = `${count} JOBS`;
      } else if (boardInfo.status === 'error') {
        badgeClass = 'status-error';
        badgeLabel = 'RETRY';
      }

      return `
        <div class="telemetry-board-card">
          <div class="board-header-row">
            <span class="board-name" title="${escapeHtml(b.domain)}">${escapeHtml(b.label)}</span>
            <span class="board-status-badge ${badgeClass}">${badgeLabel}</span>
          </div>
          <div class="board-meta-row">
            <span>${escapeHtml(b.type)}</span>
            <span class="board-count-pill">${count > 0 ? `${count} captured` : 'Ready'}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  // 3. Render terminal logs
  const stream = document.getElementById('telemetry-log-stream');
  if (stream) {
    const logs = data.logs || [];
    if (logs.length === 0) {
      stream.textContent = `[${new Date().toLocaleTimeString()}] Ready. Click "Sync 15 Boards" to launch live multi-platform harvest.`;
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

function filterRemoteVAJobs() {
  const searchInput = document.getElementById('search-input');
  const remoteCheckbox = document.getElementById('remote-only-checkbox');
  
  if (searchInput) searchInput.value = 'Virtual Assistant';
  searchQuery = 'Virtual Assistant';
  
  if (remoteCheckbox) remoteCheckbox.checked = true;
  remoteOnly = true;

  // Reset seniority to All
  selectedLevels.clear();
  selectedLevels.add('All');
  currentLevel = 'All';
  document.querySelectorAll('#level-group .filter-chip').forEach(c => {
    c.classList.toggle('active', c.getAttribute('data-val') === 'All');
  });

  showToast('Filtered feed to Remote Virtual Assistant opportunities.');
  loadJobs();
}

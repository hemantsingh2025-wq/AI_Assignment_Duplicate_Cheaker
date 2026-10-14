const authAppUrl = "https://frontend-beta-eight-65.vercel.app/";

const navItems = [
  { label: "Home", href: "#home" },
  { label: "About", href: "#about" },
  { label: "Features", href: "#features" },
  { label: "Login", href: authAppUrl },
];

const highlights = [
  { value: "98%", label: "Accuracy focus" },
  { value: "24/7", label: "Access support" },
  { value: "2 min", label: "Fast upload checks" },
];

const featureCards = [
  {
    icon: "⚡",
    title: "AI similarity engine",
    text: "Automatically compares assignments, highlights suspicious overlaps, and ranks risky submissions with explainable insights.",
  },
  {
    icon: "🔒",
    title: "Secure academic workflow",
    text: "Protect student submissions with role-based access, controlled uploads, and trusted reviewer permissions.",
  },
  {
    icon: "📊",
    title: "Live review dashboard",
    text: "Track reports, review status, and assignment trends through an intuitive analytics workspace for instructors.",
  },
];

const processSteps = [
  "Upload or sync student submissions",
  "Run AI-based duplicate checks",
  "Review flagged matches and evidence",
  "Approve or escalate the final verdict",
];

function App() {
  return (
    <div className="page-shell" id="home">
      <header className="topbar">
        <div className="brand-wrap">
          <div className="brand-mark">A</div>
          <span>Assignment AI</span>
        </div>

        <nav className="nav" aria-label="Main navigation">
          {navItems.map((item) => (
            <a key={item.label} href={item.href} className="nav-link">
              {item.label}
            </a>
          ))}
        </nav>

        <a className="nav-button" href={authAppUrl}>
          Get Started
        </a>
      </header>

      <main className="content-wrap">
        <section className="hero-section">
          <div className="hero-copy">
            <span className="eyebrow">Smart academic solutions</span>
            <h1>
              Detect student assignment duplication with <span>confidence</span>
            </h1>
            <p>
              A secure platform that helps colleges and universities review submissions, identify copied work,
              and support fair academic evaluation with AI-based similarity analysis.
            </p>

            <div className="hero-actions">
              <a className="primary-btn" href="#features">
                Explore Features
              </a>
              <a className="secondary-btn" href="#about">
                Learn More
              </a>
            </div>

            <div className="stats-row">
              {highlights.map((item) => (
                <div key={item.label} className="stat-card">
                  <strong>{item.value}</strong>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="hero-visual">
            <div className="image-card">
              <img
                src="https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=900&q=80"
                alt="Students collaborating in a classroom"
              />
            </div>
            <div className="floating-box">
              <span className="dot" />
              Duplicate reviews in real time
            </div>
          </div>
        </section>

        <section className="about-section" id="about">
          <div className="section-heading">
            <span className="mini-label">About the web</span>
            <h2>Built for smarter academic integrity.</h2>
          </div>

          <div className="about-grid">
            <div className="about-copy">
              <p>
                This platform is designed for students, teachers, and administrators to manage assignments more
                effectively. It simplifies submission review, assignment tracking, and plagiarism detection in one
                streamlined workflow.
              </p>
              <ul>
                <li>AI-powered duplicate detection</li>
                <li>Secure college login system</li>
                <li>Teacher review workflow</li>
                <li>Similarity analysis dashboard</li>
              </ul>
            </div>

            <div className="info-panel">
              <div className="panel-box">
                <span>Live review</span>
                <strong>Student submissions</strong>
              </div>
              <div className="panel-box accent">
                <span>AI analysis</span>
                <strong>Similarity score</strong>
              </div>
              <div className="panel-box">
                <span>Institution trust</span>
                <strong>Academic fairness</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="feature-section" id="features">
          <div className="section-heading center-heading">
            <span className="mini-label">Core features</span>
            <h2>Everything your academic team needs in one place.</h2>
          </div>

          <div className="feature-grid">
            {featureCards.map((feature) => (
              <article key={feature.title} className="feature-card">
                <div className="feature-icon">{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="process-section">
          <div className="process-copy">
            <span className="mini-label">How it works</span>
            <h2>From upload to verdict in a few simple steps.</h2>
            <p>
              Institutions can move from submission intake to evidence-backed decisions without complicated manual
              review processes.
            </p>
          </div>

          <div className="process-steps">
            {processSteps.map((step, index) => (
              <div key={step} className="step-item">
                <span className="step-number">0{index + 1}</span>
                <p>{step}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="cta-section" id="contact">
          <div className="cta-card">
            <div>
              <span className="mini-label">Ready to begin?</span>
              <h2>Build a stronger, fairer academic review process.</h2>
            </div>
            <a className="primary-btn" href={authAppUrl}>
              Request a Demo
            </a>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;

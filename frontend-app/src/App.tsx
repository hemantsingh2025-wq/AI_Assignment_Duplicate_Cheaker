const navItems = ["Home", "About", "Features", "Contact"];

const features = [
  "AI-powered duplicate detection",
  "Secure college login system",
  "Teacher review workflow",
  "Similarity analysis dashboard",
];

const highlights = [
  { value: "98%", label: "Accuracy focus" },
  { value: "24/7", label: "Access support" },
  { value: "2 min", label: "Fast upload checks" },
];

function App() {
  return (
    <div className="page-shell">
      <header className="topbar">
        <div className="brand-wrap">
          <div className="brand-mark">A</div>
          <span>Assignment AI</span>
        </div>

        <nav className="nav">
          {navItems.map((item) => (
            <a key={item} href="#" className="nav-link">
              {item}
            </a>
          ))}
        </nav>

        <button className="nav-button">Get Started</button>
      </header>

      <main className="content-wrap">
        <section className="hero-section">
          <div className="hero-copy">
            <span className="eyebrow">Smart academic solutions</span>
            <h1>
              Detect student assignment duplication with <span>confidence</span>
            </h1>
            <p>
              A secure platform that helps institutions review submissions, identify copied work,
              and support fair academic evaluation with AI-based similarity checks.
            </p>

            <div className="hero-actions">
              <button className="primary-btn">Explore Features</button>
              <button className="secondary-btn">Learn More</button>
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
                alt="Student studying"
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
                This platform is designed for students, teachers, and academic administrators to manage
                assignments more effectively. It streamlines uploading, evaluation, and plagiarism checks
                in a simple and reliable workflow.
              </p>
              <ul>
                {features.map((item) => (
                  <li key={item}>{item}</li>
                ))}
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
      </main>
    </div>
  );
}

export default App;

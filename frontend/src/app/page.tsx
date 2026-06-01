import React from 'react';
import Link from 'next/link';

// Fetch live ticker data using Next.js Server Components
async function getLiveTickers() {
  const symbols = [
    { ticker: 'RELIANCE.NS', name: 'RELIANCE' },
    { ticker: 'TCS.NS', name: 'TCS' },
    { ticker: 'HDFCBANK.NS', name: 'HDFCBANK' },
    { ticker: 'INFY.NS', name: 'INFY' },
    { ticker: 'SBIN.NS', name: 'SBIN' },
    { ticker: '^NSEI', name: 'NIFTY 50' },
    { ticker: '^BSESN', name: 'SENSEX' },
    { ticker: 'BAJFINANCE.NS', name: 'BAJFINANCE' },
    { ticker: 'WIPRO.NS', name: 'WIPRO' },
    { ticker: 'TATAMOTORS.NS', name: 'TATAMOTORS' },
    { ticker: 'HINDUNILVR.NS', name: 'HINDUNILVR' },
    { ticker: 'ICICIBANK.NS', name: 'ICICIBANK' }
  ];

  const results = await Promise.all(symbols.map(async ({ ticker, name }) => {
    try {
      const res = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=2d`, {
        next: { revalidate: 60 }, // Cache for 60 seconds
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
      });
      if (!res.ok) throw new Error('Fetch failed');
      const data = await res.json();
      const meta = data.chart.result[0].meta;
      const price = meta.regularMarketPrice;
      const prev = meta.chartPreviousClose;
      const pct = ((price - prev) / prev) * 100;
      return { name, price: price.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 }), pct: pct.toFixed(1), up: pct >= 0 };
    } catch (err) {
      return { name, price: '---', pct: '0.0', up: true };
    }
  }));

  return results;
}

export default async function LandingPage() {
  const tickers = await getLiveTickers();
  const tickerItems = [...tickers, ...tickers]; // Duplicate for seamless loop

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500&family=Yatra+One&display=swap');

        :root {
          --bg:        #121212;
          --bg-2:      #18181b;
          --bg-3:      #27272a;
          --accent:    #8b5cf6;
          --accent-dim:#6d28d9;
          --teal:      #14b8a6;
          --teal-dim:  #0f766e;
          --blue:      #3b82f6;
          --white:     #f4f4f5;
          --muted:     #a1a1aa;
          --red:       #ff4d6a;
          --green:     #00d97e;
          --border:    #3f3f46;
          --border-dim:#27272a;
        }

        body {
          background: var(--bg) !important;
          color: var(--white) !important;
          font-family: 'IBM Plex Sans', sans-serif !important;
          font-weight: 300 !important;
          overflow-x: hidden !important;
          margin: 0 !important;
          padding: 0 !important;
        }

        body::before {
          content: '';
          position: fixed;
          inset: 0;
          background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0,0,0,0.2) 2px,
            rgba(0,0,0,0.2) 4px
          );
          pointer-events: none;
          z-index: 1000;
          opacity: 0.3;
        }

        .ticker-wrap {
          width: 100%;
          border-bottom: 1px solid var(--border-dim);
          background: var(--bg-2);
          overflow: hidden;
          padding: 10px 0;
          position: sticky;
          top: 0;
          z-index: 100;
        }
        .ticker-inner {
          display: flex;
          white-space: nowrap;
          animation: ticker-scroll 40s linear infinite;
          gap: 0;
        }
        .ticker-wrap:hover .ticker-inner { animation-play-state: paused; }
        @keyframes ticker-scroll {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        .ticker-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 0 28px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.04em;
          color: var(--muted);
          border-right: 1px solid var(--border-dim);
        }
        .ticker-item .sym { color: var(--white); font-weight: 500; }
        .ticker-item .up  { color: var(--green); }
        .ticker-item .dn  { color: var(--red); }

        .hero {
          min-height: 92vh;
          display: grid;
          grid-template-columns: 1fr 1fr;
          align-items: center;
          padding: 80px 80px 80px 100px;
          gap: 60px;
          position: relative;
          overflow: hidden;
        }
        .hero::after {
          content: '';
          position: absolute;
          right: -200px;
          top: 50%;
          transform: translateY(-50%);
          width: 600px;
          height: 600px;
          background: radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 70%);
          pointer-events: none;
        }

        .hero-label {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 10px;
          letter-spacing: 0.2em;
          color: var(--accent);
          text-transform: uppercase;
          margin-bottom: 24px;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .hero-label::before {
          content: '';
          display: block;
          width: 24px;
          height: 1px;
          background: var(--accent);
        }

        .hero-title {
          font-family: 'Playfair Display', serif;
          font-size: clamp(56px, 7vw, 96px);
          font-weight: 900;
          line-height: 0.95;
          letter-spacing: -0.02em;
          color: var(--white);
          margin-bottom: 8px;
        }
        .hero-title em {
          font-style: italic;
          color: var(--teal);
          display: inline-block;
          margin-left: 16px;
        }

        .hero-sub {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.12em;
          color: var(--muted);
          text-transform: uppercase;
          margin-bottom: 32px;
          margin-top: 16px;
        }

        .hero-desc {
          font-size: 16px;
          line-height: 1.75;
          color: rgba(244, 244, 245, 0.65);
          max-width: 440px;
          margin-bottom: 48px;
        }

        .cta-row {
          display: flex;
          gap: 16px;
          align-items: center;
        }
        .btn-primary {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: var(--accent);
          color: #fff;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          text-decoration: none;
          padding: 14px 28px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          transition: background 0.2s, transform 0.15s;
        }
        .btn-primary:hover { background: var(--accent-dim); transform: translateY(-1px); }
        .btn-secondary {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: var(--bg-3);
          color: var(--white);
          font-family: 'IBM Plex Mono', monospace;
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          text-decoration: none;
          padding: 14px 28px;
          border: 1px solid var(--border);
          border-radius: 4px;
          cursor: pointer;
          transition: background 0.2s, transform 0.15s;
        }
        .btn-secondary:hover { background: var(--border-dim); transform: translateY(-1px); }

        .terminal {
          background: var(--bg-2);
          border: 1px solid var(--border);
          border-radius: 8px;
          position: relative;
          overflow: hidden;
          animation: fade-up 0.8s 0.3s both;
          box-shadow: 0 20px 40px rgba(0,0,0,0.4);
        }
        .terminal-bar {
          background: var(--bg-3);
          border-bottom: 1px solid var(--border-dim);
          padding: 12px 16px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .dot { width: 10px; height: 10px; border-radius: 50%; }
        .dot.r { background: #e05555; }
        .dot.y { background: #f59e0b; }
        .dot.g { background: #4caf7a; }
        .terminal-title {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 11px;
          color: var(--muted);
          margin-left: 8px;
          letter-spacing: 0.06em;
        }
        .terminal-body {
          padding: 24px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 12px;
          line-height: 2;
          min-height: 340px;
        }
        .line { display: flex; gap: 12px; align-items: baseline; opacity: 0; animation: fade-in 0.4s forwards; }
        .line:nth-child(1)  { animation-delay: 0.8s; }
        .line:nth-child(2)  { animation-delay: 1.1s; }
        .line:nth-child(3)  { animation-delay: 1.4s; }
        .line:nth-child(4)  { animation-delay: 1.7s; }
        .line:nth-child(5)  { animation-delay: 2.0s; }
        .line:nth-child(6)  { animation-delay: 2.3s; }
        .line:nth-child(7)  { animation-delay: 2.6s; }
        .line:nth-child(8)  { animation-delay: 2.9s; }
        .line:nth-child(9)  { animation-delay: 3.2s; }
        .line:nth-child(10) { animation-delay: 3.5s; }
        .prompt { color: var(--accent); user-select: none; }
        .cmd    { color: var(--white); }
        .out    { color: var(--muted); }
        .val-up { color: var(--green); font-weight: 500; }
        .val-dn { color: var(--red); }
        .val-nu { color: var(--teal); font-weight: 500; }
        .cursor {
          display: inline-block; width: 8px; height: 14px;
          background: var(--accent); margin-left: 2px;
          animation: blink 1s step-end infinite;
          vertical-align: middle;
          opacity: 0;
          animation-delay: 3.8s, 3.8s;
        }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

        .stats-band {
          border-top: 1px solid var(--border-dim);
          border-bottom: 1px solid var(--border-dim);
          background: var(--bg-2);
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          padding: 0 100px;
        }
        .stat-item {
          padding: 40px 0;
          border-right: 1px solid var(--border-dim);
          padding-left: 40px;
          opacity: 1 !important;
          transform: none !important;
        }
        .stat-item:first-child { padding-left: 0; }
        .stat-item:last-child { border-right: none; }
        .stat-num {
          font-family: 'Playfair Display', serif;
          font-size: 42px;
          font-weight: 700;
          color: var(--teal);
          line-height: 1;
          margin-bottom: 8px;
        }
        .stat-num sup { font-size: 20px; vertical-align: super; }
        .stat-label {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 10px;
          letter-spacing: 0.14em;
          color: var(--muted);
          text-transform: uppercase;
        }

        .section {
          padding: 100px 100px;
        }
        .section-label {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 10px;
          letter-spacing: 0.2em;
          color: var(--accent);
          text-transform: uppercase;
          margin-bottom: 20px;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .section-label::after {
          content: '';
          flex: 1;
          height: 1px;
          background: var(--border);
          max-width: 60px;
        }
        .section-title {
          font-family: 'Playfair Display', serif;
          font-size: clamp(32px, 4vw, 52px);
          font-weight: 700;
          line-height: 1.1;
          color: var(--white);
          margin-bottom: 64px;
          max-width: 560px;
        }
        .section-title em { font-style: italic; color: var(--teal); }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1px;
          background: var(--border-dim);
        }
        .feature-card {
          background: var(--bg);
          padding: 40px 36px;
          position: relative;
          overflow: hidden;
          transition: background 0.25s;
          opacity: 1 !important;
          transform: none !important;
        }
        .feature-card:hover { background: var(--bg-2); }
        .feature-card::before {
          content: '';
          position: absolute;
          top: 0; left: 0;
          width: 2px;
          height: 0;
          background: var(--accent);
          transition: height 0.3s;
        }
        .feature-card:hover::before { height: 100%; }
        .feat-num {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 10px;
          letter-spacing: 0.14em;
          color: var(--teal);
          margin-bottom: 16px;
        }
        .feat-title {
          font-family: 'Playfair Display', serif;
          font-size: 22px;
          font-weight: 700;
          color: var(--white);
          margin-bottom: 12px;
          line-height: 1.2;
        }
        .feat-desc {
          font-size: 14px;
          line-height: 1.7;
          color: rgba(244, 244, 245, 0.6);
        }

        .stack-section {
          padding: 80px 100px;
          background: var(--bg-2);
          border-top: 1px solid var(--border-dim);
        }
        .stack-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 48px;
        }
        .stack-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          border: 1px solid var(--border);
          background: var(--bg-3);
          border-radius: 4px;
          padding: 10px 20px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 12px;
          color: var(--muted);
          letter-spacing: 0.06em;
          transition: border-color 0.2s, color 0.2s;
          cursor: default;
          opacity: 1 !important;
          transform: none !important;
        }
        .stack-pill:hover { border-color: var(--teal); color: var(--white); }
        .stack-pill span { width: 6px; height: 6px; border-radius: 50%; background: var(--teal); }

        .screen-section {
          padding: 100px;
          background: var(--bg);
          border-top: 1px solid var(--border-dim);
        }
        .screen-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 40px;
          margin-top: 56px;
        }
        .screen-card {
          border: 1px solid var(--border);
          border-radius: 8px;
          overflow: hidden;
          position: relative;
          background: var(--bg-2);
          padding: 4px;
          box-shadow: 0 20px 40px rgba(0,0,0,0.3);
          opacity: 1 !important;
          transform: none !important;
        }
        .screen-card img {
          width: 100%;
          height: auto;
          border-radius: 4px;
          display: block;
        }
        .screen-card-label {
          position: absolute;
          bottom: 24px;
          left: 24px;
          background: rgba(18, 18, 18, 0.85);
          border: 1px solid var(--border);
          border-radius: 4px;
          padding: 8px 16px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.1em;
          color: var(--teal);
          text-transform: uppercase;
        }

        .flow-container {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 40px;
        }
        .flow-step {
          display: flex;
          align-items: center;
          background: var(--bg-2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 24px;
          transition: transform 0.2s;
        }
        .flow-step:hover {
          transform: translateX(8px);
          border-color: var(--teal);
        }
        .flow-step-num {
          font-family: 'IBM Plex Mono', monospace;
          color: var(--teal);
          font-size: 20px;
          font-weight: 600;
          margin-right: 24px;
          border-right: 1px solid var(--border);
          padding-right: 24px;
          min-width: 60px;
          text-align: center;
        }
        .flow-step-content h3 {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 15px;
          color: var(--white);
          margin: 0 0 6px 0;
        }
        .flow-step-content p {
          font-size: 13px;
          color: var(--muted);
          line-height: 1.5;
          margin: 0;
        }
        .backdrop-filter { backdrop-filter: blur(8px); }

        footer {
          border-top: 1px solid var(--border-dim);
          padding: 60px 100px;
          background: var(--bg-2);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .footer-brand {
          font-family: 'Playfair Display', serif;
          font-size: 22px;
          font-weight: 700;
          color: var(--white);
        }
        .footer-brand span { color: var(--teal); font-style: italic; }
        .footer-links {
          display: flex;
          gap: 32px;
        }
        .footer-links a {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.1em;
          color: var(--muted);
          text-decoration: none;
          text-transform: uppercase;
          transition: color 0.2s;
        }
        .footer-links a:hover { color: var(--teal); }
        .footer-copy {
          font-family: 'IBM Plex Mono', monospace;
          font-size: 10px;
          color: var(--muted);
          letter-spacing: 0.06em;
        }

        @keyframes fade-in  { from { opacity:0; } to { opacity:1; } }
        @keyframes fade-up  { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
        .fade-up { opacity:0; animation: fade-up 0.7s ease forwards; }
        .delay-1 { animation-delay: 0.1s; }
        .delay-2 { animation-delay: 0.25s; }
        .delay-3 { animation-delay: 0.4s; }
        .delay-4 { animation-delay: 0.55s; }

        @media (max-width: 1024px) {
          .hero { grid-template-columns: 1fr; padding: 60px 40px; }
          .terminal { display: none; }
          .stats-band { grid-template-columns: repeat(2,1fr); padding: 0 40px; }
          .section, .stack-section, .arch-section, .screen-section { padding: 60px 40px; }
          .features-grid { grid-template-columns: 1fr; }
          .screen-grid { grid-template-columns: 1fr; }
          .flow-step { flex-direction: column; text-align: center; }
          .flow-step-num { border-right: none; border-bottom: 1px solid var(--border); padding-right: 0; padding-bottom: 16px; margin-right: 0; margin-bottom: 16px; }
          footer { flex-direction: column; gap: 32px; text-align: center; padding: 40px; }
        }
      `}} />

      {/* TICKER */}
      <div className="ticker-wrap">
        <div className="ticker-inner">
          {tickerItems.map((item, idx) => (
            <span key={idx} className="ticker-item">
              <span className="sym">{item.name}</span>
              <span className={item.up ? "up" : "dn"}>
                {item.up ? '▲' : '▼'} {item.price}
              </span>
              <span className={item.up ? "up" : "dn"}>
                {item.up ? '+' : ''}{item.pct}%
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* HERO */}
      <section className="hero">
        <div className="hero-left">
          <div className="hero-label fade-up">Quantitative Trading Platform V2</div>
          <h1 className="hero-title fade-up delay-1"><span style={{ fontFamily: "'Yatra One', system-ui" }}>धन</span> <em>Niti</em></h1>
          <p className="hero-sub fade-up delay-2">Advanced Agentic Intelligence</p>
          <p className="hero-desc fade-up delay-3">
            An elite dashboard for Indian equity markets — combining Reinforcement Learning (PPO/SAC) portfolio optimization, Groq LLM advisory, and institutional-grade charting (Volume Profile, Footprint, DOM) powered by Next.js and FastAPI.
          </p>
          <div className="cta-row fade-up delay-4">
            <Link href="/dashboard" className="btn-primary">
              View App Demo
            </Link>
            <a href="https://github.com/siddharthsky/Dhan-Optimizer" className="btn-secondary" target="_blank" rel="noopener noreferrer">
              GitHub Repository
            </a>
          </div>
        </div>

        <div className="terminal" style={{ animationDelay: '0.3s' }}>
          <div className="terminal-bar">
            <div className="dot r"></div>
            <div className="dot y"></div>
            <div className="dot g"></div>
            <span className="terminal-title">dhan_niti_v2 — agent_training_session</span>
          </div>
          <div className="terminal-body">
            <div className="line"><span className="prompt">➜</span><span className="cmd">poetry run python train_agent.py --algo PPO --epochs 2000</span></div>
            <div className="line"><span className="out">  [✓] Fetching 5Y historical context ...........</span></div>
            <div className="line"><span className="out">  [✓] Initializing Stable-Baselines3 Env .......</span></div>
            <div className="line"><span className="out">  [✓] Setting up Groq Llama-3 reward layer .....</span></div>
            <div className="line"><span className="out">  [✓] Running episodes .........................</span></div>
            <div className="line"><span className="prompt"> </span></div>
            <div className="line"><span className="out">  AGENT PERFORMANCE METRICS</span></div>
            <div className="line"><span className="out">  ─────────────────────────────────</span></div>
            <div className="line"><span className="out">  Initial Portfolio <span className="val-nu">₹ 1,000,000.00</span></span></div>
            <div className="line"><span className="out">  Final Portfolio   <span className="val-up">₹ 3,248,150.20</span></span></div>
            <div className="line"><span className="out">  Max Drawdown      <span className="val-dn">-14.2%</span></span></div>
            <div className="line"><span className="out">  Sharpe Ratio      <span className="val-up">2.14</span></span></div>
            <div className="line"><span className="prompt"> </span></div>
            <div className="line"><span className="out">  [✓] Exporting PPO model to ONNX format...</span></div>
            <span className="cursor"></span>
          </div>
        </div>
      </section>

      {/* STATS BAND */}
      <div className="stats-band">
        <div className="stat-item">
          <div className="stat-num" data-target="2">V<span className="counter">2</span></div>
          <div className="stat-label">Architecture Update</div>
        </div>
        <div className="stat-item">
          <div className="stat-num"><span className="counter">5</span>ms</div>
          <div className="stat-label">Websocket Latency</div>
        </div>
        <div className="stat-item">
          <div className="stat-num"><span className="counter">L3</span></div>
          <div className="stat-label">Groq AI Advisory</div>
        </div>
        <div className="stat-item">
          <div className="stat-num"><span>∞</span></div>
          <div className="stat-label">Open Source · Free</div>
        </div>
      </div>

      {/* FEATURES */}
      <section className="section" id="features">
        <div className="section-label">Core Capabilities</div>
        <h2 className="section-title">Engineered for<br/><em>Outperformance</em></h2>
        <div className="features-grid">

          <div className="feature-card">
            <div className="feat-num">01 / CHARTING</div>
            <div className="feat-title">Institutional Charting</div>
            <p className="feat-desc">
              Powered by Lightweight Charts. Features real-time Candlesticks, Footprint/Heatmap charts, Volume Profile overlays, and multi-timeframe panel layouts for deep orderflow analysis.
            </p>
          </div>

          <div className="feature-card">
            <div className="feat-num">02 / AGENTIC RL</div>
            <div className="feat-title">PPO & SAC Optimization</div>
            <p className="feat-desc">
              Portfolio rebalancing driven by advanced Reinforcement Learning agents (Stable-Baselines3). Evaluates market regimes and optimizes for maximum Sharpe ratio dynamically.
            </p>
          </div>

          <div className="feature-card">
            <div className="feat-num">03 / ADVISOR</div>
            <div className="feat-title">Groq Llama-3 AI</div>
            <p className="feat-desc">
              Integrated LLM intelligence parses breaking news, correlates sentiment with price action, and provides natural-language reasoning for portfolio allocation shifts.
            </p>
          </div>

          <div className="feature-card">
            <div className="feat-num">04 / ORDERFLOW</div>
            <div className="feat-title">Real-Time DOM & Imbalance</div>
            <p className="feat-desc">
              Connects directly to Fyers WebSocket for live 50-level Depth of Market (L2) data. Calculates order imbalances and buy/sell sentiment instantaneously.
            </p>
          </div>

          <div className="feature-card">
            <div className="feat-num">05 / INDICATORS</div>
            <div className="feat-title">Dynamic Tech Engine</div>
            <p className="feat-desc">
              Custom TypeScript engine calculates SMA, EMA, VWAP, and Bollinger Bands on the fly, rendering seamlessly directly on the live WebGL canvas.
            </p>
          </div>

          <div className="feature-card">
            <div className="feat-num">06 / UX</div>
            <div className="feat-title">Next.js & Tailwind</div>
            <p className="feat-desc">
              Rewritten from Streamlit to a state-of-the-art Next.js App Router SPA. Features a premium charcoal-slate UI, ultra-fast navigation, and fully responsive data grids.
            </p>
          </div>

        </div>
      </section>

      {/* SCREENSHOT SECTION */}
      <section className="screen-section" id="demo">
        <div className="section-label">Interface Preview</div>
        <h2 className="section-title">The <em>Workbench</em></h2>
        <div className="screen-grid">

          <div className="screen-card">
            <img src="/assets/dashboard.png" alt="Main Dashboard UI" />
            <div className="screen-card-label">Main Dashboard & KPI Panel</div>
          </div>

          <div className="screen-card">
            <img src="/assets/allocations.png" alt="Portfolio Allocations" />
            <div className="screen-card-label">RL Agent Portfolio Allocations</div>
          </div>
          
          <div className="screen-card">
            <img src="/assets/charts_candlestick.png" alt="Candlestick Charting" />
            <div className="screen-card-label">Candlestick & Volume Profile</div>
          </div>

          <div className="screen-card">
            <img src="/assets/charts_footprint.png" alt="Footprint Charting" />
            <div className="screen-card-label">Orderflow Footprint Charts</div>
          </div>

          <div className="screen-card">
            <img src="/assets/charts_dom.png" alt="Depth of Market" />
            <div className="screen-card-label">L2 Depth of Market (DOM)</div>
          </div>

          <div className="screen-card">
            <img src="/assets/groq.png" alt="Groq LLM Synthesis" />
            <div className="screen-card-label">Groq AI Advisory & RAG Memory</div>
          </div>

        </div>
      </section>

      {/* ARCHITECTURE FLOWCHART SECTION */}
      <section className="section" id="architecture" style={{ background: 'var(--bg-3)' }}>
        <div className="section-label">Architecture</div>
        <h2 className="section-title">AI Decision <em>Pipeline</em></h2>
        <div className="flow-container">
          
          <div className="flow-step">
            <div className="flow-step-num">01</div>
            <div className="flow-step-content">
              <h3>Market Data Ingestion (Fyers WebSocket)</h3>
              <p>L2 Depth of Market and live tick data is streamed via WebSockets. The system builds real-time OHLCV candles, calculates order imbalances, and aggregates tick-level footprint data.</p>
            </div>
          </div>

          <div className="flow-step">
            <div className="flow-step-num">02</div>
            <div className="flow-step-content">
              <h3>XGBoost Signal Generation</h3>
              <p>Live technical indicators (SMA, EMA, VWAP, Bollinger Bands) are fed into an XGBoost classification model to predict short-term directional probabilities (Buy/Hold/Sell) and output a confidence score.</p>
            </div>
          </div>

          <div className="flow-step">
            <div className="flow-step-num">03</div>
            <div className="flow-step-content">
              <h3>Stable-Baselines3 Agent Rebalancing</h3>
              <p>The Reinforcement Learning agent (PPO/SAC) evaluates the XGBoost signals alongside the current portfolio state and market regime (e.g., VIX). It outputs continuous actions to reallocate optimal portfolio weights for maximum Sharpe Ratio.</p>
            </div>
          </div>

          <div className="flow-step">
            <div className="flow-step-num">04</div>
            <div className="flow-step-content">
              <h3>Groq Llama-3 Synthesis & RAG Memory</h3>
              <p>The proposed allocations are sent to a Groq Llama-3 model alongside past episodic memories stored in Qdrant (Vector DB). The LLM synthesizes the logic, cross-references historical regimes, and outputs a human-readable advisory report.</p>
            </div>
          </div>

          <div className="flow-step">
            <div className="flow-step-num">05</div>
            <div className="flow-step-content">
              <h3>Execution & Frontend Rendering</h3>
              <p>The final verified allocations are displayed on the Next.js institutional dashboard. Traders review the AI's reasoning, investigate the charts, and approve execution via the Python FastAPI backend.</p>
            </div>
          </div>

        </div>
      </section>

      {/* TECH STACK */}
      <section className="stack-section">
        <div className="section-label">Technology</div>
        <h2 className="section-title">Stack &amp; <em>Dependencies</em></h2>
        <div className="stack-grid">
          <div className="stack-pill"><span></span>Next.js 14</div>
          <div className="stack-pill"><span></span>TypeScript</div>
          <div className="stack-pill"><span></span>Tailwind CSS</div>
          <div className="stack-pill"><span></span>FastAPI</div>
          <div className="stack-pill"><span></span>Python 3.10+</div>
          <div className="stack-pill"><span></span>Stable-Baselines3</div>
          <div className="stack-pill"><span></span>Groq / Llama-3</div>
          <div className="stack-pill"><span></span>Lightweight Charts</div>
          <div className="stack-pill"><span></span>Fyers API & WebSockets</div>
          <div className="stack-pill"><span></span>Vercel</div>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="footer-brand">Dhan <span>Niti</span></div>
        <div className="footer-links">
          <a href="https://github.com/siddharthsky/Dhan-Optimizer" target="_blank" rel="noopener noreferrer">GitHub</a>
          <a href="#features">Features</a>
          <a href="#demo">Demo</a>
        </div>
        <div className="footer-copy">
          MIT License · Personal Research Tool · Not Financial Advice
        </div>
      </footer>
    </>
  );
}

// ── DhanNiti Console Logger ────────────────────────────────────
// Provides rich, styled, grouped console output for every app event.
// Open DevTools > Console to see all tagged events in real-time.

const STYLES = {
  CLICK:    "background:#00d97e22;color:#00d97e;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #00d97e",
  LOAD:     "background:#3b82f622;color:#60a5fa;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #3b82f6",
  WS:       "background:#a855f722;color:#c084fc;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #a855f7",
  PIPELINE: "background:#f59e0b22;color:#fbbf24;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #f59e0b",
  SUCCESS:  "background:#10b98122;color:#34d399;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #10b981",
  ERROR:    "background:#ef444422;color:#f87171;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #ef4444",
  NAV:      "background:#0ea5e922;color:#38bdf8;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #0ea5e9",
  DATA:     "background:#8b5cf622;color:#a78bfa;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #8b5cf6",
  CONFIG:   "background:#f9731622;color:#fb923c;font-weight:bold;padding:2px 8px;border-radius:4px;border-left:3px solid #f97316",
  LABEL:    "color:#94a3b8;font-size:10px",
};

const ts = () => new Date().toLocaleTimeString("en-IN", { hour12: false });

/** Button/user click event */
export const logClick = (action: string, detail?: Record<string, unknown>) => {
  console.group(`%c🖱 CLICK%c  ${action}  %c${ts()}`, STYLES.CLICK, "color:#e2e8f0;font-weight:bold", STYLES.LABEL);
  if (detail) console.table(detail);
  console.groupEnd();
};

/** Data fetch started */
export const logLoadStart = (resource: string, params?: Record<string, unknown>) => {
  console.group(`%c⏳ LOAD START%c  ${resource}  %c${ts()}`, STYLES.LOAD, "color:#e2e8f0;font-weight:bold", STYLES.LABEL);
  if (params) console.table(params);
  console.groupEnd();
};

/** Data fetch completed successfully */
export const logLoadSuccess = (resource: string, summary?: Record<string, unknown>) => {
  console.group(`%c✅ LOAD OK%c  ${resource}  %c${ts()}`, STYLES.SUCCESS, "color:#e2e8f0;font-weight:bold", STYLES.LABEL);
  if (summary) console.table(summary);
  console.groupEnd();
};

/** Data fetch failed */
export const logLoadError = (resource: string, error: unknown) => {
  console.group(`%c❌ LOAD ERROR%c  ${resource}  %c${ts()}`, STYLES.ERROR, "color:#e2e8f0;font-weight:bold", STYLES.LABEL);
  console.error(error);
  console.groupEnd();
};

/** WebSocket lifecycle event */
export const logWs = (event: string, detail?: Record<string, unknown>) => {
  console.group(`%c🔌 WS%c  ${event}  %c${ts()}`, STYLES.WS, "color:#e2e8f0;font-weight:bold", STYLES.LABEL);
  if (detail) console.table(detail);
  console.groupEnd();
};

/** Pipeline node progress update */
export const logPipeline = (node: string, label: string, completedCount: number, total: number) => {
  const pct = Math.round((completedCount / total) * 100);
  console.log(
    `%c⚙ PIPELINE%c  [${pct}%] ${label}  %c${ts()}`,
    STYLES.PIPELINE, "color:#e2e8f0;font-weight:bold", STYLES.LABEL
  );
};

/** Navigation / tab change */
export const logNav = (to: string, from?: string) => {
  console.log(
    `%c🧭 NAV%c  ${from ? `${from} → ` : ""}${to}  %c${ts()}`,
    STYLES.NAV, "color:#e2e8f0;font-weight:bold", STYLES.LABEL
  );
};

/** Ticker selection change */
export const logTickerSelect = (ticker: string, context?: string) => {
  console.log(
    `%c📈 TICKER%c  ${ticker}${context ? `  (${context})` : ""}  %c${ts()}`,
    STYLES.DATA, "color:#e2e8f0;font-weight:bold", STYLES.LABEL
  );
};

/** Config/setup change */
export const logConfig = (key: string, value: unknown) => {
  console.log(
    `%c⚙ CONFIG%c  ${key} = ${JSON.stringify(value)}  %c${ts()}`,
    STYLES.CONFIG, "color:#e2e8f0;font-weight:bold", STYLES.LABEL
  );
};

/** Generic app event */
export const logEvent = (label: string, detail?: Record<string, unknown>) => {
  console.group(`%c🔔 EVENT%c  ${label}  %c${ts()}`, STYLES.CLICK, "color:#e2e8f0;font-weight:bold", STYLES.LABEL);
  if (detail) console.table(detail);
  console.groupEnd();
};

// Print a startup banner so user knows logging is active
console.log(
  "%c╔═══════════════════════════════════════╗\n║   DhanNiti  Console Logger  Active    ║\n║   Open DevTools → Console to trace    ║\n╚═══════════════════════════════════════╝",
  "color:#00d97e;font-weight:bold;font-family:monospace"
);

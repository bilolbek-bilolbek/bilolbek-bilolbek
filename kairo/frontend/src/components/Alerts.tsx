import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { subscribeAlerts } from "../api";
import type { Alert } from "../types";
import { ago } from "../format";

const TOAST_MS = 9000;

function canNotify() {
  return typeof Notification !== "undefined";
}

function AlertBody({ a }: { a: Alert }) {
  const up = a.change_pct >= 0;
  return (
    <>
      <div className="alert-top">
        <b className={up ? "up" : "down"}>{a.title}</b>
        <span className="faint">{a.kind === "test" ? "test" : ago(a.at)}</span>
      </div>
      <div className="alert-reason">
        {a.reason
          ? <>Likely: <b>{a.reason}</b>{a.reason_likelihood != null && <span className="faint mono"> {Math.round(a.reason_likelihood * 100)}%</span>}</>
          : <span className="faint">Checking the news…</span>}
      </div>
    </>
  );
}

/**
 * Bell in the top bar + pop-up cards when a watchlist stock moves sharply.
 * The cards render into <body>: the top bar's blur effect would otherwise pin them to the bar.
 */
export default function Alerts({ onPick }: { onPick: (ticker: string) => void }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [toasts, setToasts] = useState<number[]>([]);
  const [open, setOpen] = useState(false);
  const [unseen, setUnseen] = useState(0);
  const [perm, setPerm] = useState(canNotify() ? Notification.permission : "denied");
  const started = useRef(Date.now());
  const seen = useRef(new Set<number>());

  useEffect(() => subscribeAlerts((a) => {
    // The same alert comes again once its reason is refreshed: update it, don't count it twice.
    const isNew = !seen.current.has(a.id);
    seen.current.add(a.id);
    setAlerts((prev) => (isNew ? [a, ...prev].slice(0, 30) : prev.map((x) => (x.id === a.id ? a : x))));
    // Old alerts replayed on connect go in the list quietly; new ones pop up.
    const fresh = Date.parse(a.at) >= started.current - 5000;
    if (isNew && fresh) {
      setUnseen((n) => n + 1);
      setToasts((t) => [a.id, ...t].slice(0, 3));
      setTimeout(() => setToasts((t) => t.filter((id) => id !== a.id)), TOAST_MS);
      if (canNotify() && Notification.permission === "granted" && document.hidden) {
        new Notification(a.title, { body: a.reason ? `Likely: ${a.reason}` : "Kairo is checking the news" });
      }
    }
  }), []);

  const byId = (id: number) => alerts.find((a) => a.id === id);
  const go = (a: Alert) => { onPick(a.ticker); setOpen(false); setToasts((t) => t.filter((id) => id !== a.id)); };

  return (
    <>
      <div className="bell-wrap">
        <button className="bell" aria-label={`Alerts${unseen ? `, ${unseen} new` : ""}`} aria-expanded={open}
                onClick={() => { setOpen(!open); setUnseen(0); }}>
          <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden="true">
            <path d="M10 2.5a5 5 0 0 0-5 5v3.2L3.5 13.5h13L15 10.7V7.5a5 5 0 0 0-5-5z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M8 16a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          {unseen > 0 && <span className="badge">{unseen}</span>}
        </button>
        {open && (
          <div className="alert-panel" role="dialog" aria-label="Alerts">
            <div className="alert-panel-head">
              <b>Alerts</b>
              <span className="faint small">1% in 15 min, or a 3% day</span>
            </div>
            {alerts.length === 0 && <p className="faint small pad">No sharp moves yet. Alerts appear here while the market trades.</p>}
            <ul>
              {alerts.map((a) => (
                <li key={a.id}><button className="alert-item" onClick={() => go(a)}><AlertBody a={a} /></button></li>
              ))}
            </ul>
            {canNotify() && perm !== "granted" && perm !== "denied" && (
              <button className="notify-btn" onClick={() => Notification.requestPermission().then(setPerm)}>
                Also notify me when this tab is in the background
              </button>
            )}
          </div>
        )}
      </div>
      {createPortal(<div className="toasts" aria-live="polite">
        {toasts.map(byId).filter(Boolean).map((a) => (
          <button key={a!.id} className={`toast ${a!.change_pct >= 0 ? "t-up" : "t-down"}`} onClick={() => go(a!)}>
            <AlertBody a={a!} />
          </button>
        ))}
      </div>, document.body)}
    </>
  );
}

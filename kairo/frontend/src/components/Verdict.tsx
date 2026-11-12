import type { Analysis, Driver, NewsItem } from "../types";
import { CATEGORY_LABEL } from "../types";
import { ago, speed } from "../format";

interface Props {
  analysis: Analysis | null;
  loading: boolean;
  news: NewsItem[];
  active: number | null;
  onSelect: (i: number | null) => void;
  ticker: string;
}

const pct = (x: number) => `${Math.round(x * 100)}%`;

/** One bar split by how likely each reason is; the grey part is what the news doesn't explain. */
function SplitBar({ drivers, unexplained, active, onSelect }: {
  drivers: Driver[]; unexplained: number; active: number | null; onSelect: Props["onSelect"];
}) {
  return (
    <div className="split" role="img" aria-label="How the likelihood splits across reasons">
      {drivers.map((d, i) => (
        <button key={i} className={`seg cat-bg-${d.category} ${active === i ? "on" : ""}`}
                style={{ flexGrow: Math.max(d.likelihood, 0.02) }}
                title={`${d.title}: ${pct(d.likelihood)}`} onClick={() => onSelect(active === i ? null : i)} />
      ))}
      {unexplained > 0.01 && <span className="seg seg-rest" style={{ flexGrow: unexplained }} title={`Not explained: ${pct(unexplained)}`} />}
    </div>
  );
}

function DriverRow({ d, i, open, news, onSelect }: {
  d: Driver; i: number; open: boolean; news: NewsItem[]; onSelect: Props["onSelect"];
}) {
  const evidence = d.evidence_ids.map((id) => news.find((n) => n.id === id)).filter(Boolean) as NewsItem[];
  return (
    <li className={`driver ${open ? "open" : ""}`}>
      <button className="driver-main" onClick={() => onSelect(open ? null : i)} aria-expanded={open}>
        <span className={`dot cat-bg-${d.category}`} />
        <span className="driver-text">
          <span className="driver-title">{d.title}</span>
          <span className="driver-meta">
            {CATEGORY_LABEL[d.category]} · <span className={d.direction === "up" ? "up" : "down"}>
              {d.direction === "up" ? "▲ pushed it up" : "▼ pushed it down"}</span>
          </span>
        </span>
        <span className="driver-pct mono">{pct(d.likelihood)}</span>
      </button>
      <p className="driver-why">{d.explanation}</p>
      {open && evidence.length > 0 && (
        <ul className="evidence">
          {evidence.map((n) => (
            <li key={n.id}>
              {n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.headline}</a> : n.headline}
              <span className="faint"> · {n.source} · {ago(n.published_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function Verdict({ analysis, loading, news, active, onSelect, ticker }: Props) {
  const instant = analysis?.from_cache;
  return (
    <section className="card verdict" aria-live="polite">
      <header className="verdict-head">
        <span className="eyebrow gold">Kairo verdict · {ticker}</span>
        {analysis && (
          <span className={`chip speed ${instant ? "instant" : ""}`}
                title={instant ? `Pre-computed ${ago(analysis.analyzed_at)}; the AI took ${speed(analysis.latency_ms)}` : "Analyzed just now"}>
            {instant ? "⚡ " : ""}{speed(analysis.served_ms ?? analysis.latency_ms)}
          </span>
        )}
      </header>

      {loading && !analysis && (
        <div className="thinking">
          <div className="scan"><span /><span /><span /></div>
          <p>Reading the news around {ticker} and lining it up with the price…</p>
        </div>
      )}

      {analysis && (
        <>
          <p className="verdict-text">{analysis.summary}</p>
          <SplitBar drivers={analysis.drivers} unexplained={analysis.unexplained} active={active} onSelect={onSelect} />
          <div className="split-legend">
            <span>Likely reasons</span>
            <span className="faint">{pct(analysis.unexplained)} not explained by the news</span>
          </div>
          <ol className="drivers">
            {analysis.drivers.map((d, i) => (
              <DriverRow key={i} d={d} i={i} open={active === i} news={news} onSelect={onSelect} />
            ))}
          </ol>
          {analysis.watch_next.length > 0 && (
            <div className="watch">
              <span className="eyebrow">What to watch next</span>
              <ul>{analysis.watch_next.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}
          <footer className="verdict-foot faint">
            <span className={`conf conf-${analysis.confidence}`}>{analysis.confidence} confidence</span>
            <span>{analysis.engine.replace("openai:", "AI · ")}{analysis.analyzed_at ? ` · ${ago(analysis.analyzed_at)}` : ""}</span>
          </footer>
          {analysis.warnings.map((w, i) => <p key={i} className="warning">{w}</p>)}
        </>
      )}
    </section>
  );
}

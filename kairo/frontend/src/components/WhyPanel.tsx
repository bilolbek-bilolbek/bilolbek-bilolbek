import type { Analysis, Driver, NewsItem } from "../types";
import { CATEGORY_LABEL } from "../types";

interface Props {
  analysis: Analysis | null;
  loading: boolean;
  news: NewsItem[];
  active: number | null;
  onSelect: (i: number | null) => void;
}

function pct(x: number) {
  return `${Math.round(x * 100)}%`;
}

function DriverCard({ d, i, active, news, onSelect }: { d: Driver; i: number; active: boolean; news: NewsItem[]; onSelect: Props["onSelect"] }) {
  const evidence = d.evidence_ids.map((id) => news.find((n) => n.id === id)).filter(Boolean) as NewsItem[];
  return (
    <button className={`driver ${active ? "active" : ""}`} onClick={() => onSelect(active ? null : i)}>
      <div className="driver-top">
        <span className="rank">{i + 1}</span>
        <span className="driver-title">{d.title}</span>
        <span className="likelihood mono">{pct(d.likelihood)}</span>
      </div>
      <div className="bar"><div className={`fill ${d.direction}`} style={{ width: pct(d.likelihood) }} /></div>
      <div className="chips">
        <span className={`chip cat-${d.category}`}>{CATEGORY_LABEL[d.category]}</span>
        <span className={`chip dir-${d.direction}`}>{d.direction === "up" ? "▲ pushed up" : "▼ pushed down"}</span>
      </div>
      <p className="explanation">{d.explanation}</p>
      {active && evidence.length > 0 && (
        <ul className="evidence">
          {evidence.map((n) => (
            <li key={n.id}>
              {n.url ? <a href={n.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{n.headline}</a> : n.headline}
              <span className="src"> · {n.source}</span>
            </li>
          ))}
        </ul>
      )}
    </button>
  );
}

export default function WhyPanel({ analysis, loading, news, active, onSelect }: Props) {
  return (
    <section className="panel why">
      <header className="panel-head">
        <h2>Why is it moving?</h2>
        {analysis && <span className="muted small mono">{(analysis.latency_ms / 1000).toFixed(1)}s · {analysis.engine}</span>}
      </header>

      {loading && !analysis && (
        <div className="thinking">
          <div className="pulse" />
          <span>Reading the headlines and lining them up with the price…</span>
        </div>
      )}

      {analysis && (
        <>
          <p className="summary">{analysis.summary}</p>
          <div className="drivers">
            {analysis.drivers.map((d, i) => (
              <DriverCard key={i} d={d} i={i} active={active === i} news={news} onSelect={onSelect} />
            ))}
          </div>
          <div className="unexplained">
            <span>Not explained by the news</span>
            <span className="mono">{pct(analysis.unexplained)}</span>
          </div>
          <div className="meta-row">
            <span className={`confidence c-${analysis.confidence}`}>Confidence: {analysis.confidence}</span>
          </div>
          {analysis.watch_next.length > 0 && (
            <div className="watch">
              <h3>What to watch next</h3>
              <ul>{analysis.watch_next.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}
          {analysis.warnings.map((w, i) => <p key={i} className="warning small">{w}</p>)}
        </>
      )}
    </section>
  );
}

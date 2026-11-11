import { useState } from "react";
import type { Bucket, NewsItem } from "../types";
import { CATEGORY_LABEL } from "../types";

const TABS: (Bucket | "all")[] = ["all", "company", "peers_supply_chain", "sector", "macro", "geopolitics"];

function ago(iso: string) {
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

export default function NewsFeed({ news, highlighted }: { news: NewsItem[]; highlighted: string[] }) {
  const [tab, setTab] = useState<Bucket | "all">("all");
  const shown = tab === "all" ? news : news.filter((n) => n.bucket === tab);
  return (
    <section className="panel news">
      <header className="panel-head">
        <h2>News around this stock</h2>
        <span className="muted small">{news.length} headlines</span>
      </header>
      <div className="tabs">
        {TABS.map((t) => {
          const count = t === "all" ? news.length : news.filter((n) => n.bucket === t).length;
          return (
            <button key={t} className={`tab ${tab === t ? "on" : ""}`} onClick={() => setTab(t)} disabled={!count}>
              {t === "all" ? "All" : CATEGORY_LABEL[t]} <span className="muted">{count}</span>
            </button>
          );
        })}
      </div>
      <ul className="headlines">
        {shown.map((n) => (
          <li key={n.id} className={highlighted.includes(n.id) ? "hot" : ""}>
            <span className={`dot cat-${n.bucket}`} />
            <div>
              {n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.headline}</a> : <span>{n.headline}</span>}
              <div className="muted small">
                {n.source} · {ago(n.published_at)}
                {n.reaction_pct !== null && Math.abs(n.reaction_pct) >= 0.05 && (
                  <span className={`reaction mono ${n.reaction_pct >= 0 ? "up" : "down"}`} title="Stock move right after this headline">
                    {" "}· {n.reaction_pct >= 0 ? "+" : ""}{n.reaction_pct.toFixed(2)}% after
                  </span>
                )}
              </div>
            </div>
          </li>
        ))}
        {!shown.length && <li className="muted">No headlines in this group.</li>}
      </ul>
    </section>
  );
}

import { useState } from "react";
import type { Bucket, NewsItem } from "../types";
import { CATEGORY_LABEL } from "../types";
import { ago, signed } from "../format";

const TABS: (Bucket | "all")[] = ["all", "company", "peers_supply_chain", "sector", "macro", "geopolitics"];

export default function NewsFeed({ news, highlighted }: { news: NewsItem[]; highlighted: string[] }) {
  const [tab, setTab] = useState<Bucket | "all">("all");
  const [expanded, setExpanded] = useState(false);
  const filtered = tab === "all" ? news : news.filter((n) => n.bucket === tab);
  const LIMIT = 8;
  // Headlines tied to the selected reason always stay visible.
  const shown = expanded ? filtered : filtered.filter((n, i) => i < LIMIT || highlighted.includes(n.id));
  return (
    <section className="card news">
      <header className="card-head">
        <h2>News around this stock</h2>
        <span className="faint">{news.length} headlines · price move shown after each</span>
      </header>
      <div className="tabs" role="tablist">
        {TABS.map((t) => {
          const count = t === "all" ? news.length : news.filter((n) => n.bucket === t).length;
          return (
            <button key={t} role="tab" aria-selected={tab === t} className={`tab ${tab === t ? "on" : ""}`}
                    onClick={() => setTab(t)} disabled={!count}>
              {t !== "all" && <span className={`dot cat-bg-${t}`} />}
              {t === "all" ? "All" : CATEGORY_LABEL[t]} <span className="faint">{count}</span>
            </button>
          );
        })}
      </div>
      <ul className="timeline">
        {shown.map((n) => (
          <li key={n.id} className={highlighted.includes(n.id) ? "hot" : ""}>
            <span className="tl-time mono faint">{ago(n.published_at)}</span>
            <span className={`tl-dot cat-bg-${n.bucket}`} />
            <div className="tl-body">
              {n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.headline}</a> : <span>{n.headline}</span>}
              <div className="tl-meta">
                <span>{n.source}</span>
                {n.reaction_pct !== null && Math.abs(n.reaction_pct) >= 0.05 && (
                  <span className={`react mono ${n.reaction_pct >= 0 ? "up" : "down"}`} title="How the stock moved right after this headline">
                    {signed(n.reaction_pct)} after
                  </span>
                )}
              </div>
            </div>
          </li>
        ))}
        {!shown.length && <li className="faint">No headlines in this group.</li>}
      </ul>
      {filtered.length > shown.length && (
        <button className="more" onClick={() => setExpanded(true)}>Show all {filtered.length} headlines</button>
      )}
    </section>
  );
}

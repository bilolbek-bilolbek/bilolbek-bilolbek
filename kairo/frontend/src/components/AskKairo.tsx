import { Fragment, useEffect, useRef, useState } from "react";
import { askKairo, type ChatTurn } from "../api";
import type { NewsItem, Window } from "../types";

const SUGGESTIONS = [
  "Is this already priced in?",
  "What would change this explanation?",
  "How did its peers move?",
  "Explain it like I'm new to trading",
];

/** Turns [H3] citations into links to the matching headline. */
function Answer({ text, news }: { text: string; news: NewsItem[] }) {
  const parts = text.split(/(\[H\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[H(\d+)\]$/);
        if (!m) return <Fragment key={i}>{p}</Fragment>;
        const n = news[Number(m[1]) - 1];
        if (!n) return <Fragment key={i}>{p}</Fragment>;
        const label = `H${m[1]}`;
        return n.url
          ? <a key={i} className="cite" href={n.url} target="_blank" rel="noreferrer" title={`${n.headline} · ${n.source}`}>{label}</a>
          : <span key={i} className="cite" title={`${n.headline} · ${n.source}`}>{label}</span>;
      })}
    </>
  );
}

export default function AskKairo({ ticker, window, news }: { ticker: string; window: Window; news: NewsItem[] }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);

  // A new stock starts a new conversation.
  useEffect(() => {
    abort.current?.abort();
    setTurns([]);
    setBusy(false);
  }, [ticker, window]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const history = turns;
    setTurns([...history, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setDraft("");
    setBusy(true);
    abort.current = new AbortController();
    try {
      await askKairo(ticker, window, q, history, (soFar) =>
        setTurns((t) => [...t.slice(0, -1), { role: "assistant", content: soFar }]), abort.current.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setTurns((t) => [...t.slice(0, -1), { role: "assistant", content: "Couldn't reach the Kairo server. Is it running?" }]);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card ask">
      <header className="card-head">
        <h2>Ask Kairo</h2>
        <span className="faint">about {ticker}</span>
      </header>
      {turns.length === 0 && (
        <div className="suggestions">
          {SUGGESTIONS.map((s) => <button key={s} className="chip suggestion" onClick={() => send(s)}>{s}</button>)}
        </div>
      )}
      {turns.length > 0 && (
        <div className="chat">
          {turns.map((t, i) => (
            <div key={i} className={`msg ${t.role}`}>
              {t.role === "assistant"
                ? (t.content ? <Answer text={t.content} news={news} /> : <span className="typing"><i /><i /><i /></span>)
                : t.content}
            </div>
          ))}
          <div ref={end} />
        </div>
      )}
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <input id="ask-input" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={1000}
               placeholder={`Ask a follow-up about ${ticker}…`} aria-label={`Ask Kairo about ${ticker}`} />
        <button type="submit" className="send" disabled={busy || !draft.trim()} aria-label="Send">↑</button>
      </form>
      <p className="faint small">Answers come from the headlines above. Not investment advice.</p>
    </section>
  );
}

export type Bucket = "company" | "peers_supply_chain" | "sector" | "macro" | "geopolitics";
export type Category = Bucket | "market_flow";
export type Window = "1d" | "5d" | "1mo";

export interface PricePoint { t: string; price: number }
export interface PriceMove {
  symbol: string; last: number; reference: number; change_pct: number; high: number; low: number;
}
export interface NewsItem {
  id: string; headline: string; summary: string; source: string; url: string | null;
  published_at: string; bucket: Bucket; reaction_pct: number | null;
}
export interface MarketContext {
  ticker: string; company: string; sector: string; window: Window;
  stock: PriceMove; benchmark: PriceMove | null; sector_etf: PriceMove | null;
  excess_vs_market_pct: number | null; excess_vs_sector_pct: number | null;
  series: PricePoint[]; news: NewsItem[]; is_sample: boolean;
  sources: string[]; warnings: string[]; generated_at: string;
}
export interface Driver {
  title: string; explanation: string; category: Category; direction: "up" | "down";
  likelihood: number; evidence_ids: string[];
}
export interface Analysis {
  ticker: string; summary: string; drivers: Driver[]; unexplained: number;
  confidence: "low" | "medium" | "high"; watch_next: string[]; engine: string;
  latency_ms: number; warnings: string[];
}
export interface Health { ok: boolean; data_mode: string; ai: string; finnhub: boolean }

export const CATEGORY_LABEL: Record<Category, string> = {
  company: "Company",
  peers_supply_chain: "Peers & supply chain",
  sector: "Sector",
  macro: "Economy",
  geopolitics: "Geopolitics",
  market_flow: "Whole market",
};

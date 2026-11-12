"""What each stock is connected to.

For each ticker we list the things whose news can move it: competitors,
suppliers and customers, the sector, and the macro and geopolitical themes it
is sensitive to. The news layer turns these into search queries.

Tickers that are not listed still work: they get a generic profile.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    ticker: str
    name: str
    sector: str
    sector_etf: str | None = None
    peers: list[str] = field(default_factory=list)
    supply_chain: list[str] = field(default_factory=list)
    sector_terms: list[str] = field(default_factory=list)
    macro_terms: list[str] = field(default_factory=list)
    geo_terms: list[str] = field(default_factory=list)


_DEFAULT_MACRO = ["Federal Reserve", "inflation", "Treasury yields", "jobs report"]

PROFILES: dict[str, Profile] = {
    p.ticker: p
    for p in [
        Profile("AAPL", "Apple", "Consumer Technology", "XLK",
                peers=["Samsung", "Microsoft", "Alphabet"],
                supply_chain=["TSMC", "Foxconn", "Qualcomm"],
                sector_terms=["smartphone sales", "iPhone demand", "App Store"],
                macro_terms=_DEFAULT_MACRO + ["consumer spending"],
                geo_terms=["China tariffs", "China smartphone market", "EU Digital Markets Act"]),
        Profile("MSFT", "Microsoft", "Software & Cloud", "XLK",
                peers=["Alphabet", "Amazon", "Oracle"],
                supply_chain=["Nvidia", "OpenAI"],
                sector_terms=["cloud computing", "AI spending", "enterprise software"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["EU antitrust", "AI regulation"]),
        Profile("NVDA", "Nvidia", "Semiconductors", "SMH",
                peers=["AMD", "Broadcom", "Intel"],
                supply_chain=["TSMC", "SK Hynix", "Micron"],
                sector_terms=["AI chips", "data center spending", "semiconductor stocks"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["chip export controls", "China chips", "Taiwan chipmakers"]),
        Profile("AMD", "AMD", "Semiconductors", "SMH",
                peers=["Nvidia", "Intel", "Broadcom"],
                supply_chain=["TSMC"],
                sector_terms=["AI chips", "PC market", "semiconductor stocks"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["chip export controls", "Taiwan chipmakers"]),
        Profile("INTC", "Intel", "Semiconductors", "SMH",
                peers=["AMD", "Nvidia", "TSMC"],
                supply_chain=["ASML"],
                sector_terms=["chip foundry", "PC market", "semiconductor stocks"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["CHIPS Act", "chip export controls"]),
        Profile("AVGO", "Broadcom", "Semiconductors", "SMH",
                peers=["Nvidia", "Marvell", "AMD"],
                supply_chain=["TSMC"],
                sector_terms=["AI networking", "custom AI chips", "semiconductor stocks"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["chip export controls", "China chips"]),
        Profile("TSLA", "Tesla", "Autos & EVs", "XLY",
                peers=["BYD", "Rivian", "General Motors"],
                supply_chain=["Panasonic", "CATL", "lithium prices"],
                sector_terms=["electric vehicle sales", "EV demand", "robotaxi"],
                macro_terms=_DEFAULT_MACRO + ["auto loans"],
                geo_terms=["EV tariffs", "China EV market", "EV tax credit"]),
        Profile("AMZN", "Amazon", "E-commerce & Cloud", "XLY",
                peers=["Walmart", "Microsoft", "Alphabet"],
                supply_chain=["UPS", "FedEx"],
                sector_terms=["e-commerce", "cloud computing", "AWS"],
                macro_terms=_DEFAULT_MACRO + ["consumer spending", "retail sales"],
                geo_terms=["China tariffs", "FTC antitrust"]),
        Profile("GOOGL", "Alphabet", "Internet & Advertising", "XLC",
                peers=["Meta", "Microsoft", "Amazon"],
                supply_chain=["Nvidia", "Broadcom"],
                sector_terms=["digital advertising", "search engine", "AI search"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["Google antitrust", "EU fine", "AI regulation"]),
        Profile("META", "Meta Platforms", "Internet & Advertising", "XLC",
                peers=["Alphabet", "Snap", "TikTok"],
                supply_chain=["Nvidia"],
                sector_terms=["digital advertising", "social media", "AI spending"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["EU Digital Markets Act", "FTC antitrust", "TikTok ban"]),
        Profile("NFLX", "Netflix", "Media & Streaming", "XLC",
                peers=["Disney", "Warner Bros Discovery", "YouTube"],
                sector_terms=["streaming subscribers", "streaming prices"],
                macro_terms=_DEFAULT_MACRO + ["consumer spending"],
                geo_terms=["streaming regulation"]),
        Profile("DIS", "Disney", "Media & Entertainment", "XLC",
                peers=["Netflix", "Comcast", "Warner Bros Discovery"],
                sector_terms=["box office", "theme parks", "streaming subscribers"],
                macro_terms=_DEFAULT_MACRO + ["consumer spending"],
                geo_terms=["China box office"]),
        Profile("JPM", "JPMorgan Chase", "Banks", "XLF",
                peers=["Bank of America", "Citigroup", "Wells Fargo", "Goldman Sachs"],
                sector_terms=["bank earnings", "net interest income", "credit card delinquencies"],
                macro_terms=_DEFAULT_MACRO + ["yield curve", "bank regulation"],
                geo_terms=["Basel III endgame", "sanctions"]),
        Profile("GS", "Goldman Sachs", "Banks & Capital Markets", "XLF",
                peers=["Morgan Stanley", "JPMorgan Chase"],
                sector_terms=["investment banking fees", "IPO market", "trading revenue"],
                macro_terms=_DEFAULT_MACRO + ["yield curve"],
                geo_terms=["bank regulation", "sanctions"]),
        Profile("XOM", "Exxon Mobil", "Energy", "XLE",
                peers=["Chevron", "Shell", "BP"],
                supply_chain=["OPEC"],
                sector_terms=["oil prices", "Brent crude", "natural gas prices"],
                macro_terms=_DEFAULT_MACRO + ["oil demand"],
                geo_terms=["OPEC+ output", "Middle East", "Russia oil sanctions"]),
        Profile("CVX", "Chevron", "Energy", "XLE",
                peers=["Exxon Mobil", "ConocoPhillips", "Shell"],
                supply_chain=["OPEC"],
                sector_terms=["oil prices", "Brent crude", "refining margins"],
                macro_terms=_DEFAULT_MACRO + ["oil demand"],
                geo_terms=["OPEC+ output", "Middle East", "Venezuela oil"]),
        Profile("BA", "Boeing", "Aerospace & Defense", "XLI",
                peers=["Airbus", "Lockheed Martin"],
                supply_chain=["Spirit AeroSystems", "GE Aerospace"],
                sector_terms=["aircraft orders", "aircraft deliveries", "FAA"],
                macro_terms=_DEFAULT_MACRO + ["air travel demand"],
                geo_terms=["China aircraft orders", "defense spending", "tariffs"]),
        Profile("LMT", "Lockheed Martin", "Aerospace & Defense", "XLI",
                peers=["RTX", "Northrop Grumman", "General Dynamics"],
                sector_terms=["defense contracts", "F-35", "Pentagon budget"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["defense spending", "NATO", "Ukraine", "Middle East"]),
        Profile("LLY", "Eli Lilly", "Pharmaceuticals", "XLV",
                peers=["Novo Nordisk", "Pfizer", "Merck"],
                sector_terms=["GLP-1", "obesity drugs", "FDA approval"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["drug pricing", "pharma tariffs", "Medicare negotiation"]),
        Profile("PFE", "Pfizer", "Pharmaceuticals", "XLV",
                peers=["Merck", "Johnson & Johnson", "Eli Lilly"],
                sector_terms=["FDA approval", "clinical trial", "vaccines"],
                macro_terms=_DEFAULT_MACRO,
                geo_terms=["drug pricing", "pharma tariffs", "Medicare negotiation"]),
        Profile("WMT", "Walmart", "Retail", "XLP",
                peers=["Costco", "Target", "Amazon"],
                sector_terms=["retail sales", "same-store sales", "grocery prices"],
                macro_terms=_DEFAULT_MACRO + ["consumer spending", "consumer confidence"],
                geo_terms=["tariffs", "China imports"]),
        Profile("KO", "Coca-Cola", "Consumer Staples", "XLP",
                peers=["PepsiCo", "Keurig Dr Pepper"],
                supply_chain=["sugar prices", "aluminum prices"],
                sector_terms=["beverage sales", "consumer staples"],
                macro_terms=_DEFAULT_MACRO + ["US dollar"],
                geo_terms=["aluminum tariffs", "emerging markets"]),
    ]
}

# Short names shown in the watchlist, in this order.
WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "JPM", "XOM", "LLY", "BA", "WMT"]


def get_profile(ticker: str) -> Profile:
    ticker = ticker.upper()
    if ticker in PROFILES:
        return PROFILES[ticker]
    return Profile(ticker, ticker, "Unknown sector", None, macro_terms=_DEFAULT_MACRO)

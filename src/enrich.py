"""Analyst-intelligence generator — memos, bull/bear, red flags, SWOT, timelines.

Runs at SITE BUILD TIME (no runtime AI, keeps the deployed site static/secure).
Every output is grounded in the company's structured fields plus a curated
EXTRA intel layer for flagship companies; where data is missing the output
says so explicitly ("flag for diligence") instead of inventing facts. When a
live PitchBook/Crunchbase feed is wired in, these generators consume the
richer fields with no schema change.

Kept Python 3.9-compatible.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

TIER1 = {"sequoia", "a16z", "andreessen horowitz", "founders fund", "thrive capital",
         "lightspeed", "general catalyst", "index", "accel", "khosla", "kleiner perkins",
         "coatue", "tiger global", "temasek", "softbank", "greenoaks", "benchmark",
         "insight", "capitalg", "gv", "google", "microsoft", "nvidia", "y combinator"}

DISTRESS_RE = re.compile(r"chapter 11|bankrupt|restructur|marked down|wound down|"
                         r"shut down|ceased|cautionary|distress", re.I)
HW_RE = re.compile(r"rocket|drone|robot|vessel|charger|charging|hardware|satellite|"
                   r"device|vehicle|farm|reactor|machine|microwave|lander|aircraft", re.I)
REG_SECTORS = {"defense-tech": "defense export controls and procurement cycles",
               "ai-healthcare-diagnostics": "FDA clearance and reimbursement pathways",
               "payments-infrastructure": "money-transmission licensing and PSD2/card-network rules",
               "neobanks": "banking licenses and consumer-finance regulation",
               "alternative-proteins": "novel-food regulatory approval",
               "carbon-capture": "carbon-credit policy and verification standards",
               "foundation-models": "AI-safety regulation (EU AI Act et al.)",
               "space-launch": "launch licensing (FAA/ITAR)",
               "ev-charging-infrastructure": "public-infrastructure subsidy dependence",
               "crypto-and-digital-assets": "securities regulation"}

ACQUIRERS = {
    "foundation-models": ["Microsoft", "Google", "Amazon", "Meta"],
    "ai-coding-assistants": ["Microsoft/GitHub", "Google", "Atlassian", "JetBrains"],
    "cloud-security": ["Google", "Palo Alto Networks", "Cisco", "CrowdStrike"],
    "payments-infrastructure": ["Visa", "Mastercard", "FIS", "Adyen"],
    "neobanks": ["JPMorgan", "large incumbent banks", "PayPal"],
    "vertical-farming": ["Cox Enterprises", "large grocers", "AgCo strategics"],
    "ai-healthcare-diagnostics": ["Roche", "Philips", "GE HealthCare", "Siemens Healthineers"],
    "carbon-capture": ["Occidental", "Chevron", "Shell"],
    "ev-charging-infrastructure": ["utilities", "oil majors (Shell/BP)", "OEMs"],
    "space-launch": ["defense primes (L3Harris/Northrop)", "Boeing/Lockheed"],
    "last-mile-delivery": ["Uber", "DoorDash", "Amazon", "FedEx/UPS"],
    "defense-tech": ["defense primes (RTX/Lockheed/L3Harris)", "General Dynamics"],
    "alternative-proteins": ["Nestlé", "Unilever", "Tyson", "JBS"],
}

# ---------------------------------------------------------------------------
# Curated intel layer for flagship companies (metrics are reported estimates
# from public press — illustrative; verify before citing).
# ---------------------------------------------------------------------------
EXTRA: Dict[str, dict] = {
"openai": {
  "arr": "~$10B+ ARR (reported mid-2025)", "growth": "revenue ~3x y/y (reported)", "margin": "negative (compute-heavy)",
  "hiring": {"eng": "+40% y/y (reported)", "sales": "scaling enterprise GTM", "exec": "repeated senior churn (CTO, CRO departures 2024-25)", "regions": ["US", "UK", "SG", "JP"], "roles": ["infra engineers", "enterprise AEs"], "layoffs": ""},
  "founder_notes": {"Sam Altman": "Ex-YC president; ousted and reinstated as CEO in Nov 2023; prolific angel.", "Greg Brockman": "Ex-Stripe CTO.", "Ilya Sutskever": "Departed 2024 to found Safe Superintelligence."},
  "timeline": [[2015, "Founded as nonprofit lab", "founded"], [2019, "Capped-profit restructuring; $1B Microsoft deal", "round"], [2022, "ChatGPT launch — fastest consumer product to 100M users", "launch"], [2023, "Board crisis: CEO fired and reinstated in 5 days", "leadership"], [2024, "Senior exodus: Sutskever, Murati, others depart", "leadership"], [2025, "~$40B round (SoftBank-led); for-profit conversion advanced", "round"]],
  "changes": [["funding", "Raised ~$40B at ~$300B (SoftBank-led) — largest private round ever"], ["exec", "Continued senior leadership turnover"], ["product", "Agentic product push (Operator et al.)"], ["regulatory", "For-profit restructuring under AG scrutiny"]],
  "flags": ["Governance history: 2023 board crisis and unresolved nonprofit-to-profit conversion", "Sustained senior-executive turnover", "Extreme capital intensity — dependent on continual mega-raises"]},
"anthropic": {
  "arr": "~$4B+ run-rate (reported 2025)", "growth": "revenue growing multiples y/y (reported)", "margin": "negative (compute-heavy)",
  "hiring": {"eng": "aggressive research + infra hiring", "sales": "enterprise GTM scaling", "exec": "stable founding team", "regions": ["US", "UK", "IE"], "roles": ["research engineers", "safety researchers"], "layoffs": ""},
  "founder_notes": {"Dario Amodei": "Ex-OpenAI VP of Research; public voice on AI safety.", "Daniela Amodei": "Ex-OpenAI VP; President."},
  "timeline": [[2021, "Founded by seven ex-OpenAI researchers", "founded"], [2023, "$4B Amazon + $2B Google commitments", "round"], [2024, "Claude 3 family ships", "launch"], [2025, "Series E ~$3.5B at ~$61.5B", "round"]],
  "changes": [["funding", "Series E ~$3.5B (Lightspeed-led)"], ["product", "Claude agentic/coding leadership extended"], ["hiring", "Headcount roughly doubled y/y"]],
  "flags": ["Compute dependence on two strategic investors (AWS, Google) who are also competitors"]},
"cursor": {
  "arr": "~$500M+ ARR (reported 2025)", "growth": "fastest SaaS ramp on record (reported)", "margin": "pressured by inference costs",
  "hiring": {"eng": "rapid (+3x team y/y)", "sales": "enterprise motion forming", "exec": "founder-led, young team", "regions": ["US"], "roles": ["systems engineers", "enterprise sales"], "layoffs": ""},
  "founder_notes": {"Michael Truell": "MIT dropout; CEO in mid-20s."},
  "timeline": [[2022, "Founded (Anysphere)", "founded"], [2023, "Cursor editor launch", "launch"], [2025, "Series B ~$105M (Thrive); later rounds reported at $9B+", "round"]],
  "changes": [["funding", "Valuation re-rated multiple times within 12 months"], ["product", "Agent mode shipped"], ["competitive", "OpenAI/Windsurf acquisition drama intensified talent war"]],
  "flags": ["Platform dependence: builds on VS Code + frontier-model APIs it doesn't control", "Valuation re-rated faster than revenue history supports"]},
"wiz": {
  "arr": "~$700M ARR (reported at acquisition)", "growth": "~70% y/y (reported)", "margin": "SaaS-typical gross margins",
  "hiring": {"eng": "hiring through acquisition close", "sales": "large enterprise org", "exec": "founding team intact", "regions": ["US", "IL"], "roles": [], "layoffs": ""},
  "founder_notes": {"Assaf Rappaport": "Second exit — sold Adallom to Microsoft ($320M), then Wiz to Google ($32B)."},
  "timeline": [[2020, "Founded by Adallom team", "founded"], [2021, "Fastest to $100M ARR in software history", "launch"], [2024, "Rejected $23B Google offer", "leadership"], [2025, "$32B Google acquisition agreed", "acquisition"]],
  "changes": [["acquisition", "Google acquisition (~$32B) in regulatory review"], ["hiring", "Retention packages through close"]],
  "flags": ["Deal-close risk: antitrust review of the Google acquisition"]},
"stripe": {
  "arr": "~$1.4T payment volume; revenue undisclosed (reported 2024)", "growth": "volume +38% y/y (reported)", "margin": "take-rate model; profitable (reported)",
  "hiring": {"eng": "resumed growth after 2022 cuts", "sales": "enterprise expansion", "exec": "stable founder control", "regions": ["US", "IE", "SG"], "roles": ["AI/agentic-commerce roles"], "layoffs": "14% cut in 2022 (recovered)"},
  "founder_notes": {"Patrick Collison": "Serial founder (Auctomatic exit at 19); intellectual public presence.", "John Collison": "Co-founder; president."},
  "timeline": [[2010, "Founded", "founded"], [2021, "$95B valuation peak", "round"], [2022, "14% layoff; valuation cut to $50B", "leadership"], [2023, "$6.5B employee-liquidity round", "round"], [2024, "Valuation recovered to ~$70B via tenders", "round"]],
  "changes": [["funding", "Tender offers marching valuation back toward peak"], ["product", "Stablecoin/agentic-commerce infrastructure (Bridge acquisition)"], ["hiring", "Net headcount growing again"]],
  "flags": ["IPO repeatedly deferred — late employee liquidity pressure"]},
"revolut": {
  "arr": "~$4B revenue, ~$1.4B pre-tax profit (reported FY2024)", "growth": "revenue +72% y/y (reported)", "margin": "profitable",
  "hiring": {"eng": "+30% y/y", "sales": "global expansion teams", "exec": "long CFO/compliance churn history", "regions": ["UK", "EU", "US", "IN", "BR"], "roles": ["compliance officers", "country GMs"], "layoffs": ""},
  "founder_notes": {"Nik Storonsky": "Ex-Lehman/Credit Suisse trader; famously hard-driving culture."},
  "timeline": [[2015, "Founded", "founded"], [2021, "$33B Series E (SoftBank/Tiger)", "round"], [2024, "UK banking licence granted after 3-year wait; $45B secondary", "leadership"], [2025, "Reported ~$75B secondary discussions", "round"]],
  "changes": [["regulatory", "UK licence mobilization phase"], ["funding", "Secondary valuation step-ups"], ["product", "Mortgages + AI assistant launches"]],
  "flags": ["Multi-year audit/licence friction history", "Culture/attrition reputation risk"]},
"anduril": {
  "arr": "~$1B revenue (reported 2024)", "growth": "revenue ~2x y/y (reported)", "margin": "hardware margins below software peers",
  "hiring": {"eng": "+50% y/y", "sales": "gov BD growing", "exec": "stable", "regions": ["US", "AU", "UK"], "roles": ["manufacturing engineers (Arsenal-1)"], "layoffs": ""},
  "founder_notes": {"Palmer Luckey": "Founded Oculus (sold to Facebook, $2B) at 21; politically outspoken.", "Trae Stephens": "Founders Fund partner."},
  "timeline": [[2017, "Founded", "founded"], [2022, "IVAS/CCA program wins begin", "launch"], [2024, "Microsoft IVAS takeover; Arsenal-1 factory announced", "launch"], [2025, "Series G ~$2.5B at $30.5B", "round"]],
  "changes": [["funding", "Series G ~$2.5B (Founders Fund-led)"], ["product", "Arsenal-1 mass-production build-out"], ["contracts", "Major program-of-record wins (IVAS, CCA)"]],
  "flags": ["Program-of-record concentration: a few DoD decisions swing outcomes", "Founder's political profile is polarizing for some LPs/customers"]},
"spacex": {
  "arr": "~$13B+ revenue (reported 2024, majority Starlink)", "growth": "Starlink revenue +60%+ y/y (reported)", "margin": "launch margins strong; Starship heavy capex",
  "hiring": {"eng": "continuous", "sales": "Starlink enterprise/gov", "exec": "key-person structure around CEO", "regions": ["US"], "roles": ["Starship production"], "layoffs": ""},
  "founder_notes": {"Elon Musk": "Serial founder (PayPal, Tesla); key-person risk and political exposure in one."},
  "timeline": [[2002, "Founded", "founded"], [2015, "First orbital booster landing", "launch"], [2020, "First crewed NASA flight", "launch"], [2024, "$350B secondary valuation", "round"], [2025, "Starship iterative test campaign continues", "launch"]],
  "changes": [["funding", "Secondary at ~$350B"], ["product", "Starship cadence increasing"], ["regulatory", "Launch-licence cadence normalized"]],
  "flags": ["Extreme key-person risk (CEO)", "Political entanglement affects government relationships both ways"]},
"helsing": {
  "arr": "revenue undisclosed; large EU ministry contracts (reported)", "growth": "contract base expanding with EU rearmament", "margin": "software-led",
  "hiring": {"eng": "+60% y/y", "sales": "ministry BD across EU", "exec": "stable trio", "regions": ["DE", "UK", "FR", "EE"], "roles": ["autonomy engineers"], "layoffs": ""},
  "founder_notes": {"Torsten Reil": "Ex-gaming founder (NaturalMotion, $527M exit to Zynga).", "Gundbert Scherf": "Ex-McKinsey/German MoD."},
  "timeline": [[2021, "Founded", "founded"], [2023, "Ukraine deployments", "launch"], [2024, "HX-2 strike drone unveiled", "launch"], [2025, "Series D ~€600M at €12B (Prima Materia-led)", "round"]],
  "changes": [["funding", "Series D €600M"], ["product", "Naval + air autonomy expansion"], ["contracts", "Multiple EU ministry wins"]],
  "flags": ["Valuation prices in sustained EU defense-budget expansion"]},
"plenty": {
  "arr": "revenue never disclosed", "growth": "n/a — restructuring", "margin": "unit economics failed at scale",
  "hiring": {"eng": "frozen", "sales": "frozen", "exec": "leadership departures through 2024-25", "regions": ["US"], "roles": [], "layoffs": "successive rounds pre-filing"},
  "founder_notes": {"Matt Barnard": "Departed CEO role prior to restructuring."},
  "timeline": [[2014, "Founded", "founded"], [2017, "$200M SoftBank round — sector high-water mark", "round"], [2022, "$400M round; Walmart partnership", "round"], [2025, "Chapter 11 filing", "leadership"]],
  "changes": [["distress", "Chapter 11 filing; asset restructuring"], ["exec", "Leadership departures"], ["hiring", "Workforce reductions"]],
  "flags": ["Chapter 11 (2025) — most-funded player in a failed capex model", "Energy costs structurally broke the tower-farm unit economics", "Executive exodus preceded filing"]},
"tempus-ai": {
  "arr": "~$700M revenue (reported FY2024)", "growth": "+30% y/y (reported)", "margin": "gross margin ~60% and improving",
  "hiring": {"eng": "steady", "sales": "provider + pharma teams", "exec": "founder-CEO", "regions": ["US"], "roles": ["clinical data scientists"], "layoffs": ""},
  "founder_notes": {"Eric Lefkofsky": "Serial founder (Groupon); funded Tempus after wife's cancer diagnosis."},
  "timeline": [[2015, "Founded", "founded"], [2024, "Nasdaq IPO", "round"], [2025, "Ambry Genetics acquisition closed ($600M)", "acquisition"]],
  "changes": [["ma", "Acquired Ambry Genetics ($600M)"], ["financial", "Raised FY guidance"], ["product", "Foundation-model partnership for oncology data"]],
  "flags": ["Short-seller scrutiny of related-party revenue (2024)", "Persistent GAAP losses despite scale"]},
"mistral-ai": {
  "arr": "~$100M+ ARR early 2025 (reported)", "growth": "enterprise pipeline growing with EU sovereignty push", "margin": "negative (compute)",
  "hiring": {"eng": "+80% y/y from small base", "sales": "EU enterprise GTM", "exec": "stable trio", "regions": ["FR", "UK", "US"], "roles": ["inference engineers"], "layoffs": ""},
  "founder_notes": {"Arthur Mensch": "Ex-DeepMind (Chinchilla paper).", "Guillaume Lample": "Ex-Meta (LLaMA lead author)."},
  "timeline": [[2023, "Founded; record €105M seed at 4 weeks old", "founded"], [2024, "Microsoft partnership; Series B €600M", "round"], [2025, "Reported ~€2B raise talks at ~$14B", "round"]],
  "changes": [["funding", "New mega-round reported (ASML anchor)"], ["product", "Le Chat consumer push"], ["contracts", "French state + EU enterprise wins"]],
  "flags": ["Caught between US frontier labs and open-source commoditization"]},
"zipline": {
  "arr": "revenue undisclosed; 100M+ autonomous miles", "growth": "US retail expansion (Walmart) scaling", "margin": "per-delivery economics improving with density",
  "hiring": {"eng": "steady", "sales": "health-system + retail BD", "exec": "stable", "regions": ["US", "RW", "GH", "NG", "JP"], "roles": ["flight-ops engineers"], "layoffs": ""},
  "founder_notes": {"Keller Rinaudo Cliffton": "Robotics background; built the world's largest drone-delivery network."},
  "timeline": [[2014, "Founded", "founded"], [2016, "Rwanda national blood network", "launch"], [2023, "Series F $330M at $4.2B; Platform 2 unveiled", "round"], [2025, "US suburban expansion with Walmart", "launch"]],
  "changes": [["product", "Platform 2 (P2) rollout in US metros"], ["contracts", "Walmart expansion"], ["regulatory", "FAA BVLOS approvals broadened"]],
  "flags": ["Regulatory ceiling: BVLOS rules gate US scale"]},
"climeworks": {
  "arr": "credit sales growing but small vs. costs", "growth": "capacity scaling (Mammoth 10x Orca)", "margin": "cost/ton still far above credit prices",
  "hiring": {"eng": "slowed 2025 (10% workforce cut reported)", "sales": "corporate offtake team", "exec": "co-CEO founders", "regions": ["CH", "IS", "US"], "roles": [], "layoffs": "~10% (2025, reported)"},
  "founder_notes": {"Christoph Gebald": "ETH Zurich; co-CEO.", "Jan Wurzbacher": "ETH Zurich; co-CEO."},
  "timeline": [[2009, "Founded", "founded"], [2021, "Orca plant (first commercial DAC)", "launch"], [2022, "$650M equity round", "round"], [2024, "Mammoth plant online", "launch"], [2025, "Workforce reduction; US DAC-hub funding uncertainty", "leadership"]],
  "changes": [["hiring", "~10% workforce reduction"], ["regulatory", "US DOE DAC-hub funding under review"], ["financial", "Cost-per-ton reduction roadmap published"]],
  "flags": ["Layoffs (2025) amid policy uncertainty", "Economics depend on voluntary credit prices + subsidies", "US expansion tied to DOE hub funding"]},
"upside-foods": {
  "arr": "pre-revenue at scale (regulatory-gated)", "growth": "n/a — awaiting scaled production", "margin": "n/a",
  "hiring": {"eng": "slowed; 2024 restructuring", "sales": "", "exec": "stable founder-CEO", "regions": ["US"], "roles": [], "layoffs": "restructuring + plant pause (2024, reported)"},
  "founder_notes": {"Uma Valeti": "Cardiologist-turned-founder; face of the cultivated-meat category."},
  "timeline": [[2015, "Founded (as Memphis Meats)", "founded"], [2022, "FDA green-light (first ever); $400M Series C", "round"], [2023, "USDA approval; first US sales", "launch"], [2024, "Scaled-plant pause + restructuring", "leadership"]],
  "changes": [["distress", "Large-scale plant paused; restructuring"], ["regulatory", "State-level cultivated-meat bans (FL, AL)"], ["hiring", "Headcount reduced"]],
  "flags": ["Scale-up paused — cost curve unproven", "US state-level product bans emerging", "Category funding winter"]},
"firefly-aerospace": {
  "arr": "~$60M revenue (reported 2024) + $1.1B backlog", "growth": "backlog-driven", "margin": "negative during ramp",
  "hiring": {"eng": "+25% y/y", "sales": "gov BD", "exec": "CEO change 2025 (post-IPO)", "regions": ["US"], "roles": ["propulsion engineers"], "layoffs": ""},
  "founder_notes": {"Tom Markusic": "Ex-SpaceX/Virgin/Blue Origin propulsion; founder (no longer CEO)."},
  "timeline": [[2017, "Refounded from bankruptcy of Firefly Space Systems", "founded"], [2023, "Alpha reaches orbit", "launch"], [2025, "Blue Ghost lands on the Moon (first fully-successful commercial landing); Nasdaq IPO", "round"]],
  "changes": [["ipo", "Nasdaq IPO (2025-08)"], ["product", "Blue Ghost Mission 2 in prep"], ["exec", "Post-IPO CEO transition"]],
  "flags": ["Alpha rocket reliability record is mixed (multiple anomalies)", "Post-IPO leadership change"]},
"xai": {
  "arr": "modest API/subscription revenue vs. capex (reported)", "growth": "usage growing via X integration", "margin": "deeply negative (Colossus buildout)",
  "hiring": {"eng": "aggressive infra hiring (Memphis)", "sales": "minimal enterprise motion", "exec": "merged with X (2025) — org churn", "regions": ["US"], "roles": ["datacenter engineers"], "layoffs": ""},
  "founder_notes": {"Elon Musk": "Key-person concentration across xAI/Tesla/SpaceX/X."},
  "timeline": [[2023, "Founded; Grok-1 in months", "founded"], [2024, "Colossus (100k+ GPU) cluster built in ~4 months", "launch"], [2025, "xAI-X merger at ~$80B combined (reported)", "acquisition"]],
  "changes": [["ma", "Merged with X Corp (reported)"], ["funding", "Successive multi-billion raises"], ["product", "Grok integrated across X"]],
  "flags": ["Key-person risk", "Environmental/permitting scrutiny (Memphis turbines)", "Revenue tiny relative to capex commitment"]},
"chime": {
  "arr": "~$1.7B revenue (reported FY2024)", "growth": "+30% y/y (reported)", "margin": "interchange-dependent",
  "hiring": {"eng": "post-IPO normalization", "sales": "n/a (consumer)", "exec": "stable co-founders", "regions": ["US"], "roles": [], "layoffs": "12% cut in 2022 (pre-IPO)"},
  "founder_notes": {"Chris Britt": "Ex-Green Dot/Visa; consumer-fintech operator."},
  "timeline": [[2012, "Founded", "founded"], [2021, "$25B peak private valuation", "round"], [2025, "Nasdaq IPO (~$11B) — below peak", "round"]],
  "changes": [["ipo", "Public since 2025-06; trading below private peak"], ["product", "Credit-builder + earned-wage expansion"]],
  "flags": ["Interchange (Durbin-exempt) revenue concentration", "IPO priced ~55% below 2021 private mark"]},
}


def _low(s):  # noqa: ANN001
    return (s or "").lower()


def _tier1_hits(inv: List[str]) -> List[str]:
    return [i for i in inv if any(t in _low(i) for t in TIER1)]


def _tags(c: dict, sector_slug: str) -> List[str]:
    tags = []
    tgt = _low(c.get("target")) + " " + _low(c.get("bm"))
    if any(k in tgt for k in ("enterprise", "business", "b2b", "teams", "developer", "merchant", "fleet", "hospital", "government", "ministr", "dod", "navy", "army")):
        tags.append("B2B")
    if any(k in tgt for k in ("consumer", "b2c", "everyday", "retail shopper", "drivers", "learners", "individual")):
        tags.append("B2C")
    if "ai" in sector_slug or "ai" in _low(c.get("desc")) or "autonom" in _low(c.get("desc")):
        tags.append("AI")
    if HW_RE.search(_low(c.get("desc")) + " " + _low(c.get("diff"))):
        tags.append("Hardware")
    if any(k in _low(c.get("bm")) for k in ("saas", "subscription", "per-seat", "recurring", "per-site", "platform subscriptions")):
        tags.append("Recurring")
    if not tags:
        tags.append("B2B")
    return tags


def _country(hq: str) -> str:
    m = re.search(r",\s*([A-Z]{2})\b", hq or "")
    return m.group(1) if m else ("US" if "US" in (hq or "") else "—")


def _round_year(rnd: str) -> Optional[int]:
    m = re.search(r"(20\d\d)", rnd or "")
    return int(m.group(1)) if m else None


def build_intel(c: dict, sector_slug: str, sector_name: str, degree: int,
                rivals: List[dict], summary: str) -> dict:
    """Derive the full analyst-intel blob for one company payload dict."""
    x = EXTRA.get(c["id"], {})
    name = c["name"]
    stage = c.get("stage", "unknown")
    inv = [i.strip() for i in (c.get("inv") or "").split(";") if i.strip()]
    t1 = _tier1_hits(inv)
    tags = _tags(c, sector_slug)
    fM = c.get("fM")
    ry = _round_year(c.get("round"))
    text_blob = " ".join(_low(c.get(k)) for k in ("desc", "diff", "round", "funding", "hc"))
    distress = bool(DISTRESS_RE.search(text_blob)) or stage == "unknown"
    public = stage == "public"
    hw = "Hardware" in tags
    reg = REG_SECTORS.get(sector_slug)
    rival_names = [r["name"] for r in rivals]
    public_rivals = [r["name"] for r in rivals if r.get("stage") == "public"]

    # ----- metrics -----
    metrics = {
        "arr": x.get("arr") or "not disclosed — flag for diligence",
        "growth": x.get("growth") or ("n/a (public reporting applies)" if public else "not disclosed — flag for diligence"),
        "margin": x.get("margin") or ("hardware-weighted cost structure (est.)" if hw else "software-typical gross margins (est.)"),
    }

    # ----- red flags -----
    flags = list(x.get("flags", []))
    if distress and not any("Chapter 11" in f or "restructur" in f.lower() for f in flags):
        flags.append("Distress signals in record (restructuring/markdown language) — verify status")
    if any("(departed)" in f for f in c.get("fnd", "").split(";")):
        flags.append("Founder departure on record")
    if ry and ry <= 2022 and stage not in ("public", "acquired", "bootstrapped"):
        flags.append("No new round since %d — runway and mark-to-market risk" % ry)
    if public_rivals:
        flags.append("Competes directly with public-scale incumbents (%s)" % ", ".join(public_rivals[:2]))
    if x.get("hiring", {}).get("layoffs"):
        flags.append("Layoffs on record: %s" % x["hiring"]["layoffs"])
    if reg:
        flags.append("Regulatory exposure: %s" % reg)
    if not fM and stage not in ("public", "acquired", "bootstrapped"):
        flags.append("Undisclosed capitalization — cap-table opacity")
    flags = flags[:7]

    # ----- bull / bear -----
    bull = []
    if summary:
        bull.append("Category tailwind: %s is an actively funded sector with expanding budgets." % sector_name)
    if t1:
        bull.append("Cap-table signal: backed by %s — repeat-winner investors with follow-on capacity." % ", ".join(t1[:3]))
    if c.get("diff"):
        bull.append("Differentiation: %s" % c["diff"].rstrip("."))
    if x.get("growth") and "y/y" in x.get("growth", ""):
        bull.append("Momentum: %s." % x["growth"].rstrip("."))
    if "Recurring" in tags:
        bull.append("Revenue quality: recurring/subscription model supports multiple expansion.")
    if stage in ("growth", "series C") and fM:
        bull.append("Scale: ~$%s disclosed capital de-risks execution to the next milestone." % (("%.1fB" % (fM/1000)) if fM >= 1000 else ("%dM" % fM)))
    bull = bull[:5] or ["Insufficient verified data for a bull case — run live research."]

    bear = []
    if degree >= 4:
        bear.append("Crowded field: %d direct rivals tracked in this map alone." % degree)
    if public_rivals:
        bear.append("Incumbent pressure from %s with distribution advantages." % ", ".join(public_rivals[:2]))
    if hw:
        bear.append("Capital intensity: hardware economics — margin and cycle-time drag vs. software peers.")
    if metrics["arr"].startswith("not disclosed"):
        bear.append("No verified revenue disclosure — underwriting rests on proxies.")
    if fM and fM >= 1000 and stage != "public":
        bear.append("Priced for perfection: mega-round valuation compresses forward returns.")
    if reg:
        bear.append("Regulatory drag: %s." % reg)
    if distress:
        bear.append("Active distress/restructuring record.")
    bear = bear[:5] or ["Primary bear case is execution risk typical of the stage."]

    # ----- SWOT -----
    swot = {
        "s": ([c["diff"].rstrip(".")] if c.get("diff") else []) +
             (["Tier-1 investor syndicate (%s)" % ", ".join(t1[:2])] if t1 else []) +
             ([x["arr"]] if x.get("arr") and not x["arr"].startswith("not") else []),
        "w": ([f for f in flags if "opacity" in f or "disclosed" in f.lower()] or
              ["Limited public disclosure at this stage"]) +
             (["Hardware cost structure"] if hw else []),
        "o": ["Expansion within %s as budgets consolidate to leaders" % sector_name] +
             (["Adjacent-segment expansion from current beachhead (%s)" % c.get("target", "").rstrip(".")] if c.get("target") else []),
        "t": (["Incumbents: %s" % ", ".join(public_rivals[:2])] if public_rivals else
              ["Well-funded private rivals: %s" % ", ".join(rival_names[:2])] if rival_names else []) +
             ([("Regulation: %s" % reg)] if reg else []) + ["Funding-cycle dependence for the category"],
    }
    for k in swot:
        swot[k] = [s for s in swot[k] if s][:4]

    # ----- memo sections -----
    exits = ACQUIRERS.get(sector_slug, ["sector strategics"])
    memo = {
        "thesis": bull[:3] + ([("Team: %s" % "; ".join(list(x.get("founder_notes", {}).values())[:1]))] if x.get("founder_notes") else []) +
                  ["Position: %d competitive links make %s a gravity center of this map." % (degree, name) if degree >= 3 else
                   "Position: focused wedge with room to expand share of the %s map." % sector_name],
        "risks": bear[:3] + flags[:2],
        "drivers": [d for d in [
            ("Hiring signal: %s" % x["hiring"]["eng"]) if x.get("hiring", {}).get("eng") else None,
            ("Go-to-market: %s" % c["bm"].rstrip(".")) if c.get("bm") else None,
            ("Customer pull: %s" % c["target"].rstrip(".")) if c.get("target") else None,
            "Category consolidation favors scaled leaders",
        ] if d][:4],
        "market": summary or ("%s — actively contested category; see sector map." % sector_name),
        "competition": ("Direct rivals: " + "; ".join("%s (%s)" % (r["name"], r.get("stage", "?")) for r in rivals[:4]) + ".") if rivals else "No direct rivals recorded in this map.",
        "moat": (c.get("diff") or "Not established from available data.") + (" Switching-cost and data-scale effects compound with deployment footprint." if "Recurring" in tags else ""),
        "exit": ("Strategic acquirers: %s. " % ", ".join(exits[:3])) + ("Already public — outcome is market performance." if public else ("IPO path plausible at current scale." if stage == "growth" else "IPO premature; M&A is the realistic mid-term path.")),
        "questions": [q for q in [
            "Verified ARR, growth and net retention?" if metrics["arr"].startswith("not") else "Durability of reported growth (cohort retention)?",
            "True gross margin after inference/hardware costs?" if (hw or "AI" in tags) else "Unit economics at current scale?",
            "Cap table and last-round terms (structure, prefs)?",
            "Pipeline concentration — top-5 customer share of revenue?",
            ("Regulatory posture: %s?" % reg) if reg else "Key-person dependencies and retention packages?",
        ] if q][:5],
    }

    # ----- hiring / founders / timeline / changes -----
    hiring = x.get("hiring") or {
        "eng": "no public signal — pull job-board data in live mode",
        "sales": "", "exec": "", "regions": [], "roles": [], "layoffs": "",
    }
    founders = [{"name": n.strip(), "notes": (x.get("founder_notes", {}) or {}).get(n.strip(), "")}
                for n in (c.get("fnd") or "").split(";") if n.strip()]
    timeline = [{"y": t[0], "label": t[1], "type": t[2]} for t in x.get("timeline", [])]
    if not timeline:
        if c.get("founded"):
            timeline.append({"y": c["founded"], "label": "Founded", "type": "founded"})
        if ry:
            timeline.append({"y": ry, "label": c.get("round", "Last round"), "type": "round"})
    changes = [{"type": ch[0], "text": ch[1]} for ch in x.get("changes", [])]

    return {
        "tags": tags, "country": _country(c.get("hq", "")), "metrics": metrics,
        "memo": memo, "bull": bull, "bear": bear, "flags": flags, "swot": swot,
        "hiring": hiring, "founders": founders, "timeline": timeline,
        "changes": changes, "curated": bool(x),
    }

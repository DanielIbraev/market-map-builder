"""Sector taxonomy — the atlas catalog of categories and subsectors.

Every subsector here is a valid input to `map "<subsector>"`. The site
builder cross-references this list against the vault to mark which sectors
have data. Curated, not exhaustive — extend freely; slugs are derived, so
adding a line here is all it takes.

Kept Python 3.9-compatible.
"""
from __future__ import annotations

from typing import Dict, List

TAXONOMY: "Dict[str, List[str]]" = {
    "Artificial Intelligence": [
        "AI coding assistants",
        "Foundation models",
        "AI agents and automation",
        "AI infrastructure and MLOps",
        "Computer vision",
        "AI voice and speech",
        "AI search and knowledge tools",
    ],
    "Healthcare and Biotech": [
        "AI healthcare diagnostics",
        "Digital health platforms",
        "Telemedicine",
        "Biotech drug discovery",
        "Medical devices",
        "Mental health tech",
        "Healthcare data interoperability",
    ],
    "Fintech": [
        "Payments infrastructure",
        "Neobanks",
        "Wealth management tech",
        "Lending platforms",
        "Insurtech",
        "Crypto and digital assets",
        "RegTech and compliance",
    ],
    "Agriculture and Food": [
        "Vertical farming",
        "Precision agriculture",
        "Alternative proteins",
        "Agricultural robotics",
        "Food supply chain tech",
        "Livestock technology",
    ],
    "Climate and Energy": [
        "Carbon capture",
        "Grid and battery storage",
        "Solar technology",
        "EV charging infrastructure",
        "Fusion energy startups",
        "Climate risk analytics",
    ],
    "Cybersecurity": [
        "Cloud security",
        "Identity and access management",
        "Endpoint security",
        "Application security",
        "Security operations and SIEM",
        "Data privacy tech",
    ],
    "Enterprise Software": [
        "Sales tech and CRM",
        "HR tech",
        "Legal tech",
        "Procurement and spend management",
        "Workflow automation",
        "Business intelligence tools",
    ],
    "Developer Tools and Infrastructure": [
        "Cloud infrastructure",
        "Observability and monitoring",
        "CI/CD and DevOps tools",
        "API platforms",
        "Databases and data infrastructure",
        "Edge computing",
    ],
    "Consumer and Commerce": [
        "E-commerce enablement",
        "Creator economy platforms",
        "Social commerce",
        "Online marketplaces",
        "Subscription commerce",
        "Retail tech",
    ],
    "Logistics and Mobility": [
        "Autonomous vehicles",
        "Last-mile delivery",
        "Freight tech",
        "Fleet management",
        "Drone logistics",
        "Micromobility",
    ],
    "Real Estate and Construction": [
        "PropTech platforms",
        "Construction tech",
        "Smart buildings",
        "Real estate fintech",
        "Facilities management tech",
    ],
    "Aerospace and Defense": [
        "Space launch",
        "Satellite technology",
        "Defense tech",
        "Earth observation",
    ],
    "Education and Future of Work": [
        "EdTech platforms",
        "Corporate learning",
        "Skills assessment",
        "Remote work tools",
    ],
}


def all_subsectors() -> List[str]:
    out: List[str] = []
    for subs in TAXONOMY.values():
        out.extend(subs)
    return out

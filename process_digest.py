#!/usr/bin/env python3
"""
Bay Area News Digest — Story Processor
Reads stories_latest.json, applies theme tagging, national significance scoring,
enterprise journalism detection, and recency decay. Outputs digest_data.json.
"""

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# ─── Theme keywords ──────────────────────────────────────────────────────────

THEME_KEYWORDS = {
    "Tech & Economy": [
        r"\bA\.?I\.?\b", r"\bartificial intelligence\b", r"\bstartup",
        r"\blayoff", r"\bventure capital\b", r"\bVC\s", r"\bIPO\b",
        r"\btech worker", r"\bSilicon Valley\b", r"\bgig economy\b",
        r"\bautomation\b", r"\bhousing cost", r"\bcost of living\b",
        r"\bwage\b", r"\bjob market\b", r"\beconom", r"\binflation\b",
        r"\bGoogle\b", r"\bMeta\b", r"\bApple\b", r"\bOpenAI\b",
        r"\bAnthrop", r"\bSalesforce\b", r"\bUber\b", r"\bLyft\b",
        r"\bAirbnb\b", r"\bNvidia\b", r"\btech industr",
        r"\bcrypto", r"\bblockchain\b", r"\bfunding round\b",
        r"\bunicorn\b", r"\bvaluation\b", r"\bdowntown.{0,15}recover",
        r"\boffice.{0,10}vacanc", r"\breturn.{0,10}office\b",
        r"\bremote work", r"\bgig\s+work", r"\bforeclos",
        r"\bjob loss", r"\bjobs\b", r"\bhiring\b", r"\bworkforce\b",
        r"\bdata center", r"\benergy capacity\b",
    ],
    "Housing & Displacement": [
        r"\bhousing\b", r"\brent\b", r"\bevict", r"\bgentrific",
        r"\bzon(?:e|ing)\b", r"\bhomeless", r"\btenant", r"\blandlord",
        r"\baffordab", r"\bdisplace", r"\bshelter\b", r"\bencampment",
        r"\bunhoused\b", r"\bproperty tax\b", r"\brent control\b",
        r"\bpublic housing\b", r"\bsection 8\b", r"\bADU\b",
        r"\bNIMBY\b", r"\bYIMBY\b", r"\bmodular\s+home",
        r"\bpermit\b.*\bhousing\b", r"\bhome.?buyer",
        r"\bcommunity land trust\b", r"\binterim housing\b",
        r"\breal estate\b", r"\bcondo", r"\bresidential unit",
    ],
    "Climate & Environment": [
        r"\bwildfire", r"\bdrought\b", r"\bwater\b.*\bsupply\b",
        r"\bsea level\b", r"\bemission", r"\bpollut", r"\bclimate\b",
        r"\benvironment", r"\bflood", r"\bair quality\b",
        r"\bsmoke\b", r"\bfire season\b", r"\brenewable\b",
        r"\bsolar\b", r"\belectric vehicle\b",
        r"\bcoastal erosion\b", r"\bwetland", r"\brestoration\b",
        r"\bPG&E\b", r"\bpower grid\b", r"\bblackout\b",
        r"\bcontaminat", r"\btoxic\b", r"\bking tide\b",
        r"\bwatershed\b", r"\bstormwater\b", r"\bcarbon\b",
        r"\bnative plant", r"\breef\b", r"\bconservation\b",
        r"\bsustainab", r"\bFEMA\b", r"\bNOAA\b",
        r"\bpollinat", r"\borganic\b", r"\bagricultur",
        r"\brefinery\b", r"\bmarine reserve\b",
    ],
    "Governance & Power": [
        r"\bcity council\b", r"\bmayor\b", r"\bpolice\b",
        r"\bbudget\b", r"\bballot\b", r"\bmeasure [A-Z]\b",
        r"\brecall\b", r"\belection", r"\bsupervisor",
        r"\bdistrict attorney\b", r"\bcorrupt",
        r"\btransparenc", r"\baccountab", r"\bpublic safet",
        r"\bcrime\b", r"\bprosecutor\b", r"\bjail\b", r"\bprison\b",
        r"\bBART\b", r"\bMuni\b", r"\bCaltrain\b", r"\btransit\b",
        r"\bschool board\b", r"\bschool district\b",
        r"\beducation\b", r"\bpublic health\b", r"\bgovernan",
        r"\blegislat", r"\btown hall\b", r"\bcounty board\b",
        r"\bplanning commission\b", r"\btax measure\b",
        r"\bsheriff\b", r"\bimmigra", r"\bICE\b", r"\bfederal\b",
        r"\bgovernor\b", r"\bcongress", r"\bsales tax\b",
        r"\bstaffing\b", r"\bschool clos", r"\bstrike\b",
        r"\bsanctuary\b", r"\bMedi-Cal\b", r"\bredistric",
    ],
}

NATIONAL_KEYWORDS = [
    r"\bnation(?:al|wide)\b", r"\bfederal\b", r"\bCongress\b",
    r"\bWhite House\b", r"\bSupreme Court\b", r"\bprecedent",
    r"\bfirst.{0,25}(?:nation|country|state|california)\b",
    r"\bacross.{0,15}country\b", r"\bmodel.{0,15}(?:for|across)\b",
    r"\blandmark\b", r"\bbillion\b", r"\btrillion\b",
    r"\bstate(?:wide)?\s+law\b", r"\bregulat",
    r"\bimmigra", r"\bsanctuary\b",
    r"\blayoff.{0,20}\d{3,}", r"\b\d{1,3},?\d{3}\s+(?:jobs|workers)\b",
    r"\bAmendment\b", r"\bconstitution", r"\bcivil rights\b",
    r"\bfirst.{0,15}(?:city|county|municipality)\b",
    r"\bpilot program\b", r"\bcould.{0,20}(?:spread|expand|replicate)\b",
    r"\bFEMA\b", r"\bNOAA\b", r"\bfunding cut",
    r"\bgovernor\b.*\brace\b", r"\bWorld Cup\b", r"\bSuper Bowl\b",
]

# ─── Enterprise Journalism Detection ─────────────────────────────────────────

ENTERPRISE_SIGNALS = [
    (2, r"\binvestigat"), (2, r"\bexclusive\b"), (2, r"\bexpos[eé]"),
    (2, r"\buncovered?\b"), (2, r"\breveals?\b"),
    (2, r"\bobtained\s+(?:by|through|via)\b"),
    (2, r"\brecords\s+(?:show|reveal|obtained)\b"),
    (2, r"\bpublic records\b"),
    (2, r"\bdocuments\s+(?:show|reveal|obtained)\b"),
    (1, r"\baccording to\s+(?:records|documents|data|filings)\b"),
    (2, r"\baccountab"), (2, r"\bwhistleblow"),
    (1, r"\baudit\b"), (1, r"\boversight\b"), (1, r"\bmisconduct\b"),
    (1, r"\ballegation"), (1, r"\bfraud\b"), (1, r"\bcorrupt"),
    (1, r"\bwithhold"), (1, r"\btransparenc"), (1, r"\bnepotis"),
    (2, r"\bdata\s+(?:shows?|reveals?|analysis)\b"),
    (1, r"\banalysis\s+(?:of|by|shows?|finds?)\b"),
    (1, r"\bstudy\s+(?:finds?|shows?|ranks?)\b"),
    (1, r"\branks?\b.*\b(?:least|most|worst|best|first|last)\b"),
    (1, r"\baccording to\s+(?:a|an|the)\s+(?:new\s+)?(?:study|report|analysis|survey)\b"),
    (1, r"\bin-depth\b"), (1, r"\bdeep dive\b"), (1, r"\blong.?read\b"),
    (1, r"\breport(?:ing)?\s+(?:by|from)\b"), (1, r"\bprofile[sd]?\b"),
    (1, r"\bparadox\b"), (1, r"\bbreakthrough\b"),
    (1, r"\bwhy\b.*\b(?:are|is|do|does|did|has|have|can)\b"),
    (1, r"\bhow\b.*\b(?:are|is|do|does|did|has|have|can)\b"),
    (1, r"\bcould\b.*\b(?:reshape|transform|change|signal|mean)\b"),
    (1, r"\braises?\s+(?:questions?|concerns?|alarm)\b"),
    (1, r"\bimplication"),
    (1, r"\bshifting?\b.*\b(?:landscape|dynamic|equation|calculus)\b"),
    (1, r"\bCenter for Investigative\b"), (1, r"\bReveal\b"), (1, r"\bMarkup\b"),
]

ENTERPRISE_THRESHOLD = 3


def detect_enterprise(title, summary):
    combined = f"{title} {summary}"
    score = 0
    for weight, pattern in ENTERPRISE_SIGNALS:
        if re.search(pattern, combined, re.IGNORECASE):
            score += weight
    return score >= ENTERPRISE_THRESHOLD, score


def tag_themes(title, summary):
    combined = f"{title} {summary}"
    themes = []
    for theme, patterns in THEME_KEYWORDS.items():
        score = sum(1 for p in patterns if re.search(p, combined, re.IGNORECASE))
        if score >= 1:
            themes.append({"name": theme, "strength": min(score, 5)})
    themes.sort(key=lambda t: -t["strength"])
    return themes


def score_national(title, summary, themes):
    combined = f"{title} {summary}"
    score = 0
    for pattern in NATIONAL_KEYWORDS:
        if re.search(pattern, combined, re.IGNORECASE):
            score += 2
    if len(themes) >= 2:
        score += 1
    if len(themes) >= 3:
        score += 1
    max_strength = max((t["strength"] for t in themes), default=0)
    if max_strength >= 3:
        score += 1
    return min(score, 10)


def process_stories(stories):
    now = datetime.now(timezone.utc)
    seen_titles = set()
    processed = []

    for s in stories:
        norm = re.sub(r"[^a-z0-9]", "", s["title"].lower())
        if norm in seen_titles:
            continue
        seen_titles.add(norm)

        themes = tag_themes(s["title"], s["summary"])
        nat_score = score_national(s["title"], s["summary"], themes)
        is_ent, ent_score = detect_enterprise(s["title"], s["summary"])

        if is_ent:
            nat_score = min(nat_score + 2, 10)

        story_id = hashlib.md5(
            f"{s['title']}{s['link']}".encode()
        ).hexdigest()[:12]

        try:
            pub_dt = datetime.fromisoformat(s["published"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pub_dt = now
        age_days = max(0, (now - pub_dt).total_seconds() / 86400)

        recency_penalty = 0.0
        if age_days > 2:
            recency_penalty = min((age_days - 2) * 0.5, 3.0)

        rank_score = nat_score - recency_penalty

        processed.append({
            "id": story_id,
            "title": s["title"],
            "summary": s["summary"],
            "link": s["link"],
            "source": s["source"],
            "county": s["county"],
            "published": s["published"],
            "themes": themes,
            "nationalSignificance": nat_score,
            "isEnterprise": is_ent,
            "ageDays": round(age_days, 1),
            "rankScore": round(rank_score, 2),
        })

    processed.sort(key=lambda x: x["published"], reverse=True)
    processed.sort(key=lambda x: -x["rankScore"])
    return processed


if __name__ == "__main__":
    print("\n🗞  Bay Area Digest — Story Processor")
    print("=" * 55)

    # Load stories from RSS fetch output
    stories_path = SCRIPT_DIR / "stories_latest.json"
    with open(stories_path) as f:
        raw_stories = json.load(f)

    stories = process_stories(raw_stories)

    print(f"\n📊  Summary:")
    print(f"  Total stories:  {len(stories)}")
    nat = sum(1 for s in stories if s["nationalSignificance"] >= 3)
    ent = sum(1 for s in stories if s.get("isEnterprise"))
    print(f"  National reach: {nat}")
    print(f"  Enterprise:     {ent}")
    for theme in THEME_KEYWORDS:
        count = sum(1 for s in stories if any(t["name"] == theme for t in s["themes"]))
        print(f"  {theme}: {count}")
    counties = sorted(set(s["county"] for s in stories))
    print(f"  Counties ({len(counties)}): {', '.join(counties)}")
    sources = sorted(set(s["source"] for s in stories))
    print(f"  Sources ({len(sources)}): {', '.join(sources)}")

    # Write JSON
    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
    data = {"stories": stories, "generated_at": generated_at}
    out_path = SCRIPT_DIR / "digest_data.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n✅ JSON data written: {len(stories)} stories → {out_path}")

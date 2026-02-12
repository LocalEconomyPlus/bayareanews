#!/usr/bin/env python3
"""
Bay Area News Digest — RSS Feed Ingestion
Fetches stories from RSS feeds across ~35 Bay Area news sources,
with county tagging and deduplication.
"""

import feedparser
import json
import re
import time
import concurrent.futures
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# ── RSS Feed Registry ──────────────────────────────────────────────
# Each entry: (source_name, feed_url, default_county)
RSS_FEEDS = [
    # San Francisco (+ SFGate/Chronicle)
    ("SFGate", "https://www.sfgate.com/bayarea/feed/Bay-Area-News-702.php", "San Francisco"),
    ("SF Chronicle", "https://www.sfchronicle.com/bayarea/feed/Bay-Area-News-702.php", "San Francisco"),
    ("Mission Local", "https://missionlocal.org/feed/", "San Francisco"),
    ("SFist", "https://sfist.com/rss", "San Francisco"),
    ("SF Standard", "https://sfstandard.com/feed/", "San Francisco"),
    ("48 Hills", "https://48hills.org/feed/", "San Francisco"),
    ("El Tecolote", "https://eltecolote.org/content/en/feed/", "San Francisco"),
    ("Gazetteer SF", "https://sf.gazetteer.co/feed/", "San Francisco"),
    ("Coyote Media", "https://www.coyotemedia.org/rss/", "San Francisco"),
    ("Hoodline", "https://hoodline.com/news/san-francisco/rss", "San Francisco"),
    ("SF Bay Times", "https://sfbaytimes.com/feed/", "San Francisco"),
    ("SF Examiner", "https://www.sfexaminer.com/search/?f=rss&t=article&l=25&s=start_time&sd=desc", "San Francisco"),

    # Alameda / Contra Costa County
    ("Berkeleyside", "https://www.berkeleyside.org/feed/", "Alameda"),
    ("The Oaklandside", "https://oaklandside.org/feed/", "Alameda"),
    ("Richmondside", "https://richmondside.org/feed/", "Contra Costa"),
    ("East Bay Times", "https://www.eastbaytimes.com/feed/", "Alameda"),

    # Santa Clara County
    ("San Jose Spotlight", "https://sanjosespotlight.com/feed/", "Santa Clara"),
    ("Mercury News", "https://www.mercurynews.com/location/california/bay-area/feed/", "Bay Area"),
    ("Palo Alto Daily Post", "https://padailypost.com/feed/", "Santa Clara"),
    ("The Almanac", "https://www.almanacnews.com/feed/", "San Mateo"),

    # San Mateo County
    ("SM Daily Journal", "https://www.smdailyjournal.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc", "San Mateo"),

    # Marin County
    ("Marin IJ", "https://www.marinij.com/feed/", "Marin"),
    ("Point Reyes Light", "https://www.ptreyeslight.com/feed/", "Marin"),

    # Sonoma County
    ("Sonoma Index-Tribune", "https://www.sonomanews.com/feed/", "Sonoma"),
    ("Press Democrat", "https://www.pressdemocrat.com/feed/", "Sonoma"),

    # Napa County
    ("Napa Valley Register", "https://napavalleyregister.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc", "Napa"),

    # Solano County
    ("Vallejo Sun", "https://vallejosun.com/rss/", "Solano"),
    ("Vallejo Times-Herald", "https://www.timesheraldonline.com/feed/", "Solano"),
    ("Daily Republic", "https://www.dailyrepublic.com/feed/", "Solano"),

    # Santa Cruz County
    ("Lookout Santa Cruz", "https://lookout.co/feed/", "Santa Cruz"),

    # Regional / Statewide
    ("Sacramento Bee", "https://www.sacbee.com/news/politics-government/capitol-alert/index.rss", "Bay Area"),
    ("CalMatters", "https://calmatters.org/feed/", "Bay Area"),
    ("Streetsblog SF", "https://sf.streetsblog.org/feed/", "Bay Area"),
    ("KQED", "https://ww2.kqed.org/news/feed/", "Bay Area"),
    ("Local News Matters", "https://localnewsmatters.org/feed/", "Bay Area"),
    ("SF Business Journal", "https://feeds.bizjournals.com/sanfrancisco", "San Francisco"),

    # TV stations
    ("ABC7 News", "https://abc7news.com/feed/", "Bay Area"),
    ("KRON4", "https://kron4.com/news/app-feed/", "Bay Area"),
    ("NBC Bay Area", "https://www.nbcbayarea.com/?rss=y", "Bay Area"),
    # KTVU: no public RSS feed available
    ("CBS San Francisco", "https://www.cbsnews.com/sanfrancisco/latest/rss/main", "Bay Area"),
]

# ── County detection from content ──────────────────────────────────
COUNTY_PATTERNS = {
    "San Francisco": r"san francisco|sf |sfusd|soma|tenderloin|mission district|castro|sunset|richmond district|presidio|bayview|fillmore|nob hill|haight",
    "Alameda": r"oakland|berkeley|fremont|hayward|alameda|livermore|pleasanton|dublin|union city|emeryville|piedmont|east bay",
    "Santa Clara": r"san jose|silicon valley|santa clara|sunnyvale|mountain view|cupertino|palo alto|milpitas|campbell|los gatos|saratoga|gilroy",
    "San Mateo": r"san mateo|daly city|redwood city|half moon bay|burlingame|san bruno|foster city|menlo park|pacifica|belmont",
    "Contra Costa": r"contra costa|walnut creek|concord|richmond|antioch|martinez|danville|pleasant hill|san ramon|pittsburg|orinda|lafayette",
    "Marin": r"marin|san rafael|novato|mill valley|sausalito|tiburon|fairfax|point reyes|stinson",
    "Sonoma": r"sonoma|santa rosa|petaluma|healdsburg|sebastopol|rohnert park|windsor|cloverdale",
    "Napa": r"napa|st\.? helena|calistoga|yountville|american canyon",
    "Solano": r"solano|vallejo|benicia|fairfield|vacaville|dixon|suisun",
    "Santa Cruz": r"santa cruz|watsonville|capitola|scotts valley|aptos|soquel",
}


def detect_county(title, summary, default_county):
    """Try to detect a more specific county from content."""
    text = (title + " " + summary).lower()
    matches = []
    for county, pattern in COUNTY_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            matches.append(county)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1 and default_county in matches:
        return default_county
    if len(matches) > 1:
        return matches[0]
    return default_county


def parse_date(entry):
    """Extract published date from a feed entry, return ISO string."""
    for field in ("published", "updated", "created"):
        raw = entry.get(field)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
            parsed = entry.get(field + "_parsed")
            if parsed:
                try:
                    dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                    return dt.isoformat()
                except Exception:
                    pass
    return datetime.now(timezone.utc).isoformat()


def fetch_one_feed(source_name, feed_url, default_county, cutoff_days=10):
    """Fetch and parse a single RSS feed. Returns list of story dicts."""
    stories = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)

    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            exc = getattr(feed, 'bozo_exception', 'unknown')
            print(f"  ⚠  {source_name}: Feed error — {exc}")
            print(f"       URL: {feed_url}")
            return stories
        # Some feeds are bozo but still have entries (minor XML issues) — allow those

        for entry in feed.entries[:25]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            summary = ""
            if entry.get("summary"):
                summary = re.sub(r"<[^>]+>", "", entry.summary).strip()[:500]
            elif entry.get("description"):
                summary = re.sub(r"<[^>]+>", "", entry.description).strip()[:500]

            link = entry.get("link", "")
            published = parse_date(entry)

            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass

            county = detect_county(title, summary, default_county)

            stories.append({
                "title": title,
                "summary": summary,
                "link": link,
                "source": source_name,
                "county": county,
                "published": published,
            })

        print(f"  ✓  {source_name}: {len(stories)} stories")
    except Exception as e:
        print(f"  ✗  {source_name}: {e}")

    return stories


def fetch_all_feeds():
    """Fetch all RSS feeds in parallel."""
    print("🗞  Bay Area Digest — RSS Feed Ingestion")
    print("=" * 55)
    print(f"  Feeds to check: {len(RSS_FEEDS)}")
    print()

    all_stories = []
    succeeded = 0
    failed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(fetch_one_feed, name, url, county): name
            for name, url, county in RSS_FEEDS
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                stories = future.result()
                all_stories.extend(stories)
                if stories:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  ✗  {name}: {e}")
                failed += 1

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for s in all_stories:
        key = re.sub(r"[^a-z0-9]", "", s["title"].lower())[:60]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(s)

    print()
    print(f"📊  RSS Results:")
    print(f"  Feeds succeeded: {succeeded}")
    print(f"  Feeds failed/empty: {failed}")
    print(f"  Total stories: {len(unique)}")

    sources = sorted(set(s["source"] for s in unique))
    counties = sorted(set(s["county"] for s in unique))
    print(f"  Sources ({len(sources)}): {', '.join(sources)}")
    print(f"  Counties ({len(counties)}): {', '.join(counties)}")

    return unique


if __name__ == "__main__":
    start = time.time()
    stories = fetch_all_feeds()

    # Write stories as JSON for the processing pipeline
    outpath = SCRIPT_DIR / "stories_latest.json"
    with open(outpath, "w") as f:
        json.dump(stories, f, indent=2)
    print(f"\n✅ Wrote {len(stories)} stories → {outpath}")

    elapsed = time.time() - start
    print(f"⏱  RSS fetch took {elapsed:.1f} seconds")

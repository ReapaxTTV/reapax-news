#!/usr/bin/env python3
"""
Reapax News Aggregator (API-FREE version)
Fetches RSS feeds, deduplicates, categorizes, ranks, and summarizes
articles using smart keyword matching — no paid API needed.

Schedule: twice daily via GitHub Actions (07:00 + 19:00 Swedish time)
"""

import json
import os
import sys
import re
from datetime import datetime, timezone, timedelta
from ftplib import FTP_TLS, FTP
import io
import traceback

# pip install feedparser requests beautifulsoup4
import feedparser
import requests
from bs4 import BeautifulSoup


# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
FTP_REMOTE_DIR = os.environ.get("FTP_REMOTE_DIR", "/public_html/news")
FTP_USE_TLS = os.environ.get("FTP_USE_TLS", "true").lower() == "true"

MAX_ARTICLE_AGE_HOURS = 48
MAX_ARTICLES_OUTPUT = 80


# ══════════════════════════════════════════════════════════════
# RSS FEEDS
# ══════════════════════════════════════════════════════════════

FEEDS = [
    # Swedish News
    {"url": "https://www.tv4.se/rss", "name": "TV4", "lang": "sv", "default_cat": "sverige"},
    {"url": "https://feeds.expressen.se/nyheter/", "name": "Expressen", "lang": "sv", "default_cat": "sverige"},
    {"url": "https://feeds.expressen.se/gt", "name": "GT", "lang": "sv", "default_cat": "lokalt"},
    {"url": "https://www.folkhalsomyndigheten.se/nyheter-och-press/nyhetsarkiv/?syndication=rss", "name": "Folkhalsomyndigheten", "lang": "sv", "default_cat": "sverige"},
    {"url": "https://www.dn.se/rss/", "name": "Dagens Nyheter", "lang": "sv", "default_cat": "sverige"},
    {"url": "https://www.svt.se/rss.xml", "name": "SVT", "lang": "sv", "default_cat": "sverige"},
    {"url": "https://rss.aftonbladet.se/rss2/small/pages/sections/senastenytt/", "name": "Aftonbladet", "lang": "sv", "default_cat": "sverige"},
    {"url": "https://www.jp.se/feeds/feed.xml", "name": "Jonkopingsposten", "lang": "sv", "default_cat": "lokalt"},
    {"url": "https://www.svd.se/feed/articles.rss", "name": "Svenska Dagbladet", "lang": "sv", "default_cat": "sverige"},

    # Police
    {"url": "https://polisen.se/aktuellt/rss/jonkopings-lan/nyheter-rss---jonkopings-lan/", "name": "Polisen Jonkoping", "lang": "sv", "default_cat": "polis"},
    {"url": "https://polisen.se/aktuellt/rss/jonkopings-lan/handelser-rss---jonkoping/", "name": "Polisen Jonkoping", "lang": "sv", "default_cat": "polis"},
    {"url": "https://polisen.se/aktuellt/rss/vastra-gotaland/nyheter-rss---vastra-gotaland/", "name": "Polisen VGR", "lang": "sv", "default_cat": "polis"},
    {"url": "https://polisen.se/aktuellt/rss/vastra-gotaland/handelser-rss---vastra-gotaland/", "name": "Polisen VGR", "lang": "sv", "default_cat": "polis"},

    # International
    {"url": "http://feeds.bbci.co.uk/news/rss.xml", "name": "BBC News", "lang": "en", "default_cat": "world"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "name": "New York Times", "lang": "en", "default_cat": "world"},
    {"url": "http://rss.cnn.com/rss/edition.rss", "name": "CNN", "lang": "en", "default_cat": "world"},
    {"url": "https://feeds.bloomberg.com/technology/news.rss", "name": "Bloomberg Tech", "lang": "en", "default_cat": "social"},
    {"url": "https://techcrunch.com/feed/", "name": "TechCrunch", "lang": "en", "default_cat": "social"},

    # Social Media & Memes
    {"url": "https://knowyourmeme.com/newsfeed.rss", "name": "KnowYourMeme", "lang": "en", "default_cat": "memes"},
    {"url": "https://www.socialmediatoday.com/feeds/news", "name": "Social Media Today", "lang": "en", "default_cat": "social"},
    {"url": "https://later.com/blog/feed/", "name": "Later", "lang": "en", "default_cat": "social"},
    {"url": "https://socialbee.com/blog/feed/", "name": "SocialBee", "lang": "en", "default_cat": "social"},
    {"url": "https://napoleoncat.com/blog/feed/", "name": "NapoleonCat", "lang": "en", "default_cat": "memes"},
    {"url": "https://www.theverge.com/rss/index.xml", "name": "The Verge", "lang": "en", "default_cat": "social"},
]


# ══════════════════════════════════════════════════════════════
# SMART CATEGORIZATION
# ══════════════════════════════════════════════════════════════

CATEGORY_KEYWORDS = {
    "polis": [
        "polis", "polisen", "brott", "misstankt", "gripen", "gripna", "anhallen",
        "haktad", "atalad", "olycka", "trafikolycka", "brand", "stold", "inbrott",
        "misshandel", "mord", "skjutning", "knivdad", "narkotika", "bedrageri",
        "forsvunnen", "dodsfall", "rattfylla", "vapenbrott", "ran",
        "handelse", "larm", "ambulans", "raddningstjanst",
        "police", "crime", "arrest", "shooting", "murder", "robbery",
    ],
    "lokalt": [
        "jonkoping", "huskvarna", "bankeryd", "nassjo", "varnamo", "gislaved",
        "tranas", "vetlanda", "aneby", "eksjo", "savsjo", "mullsjo", "habo",
        "gotene", "skara", "lidkoping", "vara", "grastorp", "mariestad",
        "vastra gotaland", "gotaland",
        "kommun", "kommunen", "lokalt", "regionen",
        "jonkopings lan", "smaland",
    ],
    "memes": [
        "meme", "memes", "viral", "tiktok trend", "brainrot", "shitpost",
        "know your meme", "trending meme", "internet culture",
        "dank", "cringe", "based", "sus", "skibidi",
        "challenge", "filter trend",
    ],
    "social": [
        "tiktok", "instagram", "snapchat", "youtube", "twitter",
        "facebook", "meta", "threads", "bluesky", "reddit", "twitch",
        "social media", "sociala medier", "influencer", "creator",
        "algoritm", "algorithm", "plattform", "platform",
        "app update", "new feature", "uppdatering",
        "artificial intelligence", "chatgpt", "openai", "startup",
        "tech company", "silicon valley", "apple", "google", "microsoft",
    ],
    "world": [
        "usa", "china", "russia", "ukraine", "eu ", "european union",
        "nato", "united nations", "trump", "biden", "putin",
        "war", "conflict", "krig", "summit", "trade", "sanctions",
        "earthquake", "hurricane", "tsunami", "climate",
        "white house", "congress", "parliament",
    ],
}

IMPORTANCE_BOOSTERS = {
    5: ["kris", "crisis", "terror", "jordbavning", "earthquake", "tsunami",
        "pandemi", "pandemic", "doda", "killed", "masskjutning", "mass shooting"],
    4: ["brott", "crime", "avslojar", "reveals", "skandal", "scandal",
        "regeringen", "government", "riksdag", "reform", "miljarder", "billion",
        "strejk", "strike", "protest", "explosion", "allvarlig", "serious", "dodlig", "fatal"],
    3: ["ny rapport", "new report", "studie visar", "study shows",
        "viral", "trending", "rekord", "record", "lanserar", "launches",
        "varning", "warning"],
}

HIGH_IMPORTANCE_SOURCES = ["Polisen Jonkoping", "Polisen VGR", "Folkhalsomyndigheten"]


def categorize_article(title, summary, default_cat, source_name):
    text = (title + " " + summary).lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(3 if kw in title.lower() else 1 for kw in keywords if kw in text)
        scores[cat] = score
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else default_cat


def calculate_importance(title, summary, sources_count, source_name):
    text = (title + " " + summary).lower()
    importance = 2
    for level, keywords in IMPORTANCE_BOOSTERS.items():
        if any(kw in text for kw in keywords):
            importance = max(importance, level)
    if sources_count >= 4:
        importance = max(importance, 4)
    elif sources_count >= 3:
        importance = max(importance, 3)
    elif sources_count >= 2:
        importance = min(importance + 1, 5)
    if source_name in HIGH_IMPORTANCE_SOURCES:
        importance = max(importance, 3)
    return importance


def clean_summary(title, raw):
    if not raw:
        return ""
    s = raw.strip()
    if s.lower().startswith(title.lower()[:30]):
        s = s[len(title):].strip().lstrip(".-:,")
    s = s.strip()
    if len(s) > 220:
        cut = s[:220].rfind(". ")
        s = s[:cut + 1] if cut > 80 else s[:217] + "..."
    return s


# ══════════════════════════════════════════════════════════════
# FETCH + SCRAPE + DEDUP
# ══════════════════════════════════════════════════════════════

def fetch_feeds():
    articles = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)

    for fc in FEEDS:
        print(f"  [{fc['name']}] ", end="", flush=True)
        try:
            parsed = feedparser.parse(fc["url"])
            if parsed.bozo and not parsed.entries:
                print(f"ERROR")
                continue
            count = 0
            for entry in parsed.entries[:25]:
                published = None
                for df in ["published_parsed", "updated_parsed", "created_parsed"]:
                    dt = getattr(entry, df, None)
                    if dt:
                        try:
                            published = datetime(*dt[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass
                        break
                if published and published < cutoff:
                    continue
                if not published:
                    published = datetime.now(timezone.utc)
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                summary = ""
                for attr in ["summary", "description"]:
                    if hasattr(entry, attr):
                        summary = getattr(entry, attr)
                        break
                if not summary and hasattr(entry, "content") and entry.content:
                    summary = entry.content[0].get("value", "")
                if summary:
                    summary = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
                    summary = re.sub(r'\s+', ' ', summary).strip()[:500]
                articles.append({
                    "title": title, "summary": summary, "link": entry.get("link", ""),
                    "source_name": fc["name"], "default_cat": fc["default_cat"],
                    "published": published.isoformat(), "lang": fc["lang"],
                })
                count += 1
            print(f"{count}")
        except Exception as e:
            print(f"FAIL ({e})")
    return articles


def scrape_gotene():
    articles = []
    sites = [
        ("Gotene kommun", "https://www.gotene.se/kommunochpolitik/omwebbplatsen/programteknikochfiler/sok/nyhetsarkiv.157.html"),
        ("Gotene Tidning", "https://www.gotenetidning.se/"),
    ]
    for name, url in sites:
        try:
            print(f"  [{name}] ", end="", flush=True)
            r = requests.get(url, timeout=15, headers={"User-Agent": "ReapaxNewsBot/1.0"})
            if not r.ok:
                print(f"HTTP {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("article, .news-item, .list-item, h2 a, h3 a")
            count = 0
            for item in items[:8]:
                el = item if item.name == "a" else item.select_one("h2 a, h3 a, h2, h3, a")
                if not el:
                    continue
                title = el.get_text(strip=True)
                link = el.get("href", "")
                if link and not link.startswith("http"):
                    link = url.rstrip("/") + "/" + link.lstrip("/")
                if title and len(title) > 5:
                    articles.append({
                        "title": title, "summary": "", "link": link,
                        "source_name": name, "default_cat": "lokalt",
                        "published": datetime.now(timezone.utc).isoformat(), "lang": "sv",
                    })
                    count += 1
            print(f"{count}")
        except Exception as e:
            print(f"FAIL ({e})")
    return articles


def deduplicate(articles):
    groups, used = [], set()
    for i, a in enumerate(articles):
        if i in used:
            continue
        group = [a]
        ni = set(re.sub(r'[^\w\s]', '', a["title"].lower()).split())
        for j in range(i + 1, len(articles)):
            if j in used:
                continue
            nj = set(re.sub(r'[^\w\s]', '', articles[j]["title"].lower()).split())
            if ni and nj and len(ni & nj) / len(ni | nj) > 0.4:
                group.append(articles[j])
                used.add(j)
        used.add(i)
        groups.append(group)
    return groups


# ══════════════════════════════════════════════════════════════
# BUILD OUTPUT + UPLOAD
# ══════════════════════════════════════════════════════════════

def build_output(groups):
    results = []
    for group in groups:
        sv = [a for a in group if a["lang"] == "sv"]
        pool = sv if sv else group
        best_title = max(pool, key=lambda a: len(a["title"]))["title"]
        sources, seen = [], set()
        for a in group:
            if a["source_name"] not in seen:
                sources.append({"name": a["source_name"], "url": a["link"]})
                seen.add(a["source_name"])
        raw_summary = max((a["summary"] for a in group), key=len, default="")
        summary = clean_summary(best_title, raw_summary)
        published = max(a["published"] for a in group)
        cat = categorize_article(best_title, raw_summary, group[0]["default_cat"], group[0]["source_name"])
        imp = calculate_importance(best_title, raw_summary, len(sources), group[0]["source_name"])
        results.append({
            "title": best_title, "summary": summary, "category": cat,
            "importance": imp, "published": published, "sources": sources,
        })
    results.sort(key=lambda x: (-x["importance"], x["published"]))
    return results[:MAX_ARTICLES_OUTPUT]


def upload_ftp(json_str):
    if not FTP_HOST or not FTP_USER:
        print("  FTP not configured, local only.")
        return False
    print(f"  Uploading to {FTP_HOST}...", end="", flush=True)
    try:
        if FTP_USE_TLS:
            ftp = FTP_TLS(FTP_HOST, timeout=30)
            ftp.login(FTP_USER, FTP_PASS)
            ftp.prot_p()
        else:
            ftp = FTP(FTP_HOST, timeout=30)
            ftp.login(FTP_USER, FTP_PASS)
        try:
            ftp.cwd(FTP_REMOTE_DIR)
        except Exception:
            parts = FTP_REMOTE_DIR.strip("/").split("/")
            path = ""
            for p in parts:
                path += "/" + p
                try:
                    ftp.cwd(path)
                except Exception:
                    ftp.mkd(path)
                    ftp.cwd(path)
        ftp.storbinary("STOR news.json", io.BytesIO(json_str.encode("utf-8")))
        ftp.quit()
        print(" OK")
        return True
    except Exception as e:
        print(f" FAIL: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  REAPAX NEWS AGGREGATOR")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    print("\n[1/5] Fetching RSS feeds...")
    articles = fetch_feeds()

    print("\n[2/5] Scraping Gotene...")
    articles.extend(scrape_gotene())
    print(f"\n  Raw total: {len(articles)}")

    if not articles:
        print("  No articles! Exiting.")
        sys.exit(1)

    print("\n[3/5] Deduplicating...")
    groups = deduplicate(articles)
    print(f"  {len(articles)} -> {len(groups)} unique stories")

    print("\n[4/5] Categorizing & ranking...")
    final = build_output(groups)
    cats = {}
    for a in final:
        cats[a["category"]] = cats.get(a["category"], 0) + 1
    for c, n in sorted(cats.items()):
        print(f"  {c}: {n}")
    print(f"  Total: {len(final)} articles")

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "article_count": len(final),
        "articles": final,
    }
    json_str = json.dumps(output, ensure_ascii=False, indent=2)
    with open("news.json", "w", encoding="utf-8") as f:
        f.write(json_str)

    print("\n[5/5] Uploading...")
    upload_ftp(json_str)

    print("\n" + "=" * 55)
    print("  DONE!")
    print("=" * 55)


if __name__ == "__main__":
    main()

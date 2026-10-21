#!/usr/bin/env python3
"""Daily "New papers on <topic>" thread for Doclert's Bluesky account.

Takes up to three recent papers from PubMed (NLM E-utilities) for the day's topic and renders a
thread: a head post with the Doclert short link, then one reply per paper with its title exactly as
PubMed gives it, the journal, the date, the PubMed link and "Source: PubMed". Nothing else: no
abstract, no author names, no text written by AI (DATA-RIGHTS tier 1 without the author).

Modes (config.json "mode", or --mode):
  off      do nothing
  preview  render and print, never post (default; also what a push to a branch runs)
  live     post to Bluesky, only from config "start" on and only with BLUESKY_HANDLE and
           BLUESKY_APP_PASSWORD set; writes state/posted.json so a paper is never posted twice

Standard library only. NCBI: tool and email on every call, two requests a run.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
NCBI_TOOL = "doclert-social"
NCBI_EMAIL = "hello@doclert.com"
BSKY = "https://bsky.social/xrpc/"
LIMIT = 300  # Bluesky graphemes per post
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COUNT_WORDS = {2: "Two", 3: "Three"}
BLOCKED_TITLE = re.compile(r"\b(retract|erratum|errata|corrigendum|correction|withdrawn|expression of concern|in memoriam|obituary)", re.I)


def get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise RuntimeError(f"{url.split('?')[0]} -> HTTP {e.code}: {e.read()[:300]!r}") from None
        except urllib.error.URLError:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url.split('?')[0]} failed three times")


def eutils(endpoint, params):
    params = dict(params, tool=NCBI_TOOL, email=NCBI_EMAIL, retmode="json")
    time.sleep(0.4)  # well under NCBI's 3 requests a second
    return get_json(EUTILS + endpoint + "?" + urllib.parse.urlencode(params))


def clean_title(raw):
    text = html.unescape(re.sub(r"<[^>]+>", "", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def nice_date(summary):
    """The online date when PubMed has one (an issue date can lie weeks ahead), else the publication date."""
    m = re.match(r"(\d{4}) ([A-Z][a-z]{2}) (\d{1,2})$", (summary.get("epubdate") or "").strip())
    if m and m.group(2) in MONTHS:
        return f"{int(m.group(3))} {m.group(2)} {m.group(1)}"
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", summary.get("sortpubdate", ""))
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{d} {MONTHS[mo - 1]} {y}"
    return summary.get("pubdate", "").strip()


def find_papers(cfg, topic, today, blocked):
    journals = " OR ".join(f'"{j}"[ta]' for j in topic["journals"] + cfg["general_journals"])
    on_topic = re.compile(topic["title_words"], re.I)
    term = f"({topic['query']}) AND ({journals}) AND {cfg['filters']}"
    found = eutils("esearch.fcgi", {
        "db": "pubmed", "term": term, "datetype": "edat",
        "reldate": cfg["days_back"], "retmax": 60, "sort": "pub_date",
    })["esearchresult"]
    if os.environ.get("PAPERS_DEBUG"):
        print("query:", found.get("querytranslation"), "| errors:", found.get("errorlist"),
              "| warnings:", found.get("warninglist"), file=sys.stderr)
    ids = [i for i in found.get("idlist", []) if i not in blocked]
    if not ids:
        return [], int(found.get("count", 0))
    result = eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(ids)})["result"]
    papers, journals = [], set()
    for pmid in result.get("uids", []):
        s = result[pmid]
        title = clean_title(s.get("title"))
        journal = (s.get("source") or "").strip()
        if not title or not journal or BLOCKED_TITLE.search(title) or journal in journals:
            continue
        if "Has Abstract" not in s.get("attributes", []):
            continue  # news, editorials and commentary rarely have one; research papers do
        if not on_topic.search(title):
            continue  # the title itself must name the day's topic
        paper = {"pmid": pmid, "title": title, "journal": journal, "date": nice_date(s)}
        if len(paper_text(paper, 1, 3)) > LIMIT:
            continue  # never shorten a title: skip it
        papers.append(paper)
        journals.add(journal)
        if len(papers) == cfg["papers_per_post"]:
            break
    return papers, int(found.get("count", 0))


def post_id(cfg, day):
    week = day.isocalendar()[1]
    return f"w{week}-{cfg['page']}-{cfg['network']}-{day.isoweekday()}"


def head_text(cfg, topic, day, n):
    link = f"doclert.com/go/{post_id(cfg, day)}"
    text = (
        f"New papers on {topic['name']}, {day.day} {MONTHS[day.month - 1]} {day.year}\n\n"
        f"{COUNT_WORDS[n]} recent papers from PubMed, one per reply ↓\n\n"
        f"New papers on your own topics by e-mail, SMS or WhatsApp: {link}"
    )
    return text, [(link, "https://" + link)]


def paper_text(paper, i, n):
    link = f"pubmed.ncbi.nlm.nih.gov/{paper['pmid']}"
    return f"{i}/{n} {paper['title']}\n\n{paper['journal']} · {paper['date']}\n{link}\nSource: PubMed"


def paper_post(paper, i, n):
    link = f"pubmed.ncbi.nlm.nih.gov/{paper['pmid']}"
    return paper_text(paper, i, n), [(link, f"https://{link}/")]


def facets(text, links):
    out, raw = [], text.encode("utf-8")
    for shown, uri in links:
        start = raw.find(shown.encode("utf-8"))
        if start >= 0:
            out.append({
                "index": {"byteStart": start, "byteEnd": start + len(shown.encode("utf-8"))},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": uri}],
            })
    return out


def build_thread(cfg, day, blocked):
    topic = cfg["topics"][str(day.isoweekday())]
    papers, count = find_papers(cfg, topic, day, blocked)
    if len(papers) < 2:
        return None, papers, count
    n = len(papers)
    posts = [head_text(cfg, topic, day, n)] + [paper_post(p, i + 1, n) for i, p in enumerate(papers)]
    for text, _ in posts:
        assert len(text) <= LIMIT, (len(text), text)
    return posts, papers, count


def bsky_post(session, text, links, reply):
    record = {
        "$type": "app.bsky.feed.post", "text": text, "langs": ["en"],
        "createdAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    f = facets(text, links)
    if f:
        record["facets"] = f
    if reply:
        record["reply"] = reply
    body = json.dumps({"repo": session["did"], "collection": "app.bsky.feed.post", "record": record}).encode()
    return get_json(BSKY + "com.atproto.repo.createRecord", body, {
        "Content-Type": "application/json", "Authorization": "Bearer " + session["accessJwt"],
    })


def publish(posts):
    handle, password = os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not password:
        raise RuntimeError("live mode needs BLUESKY_HANDLE and BLUESKY_APP_PASSWORD")
    body = json.dumps({"identifier": handle, "password": password}).encode()
    session = get_json(BSKY + "com.atproto.server.createSession", body, {"Content-Type": "application/json"})
    root = parent = None
    uris = []
    try:
        for text, links in posts:
            reply = {"root": root, "parent": parent} if root else None
            ref = bsky_post(session, text, links, reply)
            ref = {"uri": ref["uri"], "cid": ref["cid"]}
            root, parent = root or ref, ref
            uris.append(ref["uri"])
            time.sleep(1)
    except Exception:
        for uri in reversed(uris):  # never leave half a thread up
            bsky_delete(session, uri)
        raise
    return uris


def bsky_delete(session, uri):
    rkey = uri.rsplit("/", 1)[-1]
    body = json.dumps({"repo": session["did"], "collection": "app.bsky.feed.post", "rkey": rkey}).encode()
    try:
        get_json(BSKY + "com.atproto.repo.deleteRecord", body, {
            "Content-Type": "application/json", "Authorization": "Bearer " + session["accessJwt"],
        })
    except Exception as e:  # report and go on deleting the rest
        print("could not delete", uri, e, file=sys.stderr)


def load_state():
    path = os.path.join(HERE, "state", "posted.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"posts": []}


def save_state(state):
    os.makedirs(os.path.join(HERE, "state"), exist_ok=True)
    with open(os.path.join(HERE, "state", "posted.json"), "w") as f:
        json.dump(state, f, indent=1)
        f.write("\n")


def show(day, posts, papers, count):
    print(f"## {day.isoformat()} ({day.strftime('%A')}): {count} PubMed matches, {len(papers)} used\n")
    if not posts:
        print("No post today (fewer than 2 usable papers).\n")
        return
    for text, _ in posts:
        print("```\n" + text + "\n```")
        print(f"({len(text)}/{LIMIT} characters)\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["off", "preview", "live"])
    ap.add_argument("--date", help="YYYY-MM-DD, default today (UTC)")
    ap.add_argument("--week", action="store_true", help="preview all seven topics")
    args = ap.parse_args()
    with open(os.path.join(HERE, "config.json")) as f:
        cfg = json.load(f)
    mode = args.mode or os.environ.get("PAPERS_MODE_OVERRIDE") or cfg["mode"]
    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(dt.timezone.utc).date()
    if mode == "off":
        print("mode off: nothing to do")
        return 0
    state = load_state()
    cutoff = (today - dt.timedelta(days=cfg["repeat_block_days"])).isoformat()
    blocked = {p for s in state["posts"] if s["date"] >= cutoff for p in s["pmids"]}

    if mode == "preview":
        days = [today + dt.timedelta(days=k) for k in range(7)] if args.week else [today]
        for day in days:
            posts, papers, count = build_thread(cfg, day, blocked)
            show(day, posts, papers, count)
            blocked |= {p["pmid"] for p in papers}
        return 0

    if today < dt.date.fromisoformat(cfg["start"]):
        print(f"live mode, but start is {cfg['start']}: nothing posted")
        return 0
    if any(s["date"] == today.isoformat() for s in state["posts"]):
        print("already posted today")
        return 0
    posts, papers, count = build_thread(cfg, today, blocked)
    show(today, posts, papers, count)
    if not posts:
        return 0
    uris = publish(posts)
    state["posts"].append({"date": today.isoformat(), "pmids": [p["pmid"] for p in papers], "uris": uris})
    save_state(state)
    print("posted:", *uris, sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

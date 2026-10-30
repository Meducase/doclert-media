#!/usr/bin/env python3
"""Daily "New papers on <topic>" thread for Doclert's Bluesky account.

Takes up to three recent papers for the day's topic and renders a
thread: a head post with the Doclert short link, then one reply per paper with its title exactly as
PubMed gives it, the journal, the date and a link to the paper (its DOI, else its PubMed record).
The topic's journal and title rules of config.json give the candidates; the Doclert Ranking orders them
(GET /api/stats.php?view=ranking&pmids=… with the DOCLERT_RANKING_KEY secret; it only chooses, posts never show it);
without the key or on any endpoint error the newest come first. Titles and journals
always come from PubMed (NLM E-utilities). A post carries nothing else: no abstract, no author names, no text written by AI (DATA-RIGHTS tier 1 without the
author). Copy never names PubMed (Matt, 21 Oct 2026); NLM's required acknowledgement sits in the bio
and the pinned post (config "profile").

Modes (config.json "mode", or --mode):
  off      do nothing
  preview  render and print, never post (default; also what a push to a branch runs)
  live     post to Bluesky as config "handle", only from config "start" on and only with the
           BLUESKY_APP_PASSWORD secret; writes state/posted.json so a paper is never posted twice
--setup-profile, once after Matt's OK, sets the bio and the pinned post of config "profile".
--follow follows the accounts of config "follow" (journals, societies, educators): only a handle whose
display name contains the expected name, at most 50, never one already followed. --check-follows (no
secret; a branch push runs it) only reports what each handle resolves to and lists search candidates.
state/posted.json keeps, per day, the topic, the thread link and each paper's title, journal, date and
link: the source for other "what's new" posts (raw file on GitHub).

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
APPVIEW = "https://public.api.bsky.app/xrpc/"  # public reads, no login
MAX_FOLLOWS = 50
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
    """The online date when PubMed has one (an issue date can lie weeks ahead), else the publication date, never a
    date after today: then the day PubMed added the record."""
    today = dt.datetime.now(dt.timezone.utc).date()
    m = re.match(r"(\d{4}) ([A-Z][a-z]{2}) (\d{1,2})$", (summary.get("epubdate") or "").strip())
    if m and m.group(2) in MONTHS:
        day = dt.date(int(m.group(1)), MONTHS.index(m.group(2)) + 1, int(m.group(3)))
        if day <= today:
            return f"{day.day} {m.group(2)} {day.year}"
    dates = [summary.get("sortpubdate", "")]
    dates += [h.get("date", "") for h in summary.get("history", []) if h.get("pubstatus") in ("entrez", "pubmed")]
    for raw in dates:
        m = re.match(r"(\d{4})/(\d{2})/(\d{2})", raw or "")
        if m:
            day = dt.date(*(int(x) for x in m.groups()))
            if day <= today:
                return f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    return summary.get("pubdate", "").strip()


def eligible(result, pmids, on_topic):
    """Papers in the order of pmids that pass the post rules (the day's topic in the title, an abstract, English, fits)."""
    papers = []
    for pmid in pmids:
        s = result.get(pmid)
        if not s:
            continue
        title = clean_title(s.get("title"))
        journal = (s.get("source") or "").strip()
        if not title or not journal or BLOCKED_TITLE.search(title):
            continue
        if "Has Abstract" not in s.get("attributes", []):
            continue  # news, editorials and commentary rarely have one; research papers do
        if "eng" not in s.get("lang", ["eng"]):
            continue  # a translated title in brackets is not the title as published
        if not on_topic.search(title):
            continue  # the title itself must name the day's topic
        paper = {"pmid": pmid, "title": title, "journal": journal, "date": nice_date(s), "doi": doi_of(s)}
        if len(paper_text(paper, 1, 3)) > LIMIT:
            continue  # never shorten a title: skip it
        papers.append(paper)
    return papers


def choose(cfg, papers):
    """The first papers_per_post, one per journal."""
    out, journals = [], set()
    for p in papers:
        if p["journal"] not in journals:
            out.append(p)
            journals.add(p["journal"])
        if len(out) == cfg["papers_per_post"]:
            break
    return out


def rankings(cfg, pmids):
    """{pmid: Doclert Ranking} from GET /api/stats.php?view=ranking&pmids=… (None without the key)."""
    key = os.environ.get("DOCLERT_RANKING_KEY", "").strip()
    rk = cfg.get("ranking") or {}
    if not key or not rk.get("enabled") or not pmids:
        return None
    out = {}
    for k in range(0, len(pmids), 50):
        query = urllib.parse.urlencode({"view": "ranking", "pmids": ",".join(pmids[k:k + 50]), "days": 7, "limit": 50})
        for i in get_json(rk["api"] + "?" + query, headers={"X-Doclert-Stats-Key": key})["items"]:
            out[i["pmid"]] = float(i["ranking"])
    return out


def candidates(cfg, topic, blocked):
    """The topic's papers from its journals and the general ones, added in the last days_back days, newest first."""
    journals = " OR ".join(f'"{j}"[ta]' for j in topic["journals"] + cfg["general_journals"])
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
        return []
    result = eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(ids)})["result"]
    return eligible(result, result.get("uids", []), re.compile(topic["title_words"], re.I))


def find_papers(cfg, topic, today, blocked):
    """The journal and title rules give the candidates; the Doclert Ranking orders them when its key is there
    (unranked papers after the ranked ones, newest first), else, or on any endpoint error, the newest come first."""
    papers = candidates(cfg, topic, blocked)
    try:
        ranks = rankings(cfg, [p["pmid"] for p in papers])
    except Exception as e:  # never lose a day over the endpoint
        print("ranking unavailable, newest first:", str(e)[:200], file=sys.stderr)
        ranks = None
    how = "rules"
    if ranks:
        papers.sort(key=lambda p: -ranks.get(p["pmid"], -1))  # stable: newest first within a tie
        how = f"ranking ({len(ranks)} of {len(papers)} ranked)"
    return choose(cfg, papers), len(papers), how


def check_ranking(cfg):
    """Branch push: does the endpoint answer the runner? Candidates and ranked counts per topic, posts nothing."""
    for n, topic in sorted(cfg["topics"].items()):
        try:
            papers = candidates(cfg, topic, set())
            ranks = rankings(cfg, [p["pmid"] for p in papers])
            print(f"- {topic['name']}: {len(papers)} candidates, " + ("no key" if ranks is None else f"{len(ranks)} ranked"))
        except Exception as e:
            print(f"- {topic['name']}: ERROR {str(e)[:200]}")


def post_id(cfg, day):
    week = day.isocalendar()[1]
    return f"w{week}-{cfg['page']}-{cfg['network']}-{day.isoweekday()}"


def head_text(cfg, topic, day, n):
    link = f"doclert.com/go/{post_id(cfg, day)}"
    text = (
        f"New papers on {topic['name']}, {day.day} {MONTHS[day.month - 1]} {day.year}\n\n"
        f"{COUNT_WORDS[n]} recent papers, one per reply ↓\n\n"
        f"Get new papers on your own topics: {link}"
    )
    return text, [(link, "https://" + link)]


def doi_of(summary):
    for aid in summary.get("articleids", []):
        if aid.get("idtype") == "doi" and re.match(r"10\.\S+$", aid.get("value", "")):
            return aid["value"]
    return None


def paper_link(paper):
    """The paper itself (its DOI) when it has one, else its record page."""
    if paper.get("doi"):
        return f"doi.org/{paper['doi']}"
    return f"pubmed.ncbi.nlm.nih.gov/{paper['pmid']}"


def paper_text(paper, i, n):
    return f"{i}/{n} {paper['title']}\n\n{paper['journal']} · {paper['date']}\n{paper_link(paper)}"


def paper_post(paper, i, n):
    link = paper_link(paper)
    return paper_text(paper, i, n), [(link, "https://" + link)]


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
    papers, count, how = find_papers(cfg, topic, day, blocked)
    print(f"({topic['name']}: chosen by {how})", file=sys.stderr)
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


def login(cfg):
    handle = os.environ.get("BLUESKY_HANDLE") or cfg["handle"]
    password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not password:
        raise RuntimeError("posting needs the BLUESKY_APP_PASSWORD secret")
    body = json.dumps({"identifier": handle, "password": password}).encode()
    return get_json(BSKY + "com.atproto.server.createSession", body, {"Content-Type": "application/json"})


def auth(session):
    return {"Content-Type": "application/json", "Authorization": "Bearer " + session["accessJwt"]}


def setup_profile(cfg):
    """One time, after Matt's OK: the bio and the pinned post of config "profile"."""
    session = login(cfg)
    text = cfg["profile"]["pinned"]
    assert len(text) <= LIMIT and len(cfg["profile"]["bio"]) <= 256
    pinned = bsky_post(session, text, [], None)
    query = urllib.parse.urlencode({"repo": session["did"], "collection": "app.bsky.actor.profile", "rkey": "self"})
    req = urllib.request.Request(BSKY + "com.atproto.repo.getRecord?" + query, headers=auth(session))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            record = json.load(r)["value"]
    except urllib.error.HTTPError:
        record = {"$type": "app.bsky.actor.profile"}
    record["description"] = cfg["profile"]["bio"]  # name, avatar and banner stay as they are
    record["pinnedPost"] = {"uri": pinned["uri"], "cid": pinned["cid"]}
    body = json.dumps({"repo": session["did"], "collection": "app.bsky.actor.profile", "rkey": "self", "record": record}).encode()
    get_json(BSKY + "com.atproto.repo.putRecord", body, auth(session))
    print("bio set, pinned:", pinned["uri"])


def publish(cfg, posts):
    session = login(cfg)
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


def profiles(actors, headers=None, base=APPVIEW):
    out = []
    for k in range(0, len(actors), 25):
        query = urllib.parse.urlencode([("actors", a) for a in actors[k:k + 25]])
        out += get_json(base + "app.bsky.actor.getProfiles?" + query, headers=headers)["profiles"]
    return {p["handle"]: p for p in out}


def follow_matches(cfg, found):
    """Configured handles whose display name has the expected name (keeps impostors and renamed accounts out)."""
    ok, skipped = [], []
    for item in cfg["follow"]["accounts"]:
        p = found.get(item["handle"])
        if p and item["name"].lower() in (p.get("displayName") or "").lower():
            ok.append(p)
        else:
            skipped.append((item["handle"], (p or {}).get("displayName", "not found")))
    return ok[:MAX_FOLLOWS], skipped


def check_follows(cfg):
    found = profiles([a["handle"] for a in cfg["follow"]["accounts"]])
    ok, skipped = follow_matches(cfg, found)
    print(f"## Follows: {len(ok)} would be followed, {len(skipped)} skipped\n")
    for p in ok:
        print(f"- ok {p['handle']} | {p.get('displayName')} | {p.get('followersCount')} followers")
    for handle, name in skipped:
        print(f"- SKIP {handle} | {name}")
    known = set(found)
    print("\n### Search candidates (not in the list)\n")
    for q in cfg["follow"].get("search", []):
        res = get_json(APPVIEW + "app.bsky.actor.searchActors?" + urllib.parse.urlencode({"q": q, "limit": 8}))
        for a in res.get("actors", []):
            if a["handle"] not in known:
                known.add(a["handle"])
                print(f"- [{q}] {a['handle']} | {a.get('displayName')} | {(a.get('description') or '')[:80]!r}")


def follow(cfg):
    session = login(cfg)
    found = profiles([a["handle"] for a in cfg["follow"]["accounts"]], auth(session), BSKY)
    ok, skipped = follow_matches(cfg, found)
    done = 0
    for p in ok:
        if (p.get("viewer") or {}).get("following"):
            continue
        record = {"$type": "app.bsky.graph.follow", "subject": p["did"],
                  "createdAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
        body = json.dumps({"repo": session["did"], "collection": "app.bsky.graph.follow", "record": record}).encode()
        get_json(BSKY + "com.atproto.repo.createRecord", body, auth(session))
        done += 1
        time.sleep(1)
    print(f"followed {done} new, {len(ok) - done} already followed, skipped:", skipped or "none")


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
    print(f"## {day.isoformat()} ({day.strftime('%A')}): {count} candidates, {len(papers)} used\n")
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
    ap.add_argument("--setup-profile", action="store_true", help="one time: set the bio and the pinned post")
    ap.add_argument("--check-login", action="store_true", help="log in with the secret and stop; posts nothing")
    ap.add_argument("--follow", action="store_true", help="follow the accounts of config \"follow\"")
    ap.add_argument("--check-ranking", action="store_true", help="ask the Ranking endpoint for every topic; posts nothing")
    ap.add_argument("--check-follows", action="store_true", help="report what the follow list resolves to; no login")
    args = ap.parse_args()
    with open(os.path.join(HERE, "config.json")) as f:
        cfg = json.load(f)
    mode = args.mode or os.environ.get("PAPERS_MODE_OVERRIDE") or cfg["mode"]
    today = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(dt.timezone.utc).date()
    if args.check_login:
        session = login(cfg)
        print("login ok:", session.get("handle"), "- nothing posted")
        return 0
    if args.setup_profile:
        setup_profile(cfg)
        return 0
    if args.check_ranking:
        check_ranking(cfg)
        return 0
    if args.check_follows:
        check_follows(cfg)
        return 0
    if args.follow:
        follow(cfg)
        return 0
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
    uris = publish(cfg, posts)
    topic = cfg["topics"][str(today.isoweekday())]["name"]
    thread = f"https://bsky.app/profile/{cfg['handle']}/post/{uris[0].rsplit('/', 1)[-1]}"
    state["posts"].append({
        "date": today.isoformat(), "topic": topic, "thread": thread,
        "papers": [{"title": p["title"], "journal": p["journal"], "date": p["date"],
                    "link": "https://" + paper_link(p)} for p in papers],
        "pmids": [p["pmid"] for p in papers], "uris": uris,
    })
    save_state(state)
    print("posted:", *uris, sep="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

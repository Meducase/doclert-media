# bluesky-papers

A daily thread on Doclert's Bluesky account: "New papers on <topic>", then up to three replies, one per paper.
One topic per weekday (`config.json` "topics", 1 = Monday). Papers come from PubMed (NLM E-utilities): the
day's topic in the title, the topic's specialty journals plus a few general ones (`config.json`), records with an abstract,
added in the last 7 days; retractions, errata, comments, letters and editorials left out; one paper per
journal; a paper is not posted again for 60 days.

What a post carries, and nothing more: the title exactly as PubMed gives it, the journal, the date and a
link to the paper (DOI, else the PubMed record). Copy never names PubMed (Matt, 21 Oct 2026); NLM's required
"Courtesy of the U.S. National Library of Medicine" is in the bio and the pinned post. Never an abstract, author names or text written by AI. A title that would
not fit Bluesky's 300 characters is skipped, never shortened. Fewer than two usable papers: no post that day.

Modes (`config.json` "mode"):
- `preview`: renders and prints, posts nothing. A push to any branch other than `main` previews seven days in
  the Actions run summary.
- `live`: the scheduled run (13:00 UTC) posts as "handle", from "start" on, with the secret `BLUESKY_APP_PASSWORD`
  of the environment `production-media` (a Bluesky app password, never the account password). It records what it posted in
  `state/posted.json`.

Once, after Matt's OK: run the workflow by hand with "setup_profile" ticked; it sets the bio and posts and pins
the post of config "profile" (NLM acknowledgement, "not medical advice").
- `off`: stops everything. Changing the mode is one commit.

Follows (config "follow"): journals, scientific societies and medical educators, in English, 30 to 50 accounts.
A branch push reports what each handle resolves to and lists search candidates (public reads, no login). Run the
workflow by hand with "follow" ticked to follow them: only a handle whose display name contains the expected
name, at most 50, never one already followed.

For other posts: `state/posted.json` keeps, per day, the topic, the thread link and each paper's title, journal,
date and link (raw: https://raw.githubusercontent.com/Meducase/doclert-media/main/bluesky-papers/state/posted.json).
Copy built on it follows the same rules: title verbatim, no PubMed name, no authors, no abstract.

Template, topics and wording are approved by Matt (Doclert Marketing). Change them only with his OK.

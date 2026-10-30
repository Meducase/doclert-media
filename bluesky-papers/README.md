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

Doclert Ranking (from 30 Oct 2026, Matt's decision of 29 Oct): with the secret `DOCLERT_RANKING_KEY` (environment
`production-media`; the bot's own key, it opens only `GET /api/stats.php?view=ranking`), the papers are the highest in
the Doclert Ranking among the candidates the rules above give (topic journals plus general ones, topic word in the title,
abstract, English, fits 300 characters, not posted in 60 days; one per journal). The Ranking only orders them; a post never
shows it. Without the key or on any endpoint error the newest candidates come first. (29 Oct preview: the Ranking over a
whole specialty picked regional guidelines from small journals and off-topic papers, so it orders the rules' candidates
instead.) A branch push runs `--check-ranking` and a preview with the Ranking (posts nothing).

Modes (`config.json` "mode"):
- `preview`: renders and prints, posts nothing. A push to any branch other than `main` previews seven days in
  the Actions run summary.
- `live`: the scheduled run (13:07 UTC, retried 13:37 and 14:17; one post a day) posts as "handle", from "start" on, with the secret `BLUESKY_APP_PASSWORD`
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

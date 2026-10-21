# bluesky-papers

A daily thread on Doclert's Bluesky account: "New papers on <topic>", then up to three replies, one per paper.
One topic per weekday (`config.json` "topics", 1 = Monday). Papers come from PubMed (NLM E-utilities): the
day's topic in the title, the topic's specialty journals plus a few general ones (`config.json`), records with an abstract,
added in the last 7 days; retractions, errata, comments, letters and editorials left out; one paper per
journal; a paper is not posted again for 60 days.

What a post carries, and nothing more: the title exactly as PubMed gives it, the journal, the date, the
PubMed link and "Source: PubMed". Never an abstract, author names or text written by AI. A title that would
not fit Bluesky's 300 characters is skipped, never shortened. Fewer than two usable papers: no post that day.

Modes (`config.json` "mode"):
- `preview`: renders and prints, posts nothing. A push to any branch other than `main` previews seven days in
  the Actions run summary.
- `live`: the scheduled run (13:00 UTC) posts, from "start" on, with the repository variable `BLUESKY_HANDLE`
  and the secret `BLUESKY_APP_PASSWORD` (a Bluesky app password, never the account password). It records
  what it posted in `state/posted.json`.
- `off`: stops everything. Changing the mode is one commit.

Template, topics and wording are approved by Matt (Doclert Marketing). Change them only with his OK.

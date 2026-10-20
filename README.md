# doclert-media

Public images for Doclert's social posts. Metricool fetches them through raw links:
`https://raw.githubusercontent.com/Meducase/doclert-media/main/<week>/<file>.png`

Layout: one folder per ISO week, named `w<ISO week>-<year>` (e.g. `w44-2026/`), holding that week's post images as `<post id>.png` (e.g. `w44-meducase-linkedin-1.png`). Files are pushed with git, never edited in place: a changed image gets a new name, so a link in a scheduled post never changes under it. Brand images only; never personal data.

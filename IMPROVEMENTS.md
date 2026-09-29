# Stock Learn Easy IG: improvement log

One improvement per run of `stocklearneasy-ig-improve`. Read before choosing.

## 2026-09-29: the app finally gets named
- **Changed:** every caption now carries one line above the disclaimer ("📲 Want the full lesson? Stock Learn Easy on the App Store, link in bio."), and the reel's closing scene says "Daily lessons in the app. Link in bio." instead of "Follow for one story a day". `generate.py rebuild` now rewrites caption.txt too, so the 5 already-queued slots got the new line.
- **Aimed at:** installs. Before this, no post or reel mentioned the app anywhere; the only path was the bio link (which does point at the App Store, id6761296421).
- **Numbers at the time (7d):** 2 followers, 13 posts, reach 14 total (1 per post), views 44, likes 8, saves 0, shares 0. First reel (29.9 12:00 UTC) published OK: reach 1, views 4 after ~3h.
- **Real bottleneck:** reach, not conversion. Reach of 1 per post means Instagram shows it to almost nobody outside the account. Next runs should target non-follower reach (reel hook / first 2 seconds, reel vs carousel comparison once there are a few reels).

## 2026-09-29 (evening): visual redesign in the app's own brand
- **Changed:** cards and reel frames rebuilt on one shared look (`design.py`), picked from three directions on the design canvas "Stock Learn Easy IG Card Directions" (https://claude.ai/artifact/QrBJ9cWfd2hzq5CHMZHgY3, A. Lesson Card). Fonts are the app's own (DM Serif Display headings, DM Sans text) and load from `assets/fonts/` on disk: before this the Inter @import usually lost the race with the screenshot, so most cards went out in Helvetica. App icon in the header of every card; the numbers in a hook ("10x", "$50", "4-month") in the app's yellow; the lesson set in a light card like the app's lesson list; last slide is "Rule of thumb, save this" plus an app strip with the icon ("The full lesson is in the app"); progress dots instead of "2/4"; reel closes on the icon and "Investing, explained from zero." Chart: dashed line at the starting value, endpoint no longer cut by the edge. A fit script shrinks any unusually long text instead of letting it overflow, and Chrome now waits (`--virtual-time-budget`) for fonts before the shot.
- **Fixed on the way:** the 1.10 18:00 IPO post charted `$ANTW`, an "Anthropic AI Lab Ecosystem ETF", as if it were Anthropic. `lookup_ticker` now skips funds/ETFs/trusts, that slot's ticker was cleared (now 3 slides, no chart), and a chart with less history than its range says "since Aug 13" instead of "past 6 months".
- **Aimed at:** saves (explicit "save this" rule-of-thumb card) and installs (brand continuity from post to App Store page, icon on every card). Also plain quality: a scroller now sees a finance brand, not a template.
- **Numbers at the time:** unchanged from the entry above (reach ~1 per post). All 4 queued slots re-rendered, both reels re-uploaded.

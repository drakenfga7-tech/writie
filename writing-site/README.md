# Your writing site

A simple, fast website for stories and articles. You write in plain text files, run one command, and get a ready-to-host website (home page, article pages, tag pages, an RSS feed, light and dark mode).

## One-time setup

1. Install Python 3 (python.org) if you don't have it.
2. In this folder, run `pip install -r requirements.txt`.
3. Open `site.json` and put in your name, tagline, and short bio.

## Writing

```
python build.py new "My story title"
```

This creates a file in `posts/`. Open it in any text editor and write below the header. Posts use Markdown:

| You type | You get |
| --- | --- |
| `## Heading` | section heading |
| `*word*` / `**word**` | italics / bold |
| `[text](https://...)` | link |
| `> quote` | pull quote |
| `---` on its own line | scene break (shown as * * *) |
| `![description](/static/images/pic.jpg)` | image (put the file in `static/images/`) |

The header at the top of each post:

```
---
title: My story title
date: 2026-11-22
tags: fiction, short stories
description: One sentence that appears in lists and link previews.
draft: true
---
```

Delete the `draft: true` line to publish. A future `date` schedules a post: it appears the first time you build on or after that day. Optional: `image:` (cover image path), `updated:` (a date), `slug:` (custom URL ending).

## Previewing

```
python build.py serve
```

Open http://localhost:8000. Drafts appear with a label, and the page rebuilds each time you save a file.

## Publishing

`python build.py` writes the finished website into the `site/` folder. Upload that folder to any static host. Easy free options:

- **Netlify Drop:** drag the `site` folder onto app.netlify.com/drop.
- **GitHub Pages:** push this project to GitHub. The included workflow in `.github/workflows/` builds and deploys it on every push.
- **Cloudflare Pages:** connect the repo, build command `python build.py`, output folder `site`.

After you know your address, set `"url"` in `site.json` (for example `"https://yourname.com"`), which turns on correct share links and a sitemap. If the site lives in a subfolder (like `https://you.github.io/stories`), also set `"base_path": "/stories"`.

## Customizing

- Colors and fonts: top of `static/style.css`.
- Page layout: `templates/base.html`.
- Menu links and footer links: `site.json`.
- Extra pages (About, Contact, etc.): add `.md` files to `pages/`.
- Remove the two sample posts in `posts/` when you're ready.

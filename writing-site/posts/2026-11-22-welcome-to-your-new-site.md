---
title: Welcome to your new site
date: 2026-11-22
tags: meta, writing
description: A quick tour of how writing and publishing works here. Delete this post when you're ready.
---

This is a sample post. Every post on this site is just a text file in the `posts` folder, and the file you're reading right now is `2026-11-22-welcome-to-your-new-site.md`. Open it next to this page to see how it maps.

## Writing a new post

From the project folder, run:

```
python build.py new "My first story"
```

That creates a file in `posts/` with a small header at the top (title, date, tags, description). Write below the header using plain text. When you're ready to publish, delete the `draft: true` line.

## Formatting you'll actually use

Put `##` before a line to make a section heading. Wrap words in `*asterisks*` for *italics* and `**double asterisks**` for **bold**. Links look like [this](https://example.com).

> A line that starts with a greater-than sign becomes a pull quote.

Three dashes on their own line make a scene break, which is handy for fiction:

---

And pictures go in `static/images`, then you reference them like this: `![A short description](/static/images/my-photo.jpg)`.

## Previewing

Run `python build.py serve` and open <http://localhost:8000>. Drafts show up there with a label, and the page rebuilds every time you save.

When you've read this far, delete this file and write something of your own.

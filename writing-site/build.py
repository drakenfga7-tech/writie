#!/usr/bin/env python3
"""
A tiny static site generator for a personal writing site.

  python build.py              Build the site into the ./site folder
  python build.py serve        Preview at http://localhost:8000 (auto-rebuilds, shows drafts)
  python build.py new "Title"  Create a new draft post in ./posts

Write posts as Markdown files in ./posts. See README.md for details.
"""
import datetime
import email.utils
import functools
import html
import http.server
import json
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from string import Template

try:
    import markdown
except ImportError:
    sys.exit("The 'markdown' package is required. Install it with:  pip install markdown")

ROOT = Path(__file__).parent.resolve()
OUT = ROOT / "site"
esc = html.escape


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "post"


def fmt_date(d):
    return f"{d:%B} {d.day}, {d.year}"


def parse_front_matter(text):
    """Split an optional '--- key: value ---' header from the Markdown body."""
    meta = {}
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip().strip("\"'")
        text = text[m.end():]
    return meta, text


def render_markdown(body):
    return markdown.markdown(
        body,
        extensions=["extra", "smarty", "sane_lists", "toc"],
        output_format="html5",
    )


def plain_text(html_text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", html_text))
    return re.sub(r"\s+", " ", text).strip()


def excerpt(html_text, limit=170):
    first = re.search(r"<p>(.*?)</p>", html_text, re.S)
    text = plain_text(first.group(1) if first else html_text)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def parse_date(value):
    try:
        return datetime.date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def url_to_file(path):
    if path.endswith(".html") or path.endswith(".xml") or path.endswith(".txt"):
        return path.strip("/")
    return (path.strip("/") + "/index.html").lstrip("/")


def write(rel_path, content):
    target = OUT / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------
# Loading config and content
# --------------------------------------------------------------------------
def load_config(preview=False):
    cfg = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    cfg.setdefault("site_name", cfg.get("author", "My Writing"))
    cfg.setdefault("author", cfg["site_name"])
    cfg.setdefault("tagline", "")
    cfg.setdefault("bio", "")
    cfg.setdefault("photo", "")
    cfg.setdefault("links", [])
    cfg.setdefault(
        "nav",
        [
            {"label": "Home", "href": "/"},
            {"label": "Writing", "href": "/blog/"},
            {"label": "About", "href": "/about/"},
        ],
    )
    cfg["url"] = cfg.get("url", "").rstrip("/")
    cfg["base_path"] = cfg.get("base_path", "").rstrip("/")
    if preview:  # local preview always runs at the root
        cfg["url"] = ""
        cfg["base_path"] = ""
    return cfg


def load_posts(preview=False):
    posts = []
    today = datetime.date.today()
    for path in sorted((ROOT / "posts").glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        draft = meta.get("draft", "").lower() in ("true", "yes", "1")
        name_date = re.match(r"(\d{4}-\d{2}-\d{2})-", path.stem)
        stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
        date = (
            parse_date(meta.get("date"))
            or (parse_date(name_date.group(1)) if name_date else None)
            or datetime.date.fromtimestamp(path.stat().st_mtime)
        )
        scheduled = date > today
        if (draft or scheduled) and not preview:
            continue

        body_html = render_markdown(body)
        words = len(re.findall(r"\w+", plain_text(body_html)))
        title = meta.get("title") or stem.replace("-", " ").title()
        slug = slugify(meta.get("slug") or stem)
        posts.append(
            {
                "title": title,
                "slug": slug,
                "date": date,
                "updated": parse_date(meta.get("updated")),
                "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                "description": meta.get("description") or excerpt(body_html),
                "html": body_html,
                "minutes": max(1, round(words / 220)),
                "image": meta.get("image", ""),
                "draft": draft or scheduled,
                "path": f"/{date:%Y}/{date:%m}/{date:%d}/{slug}/",
            }
        )
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    return posts


# --------------------------------------------------------------------------
# HTML building blocks
# --------------------------------------------------------------------------
def tags_html(tags):
    return " ".join(f'<a class="tag" href="/tags/{slugify(t)}/">{esc(t)}</a>' for t in tags)


def post_list_html(posts):
    if not posts:
        return '<p class="muted">Nothing here yet.</p>'
    items = []
    for p in posts:
        badge = ' <span class="badge">Draft</span>' if p["draft"] else ""
        items.append(
            f'<article class="post-item">'
            f'<time datetime="{p["date"]}">{fmt_date(p["date"])}</time>'
            f'<h3><a href="{p["path"]}">{esc(p["title"])}</a>{badge}</h3>'
            f'<p>{esc(p["description"])}</p>'
            f"</article>"
        )
    return "\n".join(items)


class Site:
    def __init__(self, cfg, preview=False):
        self.cfg = cfg
        self.preview = preview
        self.template = Template((ROOT / "templates" / "base.html").read_text(encoding="utf-8"))
        self.has_about = (ROOT / "pages" / "about.md").exists()

    # -- URLs ----------------------------------------------------------------
    def abs_url(self, path):
        return f"{self.cfg['url']}{self.cfg['base_path']}{path}"

    def fix_links(self, s):
        base = self.cfg["base_path"]
        if not base:
            return s
        return re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{base}/', s)

    # -- chrome --------------------------------------------------------------
    def nav_html(self, current):
        out = []
        for item in self.cfg["nav"]:
            href = item["href"]
            active = current == href or (href != "/" and current.startswith(href))
            attr = ' aria-current="page"' if active else ""
            out.append(f'<a href="{esc(href)}"{attr}>{esc(item["label"])}</a>')
        return "".join(out)

    def footer_links(self):
        parts = []
        for link in self.cfg["links"]:
            url = link["url"]
            attrs = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
            parts.append(f'<a href="{esc(url)}"{attrs}>{esc(link["label"])}</a>')
        parts.append('<a href="/feed.xml">RSS</a>')
        return " · ".join(parts)

    def author_card(self):
        cfg = self.cfg
        photo = (
            f'<img src="{esc(cfg["photo"])}" alt="" width="72" height="72">' if cfg["photo"] else ""
        )
        more = '<a href="/about/">Learn more about me →</a>' if self.has_about else ""
        bio = f'<p>{esc(cfg["bio"])}</p>' if cfg["bio"] else ""
        return (
            f'<aside class="author-card">{photo}<div>'
            f'<h3>{esc(cfg["author"])}</h3>{bio}{more}</div></aside>'
        )

    # -- full page -----------------------------------------------------------
    def page(self, path, title, content, description="", og_type="website", image="", nav_path=None):
        cfg = self.cfg
        desc = description or cfg["tagline"]
        full_title = cfg["site_name"] if path == "/" else f"{title} | {cfg['site_name']}"
        head = []
        if cfg["url"]:
            head.append(f'<link rel="canonical" href="{esc(self.abs_url(path))}">')
            head.append(f'<meta property="og:url" content="{esc(self.abs_url(path))}">')
        if image:
            img = image
            if cfg["url"] and image.startswith("/"):
                img = f"{cfg['url']}{cfg['base_path']}{image}"
            head.append(f'<meta property="og:image" content="{esc(img)}">')
        out = self.template.safe_substitute(
            page_title=esc(full_title),
            title=esc(title),
            description=esc(desc),
            og_type=og_type,
            head_extra="\n".join(head),
            site_name=esc(cfg["site_name"]),
            author=esc(cfg["author"]),
            tagline=esc(cfg["tagline"]),
            nav=self.nav_html(nav_path or path),
            content=content,
            footer_links=self.footer_links(),
            year=datetime.date.today().year,
        )
        write(url_to_file(path), self.fix_links(out))

    # -- pages ---------------------------------------------------------------
    def build_home(self, posts):
        cfg = self.cfg
        latest = posts[:5]
        content = (
            f'<section class="hero"><h1>{esc(cfg["author"])}</h1>'
            f'<p class="lede">{esc(cfg["tagline"])}</p></section>'
            f'<section><h2 class="section-title">Latest writing</h2>'
            f"{post_list_html(latest)}"
            f'<p class="more"><a href="/blog/">All writing →</a></p></section>'
        )
        self.page("/", cfg["site_name"], content, cfg["tagline"])

    def build_blog_index(self, posts):
        tag_counts = {}
        for p in posts:
            for t in p["tags"]:
                tag_counts.setdefault(slugify(t), [t, 0])[1] += 1
        chips = " ".join(
            f'<a class="tag" href="/tags/{slug}/">{esc(name)} <span>{n}</span></a>'
            for slug, (name, n) in sorted(tag_counts.items())
        )
        by_year = {}
        for p in posts:
            by_year.setdefault(p["date"].year, []).append(p)
        sections = "".join(
            f'<section><h2 class="year">{year}</h2>{post_list_html(items)}</section>'
            for year, items in sorted(by_year.items(), reverse=True)
        )
        content = (
            f"<h1>Writing</h1>"
            f'{f"<p class=tags>{chips}</p>" if chips else ""}'
            f'{sections or post_list_html([])}'
        )
        self.page("/blog/", "Writing", content, "Everything I've written.")

    def build_tags(self, posts):
        groups = {}
        for p in posts:
            for t in p["tags"]:
                groups.setdefault(slugify(t), (t, []))[1].append(p)
        for slug, (name, items) in groups.items():
            content = (
                f'<p class="crumb"><a href="/blog/">← All writing</a></p>'
                f"<h1>{esc(name)}</h1>{post_list_html(items)}"
            )
            self.page(f"/tags/{slug}/", name, content, f"Posts tagged {name}.", nav_path="/blog/")

    def build_post(self, post, posts):
        bits = [f'<time datetime="{post["date"]}">{fmt_date(post["date"])}</time>']
        if post["updated"] and post["updated"] != post["date"]:
            bits.append(f'Updated {fmt_date(post["updated"])}')
        bits.append(f'{post["minutes"]} min read')
        meta = " • ".join(bits)
        cover = (
            f'<img class="cover" src="{esc(post["image"])}" alt="">' if post["image"] else ""
        )
        badge = '<p><span class="badge">Draft preview, not published</span></p>' if post["draft"] else ""

        others = [p for p in posts if p is not post and not p["draft"]]
        others.sort(
            key=lambda p: (-len(set(p["tags"]) & set(post["tags"])), -p["date"].toordinal())
        )
        related = others[:3]
        related_html = (
            f'<section class="related"><h2 class="section-title">More to read</h2>'
            f"{post_list_html(related)}</section>"
            if related
            else ""
        )
        tags = f'<p class="tags">{tags_html(post["tags"])}</p>' if post["tags"] else ""
        content = (
            f'<article class="post">{badge}<header><h1>{esc(post["title"])}</h1>'
            f'<p class="meta">{meta}</p></header>{cover}'
            f'<div class="prose">{post["html"]}</div>{tags}</article>'
            f"{self.author_card()}{related_html}"
        )
        self.page(
            post["path"],
            post["title"],
            content,
            post["description"],
            og_type="article",
            image=post["image"],
            nav_path="/blog/",
        )

    def build_pages(self):
        for path in sorted((ROOT / "pages").glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            title = meta.get("title") or path.stem.replace("-", " ").title()
            content = (
                f'<article class="page"><h1>{esc(title)}</h1>'
                f'<div class="prose">{render_markdown(body)}</div></article>'
            )
            self.page(f"/{slugify(path.stem)}/", title, content, meta.get("description", ""))

    def build_404(self):
        content = (
            '<h1>Page not found</h1><p>That page doesn\'t exist. '
            '<a href="/">Head back home</a> or browse <a href="/blog/">all writing</a>.</p>'
        )
        self.page("/404.html", "Page not found", content)

    # -- feed, sitemap -------------------------------------------------------
    def build_feed(self, posts):
        cfg = self.cfg
        base = f"{cfg['url']}{cfg['base_path']}"
        absolutize = lambda s: re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{base}/', s)
        items = []
        for p in [p for p in posts if not p["draft"]][:20]:
            when = datetime.datetime.combine(p["date"], datetime.time(12, 0), datetime.timezone.utc)
            full = absolutize(p["html"]).replace("]]>", "]]]]><![CDATA[>")
            items.append(
                "<item>"
                f"<title>{esc(p['title'])}</title>"
                f"<link>{esc(base + p['path'])}</link>"
                f"<guid isPermaLink=\"true\">{esc(base + p['path'])}</guid>"
                f"<pubDate>{email.utils.format_datetime(when)}</pubDate>"
                f"<description>{esc(p['description'])}</description>"
                f"<content:encoded><![CDATA[{full}]]></content:encoded>"
                "</item>"
            )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            f"<channel><title>{esc(cfg['site_name'])}</title>"
            f"<link>{esc(base or '/')}</link>"
            f"<description>{esc(cfg['tagline'])}</description>"
            + "".join(items)
            + "</channel></rss>"
        )
        write("feed.xml", xml)

    def build_sitemap(self, posts):
        if not self.cfg["url"]:
            return
        urls = ["/", "/blog/"] + [f"/{slugify(p.stem)}/" for p in (ROOT / "pages").glob("*.md")]
        urls += [p["path"] for p in posts if not p["draft"]]
        body = "".join(f"<url><loc>{esc(self.abs_url(u))}</loc></url>" for u in urls)
        write(
            "sitemap.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
        )
        write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {self.abs_url('/sitemap.xml')}\n")


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def build(preview=False):
    cfg = load_config(preview)
    posts = load_posts(preview)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    site = Site(cfg, preview)
    site.build_home(posts)
    site.build_blog_index(posts)
    site.build_tags(posts)
    for post in posts:
        site.build_post(post, posts)
    site.build_pages()
    site.build_404()
    site.build_feed(posts)
    site.build_sitemap(posts)

    if (ROOT / "static").exists():
        shutil.copytree(ROOT / "static", OUT / "static")
    for extra in ("CNAME", "favicon.ico"):
        if (ROOT / extra).exists():
            shutil.copy(ROOT / extra, OUT / extra)
    write(".nojekyll", "")

    published = [p for p in posts if not p["draft"]]
    drafts = len(posts) - len(published)
    note = f" (+{drafts} draft{'s' if drafts != 1 else ''} in preview)" if drafts and preview else ""
    print(f"Built {len(published)} post(s){note} → {OUT.relative_to(ROOT)}/")


def new_post(title):
    today = datetime.date.today()
    path = ROOT / "posts" / f"{today.isoformat()}-{slugify(title)}.md"
    if path.exists():
        sys.exit(f"{path.name} already exists.")
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\ndate: {today.isoformat()}\ntags: \ndescription: \ndraft: true\n---\n\n"
        "Start writing here.\n",
        encoding="utf-8",
    )
    print(f"Created posts/{path.name}")
    print("It's marked 'draft: true' so it won't be published. Delete that line when it's ready.")


def serve(port=8000):
    build(preview=True)

    def snapshot():
        files = [ROOT / "site.json"]
        for folder in ("posts", "pages", "templates", "static"):
            files += [p for p in (ROOT / folder).rglob("*") if p.is_file()]
        return {str(p): p.stat().st_mtime for p in files if p.exists()}

    def watch():
        last = snapshot()
        while True:
            time.sleep(1)
            now = snapshot()
            if now != last:
                last = now
                try:
                    build(preview=True)
                except Exception as exc:  # keep serving even if a post has a typo
                    print("Build error:", exc)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    threading.Thread(target=watch, daemon=True).start()
    handler = functools.partial(Quiet, directory=str(OUT))
    with http.server.ThreadingHTTPServer(("", port), handler) as httpd:
        print(f"Previewing at http://localhost:{port}  (Ctrl+C to stop)")
        print("Drafts are visible in preview. Saving a file rebuilds the site.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "serve":
        serve()
    elif cmd == "new" and len(argv) > 2:
        new_post(" ".join(argv[2:]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)

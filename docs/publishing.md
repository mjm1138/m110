# Publishing your collection

**Library → Publish / share…** turns your collection into a static website — either
into a **local folder** you host however you like, or deployed **straight to GitHub
Pages** with one click.

## What goes on the site

The dialog's **Include** checkboxes pick the pages: the full catalog table, the
Summary dashboard, the session log, the processing queue, journal notes, and image
galleries. Two privacy controls sit alongside:

- **Exclude all journal notes** hides every journal from the site; adding
  `private: true` to one object's `journal.md` frontmatter hides just that one.
- Right-click an object in the Library → **Exclude from publishing** keeps the whole
  object (page, row, images) off the site.

**Galleries** carry, by your choice:

| Level | What's published |
|---|---|
| **Finished images only** *(default)* | Images in each object's *Finished* group — your deliberate deliverables. |
| **Finished + device stacks** | Also the telescope's in-app stacks (Seestar/Dwarf). |
| **All images** | Everything, including Siril stacks and working files. Expect a much larger site and slower uploads. |

An image you've right-clicked → *Mark as finished* publishes at every level; one
marked *working* only under "All images".

Re-publishing always mirrors your current choices — images and pages that no longer
qualify are removed from the output folder (and therefore from the deployed site),
not left behind.

**Save** stores your choices without publishing anything; **Publish** runs the
export (and deploy, if selected) behind a cancellable progress dialog.

## Deploying to GitHub Pages

GitHub Pages is free static hosting attached to a GitHub repository. M110 pushes
your rendered site to the repo's `gh-pages` branch using the `git` already on your
machine — your existing GitHub authentication is used; M110 never sees a password
or token.

**One-time setup:**

1. **Have git + a GitHub account with SSH access.** Test with
   `ssh -T git@github.com` in a terminal — a greeting means you're set. (If not,
   GitHub's guide: *Settings → SSH and GPG keys → New SSH key*.)
2. **Create a repository** for the site (e.g. `you/astro-site`). Public repos get
   Pages on every plan; note the *site* is always publicly viewable either way.
3. In the Publish dialog, check **GitHub Pages** and enter the repository as
   `owner/repo` (or paste a full git URL). Click **Publish**.
4. **First time only:** on GitHub, open the repo's **Settings → Pages** and set the
   source to **deploy from the `gh-pages` branch**.

Your site serves at **`https://<owner>.github.io/<repo>/`** (the success dialog
shows the exact URL with an **Open site** button). The first deploy — and each
update — can take a minute or two to appear.

**Good to know:**

- Each publish **replaces** the `gh-pages` branch entirely (a single fresh commit),
  so the repo stays small no matter how often you publish. Don't point M110 at a
  branch you keep other work on.
- Uploads happen over your internet connection — a first full-site push takes as
  long as it takes; the progress dialog shows upload progress and **Cancel** stops
  it cleanly.
- If the push is rejected, the error dialog shows git's own message — usually an
  authentication or repo-name problem.

Next: **[On the roadmap →](upcoming.md)**

# M110 — Data Model

Canonical, human-readable description of M110's data: the entities in the
application, the files on disk, how each is derived, whether it's mutable, and how
long it lives. The goal is a model that is **scalable, logical, resource-efficient,
extensible, and discoverable** — so future use cases (multi-catalog goals, session
planning, multi-telescope ingest, an in-app assistant) come online without forced,
error-prone migrations.

> **This document is canonical.** Any change to the data model — on-disk layout,
> file formats, derived-JSON shapes, or the store version — **must** be recorded
> here. On-disk changes additionally bump `.store_version` and add a step in
> `migrate.py` (see [Versioning & migration](#versioning--migration)). See also
> [`ROADMAP.md`](ROADMAP.md) (where the model is headed) and [`BUGS.md`](BUGS.md)
> (open data items, e.g. #14/#16).

---

## Principles & invariants

These hold today and constrain every future change:

1. **Two visible content axes, kept distinct.** `Objects/` is the **catalog-object**
   axis (one folder per catalog object). `Images/` is the **capture-target** axis
   (one folder per thing the telescope was pointed at). They are separate because
   object ↔ target is **many-to-many**: one `M81 M82` capture feeds two catalog
   objects, and one object can be captured under several target folders.
2. **All machine state is hidden and disposable-by-design.** Everything the app
   generates or manages internally lives under the single hidden
   `.m110_internal_data/`. The user's irreplaceable data (images, notes) lives in
   the visible axes.
3. **Derived data is always regenerable** from content + authored files. Deleting
   anything under `derived/` or `renders/`, or `sessions.jsonl`, is safe — a
   Refresh rebuilds it. Nothing of value exists *only* in the derived layer.
4. **The content tree is written only via gated, confirm-first operations.**
   `ingest.apply_ops` and `siril.apply_import` are the only writers into `Images/`,
   and only after explicit user confirmation. Raws are never modified in place.
5. **Discoverability.** A human browsing the store on disk can find things from
   folder names alone — object ids, target names, and tier folders
   (`lights/`, `stacks/`, `finished/`, …) are self-describing.
6. **Engine stays Qt-free.** The data model is owned by the headless engine
   (`m110/*.py`); the UI only reads it. Path resolution is centralized in
   `config.py`.

---

## Entity hierarchy

```
Goal / List  (Messier, Caldwell, …)        ── many-to-many ──┐
   └─ membership of →                                        │
Catalog Object  (intrinsic: id, name, type, mag, size, coords, season, filter-rule)
   ├─ has one  Journal   (Objects/<id>/journal.md)
   └─ captured under ≥1 →                          ── many-to-many ──┘
Capture Target  (Images/<target>/ — what the scope pointed at; → ≥1 Object)
   └─ [Device]   (future path level: Images/<target>/<device>/ — the telescope)
        └─ Session   (one night for a target/device — derived from frame headers)
             └─ Frame   (one sub: light/dark/flat/bias; atomic, immutable;
                         FITS header OBJECT/IMAGETYP/FILTER/RA/DEC/EXP/DATE)
        └─ Stack   (device stack · Siril stack · finished render — derived images)
             └─ Render   (thumbnail / hero — a derivative of a stack or frame)
```

**Attribute / derivation flow** (how facts roll up):

```
Frame headers → Session rollup → Target rollup (totals.by_folder)
            → Object rollup (totals.by_slug, via the target↔object map)
            → Goal/List progress (by membership) → Summary (by category)
```

A Catalog Object is the source of truth for *intrinsic* facts. A Capture Target
holds the *observed* data. Rollups are derived, never authored.

---

## Store layout

Default root `~/Documents/M110` (override: `M110_DATA_ROOT` env → saved preference
→ default). Resolved in `config.py`; per-target paths come from
`config.{target,lights,stacks,seestar_stacks,finished,siril}_dir(name)`.

```
<data_root>/
  Objects/<catalog id>/             catalog-object axis (slug→id, e.g. Objects/M101/)
    journal.md                      frontmatter (name/hero_caption/hero) + Markdown body
  Images/<target>/                  capture-target axis (e.g. Images/"M81 M82"/)
    lights/                         raw light subs (.fit)                 [immutable]
    stacks/                         Siril stacks (.fit/.tif)              [output]
    seestar-stacks/                 device in-app stacks (+ preview .jpg) [output]
    finished/                       hand-finished renders                 [output]
    working_files/                  processing by-products (starless/crop/…) [output]
    siril/                          contained processing-prep sandbox:
      lights/ (hardlinks) · process/ (scratch) · presets/ · next-steps.md
      archive/<ts>/ (past runs)
    (darks/ flats/ biases/ — calibration; preserved if present, and **import targets**
                            for frames header-routed by IMAGETYP (ROADMAP item 6b);
                            written by ingest, layout unchanged → no .store_version bump)
  Media/<Category>_photo|_video/    lunar/planetary/scenery media
  Inbox/                            holding area / import queue (transient): unclassifiable
                                    files (`ingest.scan_holding`) await **manual assign**
                                    (`ingest.assign` → move into the content tree, 6c);
                                    no longer a user-facing import *source*
  .m110_internal_data/              hidden machine state (README: "don't touch")
    library.toml                    the user's Library = captured/annotated collection {slug:{id,name,type,…}} (starts empty)
    goals.toml                      per-store goals: active = [...] (default ["messier"]) + [[custom]] lists
    priorities.toml                 priority targets ([[priority]]; optional track=false)
    processing_overrides.toml       per-folder status overrides ([folder.<name>])
    ingest_aliases.toml             source-name → canonical-target aliases
    sessions.jsonl                  one capture session per line (generated)
    journal_template.md             reference journal format (stubs generated from it)
    derived/                        generated rollups: totals/summary/processing/
                                    priorities/images.json
    renders/                        generated thumbnails + hero/<slug>.jpg
    .store_version                  layout version stamp (= 3)
```

App-bundled **reference data** (ships in the package, not in the store):
`m110/seed/objects.toml` (object **reference** dataset incl. J2000 coords),
`m110/seed/priorities.toml`, `m110/seed/catalogs/*.toml` (bundled catalog membership lists),
`m110/guidance/*.md` (workflow playbooks).

---

## Data catalog

Lifecycle classes: **Authored** (user-owned, mutable) · **Content** (precious;
raws immutable) · **Derived** (regenerable, disposable) · **Reference**
(app-bundled, read-only).

| Entity / file | Location | Format | Derived / discovered | Mutability (enforcement) | Persistence | Retention / cleanup |
|---|---|---|---|---|---|---|
| Library | `.m110_internal_data/library.toml` | TOML | The user's **captured/annotated collection** (5d) — **starts empty**; grows by capture (`catalog.add_captured_objects`: known objects pull full reference metadata, off-catalog ones get a minimal entry + Simbad coords), the Add-object flow, or annotation. Uncaptured catalog members live in Goals, not here. Per-entry optional **`publish`** flag (item 8a): absent/`true` = published, `false` = excluded from the published site (`catalog.set_publish_flag`, default-publish opt-out) | **Mutable** — user-editable; app appends additively, never overwrites (convention); `remove_library_entry` / goal-deselect prune; `set_publish_flag` in-place rewrite | Persistent | Never auto-deleted |
| Object reference | `m110/seed/objects.toml` | TOML | Shipped with the app | **Reference** (read-only) | Persistent (in package) | n/a |
| Catalog lists | `m110/seed/catalogs/*.toml` | TOML | Shipped with the app: Messier, Caldwell, RASC Finest NGC, Best of Sharpless, Bennett, Lacaille (gen by `tools/gen_caldwell.py` + `tools/gen_catalogs.py`) | **Reference** (read-only) | Persistent (in package) | n/a |
| Goals | `.m110_internal_data/goals.toml` | TOML | The catalogs/lists this store is pursuing: `active = [...]` (bundled catalog ids + custom goal ids; default `["messier"]`) plus `[[custom]]` blocks (`id`, `name`, `members = [slugs]`); **per-store** | **Mutable** — app-written (`goals.set_active_goals` / `create_custom_goal` / `edit_custom_goal` / `delete_custom_goal`); reconstructible | Persistent | Never auto-deleted |
| Priorities | `.m110_internal_data/priorities.toml` | TOML (`[[priority]]`) | Hand-authored; joined with totals in `build_derived` | **Mutable** — user-owned | Persistent | Never auto-deleted |
| Journal | `Objects/<id>/journal.md` | Markdown + YAML-ish frontmatter | Stub generated per catalog object from `journal_template.md`; body authored by user. Optional **`private: true`** frontmatter key (item 8a) keeps this object's notes out of the published site | **Mutable** — user-owned; app upserts only frontmatter keys (`objects.set_frontmatter_key`, e.g. hero) | Persistent | Never auto-deleted |
| Published site | external (user-chosen folder, e.g. `~/Documents/M110 Site`) | static HTML/CSS/JS + image derivatives | Generated by `publish.run_publish` (item 8a) from derived JSON + `build_images` + journals; **outside the data store** (not under `<data_root>`, no `.store_version` impact) | **Output artifact** — fully regenerated each publish; user/host owns it | Transient (re-rendered) | User-managed |
| Processing overrides | `.m110_internal_data/processing_overrides.toml` | TOML (`[folder.<name>]`) | Authored (e.g. dismiss a folder) | **Mutable** — user-owned | Persistent | Never auto-deleted |
| Ingest aliases | `.m110_internal_data/ingest_aliases.toml` | TOML (`[alias]`) | Written by the ingest "remember" action (`ingest.add_alias`) | **Mutable** — app-written, user-editable | Persistent | Never auto-deleted |
| Light frames | `Images/<target>/lights/*.fit` | FITS | Ingested from device/staging (`ingest.apply_ops`) | **Immutable** — engine never writes into `lights/`; ingest writes bytes-only to `.part` then atomic `os.replace` (convention) | Persistent | Never auto-deleted |
| Calibration frames | `Images/<target>/{darks,flats,biases}/` | FITS | Preserved if present | **Immutable** (convention) | Persistent | Never auto-deleted |
| Siril stacks | `Images/<target>/stacks/` | FITS/TIFF | Imported from the siril sandbox (`siril.apply_import`) | **Output** — replaceable by re-import | Persistent | Never auto-deleted |
| Seestar stacks | `Images/<target>/seestar-stacks/` | FITS (+ preview .jpg) | Ingested from device | **Output** | Persistent | Never auto-deleted |
| Finished renders | `Images/<target>/finished/` | PNG/JPG/TIFF/FITS | Imported from the siril sandbox | **Output** — user's deliverables | Persistent | Never auto-deleted |
| Working files | `Images/<target>/working_files/` | FITS (mostly) | Diverted here on import when a `.fit` in a lights source reads as a processing by-product, not a raw sub (`config.is_light_frame`/`is_processing_product`); `ingest.plan_lights_cleanup` relocates already-mis-filed ones | **Output** — kept, not raw | Persistent | Never auto-deleted | Keeps `lights/` sub-only (raw-integrity + correct filter detection) and `finished/` for final renders only |
| Siril sandbox | `Images/<target>/siril/` | mixed | `siril.plan/apply_prep` (auto on ingest; missing-only backfill on refresh) | **Working area** — app-managed; `lights/` are hardlinks (no extra space) | Persistent (ready for re-runs) | `archive/<ts>/` accumulates; **never auto-deleted** (see Retention) |
| Media | `Media/<Category>_photo\|_video/` | images/video | Ingested (`*_photo`/`*_video`) | **Content** | Persistent | Never auto-deleted |
| Sessions index | `.m110_internal_data/sessions.jsonl` | JSONL (1 session/line) | `scan_sessions.scan()` over `lights/` FITS headers | **Derived** | Regenerable | Safe to delete; rebuilt on Refresh |
| Rollups | `.m110_internal_data/derived/*.json` | JSON | `build_derived` (totals/summary/processing/priorities), `build_images` (images) | **Derived** | Regenerable | Safe to delete; rebuilt on Refresh (`processing.json` stamps `generated_at` and is intentionally not byte-stable) |
| Renders cache | `.m110_internal_data/renders/` | JPG/PNG | `build_images` (content-hash cached: mtime+size+ver) | **Derived** | Regenerable | Safe to delete; **orphans should be pruned** (open #14) |
| Store version | `.m110_internal_data/.store_version` | text (`3`) | Written by `migrate.py`/bootstrap | **App-managed** | Persistent | Bumped on layout change |
| Bundled catalog/priorities/coords | `m110/seed/` | TOML/CSV | Shipped with the app | **Reference** (read-only) | Persistent (in package) | n/a |
| Guidance playbooks | `m110/guidance/*.md` | Markdown | Shipped with the app | **Reference** (read-only) | Persistent (in package) | n/a |

**Status vocabularies** (computed, not stored): capture status `initial` /
`deep_stack` (by integration; `totals`); processing status `not_processed` /
`out_of_date` / `up_to_date` / `dismissed` (`processing`). Summary categories come
from the catalog object `type`.

**Processing freshness & rejection are judged by capture date, not file mtime.**
`build_processing` compares each session's **capture date** (from the FITS header,
via `scan_sessions`) against the latest stack's FITS **`DATE`**: frames shot after
the stack are the unintegrated backlog → `out_of_date`; a stack that already covers
everything captured → `up_to_date`. Rejection% (`stack_meta.stack_rejection_pct`) is
`1 − STACKCNT / frames_at_stack`, where `frames_at_stack` (also emitted in
`stack_meta`) is the frames **present when the stack was made** — *not* the running
capture total (which would miscount later frames as "rejected"). This is robust to a
bulk import flattening file mtimes (e.g. the Astronomy port). When no stack `DATE` is
available (finished-render-only, or a header lacking `DATE`), it falls back to the
newest-light-vs-newest-processed mtime comparison.

---

## Mutability & enforcement policy

Today enforcement is **by convention + in-app handling**, not filesystem
permissions — this keeps the store cross-platform and friction-free, and the engine
is the only writer:

- The engine **never writes into `lights/`** (or other raw tiers). Ingest copies
  **bytes only** to a `.part` temp then `os.replace()` (atomic; no partial files;
  also avoids the EPERM `copystat` issue over SMB).
- Catalog/journal writes are **additive/upsert** and never clobber user edits.
- The content tree is mutated only by the two gated writers (ingest, import).

**Optional future hardening** (not implemented; the model permits it): mark
`lights/` read-only at the filesystem level; maintain a checksum manifest of raws
for integrity verification.

## Retention / lifecycle

- **Raws, stacks, finished, media** — persistent; **never auto-deleted**.
- **Siril sandbox** — `lights/` are hardlinks (free); after an import the run's
  intermediates move into `siril/[<FILTER>/]archive/<ts>/` and the sandbox is left
  ready for the next run. `archive/` is **retained by default** ("never delete").
  Any future pruning (keep-N-latest / age-based) must be **user-gated and explicit**
  — never automatic.
- **Renders cache** — pure cache; orphaned derivatives (from reprocessed sources
  with new content hashes) are safe to remove. Automatic orphan-pruning is the
  first concrete retention task (open **#14**).
- **Derived JSON + `sessions.jsonl`** — regenerable; safe to delete anytime
  (rebuilt on Refresh).

## Backup

`m110/backup.py` (ROADMAP item 10) writes the store to a user-chosen destination
**outside** `<data_root>` as **hardlinked dated snapshots** —
`<dest>/M110-Backups/<store-name>/<timestamp>/` mirrors the store, with files
unchanged since the previous snapshot hardlinked to it (immutable raws cost nothing
to keep across snapshots). Scope is a **denylist** aligned with the lifecycle classes
above: everything is backed up **except** the regenerable Derived tier (`derived/`,
`renders/`, `sessions.jsonl`) and the `Images/<target>/siril/` working sandboxes.
Each snapshot has a `.m110-backup-manifest.json` (per-file `{size, mtime, sha256}` +
metadata) enabling integrity/bit-rot **verify**. Restore extracts selected paths to a
folder (default) or back into the store behind a conflict preview + confirm.
Retention prunes whole oldest snapshots (keep-N / age / min-free), **explicit, never
the last one** — consistent with the "user-gated, never automatic" rule above. Backup
is an **external output** (like the published site): it reads the store and does not
change its on-disk layout, so it has **no `.store_version` impact**. This partially
realizes the "checksum manifest of raws for integrity verification" noted under
*Optional future hardening*.

## Versioning & migration

`.store_version` (currently **3**) stamps the on-disk layout. (v2→v3 renamed the per-store `catalog.toml` → `library.toml`.)
`config.ensure_data_root()` runs `migrate.migrate_store()` on launch. Migrations
are **idempotent, version-stamped, same-filesystem renames, resume-safe, and never
destructive**. **Rule:** any change to the on-disk layout or file formats bumps the
version and adds a migration step that brings older stores forward in place.

---

## Data flow

> The **Import** path below is largely shipped (ROADMAP 6a–6c / BUGS #16): point at any
> directory, recurse, classify by FITS header + layout registry, copy in, and route
> unclassifiable files to the `Inbox/` holding area for manual assign. Still open: 6d
> (lazy device-under-target). `ingest.apply_ops` remains the single gated writer.

```mermaid
flowchart TD
    subgraph sources[Sources]
        DEV[Any directory: device mount / other scope / arbitrary tree]
    end
    DEV -->|Import: recurse + classify<br/>copy, confirm-first| IMG
    DEV -.->|unclassified| INBOX[Inbox/ — holding area]
    INBOX -.->|manual assign<br/>move, confirm-first| IMG

    subgraph content[Content axis: Images/&lt;target&gt;/]
        IMG[lights/ · seestar-stacks/ · stacks/ · finished/]
        SANDBOX[siril/ sandbox<br/>lights hardlinks · presets · archive]
    end

    subgraph authored[Authored / .m110_internal_data]
        CAT[library.toml]
        PRI[priorities.toml]
        OVR[processing_overrides.toml]
    end
    JOURNAL[Objects/&lt;id&gt;/journal.md]

    IMG -->|scan_sessions| SESS[sessions.jsonl]
    SESS --> BD[build_derived]
    CAT --> BD
    PRI --> BD
    OVR --> BD
    BD --> DERIVED[derived/*.json<br/>totals·summary·processing·priorities]

    IMG -->|build_images<br/>content-hash cache| RENDERS[renders/ + images.json]

    DERIVED --> UI[PySide6 UI]
    RENDERS --> UI
    JOURNAL --> UI
    CAT --> UI

    %% siril round-trip
    IMG -->|plan/apply_prep<br/>auto on ingest| SANDBOX
    SANDBOX -->|user runs Siril| SANDBOX
    SANDBOX -->|apply_import<br/>confirm-first| IMG

    %% future SQLite index seam
    BD -.optional later.-> SQLITE[(SQLite index)]
    SQLITE -.-> UI
```

> **Viewing the diagram (macOS, free/OSS):** the embedded Mermaid renders directly
> on GitHub. Locally, the simplest is **VS Code + the "Markdown Preview Mermaid
> Support" extension** (open the Markdown preview). Zero-install: paste the block
> into the **Mermaid Live Editor** (mermaid.live). To export an image, use
> **mermaid-cli** (`@mermaid-js/mermaid-cli`): `mmdc -i DATA_MODEL.md -o flow.svg`.
> **MarkText** (free, OSS editor) also renders Mermaid natively.

---

## Future directions (designed for, not yet built)

The model is shaped to accommodate the next ROADMAP phases **without a disruptive
migration**. These are intentionally *not* implemented yet; this section records
the chosen direction so future work builds to it.

### Library, catalogs & goals (ROADMAP item 5)
Four concepts:
- **Object** — intrinsic reference facts (coords, type, mag, size). Season is
  **derived** from coords + site, not stored.
- **Catalog / List** — a curated, named, **app-bundled, immutable** reference set
  (Messier, Caldwell, …). *Reference data* (ships with the app), not user state.
- **Goal** — a catalog the user is actively pursuing (progress + dashboard).
- **Library** — the user's mutable **captured/annotated collection** (5d): objects
  they've captured, added, or annotated. Uncaptured catalog members are **not**
  here — they live in the Goals view as a checklist. Objects ↔ catalogs are
  many-to-many (membership).

**Phase 5a (done):** the per-store object set is now the **Library**
(`library.toml`; the v2→v3 migration renamed `catalog.toml`), and the bundled data
is split into an **object reference dataset** (`seed/objects.toml`, id →
coords/type/mag/size) + **catalog membership lists**. `catalog.load_library()` /
`load_reference()` / `load_bundled_catalog()`.

**Phase 5b (done):** **Goals** = active bundled catalogs stored **per-store** in
`.m110_internal_data/goals.toml` (`active = [...]`, default `["messier"]`;
`goals.py`). Per-store (not the old global `active_goals` setting) so each data
store tracks its own goals and a fresh store genuinely starts Messier-only.
Membership lists are `seed/catalogs/<id>.toml` with a `[members]` table
`slug = "<designation>"`. **Caldwell** is bundled (109 objects appended to the
reference + `caldwell.toml`; generated by `tools/gen_caldwell.py` via Simbad —
`astroquery` is a *build-time* dep, runtime stays offline). `build_derived.build_goals`
→ `derived/goals.json` (per-goal total/captured/deep/percent + `in_progress`).
Object detail shows a **Catalogs** membership line; Summary shows per-goal progress.
The Library has a **catalog-filter** view (narrows the collection to a catalog's
members), a **"Captured only"** filter, and shows **all identifiers** per object
(display-only: intrinsic id + catalog designations, ordered by a catalog hierarchy
— no stored change). *(Note: 5b's interim bulk-seed — activating a goal adding all
its members to the Library — was retired in 5d; see below.)*

**Reference backfill (Fill missing metadata):** a Library entry can lag the bundled
reference — e.g. a captured-but-uncatalogued object promoted by `add_captured_objects`
as a minimal stub (`name=""`, `type="unknown"`) *before* its catalog was bundled. Every
add path is append-only and never overwrites, so the stub persists. `catalog.fill_missing_metadata(slug)`
/ `fill_all_missing_metadata()` backfill **only the missing** structured fields from the
reference (and derive `season` from coords via `season_from_ra`), never touching a real
user value, via `_write_library` (an in-place rewriter that preserves every key). Surfaced
as the Library right-click action + the **Library → Fill missing metadata** menu. The
bundled reference now ships a `season` for every Caldwell member too (derived from RA in
`tools/gen_caldwell.py`), so fresh seeding + fills get it.

**Add arbitrary object + online enrich (5c):** the Library also grows on demand —
`catalog.resolve_new_object(identifier)` resolves a typed name/designation through a
cascade **bundled reference → online Simbad → coords-only** (season always derived),
previews it, and `add_library_entry` commits a new `[catalog.<slug>]` + journal stub
(refuses duplicates). The same online tier fills gaps the bundled reference *can't*
(e.g. the Veil's mag/size) for existing entries — `fill_missing_metadata(slug,
online=True)` (right-click "Enrich online") and `enrich_online(slugs)` (Library →
Enrich online, batched). Online is **opt-in** (an explicit action, never automatic) and
rides the **optional `astroquery` dependency**; without it (or offline) the action raises
`OnlineLookupError` and the UI explains, while everything offline keeps working. Object
type comes from a Simbad-otype → vocabulary map (`_simbad_type`).

**Library-=-collection reframe + Goals view (5d, done):** the Library is now the
**captured/annotated collection** (the user's actual corpus). A fresh `library.toml`
is **empty**; it grows only by capture, the Add-object flow, or annotation —
**uncaptured catalog members live in the dedicated Goals nav page** as a membership
checklist, computed on the fly. Consequences:
- **No bulk seed.** Activating a goal no longer copies its members into the Library
  (`goals.set_active_goals` just persists the active set). The launch-time
  reconcile (`ensure_library_has_active_goals`) and the `_seed_library` goal-seed
  were removed.
- **Goal de-select removal** — deactivating a goal (or deleting a custom goal)
  prunes its members that are **uncaptured AND un-noted AND not in another active
  goal** (`catalog.remove_goal_members_from_library`; "noted" = `objects.has_notes`,
  "captured" = present in `derived` totals). Captured/annotated objects always stay.
- **Manual removal** — `catalog.remove_library_entry(slug)` (Library right-click
  "Remove from Library"); non-destructive (keeps `Objects/<id>/`).
- **Custom goals** — a goal can be a user-defined `[[custom]]` list of arbitrary
  slugs (`goals.create_custom_goal` / `edit_custom_goal` / `delete_custom_goal`),
  not just a bundled catalog. `goals.goal_members` / `goal_name` / `list_goals`
  unify bundled + custom.
- **Capture pulls reference metadata** — `add_captured_objects` now fills a known
  catalog object's entry from the bundled reference (full type/mag/size/coords),
  falling back to the minimal-stub + Simbad path only for off-catalog targets.
- Goal management moved **fully to the Goals page** (removed from Preferences).
- Annotated-but-uncaptured targets stay in the **Library** (the settled lean).

### Import & multi-source / multi-telescope (BUGS #16, ROADMAP item 6)
- **Import (was "ingest")** points at **any directory** (device mount, another scope's
  export, an arbitrary tree), recurses, classifies by **FITS header**
  (`OBJECT`/`IMAGETYP`/`FILTER`/`RA`/`DEC`) over folder names, and **copies** into the
  content tree (originals untouched, filenames preserved; collisions resolved
  content-aware — checksum/header → duplicate-skip vs. distinct-suffix). Unclassifiable
  files land in the `Inbox/` **holding area** for manual assign. `Inbox/` is no longer a
  user-facing *source*. A **layout-recognizer registry** + a **device registry** mirror
  the processing-workflow registry. (Specced 2026-06-26; phased 6a–6d.)
- **Source differentiation = lazy device-under-target.** Decided approach for "how
  lights from different sources land in the store so they can be differentiated": keep
  recording source/device as **session metadata** now, and only introduce a **device
  path level under the target** — `Images/<target>/<device>/{lights,stacks,
  seestar-stacks,finished,siril}/` — when a **2nd device actually appears**.
- Today's flat `Images/<target>/…` = an implicit **default device** (the Seestar
  S50); migration is **lazy/optional** and the absence of a device level means the
  default device. Introducing the `<device>/` level is the change that bumps
  `.store_version` + adds a `migrate.py` step (item 6d) — not done until needed.
- The `<device>` id is a **device-profile key** (links to the planning profiles
  below, `planning_config.load_device`). Classification leans on FITS headers, not
  just folder names.

### Session planning & plan files (ROADMAP items 1–2)
- **Profiles** *(landed — site profile + planning engine)* — observing **site**,
  **equipment/device**, and **horizon mask** (`.hrz`) are authored config under
  `.m110_internal_data/profiles/`. One **site** profile = one shooting location
  (home vs. a dark-site trip), each with its own horizon + glow; a `default.toml`
  is seeded on first launch (idempotent, never overwritten — like the README /
  journal template). The site profile also carries **light-pollution** data: a
  Bortle/SQM scalar (site class) + a **glow mask** — an azimuth-dependent quality
  floor layered over the physical horizon (effective floor =
  `max(physical_obstruction, glow_floor)`, `m110/horizon.effective_floor`),
  filter-aware (narrowband/LP punches through, so a softer floor). The engine
  (`m110/planning.py` over `planning_config.py` + `horizon.py`) reads it for the
  twilight / transit / seasonal **observability gate** the auto-prioritizer
  consumes. Profile TOML shape:

  ```toml
  [site]
  name = "Home"
  latitude_deg = 40.015        # +N
  longitude_deg = -105.270     # +E
  elevation_m = 1655
  timezone = "America/Denver"  # IANA; DST derived per-date
  [horizon]
  mask = "default.hrz"         # physical skyline (.hrz/.csv); "" = open
  default = true               # one site marked default (Checkpoint A)
  [glow]                        # light-dome layer — empty until derived
  bortle = 0                   # 0 = unset (optional observed-SQM/Bortle anchor)
  sqm_zenith = 0.0
  radius_mi = 50               # light-dome search radius (Checkpoint A)
  mask = ""                    # broadband glow floor (.hrz), computed + editable
  mask_narrowband = ""         # softer floor for ON/LP filters
  # sources = [...]            # contributing towns (name/bearing/intensity) for display
  ```

  This is **additive authored config** under the hidden dir — **no `.store_version`
  bump / migration** (seeded idempotently, existing files unchanged). The `[glow]`
  fields ship **empty**; **Checkpoint A** (ROADMAP item 1) populates the `mask`
  **offline** from a **bundled GeoNames** populated-places dataset — Walker's-Law
  domes (skyglow ∝ population × distance⁻²·⁵) within `radius_mi` → an upper-envelope
  azimuth floor — anchored by the optional observed Bortle/SQM and **hand-editable**;
  the contributing `sources` are stored for inspection. (Falchi **World Atlas** /
  **VIIRS** radiance is the **v2** precision upgrade.) **Equipment inventory stays
  deferred** out of this arc (the device seam remains #16-6d).
- **Generated plan files** (SSC schedule JSON, NINA sequences) are user-facing
  **outputs** → proposed visible `Plans/` axis (sibling to `Media/`). Homes are
  proposed; refine when built.
- **Priorities flip from authored to computed** (auto-prioritizer, BUGS #21;
  Checkpoint A). Today `priorities.toml` is hand-authored; with the scoring engine
  the **ranking** becomes **derived** (`derived/priorities.json`, recomputed with the
  other rollups from goals + capture state + the seasonal/positional math), leaving
  only thin **authored** inputs. Proposed persistence (refine when built):
  - **Persistent strategy** — a small prefs file (or a `[priorities]` block alongside
    `processing_workflows`): the capture-many↔go-deep **strategy slider**, **per-type
    weights**, goal ranking, and the deep-stack threshold. *Authored, persistent.*
  - **Manual overrides** — per-object **Pin / Mute** (+ optional numeric nudge),
    keyed by slug/target, in a stable file that **survives regeneration** (computed
    rank + overrides = final order). Absorbs today's `track=false` campaign entries.
    *Authored, persistent.*
  - **Night presets** — named **session-toggle** combinations (Site · Filter ·
    Available-time · Brightness · Short-window · Moon) for one-click recall. *Authored,
    persistent.* The session toggles themselves are **ephemeral UI state** (they
    re-rank live, never mutate the saved strategy), persisted only when saved as a
    preset.
  All three are **additive authored config** under the hidden dir — **no
  `.store_version` bump**; `derived/priorities.json` is regenerable/safe-to-delete
  like the other rollups. (The item-1 "Decided design" block in ROADMAP is the source
  of truth for the scoring rules; the assistant only *proposes*, never authors these.)

### Image curation state (BUGS #17)
- A per-image **finished / unfinished / hero** designation, user-curatable
  (promote/demote/set-hero), replacing today's hardcoded `siril._classify` /
  `build_images` filename heuristics. Two seams to settle when built: the **hint
  set** (configurable finished/intermediate filename patterns) is an *authored*
  preference; the **per-image override** is *authored* state that must persist
  alongside the object — proposed in `Objects/<id>/journal.md` frontmatter (hero
  already lives there) or a small per-target manifest. Whichever wins, it's
  authored (mutable, persistent), and the galleries are *derived* from it.

### Reference images for uncaptured objects + attribution (decided 2026-06-30)
- **Goal:** show a thumbnail/hero for objects the user hasn't captured yet (and let
  the user build an in-app image library), without confusing them with real captures.
- **Sourcing (decided):** two tiers. **(A) Automatic, any object** — fetch a survey
  cutout by the object's J2000 RA/Dec (`catalog.load_coords`) from **CDS hips2fits**
  (SDSS where covered, **DSS2** all-sky fallback), **cached offline like Simbad coords**;
  label it as survey data (not a capture). **(B) Curated heroes** for marquee objects —
  **ESA/Hubble + ESO (CC BY 4.0)**, NASA (public domain). ⚠️ DSS is non-commercial +
  needs acknowledgment; SDSS/CDS need acknowledgment; CC BY needs attribution.
- **New data seam:** a **reference-image tier** distinct from the capture tiers
  (`finished/ → stacks/ → seestar-stacks/`) — proposed `seed/object_images/<slug>.jpg`
  (bundled) and/or a cached `.m110_internal_data/renders/ref/<slug>.jpg` (fetched).
  `build_images._hero_source` consults it **only when there is no real capture**, so a
  capture always wins. The Library/grid/detail must visibly distinguish a reference
  image from the user's own data.
- **Attribution is mandatory, authored/reference state:** per reference image, store
  `source` · `license` · `credit` · `url` (e.g. a `seed/object_images.toml` sidecar or
  fields on the `seed/objects.toml` reference) so the object page renders a credit line.
- **In-app image spec (display path is 8-bit sRGB; `build_images` thumb 480px / hero
  1200px):** display copies are **8-bit sRGB JPEG** (PNG only for lossless/transparency).
  Provide **thumb source ≥960px** (crisp 480px @2×) and **hero source ~1600px**; aspect
  is free (UI letterboxes — a ~square/3:2 crop only matters for grid tiles). Keep 16-bit
  TIFF/FITS **masters** in the user's own archive; bundle/store only the 8-bit JPEGs.

### Custom processing workspaces (BUGS #18)
- A named processing workspace **not bound to a single target** — combining lights
  from disparate sources (#16) and **multiple objects** (mosaics, e.g. M81 + M82 +
  "M81 M82"), via hardlinks. A new entity beside the per-target `siril/` sandbox;
  must be **discoverable by name on disk**. Proposed home: a visible
  `Workspaces/<name>/` axis (sibling to `Images/`), same internal shape as the
  per-target sandbox (hardlinked `lights/`, presets, archive). Lights stay
  hardlinks, so only intermediates cost space.

### Publishing / sharing (ROADMAP item 8) — *8a built 2026-06-29*
- The generalized successor to Astronomy's `build_site`. A Qt-free `publish/`
  engine renders **selected** sections (catalog, summary, processing queue, object
  pages, journal, galleries/heroes) into a publishable artifact.
- **Selection + privacy** (8a as built): the **section set + output dir + targets +
  site title** are a transient UI choice persisted to **settings** (`~/.m110/settings.json`:
  `publish_targets`/`publish_sections`/`publish_output_dir`/`publish_exclude_journals`/
  `publish_site_title`), not store data. Per-object opt-out is the Library entry
  **`publish = false`**; per-journal privacy is the **`private: true`** journal
  frontmatter key. (Per-*list* publish flags remain future work.)
- The rendered **output** is a *derived* artifact (regenerable), written to a
  **user-chosen folder outside the data store** — keeps the store clean, no
  `.store_version` impact.
- **Pluggable targets** via a publisher **registry** (`publish.PUBLISHERS`, mirrors
  the processing-workflow + device registries): the local `static-site` target ships
  first; `github-pages`/`netlify` are registered-disabled placeholders. The registry
  + selection are the stable seams; individual targets are adapters.

### Storage substrate seam
- Human-readable files (TOML/JSONL/MD) remain the **source of truth**; the
  **derived layer** is the single heavy-query path and is **swappable**. A future
  **SQLite index** is just another derived artifact built by `build_derived` and
  read by `derived.py` — content files are never queried directly at scale. This
  keeps "scalable & efficient" reachable without changing the on-disk content
  model.

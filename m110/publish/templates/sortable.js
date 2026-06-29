/* Sortable tables for the journal site.
 *
 * Attaches to every <table class="catalog"> on page load:
 *   - Makes each <th> clickable
 *   - First click sorts ascending, second click sorts descending,
 *     third click cycles back to ascending. Sort indicator (↑/↓) is
 *     shown in the active header; inactive headers show a faint ↕.
 *   - Column types are auto-detected:
 *       num:  any <th class="num"> — parsed as numbers, with special
 *             handling for "HH:MM" integration strings (converted to
 *             minutes) and "27.0 min" / "5%" suffix-stripping.
 *       date: any column whose sampled values all match YYYY-MM-DD —
 *             sorted chronologically (ISO format sorts lexically).
 *       text: everything else — case-insensitive, locale-aware,
 *             natural-number-aware ("M2" < "M10" < "M100").
 *   - Empty / "—" cells always sink to the bottom regardless of direction.
 *   - Keyboard-accessible: Tab to header, Enter/Space to sort.
 *
 * No dependencies, no module loader. Plain ES2017+.
 */
(function () {
  "use strict";

  const collator = new Intl.Collator(undefined, {
    numeric: true,
    sensitivity: "base",
  });
  const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  const HHMM_RE = /^(\d+):(\d{2})$/;
  const NUM_RE = /-?\d+(\.\d+)?/;

  function cellText(td) {
    return (td && td.textContent ? td.textContent : "").trim();
  }

  function isEmpty(s) {
    return s === "" || s === "—" || s === "-";
  }

  function numericValue(s) {
    if (!s) return NaN;
    const hm = s.match(HHMM_RE);
    if (hm) return parseInt(hm[1], 10) * 60 + parseInt(hm[2], 10);
    const m = s.match(NUM_RE);
    return m ? parseFloat(m[0]) : NaN;
  }

  function detectType(rows, colIdx, th) {
    if (th.classList.contains("num")) return "num";
    let dateHits = 0, samples = 0;
    for (const r of rows) {
      const c = r.cells[colIdx];
      if (!c) continue;
      const t = cellText(c);
      if (isEmpty(t)) continue;
      samples++;
      if (DATE_RE.test(t)) dateHits++;
      if (samples >= 6) break;
    }
    if (samples > 0 && dateHits === samples) return "date";
    return "text";
  }

  function compareFn(type, colIdx, dir) {
    const sign = dir === "asc" ? 1 : -1;
    return function (a, b) {
      const av = cellText(a.cells[colIdx]);
      const bv = cellText(b.cells[colIdx]);
      const aE = isEmpty(av), bE = isEmpty(bv);
      if (aE && bE) return 0;
      if (aE) return 1;            // empties always at the bottom
      if (bE) return -1;
      if (type === "num") {
        const an = numericValue(av), bn = numericValue(bv);
        const aNaN = isNaN(an), bNaN = isNaN(bn);
        if (aNaN && bNaN) return 0;
        if (aNaN) return 1;
        if (bNaN) return -1;
        return (an - bn) * sign;
      }
      if (type === "date") {
        return av < bv ? -sign : av > bv ? sign : 0;
      }
      return collator.compare(av, bv) * sign;
    };
  }

  function makeSortable(table) {
    const thead = table.tHead;
    if (!thead || !thead.rows[0]) return;
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const headerRow = thead.rows[0];
    const ths = Array.prototype.slice.call(headerRow.cells);

    ths.forEach(function (th, idx) {
      th.classList.add("sortable");
      th.setAttribute("role", "button");
      th.setAttribute("tabindex", "0");

      const handler = function () {
        const rows = Array.prototype.slice.call(tbody.rows);
        if (rows.length < 2) return;
        const type = detectType(rows, idx, th);
        const wasAsc = th.classList.contains("sort-asc");
        const dir = wasAsc ? "desc" : "asc";
        ths.forEach(function (o) {
          o.classList.remove("sort-asc", "sort-desc");
        });
        th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
        rows.sort(compareFn(type, idx, dir));
        const frag = document.createDocumentFragment();
        rows.forEach(function (r) { frag.appendChild(r); });
        tbody.appendChild(frag);
      };

      th.addEventListener("click", handler);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handler();
        }
      });
    });
  }

  function init() {
    document.querySelectorAll("table.catalog").forEach(makeSortable);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}());

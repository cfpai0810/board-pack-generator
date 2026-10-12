# Release notes

## v1.2.1

**Fixes from the v1.2.0 review**

- The cash note no longer says "converted", which a reader could take for a
  change of currency: "Shown in whole Swiss francs; the KPI file states cash
  in thousands." "Convert" in any form is retired from what readers see,
  except "nothing is converted".
- No tile text is printed below 7pt. A comparison line too long for one line
  at 7pt wraps to two, and all four tiles keep one height.
- In a large pack written with a currency code (Swiss francs in the hundreds
  of millions), the budget-to-actual bridge widens to fit its labels and sits
  above the drivers table, so no label overlaps another and no driver's name
  breaks inside a word.
- `docs/releasing.md`, the release checklist.

**The app after a release** (includes `21c09d9`)

- `21c09d9`, pushed on 12 October 2026 between tagged releases: v1.2.0's
  live pages failed with "cannot import name 'CURRENCY' from 'config'",
  because Streamlit Cloud pulled the release without reloading `config` and
  `src`. From then on, Home replaced modules older than their files on its
  next run.
- v1.2.1 completes that fix. Home holds every run against the loaded release:
  the first run after a pull replaces the old modules once, under a lock,
  after the runs under way have finished, so no page view meets a
  half-loaded module. Each open session is then reset on its next run: a
  pack built by the old classes is set aside (a signed one could otherwise
  look editable), a signed pack's PDF and audit downloads stay, and the
  reviewer's edits are kept for the next draft, with the notice "The app was
  updated. Please build the draft again; your edits have been kept." The
  engine refuses to sign a pack already FINAL whichever release built it.
- The pages moved from `streamlit_app/pages/` to `streamlit_app/views/`: with
  a `pages/` folder, Streamlit could run a page without Home, skipping that
  check.

## v1.2.0

One currency per pack, chosen for the run: GBP, EUR, USD, JPY or CHF (written
with its code). Labels only; nothing is converted. A currency other than GBP
asks for its own absolute threshold. Long figures fit: the P&L table sizes its
columns to their contents. `--cash-unit pounds` still works, as `units`.

## v1.1.0

The pack tells its story: a computed headline, summary line and tiles, the
budget-to-actual bridge, each line's effect on profit, and the review screen
showing what the PDF shows. One language across the project
(`docs/glossary.md`).

## v1.0.0

The first release: the board pack from two CSV files, the materiality rule,
the commentary by template or model, review and sign-off, the audit trail,
the web app and CI.

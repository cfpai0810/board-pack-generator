# Release notes

## v1.2.3

The documentation brought up to date with v1.2.x, and the tests run on the
Python version the live app runs.

- The How it's built page lists the currency among what the review line of
  the audit trail holds, as the line itself has since v1.2.0.
- CI runs the whole suite on Python 3.14, the version the live app runs, as
  well as 3.13, on every push and pull request. Each version is reported on
  its own, so a failure on one does not hide the other.
- The README: the live app is rebooted right after every push; the bridge
  sits above the drivers table when its labels are long; the web app takes
  files in any of five currencies; what happens to an open review when the
  app is updated; the currency in the audit trail; `fresh.py` in the project
  structure; the Python versions. The CLI's usage lines include a run in
  euros.
- `docs/releasing.md`: CI must be green on the tagged commit on both Python
  versions.

## v1.2.2

v1.2.2: live app recovery after v1.2.1 (4ad5fc0); pages moved to views/ so
every page runs the release check.

- The outage: after the v1.2.1 push on 12 October 2026 every page of the live
  app failed with an AttributeError. Home called `fresh.held()`, but Streamlit
  Cloud kept the copy of `streamlit_app/lib/fresh.py` loaded from `21c09d9`,
  which has no `held()`. `4ad5fc0` (pushed the same day, untagged until this
  release) has Home reload that file itself, under a lock, when it has
  changed since it was loaded; the check then purges everything else as
  designed. The app recovered on the first page view after that push.
- The pages moved from `streamlit_app/pages/` to `streamlit_app/views/` in
  v1.2.1 (`8dcbf1a`): a `pages/` folder let Streamlit run a page without
  Home, so the release check and the session reset could be skipped. Every
  page now runs through Home.
- The page addresses are unchanged by the move and now pinned: `/`,
  `/How_the_pack_is_built`, `/Board_pack`, `/Your_own_data` and
  `/How_its_built` each open the page they always opened.
- The release checklist now requires a reboot of the live app right after
  every push, then a look at all five pages; the reload code covers only the
  gap between the push and the reboot.

Outage history, for the record:

| Push | What readers saw | Fixed by |
|---|---|---|
| v1.1.0 (`7b234e8`), 10 October 2026 | ImportError on two pages, How the pack is built and Board pack | A reboot of the app, 11 October 2026 |
| v1.2.0 (`1248c6d`), 11 October 2026 | ImportError on three pages: "cannot import name 'CURRENCY' from 'config'" | `21c09d9`, 12 October 2026 (Home replaced stale modules) |
| v1.2.1 (`fdeda3c`), 12 October 2026 | AttributeError on every page: `fresh.held()` missing from an older `fresh.py` | `4ad5fc0` (Home reloads `fresh.py`), released as v1.2.2 |

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

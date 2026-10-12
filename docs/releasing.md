# Releasing

The steps for a release, in order. A release is two commits pushed together
(the code, then the worked example rebuilt from it), so CI tests the final
state, and the version tag sits on the second.

1. **Tests.** `python -m pytest` passes in full, apart from the worked example
   check when the PDF has changed: the rebuild in step 4 settles it.
2. **Version.** Set `VERSION` in `config.py`.
3. **Commit the release.** The tree must then be clean.
4. **Rebuild the worked example** from that clean commit, so its PDF names a
   clean code version: `python scripts/build_worked_example.py` (the page
   images need `pypdfium2`).
5. **Tests again.** A full passing run writes `generated/test_counts.json`;
   copy the totals into the README's "Test suite" line.
6. **Commit the rebuild** with the counts and the README, and put the
   annotated tag `vX.Y.Z` on this commit. Add the release to
   `docs/release-notes.md` first, with any commit since the last tag that
   changed what users run.
7. **Push both commits and the tag together**:
   `git push origin main vX.Y.Z`. Confirm CI is green on the tagged commit.
8. **Reboot the app on Streamlit Cloud right after every push, then open all
   five pages**: Home, How the pack is built, Board pack, Your own data and
   How it's built (share.streamlit.io, the app's menu, Reboot app). This is
   required, not a fallback. Streamlit Cloud pulls a push into the running
   process without restarting it, and keeps old modules loaded: v1.2.0's
   pages failed with an ImportError ("cannot import name 'CURRENCY' from
   'config'"), and v1.2.1's with an AttributeError (Home called `fresh.held()`
   on an older copy of `fresh.py`). `streamlit_app/lib/fresh.py` covers the gap
   between a push and the reboot, replacing old modules and resetting open
   sessions, but it has caused one outage and proven itself once; the reboot
   takes thirty seconds and does not depend on that code being right. Keep the
   pages in `streamlit_app/views/`: a folder named `pages/` beside Home.py lets
   Streamlit run a page without Home, which skips the check.
9. **Check the live app**: every page at desktop and phone width; the sample
   built, edited and signed, with the downloaded PDF's SHA-256 equal to its
   rendered audit line and a clean code version; an own-file run; the worked
   example's hash check; one run with the model.

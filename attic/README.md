# attic

Cold recipes, kinds, and scenarios moved here after 60 days of zero real
execution (phase 2 §4). Nothing here is deleted — it can be restored by
moving the file back and updating the active index.

`scripts/usage-scan.py` lists candidates; `--apply` performs the move.
Do not hand-edit the active kind table to point at attic paths.

Script-level capabilities retire here too, under `attic/scripts/`. Those are
moved by hand: `usage-scan.py` reads product-side execution evidence and
refuses `--apply` against the kernel itself, which is the right rule and not
worth bending for a one-off move. Every retirement is recorded in `MOVED.md`
with how to bring it back — a retired capability whose restore steps are not
written down tends to be retired twice.

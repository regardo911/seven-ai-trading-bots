# Gotchas

Things that actually bit while building this, and what they cost. If you're
extending the repo, these are the traps we already stepped in.

## armed `--live` was silently unreachable

paper mode is the default, and for a while it was the *only* thing that ever ran,
even with live mode armed in source. `broker_for()` wasn't threading the `paper`
flag through, so an armed `--live` run still built a paper broker and filled
against the synthetic ledger. nothing complained, because nothing ever went
live. the safety default hid the bug instead of a test catching it. found it
writing the positive armed-live tests, not before them. now
`tests/test_live_routing.py` pins the live path with fake SDK adapters (no
network, no creds), so "armed live actually routes live" is a test, not a hope.

## `IBKRBroker`'s live path was a raised placeholder

the class was there, the method was there, and the whole thing looked done. the
body just raised. paper mode never calls it, so the suite stayed green and the
hole was invisible until you tried to arm IBKR for real. now implemented against
`ib_async`. watch the import: `ib_async`, never the abandoned `ib_insync`. same
API surface, different package, and mixing them up costs you an afternoon.

## the book disagrees with itself on who calls Claude at runtime

ch06 says the two runtime-inference bots are "news, allocator." ch11 says "PEAD,
allocator" and then names three. both can't be right, and building the
architecture table forced a decision. ch09 settles it: the allocator only calls
Claude in weekly governance, off the trade path. so the trade-path callers are
PEAD and News (two), the allocator is zero-per-trade, five of seven are zero.
the full reconciliation is in `ERRATA.md`, and the code follows ERRATA, not the
printed contradiction.

## the pairs demo needs *rigged* data or it finds nothing

two real price series are almost never cointegrated, so a pairs scanner pointed
at random synthetic walks returns zero tradeable pairs and looks broken. so
`framework/data.py` constructs KO/PEP cointegrated on purpose, so ch04 always
has a live example to trade. the fixture is honest that it's synthetic; it is
not honest that it's random. if you swap in your own data and the scanner goes
quiet, that's the p<0.05 gate working, not a bug.

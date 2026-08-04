# Vendored: german-nouns

This directory is a vendored copy of the lookup half of the
[`german-nouns`](https://github.com/gambolputty/german-nouns) package
(version **1.2.5**) by **Gregor Weichbrodt**.

## Licensing — please read

`german-nouns` and its dataset are licensed **CC BY-SA 4.0** (see `LICENSE` in
this directory). The dataset is derived from the German Wiktionary.

This is *not* the MIT license that covers the rest of this repository. The
files in this directory remain under CC BY-SA 4.0, including the ShareAlike
obligation. Keep `LICENSE` and this attribution in place when redistributing.

## Why it is vendored

`german-nouns` pins `wiktionary-de-parser >=0.9.2,<0.10.0`, which in turn
requires `lxml <5`. That transitively froze this project on `lxml 4.9.4` and
blocked every `lxml` update. Upstream `german-nouns` has had no functional
release since 2023, so the cap was not going to lift.

The parts of the package that need `wiktionary-de-parser` and `lxml` are only
used to *rebuild* the dataset from a Wiktionary XML dump — never at runtime.
Vendoring the lookup code alone drops `wiktionary-de-parser`, `mwparserfromhell`
and `lxml` from the dependency tree entirely.

## What was copied

| Upstream | Here |
| --- | --- |
| `german_nouns/lookup/__init__.py` | `lookup.py` |
| `german_nouns/config.py` | `config.py` |
| `german_nouns/nouns.csv` (19 MB) | `nouns.csv.gz` (1.8 MB) |
| `german_nouns/index.txt` (5.1 MB) | `index.txt.gz` (1.1 MB) |

Deliberately **not** copied:

- `german_nouns/parse_dump/` — rebuilds `nouns.csv` from a Wiktionary dump.
  This is the only consumer of `wiktionary-de-parser`/`lxml`, and the reason
  for the vendoring. To regenerate the dataset, use upstream in a throwaway
  environment and re-compress the output into this directory.
- `german_nouns/lookup/examples.py` — usage examples, unused here.

## Local modifications

The lookup logic is byte-for-byte upstream apart from the following:

1. **Gzipped data files.** `nouns.csv`/`index.txt` are read via `gzip.open(...)`
   in text mode. 24 MB → 2.9 MB in git, with identical parsed contents
   (verified by comparing every parsed row against upstream).
2. **`csv.field_size_limit(sys.maxsize)`.** The CSV has very wide rows; this
   avoids a platform-dependent `_csv.Error` on some systems.
3. **`create_index()` tolerates a read-only filesystem.** The index write is
   wrapped in `try/except OSError`. The Platform.sh app container is read-only
   at runtime, and the in-memory index is already complete at that point, so a
   failed cache write is not fatal. In practice `index.txt.gz` ships with this
   directory, so the rebuild path is not normally reached.
4. **Import path.** `from german_nouns.config import ...` became
   `from rules.vendor.german_nouns.config import ...`.

## Upgrading

Upstream is effectively dormant. If a release ever drops the
`wiktionary-de-parser` pin, prefer deleting this directory and returning to the
PyPI package.

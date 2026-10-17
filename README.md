# abusua2ga4gh

Convert **Abusua Pedigree Studio** session files (`.json`) into **GA4GH Pedigree Standard** messages and **GA4GH Phenopackets** (schema v2), to make Abusua pedigrees interoperable with the wider genomics ecosystem.

Pure Python, no runtime dependencies, Python ≥ 3.8.

---

## Why these output formats? (the overlap, explained)

The standards are **complementary**, and there are **three valid serialisation forms**. This package can emit all three; by default it produces the two recommended ones.

| Form | What it is | When to use |
|---|---|---|
| **Phenopackets `Family`** (single file) | One document holding the **proband** Phenopacket, **relatives** with findings, a **native PED-style pedigree**, and a `consanguinousParents` flag. | The recommended single-file deliverable for family-based genomic diagnostics. **Default.** |
| **GA4GH Pedigree Standard** | A relationship-centric graph (individuals + KIN-ontology relationships such as `isBiologicalMotherOf`). | Interop with tools built on the GA4GH Pedigree Standard. **Default.** |
| **Standalone `Phenopacket` per individual** | One file per clinically-relevant person. | When a downstream tool ingests individual phenopackets. **Optional.** |

A `Phenopacket` describes exactly **one** individual; the schema has no "list of phenopackets" container. To put a whole family in **one file**, the standard provides the `Family` message — that is the single-file form, and it embeds the pedigree plus the member phenopackets together.

> **Two different "pedigrees".** The GA4GH **Pedigree Standard** (KIN relationship triples) and the Phenopackets-**native** `Pedigree` (PED-style `Person` rows, used inside `Family`) are different artifacts. This package builds the right one for each output: the KIN graph for the standalone GA4GH Pedigree, and the PED-style rows for `Family.pedigree`.

### Default output

```bash
abusua2ga4gh session.json --out-dir out
```

writes **two files**:

- `session.family.json` — the single-file Phenopackets `Family`
- `session.ga4gh-pedigree.json` — the GA4GH Pedigree Standard message

---

## How the Abusua dual-layer model maps across

Abusua deliberately stores **biological** parentage separately from **social** parentage, with a paternity-certainty flag between them. The converters honour that split — this is the most important behaviour to understand:

- `bioMotherId` → **KIN:027** `isBiologicalMotherOf` (the *mogya* line; always emitted).
- `bioFatherId` → **KIN:028** `isBiologicalFatherOf`, **but only when `paternity` is `confirmed` or `reported`.** A `social-only` or `unknown` biological father produces **no biological edge** — the genetics must never see a guessed link. `reported` paternity is emitted but flagged in the warnings and annotated on the edge.
- `fosteredIn` with `socialMotherId` / `socialFatherId` → **KIN:022** `isAdoptiveParentOf` (the closest standard term for a social/foster parent), emitted as a *separate* edge so social and biological structure never get conflated. Use `--no-social-edges` for a strictly genetics-facing graph.

Every suppression or assumption is reported in the conversion warnings, never done silently.

---

## Install

```bash
pip install -e .          # from this directory
# or, once published:
pip install abusua2ga4gh
```

## Command line

```bash
# Default: single-file Family + GA4GH Pedigree, into ./out
abusua2ga4gh session.json --out-dir out

# Just the single-file Phenopackets Family
abusua2ga4gh session.json --format family

# Standalone per-individual Phenopackets (one file each)
abusua2ga4gh session.json --format phenopackets

# Every form
abusua2ga4gh session.json --format all

# GA4GH Pedigree only, biological edges only (strict genetics graph)
abusua2ga4gh session.json --format pedigree --no-social-edges

# Pick the proband explicitly for the Family
abusua2ga4gh session.json --format family --proband i6

# Record conditions as phenotypes (HPO-style) instead of diseases
abusua2ga4gh session.json --conditions-as phenotype
```

By default, personal **names are treated as PII and omitted** from output; pass `--include-names` to include them (stored as `alternate_ids`).

## Python API

```python
from abusua2ga4gh import (
    Pedigree, to_family, to_ga4gh_pedigree, to_phenopackets,
)

ped = Pedigree.load("example-sickle-cell.json")

# Recommended: single-file Family (proband + relatives + native pedigree)
family, warns = to_family(ped, proband_id=None)   # auto-picks the marked proband

# GA4GH Pedigree Standard (KIN-relationship graph)
pedigree_msg, warns2 = to_ga4gh_pedigree(ped, include_social_edges=True)

# Optional: standalone per-individual Phenopackets
packets, warns3 = to_phenopackets(ped, affected_only=True)
```

---

## Conditions: diseases vs phenotypes

Abusua records conditions as free text. By default this package records them as **Diseases** (`Disease.term`), which suits diagnosed conditions. If your pedigree instead records **phenotypic abnormalities** (the kind of observations described by HPO), pass `--conditions-as phenotype` (Python: `condition_kind="phenotype"`), and each condition is written as a **PhenotypicFeature** (`PhenotypicFeature.type`) in the Family/Phenopackets output, with the HPO resource declared instead of MONDO.

As with disease terms, the converter does **not** guess an ontology id for phenotypes: it puts your free text in the term `label` and leaves the `id` empty for a curator to complete. Carrier status is always recorded as a phenotypic feature (`HP:0032500`) regardless of this setting. The reverse package, `ga4gh2abusua`, reads conditions from both `diseases` and `phenotypicFeatures`, so either choice round-trips back to Abusua identically.

---

## Important limitation: condition terms

Abusua stores conditions as **free text** (e.g. `"Sickle cell anaemia"`). Phenopackets and the Pedigree disease terms expect **ontology identifiers** (MONDO/OMIM for diseases, HPO for phenotypes).

- A small built-in lookup resolves the conditions used in the bundled examples to MONDO terms.
- **Any other condition is emitted with its free-text label and an *empty* term `id`, plus a warning.** A curator (or a downstream term-mapping step) must supply the correct ontology id before the output is analysis-grade. **The converter never guesses an ontology id from free text.**

Carrier status is exported as the phenotypic feature `HP:0032500` (Heterozygous carrier); verify this is the intended term for your use.

---

## Validating the output

These converters produce JSON that follows the documented structure of each standard, and the test suite checks structural integrity (every relationship resolves, required Phenopacket fields present, correct KIN terms, etc.). For formal schema validation against the official definitions, run the output through:

- the **GA4GH Pedigree validator** / `pedigree-tools` (see the standard's *Tooling* page), and
- **phenopacket-tools** for Phenopacket v2 validation.

We recommend wiring those into CI once you adopt the package.

## Tests

```bash
pytest          # 36 tests over the five bundled example sessions
```

## Layout

```
src/abusua2ga4gh/
  model.py            # load & validate Abusua sessions (typed view, dual-layer fields)
  kin.py              # Kinship Ontology term constants
  ga4gh_pedigree.py   # -> GA4GH Pedigree Standard message (KIN relationships)
  phenopackets.py     # -> standalone Phenopackets v2 (per clinically-relevant individual)
  family.py           # -> single-file Phenopackets Family (+ native PED-style pedigree)
  cli.py              # command-line interface
examples/             # the five disease example sessions
tests/                # pytest suite
```

## References

- GA4GH Pedigree Standard — https://pedigree.readthedocs.io/
- Kinship Ontology (KIN) — http://purl.org/ga4gh/kin.owl
- GA4GH Phenopacket Schema v2 — https://phenopacket-schema.readthedocs.io/

## License

MIT.

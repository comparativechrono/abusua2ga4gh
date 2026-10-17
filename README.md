# abusua2ga4gh

Convert **Abusua Pedigree Studio** sessions (`.json`) into GA4GH files: a
**GA4GH Pedigree**, a **Phenopackets v2 Family** and, if you want them,
standalone **Phenopackets**, so that Abusua pedigrees can be read by other
genomics software.

The files are written by [pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh),
the one GA4GH implementation that the lab's pedigree tools share, so they are
in the same standard form as studio2ga4gh's and the phenopacket toolkit's, and
[ga4gh2abusua](https://github.com/comparativechrono/ga4gh2abusua) turns them back
into a session.

## Installation

```bash
pip install abusua2ga4gh
```

It needs Python 3.9 or later and installs pedigree-ga4gh with it.

## Usage

```bash
abusua2ga4gh asante.json --out-dir out
```

writes two files:

- `out/asante.family.json`, a **Phenopackets Family**: the proband's
  Phenopacket, Phenopackets for the relatives with findings, and a PED-style
  pedigree of everyone. This is the single file most clinical tools want.
- `out/asante.ga4gh-pedigree.json`, a **GA4GH Pedigree**: a Phenopacket for
  every person and the relationships between them, coded with the Kinship
  Ontology (KIN). It holds more than the Family can, such as social and foster
  parents.

Other things you can ask for:

```bash
abusua2ga4gh asante.json --terms terms.json          # match conditions to ontology terms
abusua2ga4gh asante.json --format family             # only the Family
abusua2ga4gh asante.json --format pedigree --no-social-edges   # biological relationships only
abusua2ga4gh asante.json --format phenopackets       # one Phenopacket per person
abusua2ga4gh asante.json --format all                # everything
abusua2ga4gh asante.json --format family --proband i6
abusua2ga4gh asante.json --format pedigree --stdout --narrative "Seen at the sickle cell clinic" --date 2026-10
```

Run `abusua2ga4gh --help` for every option. The options of version 0.2 still
work.

## How the session is written

Abusua keeps biological and social parentage apart, with a flag saying how
certain the father is. The GA4GH files keep them apart too, so that the
genetics never sees a guessed link:

| In the Abusua session | In the GA4GH files |
|---|---|
| `bioMotherId` | `KIN:027` isBiologicalMotherOf |
| `bioFatherId`, paternity `confirmed` | `KIN:028` isBiologicalFatherOf |
| `bioFatherId`, paternity `reported` | `KIN:028` isBiologicalFatherOf, and a note in the narrative |
| `bioFatherId`, paternity `social-only` | `KIN:020` isParentFigureOf, never a biological relationship; noted in the narrative |
| `bioFatherId`, paternity `unknown` | no relationship; the narrative says who is recorded as the father |
| `fosteredIn`, with `socialMotherId` / `socialFatherId` | `KIN:021` isFosterParentOf; noted in the narrative |
| social parents of a child who was not fostered in | `KIN:020` isParentFigureOf; noted in the narrative |
| a union without children together | `KIN:026` isPartnerOf |
| a couple related as second cousins or closer, with or without a union recorded | `KIN:030` isConsanguineousPartnerOf |
| `proband` | `indexPatients`, and the Family's proband |
| `deceased` | vital status `DECEASED` (otherwise `ALIVE`) |
| `condition` | a disease or phenotypic feature, once it is matched to an ontology term |
| `carrier` in `condition` | a note in the narrative |
| `affected` set to `unaffected`, with no condition | a note in the narrative (the Family's PED-style pedigree has it too) |

In the Family's PED-style pedigree, a father is given only when he is the
biological father, confirmed or reported; otherwise the father is `0`, as in a
PED file. A union whose couple have children together needs no relationship of
its own: the children imply it. Two people with a child together are a couple
whether or not the session records a union, as Abusua treats them; if they are
second cousins or closer, which is how KIN defines consanguinity, they are
written as consanguineous partners. `--no-social-edges` leaves out the social
and foster parents for a strictly genetic pedigree, though the narrative still
mentions them.

The narrative starts with any text given with `--narrative`. Then comes its
own part, which starts "Pedigree from Abusua Pedigree Studio:" and says what
the structure cannot, one fixed sentence at a time: who is a carrier, who has
a condition without an ontology term (quoted as the session has it), who is
affected with nothing recorded or unaffected, a father whose paternity is
reported or unknown, a social father, a social mother or father, and who was
fostered in. ga4gh2abusua reads only that part, so nothing you write yourself
is taken for one of those facts.

**Names are never written.** Phenopackets have no field for a name and are
meant to be shareable without one. The files use the session's own ids (`i1`,
`i2` …), which lead back to the session. Notes, layout and the manually set
abusua and ntoro are not written either, since neither standard has a place
for them.

## Conditions and ontology terms

Abusua records conditions as free text, such as "Sickle cell anaemia (HbSS)".
A Phenopacket names every disease and phenotype with an ontology term (Mondo
or OMIM for diseases, the HPO for phenotypes), so each condition has to be
matched to one. A condition is matched by the first of these that applies:

1. a **terms file** given with `--terms`, matched without regard to case:

   ```json
   {
     "Sickle cell anaemia (HbSS)": "MONDO:0011382",
     "Night blindness": {"id": "HP:0000662", "label": "Nyctalopia"}
   }
   ```

   The `--mapping` files of hponorm and mondonorm, and studio2ga4gh's terms
   files, can be used as they are;
2. an **ontology id in brackets** after the condition in the session, such as
   `Sickle cell anaemia [MONDO:0011382]` (ga4gh2abusua writes conditions back
   this way, so a round trip keeps the terms). Only an id from an ontology
   pedigree-ga4gh can declare in `metaData` counts (the HPO, Mondo, OMIM,
   Orphanet, the Disease Ontology, SNOMED CT, ICD-10-CM and the like), so
   free text such as "Hypertension (BP:160/95)" is not taken for one;
3. the terms file again, for the name without a final qualifier in brackets
   ("Sickle cell anaemia" for "Sickle cell anaemia (HbSS)");
4. a short **built-in list** of the conditions in the Abusua examples (sickle
   cell disease, Huntington disease, Duchenne muscular dystrophy,
   oculocutaneous albinism, breast cancer and hereditary breast ovarian cancer
   syndrome), by their exact Mondo names and synonyms, and the British
   spelling "anaemia".

Each term records the release of its ontology in the files' `metaData` when
it is known: from the terms file, if an entry gives a `version`, or, when every
Mondo term in the family is one of the built-in list's, the Mondo release the
list was checked against (2026-10-06). Otherwise the release is recorded as
unknown.

A matched term goes where its ontology says: an HPO term among the phenotypic
features, a Mondo or OMIM term among the diseases. Nothing is guessed. **A
condition that is not matched is left out of the files**, because a
Phenopacket cannot hold a term without an id, and the narrative says who has
it (`i5 has "Night blindness", which has no ontology term yet.`). The command
lists any such conditions when it finishes; add them to the terms file and run
it again.

A condition recorded for someone marked unaffected is written as excluded (looked
for and found to be absent). A condition recorded for someone whose affected
status was left unknown means they have it, so they are affected.

**Carriers** are not coded. Being a carrier is not a phenotype, so no ontology
has a phenotype term for it, and Phenopackets have no field for carrier status:
the only structured place for it is a genomic interpretation of the variant,
which needs a person who knows the variant. The GA4GH Pedigree's narrative says
who is a carrier.

## In Python

```python
from abusua2ga4gh import Pedigree, to_family, to_ga4gh_pedigree, to_phenopackets

ped = Pedigree.load("asante.json")
terms = {"Night blindness": {"id": "HP:0000662", "label": "Nyctalopia"}}

family, notes = to_family(ped, terms=terms)           # {} if nobody is the proband or affected
pedigree, notes = to_ga4gh_pedigree(ped, terms=terms, include_social_edges=True)
packets, notes = to_phenopackets(ped, terms=terms)
```

Each function returns the document and a list of notes about the conversion.
`to_kindred(ped)` gives the family as a `pedigree_ga4gh.Kindred`, for anything
else pedigree-ga4gh can do with it.

## Checking the files

`pedigree-ga4gh validate FILE` checks a file against the standard. The tests
check every file the examples give, and the files have also been checked
against phenopacket-tools' Phenopackets v2 JSON schemas.

## Files from version 0.2

Version 0.2 did not write the standard's form (see the
[changelog](CHANGELOG.md)). Its files can be rewritten once with
`pedigree-ga4gh upgrade FILE -o NEW.json`, which lists every change and what
still needs a person. If you still have the session, converting it again with
this version is better: it knows which parents were foster parents and which
were social fathers, which a 0.2 file only says in a note.

## Development

```bash
pip install -e ".[test]"
pytest
```

The tests use fictional families in `tests/data`.

## References

- GA4GH Pedigree Standard: https://pedigree.readthedocs.io/
- Kinship Ontology (KIN): http://purl.org/ga4gh/kin.owl
- GA4GH Phenopacket Schema v2: https://phenopacket-schema.readthedocs.io/

## Licence

MIT

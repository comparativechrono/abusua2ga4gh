# Changelog

## 0.3.0

abusua2ga4gh now writes its files through
[pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh), the one
GA4GH implementation shared by the lab's pedigree tools, and depends on it.
Version 0.2's files were not in the standard's form, and some of its terms were
wrong.

**The GA4GH Pedigree** is now in the Phenopackets form of the published
standard. In 0.2:

- diseases and the person's name were put inside `subject`, which the
  Phenopacket schema does not allow;
- relationships had a `description`, which the standard does not have;
- the Phenopackets had no `metaData`;
- the outer `id` of each individual was a number of its own (`"1"`, `"2"` …)
  rather than the Phenopacket's id.

In 0.3 every person is a Phenopacket v2 with its own `metaData`, and
relationships are `{individualId, relation, relativeId}`. Anything that 0.2
put in a relationship's description, such as reported paternity, is now said
in the narrative, in fixed sentences that ga4gh2abusua reads back. They
follow the narrative's own opening sentence ("Pedigree from Abusua Pedigree
Studio: ..."), after any text given with `--narrative`, and quote a condition's
own text, so that neither can be misread.

**Social and foster parents** have their own KIN terms. 0.2 wrote both as
`KIN:022` *isAdoptiveParentOf*, although neither is an adoption:

- a child fostered in now has its social parents as `KIN:021`
  *isFosterParentOf*;
- a father whose paternity is social only is `KIN:020` *isParentFigureOf*.

Social parents of a child who was not fostered in, which 0.2 left out, are
also written as `KIN:020`.

**Carriers** are no longer given the phenotypic feature `HP:0032500`
"Heterozygous carrier". `HP:0032500` is the HPO's *Exacerbated by tobacco
use*, and the HPO has no term for a carrier, since being a carrier is not a
phenotype. The narrative says who is a carrier.

**Conditions without an ontology term** are left out of the Phenopackets, with
a note, instead of being written with an empty `id`, which the Phenopacket
schema does not allow. The narrative says who has each one. `--terms FILE` is
new: it matches conditions to ontology terms, without regard to case. So is
an ontology id in brackets after the condition (`Sickle cell anaemia
[MONDO:0011382]`), which is how ga4gh2abusua 0.4 writes conditions back; only
ids from ontologies that can be declared in `metaData` count, so free text
such as "(BP:160/95)" is not taken for one. A condition recorded for someone
whose affected status is unknown makes them affected, as a matched one
always did.

**The built-in list of conditions** had two wrong ids, which are corrected:

- oculocutaneous albinism was given `MONDO:0019064`, which is hereditary
  spastic paraplegia. It is now `MONDO:0018910`.
- "breast and ovarian cancer" was given `MONDO:0003832`, which is complement
  deficiency. It is no longer matched by the list, since it names two cancers
  rather than one Mondo term. Hereditary breast ovarian cancer syndrome
  (`MONDO:0003582`) is matched by its own name, and a terms file can match the
  phrase to whichever term is meant.

Matched terms now carry Mondo's label: sickle cell anaemia is "sickle cell
disease" (`MONDO:0011382`), as Mondo now calls it. The release the list was
checked against (2026-10-06) is recorded in `metaData`.

**Other changes**

- Unions are written: `KIN:026` *isPartnerOf* for a couple without children
  together, and `KIN:030` *isConsanguineousPartnerOf* for a couple related
  as second cousins or closer, as KIN defines it, whether or not a union is
  recorded.
- A father of unknown paternity is still not given as the biological father,
  but the narrative now says who is recorded as the father.
- The narrative also says who is marked affected with no condition
  recorded, and who is marked unaffected, since a Phenopacket only says who
  has a condition.
- Names are never written. Phenopackets have no field for a name, and
  `--include-names`, kept so that 0.2's commands still run, now only prints a
  note. The files use the session's ids, which lead back to it.
- The Family's `metaData` declares every ontology used in it, with its release
  where known, and `consanguinousParents` is always written.
- In the `kin` module, the sperm donor term is `KIN:004` *isSpermDonorOf*
  (0.2 had `KIN:039`, which is *hasGestationalCarrier*). `KIN:011` is labelled
  *isPolyzygoticMultipleBirthSiblingOf*, as KIN labels it (0.2 had
  *isDizygoticMultipleBirthSiblingOf*). Neither was used in a conversion.
- `--created-by`, `--version` and `python -m abusua2ga4gh` are new, and
  `--date` is checked (YYYY, YYYY-MM or YYYY-MM-DD) before anything is
  written. All the files are made before any is written, so a mistake never
  leaves half of them.
- "Heterozygous carrier", the label 0.2 gave its carrier term, counts as a
  carrier in a session, as Abusua's own "carrier" does.
- Python 3.9 or later is needed, as for pedigree-ga4gh.
- `__version__` now matches the release (0.2.0 reported 0.1.0). There is a
  LICENSE file (the 0.2.0 release said MIT but had none). There are tests, on
  fictional families, run on Python 3.9 to 3.14.

Files written by 0.2 can be rewritten with `pedigree-ga4gh upgrade`.

## 0.2.0

Released on PyPI on 1 June 2026.

## 0.1.0

Released on PyPI on 31 May 2026.

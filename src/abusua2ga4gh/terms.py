"""Matching Abusua's free-text conditions to ontology terms.

Abusua Pedigree Studio records conditions as free text, such as "Sickle cell
anaemia (HbSS)". A Phenopacket names every disease and phenotype with an
ontology term, so a condition has to be matched to one before it can be
written; one that is not matched is left out of the files, and the narrative
says who has it.

A condition is matched by the first of these that applies:

1. a terms file (``--terms``), mapping condition names to ontology terms,
   matched without regard to case;
2. an ontology id written after the condition in square or round brackets,
   as ga4gh2abusua writes conditions back: ``Sickle cell anaemia [MONDO:0011382]``.
   Only an id from an ontology pedigree-ga4gh can declare counts (the HPO,
   Mondo, OMIM, Orphanet, the Disease Ontology, SNOMED CT, ICD-10-CM and the
   like), so free text such as "(BP:160/95)" is not taken for one;
3. the terms file again, for the name without a final qualifier in brackets
   ("Sickle cell anaemia" for "Sickle cell anaemia (HbSS)");
4. a short built-in list of exact names, for conditions in the Abusua examples.

Nothing is guessed: a name that none of these gives a term is left unmatched.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from pedigree_ga4gh import DISEASE, PHENOTYPE, ontology

# Names (lower case) and the Mondo terms they are, checked against Mondo
# release 2026-10-06: each name is the term's label or one of its exact
# synonyms, or the British spelling of one ("sickle cell anaemia").
BUILT_IN_RELEASE = "2026-10-06"
BUILT_IN: Dict[str, Tuple[str, str]] = {
    "sickle cell anaemia": ("MONDO:0011382", "sickle cell disease"),
    "sickle cell anemia": ("MONDO:0011382", "sickle cell disease"),
    "sickle cell disease": ("MONDO:0011382", "sickle cell disease"),
    "huntington disease": ("MONDO:0007739", "Huntington disease"),
    "duchenne muscular dystrophy": ("MONDO:0010679", "Duchenne muscular dystrophy"),
    "oculocutaneous albinism": ("MONDO:0018910", "oculocutaneous albinism"),
    "breast cancer": ("MONDO:0007254", "breast cancer"),
    "hereditary breast ovarian cancer syndrome": ("MONDO:0003582", "hereditary breast ovarian cancer syndrome"),
    "hereditary breast and ovarian cancer syndrome": ("MONDO:0003582", "hereditary breast ovarian cancer syndrome"),
}

# The terms in the list, by id, with their Mondo labels.
LISTED: Dict[str, str] = {tid: tlabel for tid, tlabel in BUILT_IN.values()}

_ID_IN_BRACKETS = re.compile(r"^(.*?)\s*[\[(]\s*([A-Za-z][A-Za-z0-9.\-]*:[^\s\])]+)\s*[\])]\s*$")
_QUALIFIER = re.compile(r"\s*\([^)]*\)\s*$")


def load_terms(obj) -> Dict[str, Dict[str, str]]:
    """Normalise a condition -> term mapping, keyed by the condition in lower case.

    Accepts ``{"Breast cancer": "MONDO:0007254"}``, ``{"Breast cancer": {"id": ...,
    "label": ..., "kind": ..., "version": ...}}``, the ``--mapping`` files of
    hponorm and mondonorm, and decision logs with a ``"resolved"`` mapping (from
    phenotk), the same files studio2ga4gh's ``--terms`` reads.
    """
    if isinstance(obj, dict) and isinstance(obj.get("resolved"), dict):
        obj = obj["resolved"]
    out: Dict[str, Dict[str, str]] = {}
    for label, val in (obj or {}).items():
        if not isinstance(label, str):
            continue
        if isinstance(val, str) and val.strip():
            out[label.strip().lower()] = {"id": val.strip(), "label": label.strip()}
        elif isinstance(val, dict) and (val.get("id") or val.get("curie")):
            out[label.strip().lower()] = {"id": str(val.get("id") or val.get("curie")).strip(),
                                          "label": str(val.get("label") or label).strip(),
                                          "kind": str(val.get("kind") or ""),
                                          "version": str(val.get("version") or "")}
    return out


def split_label(text: str) -> Tuple[str, Optional[str]]:
    """``"Breast cancer [MONDO:0007254]"`` -> ``("Breast cancer", "MONDO:0007254")``.

    Without an ontology id in brackets at the end, the id is ``None``; a
    qualifier such as "(HbSS)" or "(BP:160/95)" is not an id and is left in
    the name.
    """
    m = _ID_IN_BRACKETS.match(text or "")
    if m:
        curie = ontology.tidy_curie(m.group(2))
        if ontology.is_curie(curie) and ontology.prefix_of(curie) in ontology.RESOURCES:
            return (m.group(1).strip() or m.group(2)), curie
    return (text or "").strip(), None


def without_qualifier(text: str) -> str:
    """The name without a final qualifier in round brackets: "Sickle cell anaemia (HbSS)" -> "Sickle cell anaemia"."""
    return _QUALIFIER.sub("", text or "").strip()


def match(condition: str, mapping: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    """The term for one condition, or ``None``.

    The result has ``id``, ``label``, ``kind`` (disease or phenotype),
    ``version`` (the ontology release, if the terms file gives it), ``source``
    (``"terms"``, ``"id"`` or ``"built-in"``) and ``listed``, true when the
    term is one of the built-in list's, which were checked against Mondo
    release :data:`BUILT_IN_RELEASE`.
    """
    text = (condition or "").strip()
    base, curie = split_label(text)
    hit = None
    for key in (text.lower(), base.lower()):
        if key in mapping:
            hit = dict(mapping[key], source="terms")
            break
    if hit is None and curie:
        hit = {"id": curie, "label": base, "source": "id"}
    if hit is None:
        plain = without_qualifier(base).lower()
        if plain in mapping:
            hit = dict(mapping[plain], source="terms")
        elif plain in BUILT_IN:
            tid, tlabel = BUILT_IN[plain]
            hit = {"id": tid, "label": tlabel, "source": "built-in"}
    if hit is None:
        return None
    hit["id"] = ontology.tidy_curie(hit["id"])
    if not ontology.is_curie(hit["id"]):
        return None
    # a term in the list, whether found by its name or written with its id, has the label Mondo gives it
    hit["listed"] = hit["id"] in LISTED
    if hit["listed"] and hit["source"] in ("id", "built-in"):
        hit["label"] = LISTED[hit["id"]]
    hit["label"] = (hit.get("label") or base).strip() or base
    if hit.get("kind") not in (DISEASE, PHENOTYPE):
        hit["kind"] = PHENOTYPE if ontology.prefix_of(hit["id"]) == "HP" else DISEASE
    hit.setdefault("version", "")
    return hit

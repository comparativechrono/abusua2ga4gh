"""
Convert an Abusua :class:`~abusua2ga4gh.model.Pedigree` into a GA4GH
Pedigree Standard message (the Phenopackets ``GA4GHPedigree`` representation).

The GA4GH Pedigree model is relationship-centric: a pedigree is a set of
``individuals`` (each wrapping a Phenopacket ``Individual`` as its ``subject``)
plus a flat list of ``relationships``, each a (subject, KIN relation, relative)
triple. See https://pedigree.readthedocs.io/.

Design note on the Abusua dual layer
------------------------------------
Abusua records biological and social parentage separately. We honour that here:

* ``bioMotherId`` -> KIN:027 isBiologicalMotherOf
* ``bioFatherId`` -> KIN:028 isBiologicalFatherOf, BUT only when paternity is
  ``confirmed`` or ``reported``. A ``social-only`` or ``unknown`` biological
  father produces NO biological edge (the genetics must not see a guessed link).
* ``fosteredIn`` with ``socialMotherId`` / ``socialFatherId`` -> KIN:022
  isAdoptiveParentOf (the closest standard term for a social/foster parent).

This keeps the genetics-facing graph clean while still expressing the social
structure, exactly as the source tool intends. Reported (vs confirmed)
paternity is preserved as an edge ``provenance`` note and surfaced in
``conversion_warnings`` so it is never silently upgraded to certainty.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .model import Pedigree, Person
from . import kin


# Abusua sex code -> GA4GH/Phenopacket sex enum
_SEX_MAP = {"M": "MALE", "F": "FEMALE", "U": "UNKNOWN_SEX"}


def _subject(p: Person, include_clinical: bool, include_names: bool = True) -> Dict[str, Any]:
    """Build the Phenopacket Individual that is the pedigree member's ``subject``."""
    subj: Dict[str, Any] = {"id": p.id, "sex": _SEX_MAP.get(p.sex, "UNKNOWN_SEX")}
    if include_names and p.name:
        # Names are PII; included only when requested (Abusua sessions are
        # user-held files). Recorded under 'name' (round-trips cleanly) plus
        # alternate_ids for tools that look there.
        subj["name"] = p.name
        subj["alternate_ids"] = [p.name]
    if p.deceased:
        subj["vital_status"] = {"status": "DECEASED"}
    else:
        subj["vital_status"] = {"status": "ALIVE"}
    if include_clinical and p.conditions:
        subj["diseases"] = [{"term": {"id": "", "label": c}} for c in p.conditions]
    return subj


def _relationship(subject_id: str, relation: kin.KinTerm, relative_id: str,
                  provenance: Optional[str] = None) -> Dict[str, Any]:
    rel: Dict[str, Any] = {
        "individual_id": subject_id,
        "relation": relation.as_dict(),
        "relative_id": relative_id,
    }
    if provenance:
        rel["description"] = provenance
    return rel


def to_ga4gh_pedigree(
    ped: Pedigree,
    *,
    include_clinical: bool = True,
    include_social_edges: bool = True,
    include_names: bool = False,
    narrative: Optional[str] = None,
    date: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Convert to a GA4GH Pedigree dict.

    Returns ``(pedigree_dict, conversion_warnings)``.

    Parameters
    ----------
    include_clinical:
        If True, attach each member's conditions to their ``subject.diseases``.
    include_social_edges:
        If True, emit KIN:022 (adoptive/foster) edges for social parents that
        differ from the biological parents. If False, only biological edges are
        emitted (a strictly genetics-facing graph).
    narrative, date:
        Optional pedigree-level metadata.
    """
    warnings: List[str] = []
    individuals: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []

    # 1) individuals (stable ordering for reproducible output)
    for idx, p in enumerate(ped.list(), start=1):
        individuals.append({"id": str(idx), "subject": _subject(p, include_clinical, include_names)})
        if p.sex == "U":
            warnings.append(f"{p.display}: sex unknown (exported as UNKNOWN_SEX).")

    # 2) relationships
    for p in ped.list():
        # --- biological mother (the mogya line; never in doubt in this model) ---
        if p.bio_mother_id and ped.get(p.bio_mother_id):
            relationships.append(_relationship(
                p.bio_mother_id, kin.IS_BIOLOGICAL_MOTHER_OF, p.id))

        # --- biological father, gated on paternity certainty ---
        if p.bio_father_id and ped.get(p.bio_father_id):
            if p.paternity in ("confirmed", "reported"):
                prov = None
                if p.paternity == "reported":
                    prov = "paternity reported, not confirmed"
                    warnings.append(
                        f"{p.display}: biological father edge emitted but paternity is "
                        f"REPORTED, not confirmed \u2014 verify before genetic use.")
                relationships.append(_relationship(
                    p.bio_father_id, kin.IS_BIOLOGICAL_FATHER_OF, p.id, prov))
            elif p.paternity == "social-only":
                warnings.append(
                    f"{p.display}: father {ped.get(p.bio_father_id).display} is SOCIAL-only "
                    f"\u2014 no biological father edge emitted.")
                if include_social_edges:
                    relationships.append(_relationship(
                        p.bio_father_id, kin.IS_ADOPTIVE_PARENT_OF, p.id,
                        "social/levirate father (non-biological)"))
            else:  # unknown
                warnings.append(
                    f"{p.display}: biological father present but paternity 'unknown' "
                    f"\u2014 no biological father edge emitted.")

        # --- social parents from fostering, where distinct from biology ---
        if include_social_edges and p.fostered_in:
            for soc_id in (p.social_mother_id, p.social_father_id):
                if soc_id and ped.get(soc_id) and soc_id not in (p.bio_mother_id, p.bio_father_id):
                    relationships.append(_relationship(
                        soc_id, kin.IS_ADOPTIVE_PARENT_OF, p.id,
                        "social/foster parent (child fostered in)"))
            warnings.append(
                f"{p.display}: fostered-in \u2014 social parentage emitted as adoptive edges.")

    pedigree: Dict[str, Any] = {
        "id": ped.family_id,
        "individuals": individuals,
        "relationships": relationships,
    }
    index = [p.id for p in ped.probands()]
    if index:
        pedigree["index_patients"] = index
    if narrative:
        pedigree["narrative"] = narrative
    if date:
        pedigree["date"] = date

    return pedigree, warnings

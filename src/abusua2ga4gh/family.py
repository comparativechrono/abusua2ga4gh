"""
Build a Phenopackets v2 ``Family`` message \u2014 the single-file form that bundles a
proband Phenopacket, optional relative Phenopackets, and a native (PED-style)
``Pedigree`` into one document.

This is distinct from the GA4GH Pedigree Standard (see ``ga4gh_pedigree.py``):

* GA4GH Pedigree Standard = a relationship-centric graph using KIN ontology
  terms (isBiologicalMotherOf, etc.).
* Phenopackets ``Family.pedigree`` = a list of PED-style ``Person`` rows
  (familyId, individualId, paternalId, maternalId, sex, affectedStatus).

The Phenopackets ``Family`` requires the *native* pedigree, so that is what we
build here. Reference: https://phenopacket-schema.readthedocs.io/en/latest/family.html
and .../pedigree.html.

Family field summary (v2):
  id                     REQUIRED  application-specific family identifier
  proband                REQUIRED  a single Phenopacket (the index patient)
  relatives              0..*      Phenopackets for relatives WITH relevant findings
  consanguinous_parents  0..1      bool: are the proband's parents consanguineous?
  pedigree               REQUIRED  native Pedigree (PED-style Person rows)
  files                  0..*      family-level files (not produced here)
  meta_data              REQUIRED  ontologies/resources used

Per the spec, unaffected relatives do NOT need their own Phenopacket; their
status is carried by the pedigree's affectedStatus. Pedigree.individual_id MUST
match the subject.id of any Phenopacket describing that person.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .model import Pedigree, Person
from .phenopackets import (
    person_to_phenopacket, _metadata, _SEX_MAP, _now_iso,  # reuse helpers
)


# Phenopackets AffectedStatus enum
_MISSING, _UNAFFECTED, _AFFECTED = "MISSING", "UNAFFECTED", "AFFECTED"


def _affected_status(p: Person) -> str:
    if p.affected == "affected":
        return _AFFECTED
    if p.affected == "unaffected":
        return _UNAFFECTED
    return _MISSING


def _ped_person(p: Person, ped: Pedigree) -> Dict[str, Any]:
    """One native Pedigree.Person row (equivalent to a PED line).

    paternalId/maternalId use '0' for an absent/unknown parent, exactly as a PED
    founder. The biological father is only cited when paternity is confirmed or
    reported \u2014 mirroring the PED compiler and the GA4GH converter, so a
    social-only or unknown father becomes '0' here too.
    """
    mat = p.bio_mother_id if (p.bio_mother_id and ped.get(p.bio_mother_id)) else "0"
    if p.bio_father_id and ped.get(p.bio_father_id) and p.paternity in ("confirmed", "reported"):
        pat = p.bio_father_id
    else:
        pat = "0"
    return {
        "familyId": ped.family_id,
        "individualId": p.id,
        "paternalId": pat,
        "maternalId": mat,
        "sex": _SEX_MAP.get(p.sex, "UNKNOWN_SEX"),
        "affectedStatus": _affected_status(p),
    }


def to_native_pedigree(ped: Pedigree) -> Dict[str, Any]:
    """Build the Phenopackets-native Pedigree (a list of PED-style persons)."""
    return {"persons": [_ped_person(p, ped) for p in ped.list()]}


def _parents_consanguineous(proband: Person, ped: Pedigree) -> Optional[bool]:
    """Are the proband's two biological parents consanguineous?

    Returns True/False when both parents are known, else None (cannot assess).
    Uses the same shared-ancestor test the app uses for the consanguinity loop.
    """
    mum = ped.get(proband.bio_mother_id)
    dad = ped.get(proband.bio_father_id)
    if not mum or not dad:
        return None

    def ancestors(pid: Optional[str], seen=None) -> set:
        seen = seen or set()
        person = ped.get(pid)
        if not person or pid in seen:
            return set()
        seen.add(pid)
        out = set()
        for parent_id in (person.bio_mother_id, person.bio_father_id):
            if parent_id:
                out.add(parent_id)
                out |= ancestors(parent_id, seen)
        return out

    a = ancestors(mum.id) | {mum.id}
    b = ancestors(dad.id) | {dad.id}
    return bool((a & b) or mum.id in b or dad.id in a)


def to_family(
    ped: Pedigree,
    *,
    proband_id: Optional[str] = None,
    include_relative_phenopackets: bool = True,
    created_by: str = "abusua2ga4gh",
    include_names: bool = False,
    condition_kind: str = "disease",
) -> Tuple[Dict[str, Any], List[str]]:
    """Build a single Phenopackets ``Family`` message.

    Returns ``(family_dict, conversion_warnings)``.

    The ``proband`` is chosen from (in order): an explicit ``proband_id``, the
    pedigree's marked proband, then the first affected individual. ``relatives``
    receive their own Phenopacket only when they have relevant findings
    (affected or carrier); every individual\u2014affected or not\u2014appears in the
    native pedigree regardless.
    """
    warnings: List[str] = []

    # --- choose the proband ---
    proband: Optional[Person] = None
    if proband_id:
        proband = ped.get(proband_id)
        if not proband:
            warnings.append(f"requested proband_id '{proband_id}' not found; falling back.")
    if not proband:
        probands = ped.probands()
        if probands:
            proband = probands[0]
            if len(probands) > 1:
                warnings.append(
                    f"{len(probands)} probands marked; using {proband.display}. "
                    f"A Family has exactly one proband.")
    if not proband:
        affected = ped.affected()
        if affected:
            proband = affected[0]
            warnings.append(
                f"no proband marked; using first affected individual "
                f"({proband.display}) as the Family proband.")
    if not proband:
        warnings.append(
            "no proband or affected individual \u2014 cannot build a Family "
            "(the proband field is REQUIRED). Consider the GA4GH Pedigree output instead.")
        return {}, warnings

    # --- proband phenopacket (REQUIRED) ---
    proband_pp, w = person_to_phenopacket(
        proband, ped, created_by=created_by, include_names=include_names,
        condition_kind=condition_kind)
    warnings.extend(w)

    # --- relative phenopackets: only those with relevant findings ---
    relatives: List[Dict[str, Any]] = []
    if include_relative_phenopackets:
        for p in ped.list():
            if p.id == proband.id:
                continue
            relevant = (p.affected == "affected") or p.is_carrier
            if relevant:
                pp, w = person_to_phenopacket(
                    p, ped, created_by=created_by, include_names=include_names,
                    condition_kind=condition_kind)
                relatives.append(pp)
                warnings.extend(w)

    # --- native pedigree (REQUIRED): every member, PED-style ---
    pedigree_native = to_native_pedigree(ped)

    # --- consanguinity flag for the proband's parents ---
    consanguineous = _parents_consanguineous(proband, ped)

    # --- assemble ---
    # Declare whichever ontologies the member phenopackets actually reference:
    # MONDO for resolved disease terms, HPO for resolved phenotype terms and the
    # carrier feature.
    members = [proband_pp, *relatives]
    needs_mondo = any(
        d.get("term", {}).get("id", "").startswith("MONDO:")
        for pp in members for d in pp.get("diseases", []))
    needs_hpo = any(pp.get("phenotypicFeatures") for pp in members)
    family: Dict[str, Any] = {
        "id": ped.family_id,
        "proband": proband_pp,
    }
    if relatives:
        family["relatives"] = relatives
    if consanguineous is not None:
        family["consanguinousParents"] = consanguineous
        if consanguineous:
            warnings.append(
                f"proband {proband.display}: parents are consanguineous "
                f"(consanguinousParents=true).")
    family["pedigree"] = pedigree_native
    family["metaData"] = _metadata(created_by, need_mondo=needs_mondo, need_hpo=needs_hpo)

    return family, warnings

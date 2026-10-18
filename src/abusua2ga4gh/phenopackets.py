"""Standalone Phenopackets v2, one for each person with something to describe.

Each is the same Phenopacket the person has in the GA4GH Pedigree and the
Family, written by pedigree-ga4gh, with its own ``metaData``. They are written
for the people who are affected, carriers or the proband, so that a tool that
reads one Phenopacket at a time can have them.

A carrier's Phenopacket has no findings: Phenopackets have no field for being
a carrier, and no ontology has a phenotype term for it (version 0.2 wrote
HP:0032500, which is the HPO's "Exacerbated by tobacco use"). The GA4GH
Pedigree's narrative says who is a carrier.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pedigree_ga4gh.kindred import member_phenopacket

from .convert import to_kindred
from .ga4gh_pedigree import CREATED_BY
from .model import Pedigree, Person


def person_to_phenopacket(
    p: Person,
    ped: Pedigree,
    *,
    created_by: str = CREATED_BY,
    include_names: bool = False,
    condition_kind: str = "disease",
    terms=None,
    created: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """The Phenopacket for one person. Returns ``(phenopacket, warnings)``."""
    k, warnings = to_kindred(ped, terms=terms, condition_kind=condition_kind)
    m = k.member(p.id)
    if m is None:
        raise KeyError("{} is not in the session".format(p.id))
    packet = member_phenopacket(k, m, created_by=created_by, created=created, warnings=warnings)
    if p.is_carrier and not (packet.get("diseases") or packet.get("phenotypicFeatures")):
        warnings.append("{} is a carrier, which a Phenopacket has no field for, so their Phenopacket has no "
                        "findings".format(p.id))
    return packet, [w for w in dict.fromkeys(warnings) if w.startswith(p.id + ":") or w.startswith(p.id + " ")]


def to_phenopackets(
    ped: Pedigree,
    *,
    affected_only: bool = True,
    include_carriers: bool = True,
    include_probands: bool = True,
    created_by: str = CREATED_BY,
    include_names: bool = False,
    condition_kind: str = "disease",
    terms=None,
    created: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """One Phenopacket for each person who is affected, a carrier or the proband.

    With ``affected_only=False``, everyone with a condition or carrier status
    is included as well. Returns ``(phenopackets, warnings)``.
    """
    k, warnings = to_kindred(ped, terms=terms, condition_kind=condition_kind)
    out: List[Dict[str, Any]] = []
    for p in ped.list():
        relevant = ((affected_only and p.affected == "affected") or (include_carriers and p.is_carrier)
                    or (include_probands and p.proband)
                    or (not affected_only and (p.conditions or p.is_carrier)))
        if not relevant:
            continue
        packet = member_phenopacket(k, k.member(p.id), created_by=created_by, created=created, warnings=warnings)
        if not (packet.get("diseases") or packet.get("phenotypicFeatures")):
            warnings.append("{}: the Phenopacket has no findings{}".format(
                p.id, " (being a carrier has no field in a Phenopacket)" if p.is_carrier else
                " (no condition has an ontology term yet)" if p.conditions else ""))
        out.append(packet)
    if not out:
        warnings.append("nobody is affected, a carrier or the proband, so no Phenopackets were written")
    return out, list(dict.fromkeys(warnings))

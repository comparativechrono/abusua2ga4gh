"""An Abusua session as a Phenopackets v2 Family, written by pedigree-ga4gh.

A Family holds the proband's Phenopacket, Phenopackets for the relatives with
findings, and a PED-style pedigree of everyone (``familyId``,
``individualId``, ``paternalId``, ``maternalId``, ``sex``, ``affectedStatus``).
In the PED-style pedigree a father is given only when he is the biological
father, confirmed or reported; a social or unknown father is ``0``, as in a PED
file. Unaffected relatives have no Phenopacket of their own: the pedigree
carries their status.

Reference: https://phenopacket-schema.readthedocs.io/en/latest/family.html
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pedigree_ga4gh import phenopackets as pp
from pedigree_ga4gh import to_phenopackets_family

from .convert import to_kindred
from .ga4gh_pedigree import CREATED_BY
from .model import Pedigree


def to_family(
    ped: Pedigree,
    *,
    proband_id: Optional[str] = None,
    include_relative_phenopackets: bool = True,
    created_by: str = CREATED_BY,
    include_names: bool = False,
    condition_kind: str = "disease",
    terms=None,
    created: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Build a Phenopackets Family. Returns ``(family, warnings)``.

    The proband is ``proband_id`` if given, else the session's proband, else
    the first affected person. If nobody is marked as the proband or affected,
    no Family is built (a Family must have a proband) and ``family`` is ``{}``.
    ``include_relative_phenopackets=False`` leaves out the relatives'
    Phenopackets, keeping only the proband's and the pedigree.
    ``include_names`` is kept for version 0.2's calls; names are never written.
    """
    k, warnings = to_kindred(ped, terms=terms, condition_kind=condition_kind)
    chosen = proband_id if proband_id and k.member(proband_id) is not None else None
    if proband_id and chosen is None:
        warnings.append("the proband asked for, {}, is not in the session".format(proband_id))
    if chosen is None and not any(m.index for m in k.members) and not any(
            m.affected or (m.affected is None and any(t.matched and not t.excluded for t in m.terms))
            for m in k.members):
        warnings.append("nobody is marked as the proband or as affected, so no Family can be built (a Family "
                        "must have a proband); the GA4GH Pedigree can still be written")
        return {}, list(dict.fromkeys(warnings))
    doc, w = to_phenopackets_family(k, created_by=created_by, created=created, proband_id=chosen)
    warnings.extend(w)
    if not include_relative_phenopackets and doc.get("relatives"):
        doc = pp.family(doc["id"], proband=doc["proband"], relatives=[], persons=doc["pedigree"]["persons"],
                        consanguineous_parents=doc["consanguinousParents"], created_by=created_by,
                        versions=k.versions, created=doc["metaData"]["created"])
    return doc, list(dict.fromkeys(warnings))


def to_native_pedigree(ped: Pedigree, *, terms=None) -> Dict[str, Any]:
    """The PED-style pedigree of a Family, ``{"persons": [...]}``: one row for each person, as in :func:`to_family`."""
    k, _ = to_kindred(ped, terms=terms)
    if not k.members:
        return {"persons": []}
    doc, _ = to_phenopackets_family(k, created_by=CREATED_BY)
    return doc["pedigree"]

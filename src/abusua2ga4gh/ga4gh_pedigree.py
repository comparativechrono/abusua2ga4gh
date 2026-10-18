"""An Abusua session as a GA4GH Pedigree, written by pedigree-ga4gh.

The GA4GH Pedigree is written in the Phenopackets form of the published
standard: ``individuals`` are Phenopackets v2, one for each person, and
``relationships`` are ``{individualId, relation, relativeId}`` with KIN terms,
in the standard's reduced form (a relationship the others imply is left out).
See :mod:`abusua2ga4gh.convert` for what each part of the session becomes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pedigree_ga4gh import to_ga4gh_pedigree as _write_pedigree

from . import __version__
from .convert import to_kindred
from .model import Pedigree

CREATED_BY = "abusua2ga4gh " + __version__


def to_ga4gh_pedigree(
    ped: Pedigree,
    *,
    include_clinical: bool = True,
    include_social_edges: bool = True,
    include_names: bool = False,
    narrative: Optional[str] = None,
    date: Optional[str] = None,
    terms=None,
    condition_kind: str = "disease",
    created_by: str = CREATED_BY,
    created: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Convert to a GA4GH Pedigree. Returns ``(pedigree, warnings)``.

    ``include_clinical=False`` leaves out conditions and carriers;
    ``include_social_edges=False`` writes biological relationships only.
    ``narrative`` goes at the start of the pedigree's narrative and ``date``
    (YYYY, YYYY-MM or YYYY-MM-DD) is the date it was taken, today if not given.
    ``terms`` matches conditions to ontology terms (see
    :func:`abusua2ga4gh.terms.load_terms`). ``include_names`` is kept so that
    version 0.2's calls still work: names are never written, since
    Phenopackets have no field for them.
    """
    k, warnings = to_kindred(ped, terms=terms, condition_kind=condition_kind, include_clinical=include_clinical,
                             include_social_edges=include_social_edges, narrative=narrative, date=date)
    doc, w = _write_pedigree(k, created_by=created_by, created=created)
    return doc, list(dict.fromkeys(warnings + w))

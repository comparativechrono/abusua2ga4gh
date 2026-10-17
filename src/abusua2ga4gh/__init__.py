"""abusua2ga4gh: convert Abusua Pedigree Studio sessions to GA4GH files.

It writes a GA4GH Pedigree, a Phenopackets v2 Family and, if asked,
standalone Phenopackets, through pedigree-ga4gh, the one GA4GH implementation
the lab's pedigree tools share, so the files are in the same standard form as
studio2ga4gh's and the phenopacket toolkit's.

Quick start::

    from abusua2ga4gh import Pedigree, to_family, to_ga4gh_pedigree
    ped = Pedigree.load("asante.json")
    family, notes = to_family(ped, terms={"Night blindness": "HP:0000662"})
    pedigree, notes = to_ga4gh_pedigree(ped)

Or from the command line::

    abusua2ga4gh asante.json --out-dir out
"""
from __future__ import annotations

__version__ = "0.3.0"

from . import kin  # noqa: E402
from .convert import to_kindred, unmatched  # noqa: E402
from .family import to_family, to_native_pedigree  # noqa: E402
from .ga4gh_pedigree import CREATED_BY, to_ga4gh_pedigree  # noqa: E402
from .model import Pedigree, Person, Union  # noqa: E402
from .phenopackets import person_to_phenopacket, to_phenopackets  # noqa: E402
from .terms import load_terms  # noqa: E402

__all__ = [
    "Pedigree", "Person", "Union",
    "to_kindred", "unmatched", "load_terms",
    "to_ga4gh_pedigree",
    "to_family", "to_native_pedigree",
    "to_phenopackets", "person_to_phenopacket",
    "kin", "CREATED_BY", "__version__",
]

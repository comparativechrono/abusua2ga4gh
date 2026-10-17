"""
abusua2ga4gh \u2014 convert Abusua Pedigree Studio session files into GA4GH
Pedigree Standard messages and GA4GH Phenopackets.

Quick start
-----------
>>> from abusua2ga4gh import Pedigree, to_ga4gh_pedigree, to_phenopackets
>>> ped = Pedigree.load("example-sickle-cell.json")
>>> pedigree_msg, warns = to_ga4gh_pedigree(ped)
>>> packets, warns2 = to_phenopackets(ped)

Or from the command line::

    abusua2ga4gh session.json --out-dir ./out --format both
"""
from __future__ import annotations

from .model import Pedigree, Person, Union
from .ga4gh_pedigree import to_ga4gh_pedigree
from .phenopackets import to_phenopackets, person_to_phenopacket
from .family import to_family, to_native_pedigree
from . import kin

__all__ = [
    "Pedigree", "Person", "Union",
    "to_ga4gh_pedigree",
    "to_family", "to_native_pedigree",
    "to_phenopackets", "person_to_phenopacket",
    "kin",
]

__version__ = "0.1.0"

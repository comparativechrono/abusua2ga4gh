"""
Kinship Ontology (KIN) term constants used by the GA4GH Pedigree Standard.

Source: GA4GH Pedigree Standard documentation and the KIN ontology
(http://purl.org/ga4gh/kin.owl). Only the terms needed for the Abusua mapping
are listed; extend as needed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KinTerm:
    id: str
    label: str

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label}


# Biological parentage
IS_BIOLOGICAL_MOTHER_OF = KinTerm("KIN:027", "isBiologicalMotherOf")
IS_BIOLOGICAL_FATHER_OF = KinTerm("KIN:028", "isBiologicalFatherOf")

# Social / non-biological parentage
IS_ADOPTIVE_PARENT_OF = KinTerm("KIN:022", "isAdoptiveParentOf")

# Sibling relationships
IS_MONOZYGOTIC_SIBLING_OF = KinTerm("KIN:010", "isMonozygoticMultipleBirthSiblingOf")
IS_DIZYGOTIC_SIBLING_OF = KinTerm("KIN:011", "isDizygoticMultipleBirthSiblingOf")

# Assisted reproduction (available if Abusua later records it)
IS_GESTATIONAL_CARRIER_OF = KinTerm("KIN:005", "isGestationalCarrierOf")
IS_OVUM_DONOR_OF = KinTerm("KIN:038", "isOvumDonorOf")
IS_SPERM_DONOR_OF = KinTerm("KIN:039", "isSpermDonorOf")

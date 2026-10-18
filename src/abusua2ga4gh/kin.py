"""The Kinship Ontology (KIN) relations abusua2ga4gh writes, by name.

Every code and label comes from pedigree-ga4gh's copy of KIN (``pedigree_ga4gh.kin``),
which holds the whole ontology as published, so they are always written as KIN
gives them. The names are the ones version 0.2 used, so that code written
against it still runs; two of 0.2's terms were wrong and are corrected here:

* a sperm donor is ``KIN:004`` *isSpermDonorOf*; 0.2 had ``KIN:039``, which is
  *hasGestationalCarrier*;
* ``KIN:011`` is *isPolyzygoticMultipleBirthSiblingOf*; 0.2 labelled it
  *isDizygoticMultipleBirthSiblingOf*, a label KIN does not have.
"""
from __future__ import annotations

from dataclasses import dataclass

from pedigree_ga4gh import kin as _kin

TERMS = _kin.TERMS


@dataclass(frozen=True)
class KinTerm:
    id: str
    label: str

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label}


def _term(code: str) -> KinTerm:
    return KinTerm(code, _kin.TERMS[code].label)


# Biological parentage
IS_BIOLOGICAL_PARENT_OF = _term(_kin.BIOLOGICAL_PARENT)            # KIN:003
IS_BIOLOGICAL_MOTHER_OF = _term(_kin.BIOLOGICAL_MOTHER)            # KIN:027
IS_BIOLOGICAL_FATHER_OF = _term(_kin.BIOLOGICAL_FATHER)            # KIN:028

# Social parentage
IS_PARENT_FIGURE_OF = _term(_kin.PARENT_FIGURE)                    # KIN:020, a social parent
IS_FOSTER_PARENT_OF = _term(_kin.FOSTER_PARENT)                    # KIN:021
IS_ADOPTIVE_PARENT_OF = _term(_kin.ADOPTIVE_PARENT)                # KIN:022

# Partners
IS_PARTNER_OF = _term(_kin.PARTNER)                                # KIN:026
IS_CONSANGUINEOUS_PARTNER_OF = _term(_kin.CONSANGUINEOUS_PARTNER)  # KIN:030

# Siblings (Abusua does not record these yet)
IS_MONOZYGOTIC_SIBLING_OF = _term(_kin.MONOZYGOTIC_MULTIPLE_BIRTH_SIBLING)   # KIN:010
IS_POLYZYGOTIC_SIBLING_OF = _term(_kin.POLYZYGOTIC_MULTIPLE_BIRTH_SIBLING)   # KIN:011
IS_DIZYGOTIC_SIBLING_OF = IS_POLYZYGOTIC_SIBLING_OF                          # 0.2's name for KIN:011

# Assisted reproduction (Abusua does not record these yet)
IS_GESTATIONAL_CARRIER_OF = _term(_kin.GESTATIONAL_CARRIER)        # KIN:005
IS_OVUM_DONOR_OF = _term(_kin.OVUM_DONOR)                          # KIN:038
IS_SPERM_DONOR_OF = _term(_kin.SPERM_DONOR)                        # KIN:004

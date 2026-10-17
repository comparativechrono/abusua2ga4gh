"""
Convert affected individuals in an Abusua :class:`~abusua2ga4gh.model.Pedigree`
into GA4GH Phenopackets (schema v2).

When is a Phenopacket appropriate?
----------------------------------
The two GA4GH standards are complementary, not redundant:

* **GA4GH Pedigree** captures the *family structure* (who is related to whom).
  Every Abusua session maps to exactly one Pedigree.
* **A Phenopacket** is a deep, computable description of *one individual's*
  phenotype/disease. It is appropriate only for individuals who actually have
  clinical information to describe \u2014 i.e. an affected individual, a carrier, or
  a proband. We therefore emit one Phenopacket per such individual, and none
  for the unaffected relatives who exist only to define the pedigree topology.

The Pedigree's per-member ``subject`` already embeds a light Phenopacket
``Individual``; the standalone Phenopackets produced here add the disease
detail (term, onset if recorded, excluded status) that the pedigree subject
does not carry. The two reference each other by shared individual ``id``.

Important honesty note on coding
--------------------------------
Abusua stores conditions as free text (e.g. "Sickle cell anaemia"). Phenopackets
expect ontology terms (MONDO/OMIM for diseases, HPO for phenotypes). This
converter emits the free-text label with an EMPTY term ``id`` and records a
warning. A curator (or a downstream term-mapping step) must supply the ontology
id before the Phenopacket is analysis-grade. We deliberately do not guess
ontology ids from free text.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .model import Pedigree, Person


_SEX_MAP = {"M": "MALE", "F": "FEMALE", "U": "UNKNOWN_SEX"}

# Minimal MONDO terms for the conditions used in the bundled examples. This is a
# tiny convenience lookup, NOT a substitute for proper term mapping; unknown
# labels fall through to an empty id + warning.
_KNOWN_TERMS = {
    "sickle cell anaemia": ("MONDO:0011382", "sickle cell anemia"),
    "sickle cell anemia": ("MONDO:0011382", "sickle cell anemia"),
    "huntington disease": ("MONDO:0007739", "Huntington disease"),
    "duchenne muscular dystrophy": ("MONDO:0010679", "Duchenne muscular dystrophy"),
    "oculocutaneous albinism": ("MONDO:0019064", "oculocutaneous albinism"),
    "breast cancer": ("MONDO:0007254", "breast cancer"),
    "breast and ovarian cancer": ("MONDO:0003832", "hereditary breast ovarian cancer syndrome"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_term(label: str, *, resolve: bool = True) -> Tuple[Dict[str, str], Optional[str]]:
    """Map a free-text condition to an OntologyClass; warn if unresolved.

    A trailing parenthetical qualifier (e.g. "Sickle cell anaemia (HbSS)") is
    ignored for lookup but the original label is preserved in the output.

    When ``resolve`` is False (used for phenotypes, where we have no HPO lookup),
    the term is emitted with an empty id and the free-text label, matching the
    package's policy of never guessing an ontology id.
    """
    if resolve:
        import re
        key = re.sub(r"\s*\([^)]*\)\s*$", "", label.strip()).strip().lower()
        if key in _KNOWN_TERMS:
            tid, _tlabel = _KNOWN_TERMS[key]
            return {"id": tid, "label": label.strip()}, None
    return ({"id": "", "label": label.strip()},
            f"condition '{label}' has no ontology id (free text exported as-is; "
            f"a curator must supply a MONDO/OMIM/HPO id before analysis).")


_HPO_RESOURCE = {
    "id": "hp",
    "name": "Human Phenotype Ontology",
    "url": "http://purl.obolibrary.org/obo/hp.obo",
    "version": "",
    "namespacePrefix": "HP",
    "iriPrefix": "http://purl.obolibrary.org/obo/HP_",
}
_MONDO_RESOURCE = {
    "id": "mondo",
    "name": "Mondo Disease Ontology",
    "url": "http://purl.obolibrary.org/obo/mondo.obo",
    "version": "",
    "namespacePrefix": "MONDO",
    "iriPrefix": "http://purl.obolibrary.org/obo/MONDO_",
}


def _metadata(created_by: str, resources_needed: bool = False, *,
              kind: str = "disease", need_mondo: bool = None,
              need_hpo: bool = None) -> Dict[str, Any]:
    """Build metaData, declaring the ontologies actually referenced.

    For backwards compatibility, ``resources_needed`` + ``kind`` are honoured:
    a resolved term of kind 'disease' declares MONDO, of kind 'phenotype'
    declares HPO. ``need_mondo`` / ``need_hpo`` override explicitly when set.
    """
    if need_mondo is None:
        need_mondo = bool(resources_needed and kind == "disease")
    if need_hpo is None:
        need_hpo = bool(kind == "phenotype")
    md: Dict[str, Any] = {
        "created": _now_iso(),
        "createdBy": created_by,
        "phenopacketSchemaVersion": "2.0",
        "resources": [],
    }
    if need_mondo:
        md["resources"].append(dict(_MONDO_RESOURCE))
    if need_hpo:
        md["resources"].append(dict(_HPO_RESOURCE))
    return md


def person_to_phenopacket(
    p: Person,
    ped: Pedigree,
    *,
    created_by: str = "abusua2ga4gh",
    include_names: bool = False,
    condition_kind: str = "disease",
) -> Tuple[Dict[str, Any], List[str]]:
    """Build a single Phenopacket (v2) for one individual.

    ``condition_kind`` controls how the person's conditions are recorded:
      * "disease"   -> as Disease entries (term = OntologyClass), default;
      * "phenotype" -> as PhenotypicFeature entries (type = OntologyClass).
    In both cases, as elsewhere in this package, we put the free-text condition
    in the ontology ``label`` and leave the ``id`` empty for a curator to fill.
    Carrier status is always a PhenotypicFeature regardless of this setting.
    """
    warnings: List[str] = []
    as_phenotype = (condition_kind == "phenotype")

    subject: Dict[str, Any] = {"id": p.id, "sex": _SEX_MAP.get(p.sex, "UNKNOWN_SEX")}
    if include_names and p.name:
        # Phenopackets has no dedicated name field; record it under 'name' (round-trips
        # cleanly) and also in alternate_ids for tools that look there. Names are PII \u2014
        # only emitted when include_names is set.
        subject["name"] = p.name
        subject["alternate_ids"] = [p.name]
    subject["vital_status"] = {"status": "DECEASED" if p.deceased else "ALIVE"}

    diseases: List[Dict[str, Any]] = []
    phenotypic_features: List[Dict[str, Any]] = []
    resolved_any = False
    for label in p.conditions:
        term, warn = _resolve_term(label, resolve=not as_phenotype)
        if warn:
            warnings.append(f"{p.display}: {warn}")
        else:
            resolved_any = True
        if as_phenotype:
            feature: Dict[str, Any] = {"type": term}
            # 'excluded' marks an explicitly absent phenotype (parallels Disease.excluded)
            if p.affected == "unaffected":
                feature["excluded"] = True
            phenotypic_features.append(feature)
        else:
            disease: Dict[str, Any] = {"term": term}
            if p.affected == "unaffected":
                disease["excluded"] = True
            diseases.append(disease)

    if p.is_carrier:
        # Carrier status is a heterozygous-carrier phenotype; HPO term provided.
        phenotypic_features.append({
            "type": {"id": "HP:0032500", "label": "Heterozygous carrier"},
        })
        warnings.append(
            f"{p.display}: carrier status exported as a phenotypic feature "
            f"(verify HP:0032500 is the intended term for your use).")

    phenopacket: Dict[str, Any] = {
        "id": f"{ped.family_id}-{p.id}",
        "subject": subject,
    }
    if diseases:
        phenopacket["diseases"] = diseases
    if phenotypic_features:
        phenopacket["phenotypicFeatures"] = phenotypic_features
    # declare the ontology that terms reference: MONDO for resolved diseases,
    # HPO for any phenotypic features (they live in the HPO namespace by intent,
    # whether or not we resolved an HP id for them)
    need_mondo = any(d.get("term", {}).get("id", "").startswith("MONDO:") for d in diseases)
    need_hpo = bool(phenotypic_features)
    phenopacket["metaData"] = _metadata(
        created_by, need_mondo=need_mondo, need_hpo=need_hpo)

    if not diseases and not phenotypic_features:
        warnings.append(
            f"{p.display}: no condition or carrier status \u2014 Phenopacket has no "
            f"clinical content (consider omitting).")
    return phenopacket, warnings


def to_phenopackets(
    ped: Pedigree,
    *,
    affected_only: bool = True,
    include_carriers: bool = True,
    include_probands: bool = True,
    created_by: str = "abusua2ga4gh",
    include_names: bool = False,
    condition_kind: str = "disease",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Produce one Phenopacket per clinically-relevant individual.

    Returns ``(phenopackets, conversion_warnings)``.

    By default this emits a Phenopacket for every individual who is affected, a
    carrier, or a proband \u2014 the people for whom a phenotype description is
    meaningful. Unaffected topology-only relatives are skipped.

    ``condition_kind`` ("disease" | "phenotype") selects whether each person's
    conditions are recorded as Diseases or as PhenotypicFeatures.
    """
    warnings: List[str] = []
    out: List[Dict[str, Any]] = []
    seen = set()
    for p in ped.list():
        relevant = (
            (affected_only and p.affected == "affected")
            or (include_carriers and p.is_carrier)
            or (include_probands and p.proband)
            or (not affected_only and (p.conditions or p.is_carrier))
        )
        if not relevant or p.id in seen:
            continue
        seen.add(p.id)
        pp, w = person_to_phenopacket(
            p, ped, created_by=created_by, include_names=include_names,
            condition_kind=condition_kind)
        out.append(pp)
        warnings.extend(w)
    if not out:
        warnings.append("No clinically-relevant individuals \u2014 no Phenopackets produced.")
    return out, warnings

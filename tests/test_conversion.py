"""
Tests for abusua2ga4gh: loading, GA4GH Pedigree conversion, and Phenopackets.

Run with:  pytest
"""
from __future__ import annotations

import pathlib

import pytest

from abusua2ga4gh import Pedigree, to_ga4gh_pedigree, to_phenopackets
from abusua2ga4gh import kin

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "examples"
ALL = sorted(EXAMPLES.glob("example-*.json"))


def load(name):
    return Pedigree.load(EXAMPLES / name)


# ---------------------------------------------------------------- loading

def test_examples_present():
    assert len(ALL) == 5


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_loads_and_validates(path):
    ped = Pedigree.load(path)
    assert ped.people
    # all parent/union references resolve
    assert ped.validate() == [], f"integrity issues: {ped.validate()}"


def test_dual_layer_fields_preserved():
    ped = load("example-sickle-cell.json")
    foster = next(p for p in ped.list() if p.fostered_in)
    assert foster.bio_mother_id is not None
    assert foster.bio_father_id is None
    assert foster.paternity == "unknown"


# -------------------------------------------------------- GA4GH Pedigree

@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_pedigree_structure(path):
    ped = Pedigree.load(path)
    msg, warns = to_ga4gh_pedigree(ped)
    assert msg["id"]
    assert len(msg["individuals"]) == len(ped.people)
    # every relationship references real individual ids
    ids = {p.id for p in ped.list()}
    for r in msg["relationships"]:
        assert r["individual_id"] in ids
        assert r["relative_id"] in ids
        assert r["relation"]["id"].startswith("KIN:")


def test_pedigree_biological_edges_use_correct_kin_terms():
    ped = load("example-breast-cancer-brca.json")
    msg, _ = to_ga4gh_pedigree(ped)
    mother_edges = [r for r in msg["relationships"]
                    if r["relation"]["id"] == kin.IS_BIOLOGICAL_MOTHER_OF.id]
    father_edges = [r for r in msg["relationships"]
                    if r["relation"]["id"] == kin.IS_BIOLOGICAL_FATHER_OF.id]
    assert mother_edges and father_edges
    # label matches the KIN id
    assert mother_edges[0]["relation"]["label"] == "isBiologicalMotherOf"


def test_unknown_paternity_suppresses_biological_father_edge():
    ped = load("example-sickle-cell.json")
    msg, warns = to_ga4gh_pedigree(ped)
    foster = next(p for p in ped.list() if p.fostered_in)
    # the fostered child (unknown paternity, no bio father) has no father edge
    father_edges = [r for r in msg["relationships"]
                    if r["relative_id"] == foster.id
                    and r["relation"]["id"] == kin.IS_BIOLOGICAL_FATHER_OF.id]
    assert father_edges == []


def test_index_patients_are_probands():
    ped = load("example-huntington.json")
    msg, _ = to_ga4gh_pedigree(ped)
    expected = {p.id for p in ped.probands()}
    assert set(msg.get("index_patients", [])) == expected
    assert expected, "example should have a proband"


def test_no_social_edges_flag():
    ped = load("example-sickle-cell.json")
    with_social, _ = to_ga4gh_pedigree(ped, include_social_edges=True)
    without_social, _ = to_ga4gh_pedigree(ped, include_social_edges=False)
    n_adopt_with = sum(1 for r in with_social["relationships"]
                       if r["relation"]["id"] == kin.IS_ADOPTIVE_PARENT_OF.id)
    n_adopt_without = sum(1 for r in without_social["relationships"]
                          if r["relation"]["id"] == kin.IS_ADOPTIVE_PARENT_OF.id)
    assert n_adopt_without == 0
    assert n_adopt_without <= n_adopt_with


# ------------------------------------------------------------ Phenopackets

@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_phenopackets_minimal_validity(path):
    ped = Pedigree.load(path)
    packets, warns = to_phenopackets(ped)
    assert packets, "each example has affected individuals"
    for pp in packets:
        # required v2 fields
        assert pp["id"]
        assert "subject" in pp and pp["subject"]["id"]
        assert "metaData" in pp
        assert pp["metaData"]["phenopacketSchemaVersion"] == "2.0"
        assert "created" in pp["metaData"] and "createdBy" in pp["metaData"]


def test_phenopacket_emitted_only_for_relevant_people():
    ped = load("example-breast-cancer-brca.json")
    packets, _ = to_phenopackets(ped)
    ids = {pp["subject"]["id"] for pp in packets}
    for p in ped.list():
        relevant = p.affected == "affected" or p.is_carrier or p.proband
        if not relevant:
            assert p.id not in ids


def test_known_condition_resolves_to_mondo():
    ped = load("example-sickle-cell.json")
    packets, _ = to_phenopackets(ped)
    proband = next(pp for pp in packets if pp["subject"]["id"] ==
                   ped.probands()[0].id)
    terms = [d["term"]["id"] for d in proband.get("diseases", [])]
    assert any(t.startswith("MONDO:") for t in terms)


def test_freetext_condition_warns_with_empty_id():
    # craft a pedigree with an unmapped condition
    ped = Pedigree.from_dict({
        "v": 1, "fam": "T",
        "people": {"i1": {"id": "i1", "sex": "F", "affected": "affected",
                          "condition": "Some Rare Syndrome XYZ", "proband": True}},
        "unions": [], "_n": 2,
    })
    packets, warns = to_phenopackets(ped)
    assert packets[0]["diseases"][0]["term"]["id"] == ""
    assert any("no ontology id" in w for w in warns)


def test_carrier_becomes_phenotypic_feature():
    ped = load("example-sickle-cell.json")
    packets, _ = to_phenopackets(ped)
    carriers = [pp for pp in packets if "phenotypicFeatures" in pp]
    assert carriers, "sickle example has carriers"
    feat = carriers[0]["phenotypicFeatures"][0]["type"]
    assert feat["id"].startswith("HP:")


# ------------------------------------------------------------ Family (single file)

from abusua2ga4gh import to_family, to_native_pedigree


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.stem)
def test_family_structure(path):
    ped = Pedigree.load(path)
    fam, warns = to_family(ped)
    # required fields
    assert fam["id"]
    assert "proband" in fam and fam["proband"]["subject"]["id"]
    assert "pedigree" in fam and fam["pedigree"]["persons"]
    assert "metaData" in fam
    # pedigree covers EVERY individual (affected or not)
    assert len(fam["pedigree"]["persons"]) == len(ped.people)


def test_family_proband_is_marked_proband():
    ped = load("example-huntington.json")
    fam, _ = to_family(ped)
    assert fam["proband"]["subject"]["id"] == ped.probands()[0].id


def test_family_pedigree_ids_match_phenopacket_subjects():
    # Pedigree.individual_id MUST map to Phenopacket subject.id (spec requirement)
    ped = load("example-sickle-cell.json")
    fam, _ = to_family(ped)
    ped_ids = {row["individualId"] for row in fam["pedigree"]["persons"]}
    subject_ids = {fam["proband"]["subject"]["id"]}
    for rel in fam.get("relatives", []):
        subject_ids.add(rel["subject"]["id"])
    # every phenopacket subject id appears in the pedigree
    assert subject_ids <= ped_ids


def test_family_native_pedigree_uses_ped_conventions():
    ped = load("example-duchenne-xlinked.json")
    nat = to_native_pedigree(ped)
    # founders have '0' parents; affectedStatus is the enum
    statuses = {row["affectedStatus"] for row in nat["persons"]}
    assert statuses <= {"AFFECTED", "UNAFFECTED", "MISSING"}
    founders = [r for r in nat["persons"] if r["paternalId"] == "0" and r["maternalId"] == "0"]
    assert founders, "expected at least one founder with '0' parents"


def test_family_unknown_paternity_sets_paternal_zero():
    ped = load("example-sickle-cell.json")
    nat = to_native_pedigree(ped)
    foster = next(p for p in ped.list() if p.fostered_in)
    row = next(r for r in nat["persons"] if r["individualId"] == foster.id)
    assert row["paternalId"] == "0"   # unknown paternity -> no father cited
    assert row["maternalId"] == foster.bio_mother_id


def test_family_relatives_only_have_findings():
    ped = load("example-breast-cancer-brca.json")
    fam, _ = to_family(ped)
    proband_id = fam["proband"]["subject"]["id"]
    for rel in fam.get("relatives", []):
        p = ped.get(rel["subject"]["id"])
        assert p.id != proband_id
        assert p.affected == "affected" or p.is_carrier


def test_family_consanguinity_flag_on_cross_cousin_case():
    # the sickle and albinism examples include a consanguineous cross-cousin union;
    # if the chosen proband descends from it, the flag should be present & true.
    # At minimum, the flag must be a bool when both parents are known.
    ped = load("example-albinism.json")
    fam, _ = to_family(ped)
    proband = ped.probands()[0]
    if ped.get(proband.bio_mother_id) and ped.get(proband.bio_father_id):
        assert "consanguinousParents" in fam
        assert isinstance(fam["consanguinousParents"], bool)


# ------------------------------------------------ conditions as phenotypes

def test_conditions_as_phenotype_uses_phenotypic_features():
    ped = load("example-sickle-cell.json")
    packets, _ = to_phenopackets(ped, condition_kind="phenotype")
    proband = next(pp for pp in packets if pp["subject"]["id"] == ped.probands()[0].id)
    assert "phenotypicFeatures" in proband
    assert "diseases" not in proband
    # the condition label is present, with an EMPTY id (no guessing)
    labels = [f["type"]["label"] for f in proband["phenotypicFeatures"]
              if f["type"]["id"] != "HP:0032500"]
    assert any("Sickle cell" in l for l in labels)
    assert all(f["type"]["id"] == "" for f in proband["phenotypicFeatures"]
               if f["type"]["label"] != "Heterozygous carrier")


def test_conditions_as_disease_is_default():
    ped = load("example-sickle-cell.json")
    packets, _ = to_phenopackets(ped)   # default
    proband = next(pp for pp in packets if pp["subject"]["id"] == ped.probands()[0].id)
    assert "diseases" in proband


def test_phenotype_mode_declares_hpo_not_mondo():
    ped = load("example-sickle-cell.json")
    packets, _ = to_phenopackets(ped, condition_kind="phenotype")
    proband = next(pp for pp in packets if pp["subject"]["id"] == ped.probands()[0].id)
    prefixes = {r["namespacePrefix"] for r in proband["metaData"]["resources"]}
    assert "HP" in prefixes
    assert "MONDO" not in prefixes


def test_family_phenotype_mode():
    ped = load("example-huntington.json")
    fam, _ = to_family(ped, condition_kind="phenotype")
    assert "phenotypicFeatures" in fam["proband"]
    assert "diseases" not in fam["proband"]

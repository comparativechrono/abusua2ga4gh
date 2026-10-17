"""Tests for abusua2ga4gh: Abusua sessions written as GA4GH files through pedigree-ga4gh.

The sessions in tests/data are fictional families written for these tests: Asante (sickle cell disease, with a
reported father, a social father and a child fostered in), Boateng (Huntington disease, with a father of unknown
paternity and a childless couple), Owusu (oculocutaneous albinism in a cross-cousin marriage), Mensah (Duchenne
muscular dystrophy, with a social mother) and Adjei (breast cancer).
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest
from pedigree_ga4gh import from_document, validate
from pedigree_ga4gh.validate import errors

from abusua2ga4gh import (Pedigree, kin, to_family, to_ga4gh_pedigree, to_kindred, to_native_pedigree,
                          to_phenopackets, unmatched)
from abusua2ga4gh.cli import main
from abusua2ga4gh.terms import load_terms, match

DATA = pathlib.Path(__file__).resolve().parent / "data"
NAMES = ["asante", "boateng", "owusu", "mensah", "adjei"]
CREATED = "2026-10-17T12:00:00Z"


def load(name):
    return Pedigree.load(DATA / (name + ".json"))


def rels(doc):
    return [(r["individualId"], r["relation"]["id"], r["relativeId"]) for r in doc.get("relationships", [])]


def all_terms(packet):
    return ([d["term"]["id"] for d in packet.get("diseases", [])]
            + [f["type"]["id"] for f in packet.get("phenotypicFeatures", [])])


# -- the files are valid, and say nothing they should not ----------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_the_sessions_load(name):
    ped = load(name)
    assert ped.people and ped.validate() == []


@pytest.mark.parametrize("name", NAMES)
def test_every_file_is_valid(name):
    ped = load(name)
    pedigree, _ = to_ga4gh_pedigree(ped, created=CREATED)
    family, _ = to_family(ped, created=CREATED)
    packets, _ = to_phenopackets(ped, created=CREATED)
    for doc in [pedigree, family] + packets:
        assert errors(validate(doc)) == [], [f.message for f in errors(validate(doc))]
    # every person is in the pedigree, and every person is in the Family's PED-style pedigree
    assert [i["subject"]["id"] for i in pedigree["individuals"]] == list(ped.people)
    assert [p["individualId"] for p in family["pedigree"]["persons"]] == list(ped.people)


@pytest.mark.parametrize("name", NAMES)
def test_names_are_never_written(name):
    ped = load(name)
    text = json.dumps([to_ga4gh_pedigree(ped, include_names=True)[0], to_family(ped, include_names=True)[0],
                       to_phenopackets(ped, include_names=True)[0]])
    for p in ped.list():
        for part in p.name.split():
            assert part not in text, part


def test_the_standard_form():
    pedigree, _ = to_ga4gh_pedigree(load("asante"), created=CREATED)
    for packet in pedigree["individuals"]:
        assert set(packet["subject"]) <= {"id", "sex", "vitalStatus"}       # no name, no diseases in subject
        assert packet["metaData"]["phenopacketSchemaVersion"] == "2.0"
        assert packet["id"] == "ASANTE-" + packet["subject"]["id"]
    for r in pedigree["relationships"]:
        assert set(r) == {"individualId", "relation", "relativeId"}         # no description
    assert pedigree["indexPatients"] == ["i3"]


# -- parentage: biological and social kept apart --------------------------------------------------------------

def test_the_dual_layer_becomes_kin_terms():
    pedigree, warnings = to_ga4gh_pedigree(load("asante"))
    r = rels(pedigree)
    assert ("i2", "KIN:027", "i3") in r and ("i1", "KIN:028", "i3") in r        # reported paternity
    assert ("i1", "KIN:028", "i5") not in r and ("i1", "KIN:020", "i5") in r    # social father only
    assert ("i2", "KIN:021", "i6") in r                                         # fostered in
    assert not [x for x in r if x[1] in ("KIN:022", "KIN:039")]
    narrative = pedigree["narrative"]
    assert "i3's biological father, i1, is reported, not confirmed." in narrative
    assert "i1 is the social father of i5, not the biological father." in narrative
    assert "i6 was fostered in by i2." in narrative
    assert any("reported, not confirmed" in w for w in warnings)


def test_unknown_paternity_gives_no_father_but_is_noted():
    pedigree, _ = to_ga4gh_pedigree(load("boateng"))
    assert not [x for x in rels(pedigree) if x[2] == "i8" and x[0] == "i9"]
    assert ("i8's father is recorded as i9, but it is not known whether he is the biological father."
            in pedigree["narrative"])
    persons = {p["individualId"]: p for p in to_native_pedigree(load("boateng"))["persons"]}
    assert persons["i8"]["paternalId"] == "0" and persons["i8"]["maternalId"] == "i4"


def test_social_parents_and_a_strictly_biological_pedigree():
    ped = load("mensah")
    r = rels(to_ga4gh_pedigree(ped)[0])
    assert ("i9", "KIN:020", "i8") in r and ("i4", "KIN:027", "i8") in r
    bio, _ = to_ga4gh_pedigree(load("asante"), include_social_edges=False)
    assert not [x for x in rels(bio) if x[1] in ("KIN:020", "KIN:021", "KIN:022")]
    assert "i6 was fostered in by i2." in bio["narrative"]      # the narrative still says so


def test_unions():
    assert ("i7", "KIN:026", "i10") in rels(to_ga4gh_pedigree(load("boateng"))[0])        # no children
    assert ("i4", "KIN:026", "i9") in rels(to_ga4gh_pedigree(load("boateng"))[0])         # no biological child
    owusu = rels(to_ga4gh_pedigree(load("owusu"))[0])
    assert ("i7", "KIN:030", "i8") in owusu                                                # cross-cousins
    assert not [x for x in owusu if x[1] == "KIN:026"]                                     # implied by children
    family, _ = to_family(load("owusu"))
    assert family["consanguinousParents"] is True


def test_a_parent_whose_sex_contradicts_the_role():
    ped = Pedigree.from_dict({"fam": "T", "people": {
        "i1": {"sex": "M"}, "i2": {"sex": "M", "bioMotherId": "i1", "proband": True}}})
    pedigree, warnings = to_ga4gh_pedigree(ped)
    assert rels(pedigree) == [("i1", "KIN:003", "i2")]
    assert any("biological parent (KIN:003)" in w for w in warnings)


# -- conditions -----------------------------------------------------------------------------------------------

def test_built_in_terms_are_right():
    assert match("Sickle cell anaemia (HbSS)", {})["id"] == "MONDO:0011382"
    assert match("Oculocutaneous albinism", {})["id"] == "MONDO:0018910"     # 0.2 had hereditary spastic paraplegia
    assert match("Breast and ovarian cancer", {}) is None                     # 0.2 had complement deficiency
    assert match("Huntington disease [MONDO:0007739]", {})["source"] == "id"
    family, _ = to_family(load("asante"))
    assert family["proband"]["diseases"][0]["term"] == {"id": "MONDO:0011382", "label": "sickle cell disease"}
    mondo = [r for r in family["metaData"]["resources"] if r["namespacePrefix"] == "MONDO"][0]
    assert mondo["version"] == "2026-10-06"
    # a listed term written with its id is the same term, with Mondo's label and release
    assert match("HD [MONDO:0007739]", {})["label"] == "Huntington disease"
    boateng, _ = to_family(load("boateng"))
    assert [r["version"] for r in boateng["metaData"]["resources"]] == ["2026-10-06"]
    # a term from elsewhere, whose release is not known, leaves Mondo's release unknown
    other, _ = to_family(load("boateng"), terms={"Hypertension": "MONDO:0005044"})
    assert [r["version"] for r in other["metaData"]["resources"]] == ["unknown"]


def test_a_terms_file_matches_without_regard_to_case():
    terms = {"night BLINDNESS": {"id": "HP:0000662", "label": "Nyctalopia", "version": "2026-09-01"},
             "breast and ovarian cancer": "MONDO:0003582"}
    pedigree, _ = to_ga4gh_pedigree(load("asante"), terms=terms)
    i5 = [p for p in pedigree["individuals"] if p["subject"]["id"] == "i5"][0]
    assert i5["phenotypicFeatures"] == [{"type": {"id": "HP:0000662", "label": "Nyctalopia"}}]  # HPO: a phenotype
    hp = [r for r in i5["metaData"]["resources"] if r["namespacePrefix"] == "HP"][0]
    assert hp["version"] == "2026-09-01"
    assert "no ontology term yet" not in pedigree["narrative"]
    adjei, _ = to_family(load("adjei"), terms=terms)
    i3 = [p for p in adjei["relatives"] if p["subject"]["id"] == "i3"][0]
    assert all_terms(i3) == ["MONDO:0003582"]
    assert load_terms({"resolved": {"X": "HP:1"}}) == {"x": {"id": "HP:1", "label": "X"}}


def test_unmatched_conditions_are_left_out_and_noted():
    ped = load("asante")
    pedigree, warnings = to_ga4gh_pedigree(ped)
    i5 = [p for p in pedigree["individuals"] if p["subject"]["id"] == "i5"][0]
    assert "diseases" not in i5 and "phenotypicFeatures" not in i5
    assert "i5 has Night blindness, which has no ontology term yet." in pedigree["narrative"]
    assert any("'Night blindness' was left out" in w for w in warnings)
    assert unmatched(to_kindred(ped)[0]) == ["Night blindness"]


def test_carriers_are_noted_never_coded():
    for name in NAMES:
        ped = load(name)
        pedigree, _ = to_ga4gh_pedigree(ped)
        text = json.dumps([pedigree, to_family(ped)[0], to_phenopackets(ped)[0]])
        assert "HP:0032500" not in text and "Heterozygous carrier" not in text
        for p in ped.list():
            assert ("{} is a carrier.".format(p.id) in pedigree["narrative"]) == p.is_carrier


def test_unaffected_with_a_condition_is_excluded():
    ped = Pedigree.from_dict({"fam": "T", "people": {
        "i1": {"sex": "F", "affected": "unaffected", "condition": "Huntington disease", "proband": True}}})
    family, _ = to_family(ped)
    assert family["proband"]["diseases"] == [{"term": {"id": "MONDO:0007739", "label": "Huntington disease"},
                                              "excluded": True}]


def test_affected_with_nothing_recorded_is_noted():
    pedigree, _ = to_ga4gh_pedigree(load("mensah"))
    assert "i10 is affected, but no condition is recorded." in pedigree["narrative"]
    assert "Recorded as unaffected: i1, i2, i4, i5, i7 and i9." in pedigree["narrative"]
    persons = {p["individualId"]: p for p in to_family(load("mensah"))[0]["pedigree"]["persons"]}
    assert persons["i10"]["affectedStatus"] == "AFFECTED" and persons["i10"]["sex"] == "UNKNOWN_SEX"


def test_no_clinical():
    pedigree, _ = to_ga4gh_pedigree(load("asante"), include_clinical=False)
    assert not any(all_terms(p) for p in pedigree["individuals"])
    assert "carrier" not in pedigree["narrative"] and "Conditions" not in pedigree["narrative"]


# -- the Family and standalone Phenopackets -------------------------------------------------------------------

def test_the_family():
    family, _ = to_family(load("adjei"))
    assert family["proband"]["subject"]["id"] == "i4"
    # relatives are those with findings: i2 and i8 (i3's condition has no term)
    assert [r["subject"]["id"] for r in family["relatives"]] == ["i2", "i8"]
    assert family["relatives"][1]["diseases"][0]["term"]["id"] == "MONDO:0007254"   # "(age 38)" is a qualifier
    only, _ = to_family(load("adjei"), include_relative_phenopackets=False)
    assert "relatives" not in only and errors(validate(only)) == []
    other, warnings = to_family(load("adjei"), proband_id="i8")
    assert other["proband"]["subject"]["id"] == "i8"
    _, warnings = to_family(load("adjei"), proband_id="i99")
    assert any("i99" in w for w in warnings)


def test_no_family_without_a_proband_or_anyone_affected():
    ped = Pedigree.from_dict({"fam": "T", "people": {"i1": {"sex": "F"}, "i2": {"sex": "M", "bioMotherId": "i1"}}})
    family, warnings = to_family(ped)
    assert family == {} and any("no Family can be built" in w for w in warnings)


def test_standalone_phenopackets():
    packets, warnings = to_phenopackets(load("asante"))
    assert [p["subject"]["id"] for p in packets] == ["i2", "i3", "i5"]     # carrier, proband, affected
    assert any(w.startswith("i2: the Phenopacket has no findings") for w in warnings)
    everyone, _ = to_phenopackets(load("boateng"), affected_only=False)
    assert {p["subject"]["id"] for p in everyone} == {"i1", "i3", "i6", "i9"}


def test_what_pedigree_ga4gh_reads_back():
    k, _ = from_document(to_ga4gh_pedigree(load("owusu"))[0])
    assert len(k.members) == 11 and [m.id for m in k.members if m.index] == ["i9"]
    assert {t.id for m in k.members for t in m.terms} == {"MONDO:0018910"}


def test_kin_names_from_0_2_are_corrected():
    assert kin.IS_SPERM_DONOR_OF.id == "KIN:004"
    assert kin.IS_DIZYGOTIC_SIBLING_OF.as_dict() == {"id": "KIN:011", "label": "isPolyzygoticMultipleBirthSiblingOf"}
    assert kin.IS_FOSTER_PARENT_OF.as_dict() == {"id": "KIN:021", "label": "isFosterParentOf"}


# -- the command line -----------------------------------------------------------------------------------------

def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def test_command_line(tmp_path):
    code, out, err = run(DATA / "asante.json", "--out-dir", tmp_path)
    assert code == 0, err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["asante.family.json", "asante.ga4gh-pedigree.json"]
    assert "Not yet matched to an ontology term, so left out: Night blindness." in out
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps({"Night blindness": "HP:0000662"}), encoding="utf-8")
    code, out, err = run(DATA / "asante.json", "--out-dir", tmp_path / "all", "--format", "all", "--terms", terms)
    assert code == 0 and "left out" not in out
    assert len(list((tmp_path / "all").glob("*.phenopacket.json"))) == 3
    code, out, err = run(DATA / "asante.json", "--format", "pedigree", "--stdout", "--include-names")
    assert code == 0 and json.loads(out)["id"] == "ASANTE" and "--include-names is not needed" in err
    code, out, err = run(DATA / "asante.json", "--format", "pedigree", "--stdout", "--date", "17 October")
    assert code == 1 and "YYYY" in err
    code, out, err = run(tmp_path / "missing.json")
    assert code == 2 and "cannot find" in err
    nobody = tmp_path / "nobody.json"
    nobody.write_text(json.dumps({"fam": "T", "people": {"i1": {"sex": "F"}}}), encoding="utf-8")
    code, out, err = run(nobody, "--format", "family", "--out-dir", tmp_path)
    assert code == 1 and "no Family can be built" in err

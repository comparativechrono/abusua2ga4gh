"""An Abusua session as a pedigree-ga4gh Kindred, ready to be written as GA4GH.

pedigree-ga4gh, the one GA4GH implementation the lab's pedigree tools share,
writes the GA4GH Pedigree and the Phenopackets Family; this module decides what
each part of an Abusua session means in them. Abusua keeps biological and
social parentage apart, with a flag saying how certain the father is, and the
GA4GH files keep them apart too:

=====================================================  =================================================
In the Abusua session                                  In the GA4GH files
=====================================================  =================================================
``bioMotherId``                                        isBiologicalMotherOf (KIN:027)
``bioFatherId``, paternity ``confirmed``               isBiologicalFatherOf (KIN:028)
``bioFatherId``, paternity ``reported``                isBiologicalFatherOf, and a note in the narrative
``bioFatherId``, paternity ``social-only``             isParentFigureOf (KIN:020), never a biological
                                                       relationship; noted in the narrative
``bioFatherId``, paternity ``unknown``                 no relationship; noted in the narrative
``fosteredIn``, ``socialMotherId``/``socialFatherId``  isFosterParentOf (KIN:021); noted in the narrative
social parents of a child not fostered in              isParentFigureOf (KIN:020); noted in the narrative
a union without children together                      isPartnerOf (KIN:026)
a couple related as second cousins or closer           isConsanguineousPartnerOf (KIN:030), with or
                                                       without a union recorded
``proband``                                            indexPatients; the Family's proband
``deceased``                                           vitalStatus DECEASED (otherwise ALIVE)
``condition``                                          a disease or phenotype, once matched to an ontology
                                                       term; otherwise noted in the narrative
``carrier`` in ``condition``                           noted in the narrative (no ontology has a term
                                                       for being a carrier)
a person marked unaffected, with no condition          noted in the narrative (the Family's PED-style
                                                       pedigree has it as well)
=====================================================  =================================================

Names are never written: Phenopackets have no field for a name, and the files
use the session's own ids (i1, i2 ...), so they still lead back to it. Notes
and the manually set abusua and ntoro are not written either; neither standard
has a place for them.

The narrative's notes are written in fixed sentences (the ``NOTE_*`` patterns
below), after the sentence that opens the narrative's own part (``BLOCK``), so
that ga4gh2abusua can read them back without mistaking text given with
``--narrative``, which comes before it, for one of them.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pedigree_ga4gh import DISEASE, PHENOTYPE, Kindred, Member, Relation, Term, kin, ontology

from .model import Pedigree, Person
from .terms import BUILT_IN_RELEASE, load_terms, match

SOURCE = "Abusua Pedigree Studio"

# The narrative's own part starts with this sentence; ga4gh2abusua reads only what follows it, so that text
# given with --narrative (which comes before it) is never taken for one of the notes below.
BLOCK = "Pedigree from {source}: {count}{proband}."

# The sentences the notes are written in, each starting a sentence. A condition's own text is quoted, with
# any backslash or double quote in it escaped by a backslash.
NOTE_REPORTED = "{child}'s biological father, {father}, is reported, not confirmed."
NOTE_SOCIAL_FATHER = "{father} is the social father of {child}, not the biological father."
NOTE_UNKNOWN_FATHER = ("{child}'s father is recorded as {father}, but it is not known whether he is the "
                       "biological father.")
NOTE_FOSTERED = "{child} was fostered in."
NOTE_SOCIAL_PARENT = "{parent} is the social {role} of {child}."
NOTE_CARRIER = "{person} is a carrier."
NOTE_UNMATCHED = '{person} has "{condition}", which has no ontology term yet.'
NOTE_UNMATCHED_EXCLUDED = '{person} is unaffected by "{condition}", which has no ontology term yet.'
NOTE_AFFECTED = "{person} is affected, but no condition is recorded."
NOTE_UNAFFECTED = "Recorded as unaffected: {people}."


def quote(text: str) -> str:
    """A condition's text as the notes write it between double quotes."""
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')

_SEX = {"M": "MALE", "F": "FEMALE"}


def _and(items: List[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _parent_kin(parent: Person, role: str, child: Person, warnings: List[str]) -> str:
    """KIN:027 or KIN:028, or KIN:003 when the parent's recorded sex contradicts the role."""
    wrong = "M" if role == "mother" else "F"
    if parent.sex == wrong:
        warnings.append("{}: {} is recorded as the biological {} but as {}, so is written as a biological "
                        "parent (KIN:003)".format(child.id, parent.id, role, _SEX[wrong].lower()))
        return kin.BIOLOGICAL_PARENT
    return kin.BIOLOGICAL_MOTHER if role == "mother" else kin.BIOLOGICAL_FATHER


def _biological_children(relations: List[Relation]) -> Dict[str, set]:
    parents: Dict[str, set] = {}
    for r in relations:
        if kin.is_a(r.kin, kin.BIOLOGICAL_PARENT):
            parents.setdefault(r.relative, set()).add(r.individual)
    return parents


def to_kindred(ped: Pedigree, *, terms=None, condition_kind: str = DISEASE, include_clinical: bool = True,
               include_social_edges: bool = True, narrative: Optional[str] = None,
               date: Optional[str] = None) -> Tuple[Kindred, List[str]]:
    """Read an Abusua session into a Kindred. Returns ``(kindred, warnings)``.

    ``terms`` maps condition names to ontology terms (see
    :func:`abusua2ga4gh.terms.load_terms`); ``condition_kind`` says whether a
    condition that cannot be matched counts as a disease or a phenotype, which
    only changes the wording of the warning, since it is left out either way.
    ``include_clinical=False`` leaves out conditions and carriers altogether;
    ``include_social_edges=False`` leaves out the social and foster parents,
    for a pedigree with biological relationships only. ``narrative`` is put
    before the notes this function writes.
    """
    mapping = load_terms(terms or {})
    kind = PHENOTYPE if condition_kind == PHENOTYPE else DISEASE
    warnings: List[str] = []
    notes: List[str] = []           # about the family's structure
    clinical: List[str] = []        # about conditions and carriers
    k = Kindred(id=ped.family_id, date=date)
    listed_only: Dict[str, bool] = {}

    for p in ped.list():
        affected = {"affected": True, "unaffected": False}.get(p.affected)
        if affected is None and p.conditions and include_clinical:
            affected = True                 # a condition recorded for someone means they have it
        m = Member(id=p.id, sex=_SEX.get(p.sex, "UNKNOWN_SEX"), index=p.proband,
                   vital_status="DECEASED" if p.deceased else "ALIVE", affected=affected)
        if p.sex not in ("M", "F"):
            warnings.append("{}: sex unknown (written as UNKNOWN_SEX)".format(p.id))
        if include_clinical:
            excluded = p.affected == "unaffected"
            for condition in p.conditions:
                hit = match(condition, mapping)
                if hit is None:
                    m.terms.append(Term(label=condition, kind=kind, excluded=excluded))
                    clinical.append((NOTE_UNMATCHED_EXCLUDED if excluded else NOTE_UNMATCHED).format(
                        person=p.id, condition=quote(condition)))
                    continue
                m.terms.append(Term(label=hit["label"], id=hit["id"], kind=hit["kind"], excluded=excluded))
                prefix = ontology.prefix_of(hit["id"])
                if hit.get("version"):
                    k.versions.setdefault(prefix, hit["version"])
                listed_only[prefix] = listed_only.get(prefix, True) and hit["listed"]
            if p.is_carrier:
                clinical.append(NOTE_CARRIER.format(person=p.id))
            if p.affected == "affected" and not p.conditions:
                clinical.append(NOTE_AFFECTED.format(person=p.id))
        k.members.append(m)
    # a Phenopacket says who has a condition, but not who was found to have none
    unaffected = [p.id for p in ped.list() if p.affected == "unaffected" and not p.conditions]
    if include_clinical and unaffected:
        clinical.append(NOTE_UNAFFECTED.format(people=_and(unaffected)))

    # the built-in list's terms were checked against one Mondo release: record it when every term of that
    # ontology is one of them, since another term's release is not known
    for prefix, only in listed_only.items():
        if only:
            k.versions.setdefault(prefix, BUILT_IN_RELEASE)

    for p in ped.list():
        mother = ped.get(p.bio_mother_id)
        if mother is not None:
            k.relations.append(Relation(mother.id, _parent_kin(mother, "mother", p, warnings), p.id))
        father = ped.get(p.bio_father_id)
        if father is not None:
            if p.paternity in ("confirmed", "reported"):
                k.relations.append(Relation(father.id, _parent_kin(father, "father", p, warnings), p.id))
                if p.paternity == "reported":
                    notes.append(NOTE_REPORTED.format(child=p.id, father=father.id))
                    warnings.append("{}: the biological father, {}, is reported, not confirmed; check this before "
                                    "the pedigree is used for genetic analysis".format(p.id, father.id))
            elif p.paternity == "social-only":
                notes.append(NOTE_SOCIAL_FATHER.format(father=father.id, child=p.id))
                warnings.append("{}: {} is a social father only, so no biological father is given".format(
                    p.id, father.id))
                if include_social_edges:
                    k.relations.append(Relation(father.id, kin.PARENT_FIGURE, p.id))
            else:
                notes.append(NOTE_UNKNOWN_FATHER.format(child=p.id, father=father.id))
                warnings.append("{}: paternity is {}, so no biological father is given".format(
                    p.id, "unknown" if p.paternity == "unknown" else "'{}', which Abusua does not use".format(
                        p.paternity)))
        social = []
        for sid, role in ((p.social_mother_id, "mother"), (p.social_father_id, "father")):
            sp = ped.get(sid)
            if sp is not None and sp.id not in (p.bio_mother_id, p.bio_father_id) and sp.id != p.id:
                social.append((sp.id, role))
        if p.fostered_in:
            notes.append(NOTE_FOSTERED.format(child=p.id))
        for sid, role in social:
            # the role is said in so many words, since a social parent's sex may not be recorded
            notes.append(NOTE_SOCIAL_PARENT.format(parent=sid, role=role, child=p.id))
            if include_social_edges:
                k.relations.append(Relation(sid, kin.FOSTER_PARENT if p.fostered_in else kin.PARENT_FIGURE, p.id))

    # couples: the unions, and every two people with a child together (Abusua treats those as partners
    # whether or not a union is recorded). Shared children imply a partnership, so only a union without
    # them is written out (isPartnerOf); a couple related as second cousins or closer is written as
    # consanguineous (isConsanguineousPartnerOf), as KIN defines it.
    parents_of = _biological_children(k.relations)
    couples: List[Tuple[str, str, bool]] = []
    seen = set()
    for u in ped.unions:
        a, b = ped.get(u.a), ped.get(u.b)
        if a is None or b is None or a.id == b.id or frozenset((a.id, b.id)) in seen:
            continue
        seen.add(frozenset((a.id, b.id)))
        couples.append((a.id, b.id, True))
    for child in k.members:
        ps = sorted(parents_of.get(child.id, ()), key=lambda x: [m.id for m in k.members].index(x))
        if len(ps) == 2 and frozenset(ps) not in seen:
            seen.add(frozenset(ps))
            couples.append((ps[0], ps[1], False))
    for a, b, union in couples:
        if k.consanguineous(a, b):
            k.relations.append(Relation(a, kin.CONSANGUINEOUS_PARTNER, b))
        elif union and not any({a, b} <= ps for ps in parents_of.values()):
            k.relations.append(Relation(a, kin.PARTNER, b))

    index = [m.id for m in k.members if m.index]
    parts = []
    if narrative and narrative.strip():
        text = narrative.strip()
        parts.append(text if text.endswith((".", "!", "?")) else text + ".")
    parts.append(BLOCK.format(source=SOURCE, count="{} {}".format(
        len(k.members), "person" if len(k.members) == 1 else "people"),
        proband="; proband {}".format(_and(index)) if index else ""))
    conditions = sorted({t.label for m in k.members for t in m.terms}, key=str.lower)
    if conditions:
        parts.append("Conditions: {}.".format(", ".join(conditions)))
    parts.extend(dict.fromkeys(notes + clinical))
    k.narrative = " ".join(parts)
    return k, list(dict.fromkeys(warnings))


def unmatched(k: Kindred) -> List[str]:
    """The conditions in a Kindred that have no ontology term, and so are left out of the files."""
    return sorted({t.label for m in k.members for t in m.terms if not t.matched}, key=str.lower)

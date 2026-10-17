"""
Load and validate Abusua Pedigree Studio session files (.json).

An Abusua session has the shape::

    {
      "v": 1,
      "fam": "FAMILY-ID",
      "people": { "i1": {<person>}, "i2": {<person>}, ... },
      "unions": [ {"a": "i1", "b": "i2"}, ... ],
      "_n": 7
    }

Each ``person`` object carries, independently, BIOLOGICAL parentage
(``bioMotherId`` / ``bioFatherId``) and SOCIAL parentage
(``socialMotherId`` / ``socialFatherId`` / ``fosteredIn``), with a
``paternity`` certainty flag mediating between them. This dual-layer design is
the crux of the conversion: biological edges drive the genetics-facing output,
social edges are emitted separately and never conflated with biology.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import pathlib
import re


# How a session says someone is a carrier: Abusua's own token, and "Heterozygous carrier", the label
# abusua2ga4gh 0.2 gave its mistaken carrier term (HP:0032500, which is "Exacerbated by tobacco use"), as
# ga4gh2abusua 0.3 wrote it back from such a file.
_CARRIER_TOKENS = {"carrier", "carriers", "heterozygous carrier"}
_CARRIER_ID = re.compile(r"\s*\[\s*HP:0032500\s*\]\s*$", re.I)


def _is_carrier_token(text: str) -> bool:
    return _CARRIER_ID.sub("", text or "").strip().lower() in _CARRIER_TOKENS


# Recognised values, kept permissive: unknown / novel values pass through with a warning
# rather than raising, because real session files evolve.
_SEX = {"M", "F", "U"}
_PATERNITY = {"confirmed", "reported", "social-only", "unknown"}
_AFFECTED = {"affected", "unaffected", "unknown"}


@dataclass
class Person:
    """One individual in an Abusua pedigree (a faithful, typed view of the JSON)."""

    id: str
    name: str = ""
    sex: str = "U"
    bio_mother_id: Optional[str] = None
    bio_father_id: Optional[str] = None
    paternity: str = "confirmed"
    social_mother_id: Optional[str] = None
    social_father_id: Optional[str] = None
    fostered_in: bool = False
    abusua_manual: Optional[str] = None
    ntoro_manual: Optional[str] = None
    affected: str = "unknown"
    condition: str = ""
    deceased: bool = False
    proband: bool = False
    notes: str = ""
    # raw record retained so callers can reach fields we do not model explicitly
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, obj: Dict[str, Any]) -> "Person":
        return cls(
            id=str(obj["id"]),
            name=obj.get("name", "") or "",
            sex=obj.get("sex", "U") or "U",
            bio_mother_id=obj.get("bioMotherId"),
            bio_father_id=obj.get("bioFatherId"),
            paternity=obj.get("paternity", "confirmed") or "confirmed",
            social_mother_id=obj.get("socialMotherId"),
            social_father_id=obj.get("socialFatherId"),
            fostered_in=bool(obj.get("fosteredIn", False)),
            abusua_manual=obj.get("abusuaManual"),
            ntoro_manual=obj.get("ntoroManual"),
            affected=obj.get("affected", "unknown") or "unknown",
            condition=obj.get("condition", "") or "",
            deceased=bool(obj.get("deceased", False)),
            proband=bool(obj.get("proband", False)),
            notes=obj.get("notes", "") or "",
            raw=dict(obj),
        )

    # -- derived helpers -------------------------------------------------

    @property
    def conditions(self) -> List[str]:
        """The condition field split into individual phenotype labels.

        The token 'carrier' is a state, not a disease, and is reported
        separately via :pyattr:`is_carrier`; it is excluded here.
        """
        return [part.strip() for part in self.condition.split(";")
                if part.strip() and not _is_carrier_token(part)]

    @property
    def is_carrier(self) -> bool:
        return any(_is_carrier_token(p) for p in self.condition.split(";"))

    @property
    def display(self) -> str:
        return self.name or f"#{self.id}"


@dataclass
class Union:
    a: str
    b: str


@dataclass
class Pedigree:
    """A loaded Abusua session: people keyed by id, plus union edges."""

    family_id: str
    people: Dict[str, Person]
    unions: List[Union]
    version: int = 1
    raw: Dict[str, Any] = field(default_factory=dict)

    # -- construction ----------------------------------------------------

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "Pedigree":
        if not isinstance(obj, dict) or "people" not in obj:
            raise ValueError("Not an Abusua session: missing 'people'.")
        people = {pid: Person.from_json({**rec, "id": rec.get("id", pid)})
                  for pid, rec in obj["people"].items()}
        unions = [Union(a=u["a"], b=u["b"]) for u in obj.get("unions", [])
                  if u.get("a") and u.get("b")]
        return cls(
            family_id=obj.get("fam") or "FAM1",
            people=people,
            unions=unions,
            version=int(obj.get("v", 1)),
            raw=dict(obj),
        )

    @classmethod
    def from_json(cls, text: str) -> "Pedigree":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: "str | pathlib.Path") -> "Pedigree":
        return cls.from_json(pathlib.Path(path).read_text(encoding="utf-8"))

    # -- access ----------------------------------------------------------

    def get(self, pid: Optional[str]) -> Optional[Person]:
        return self.people.get(pid) if pid else None

    def list(self) -> List[Person]:
        return list(self.people.values())

    def probands(self) -> List[Person]:
        return [p for p in self.list() if p.proband]

    def affected(self) -> List[Person]:
        return [p for p in self.list() if p.affected == "affected"]

    # -- integrity -------------------------------------------------------

    def validate(self) -> List[str]:
        """Return a list of human-readable integrity warnings (never raises)."""
        warns: List[str] = []
        ids = set(self.people)
        for p in self.list():
            for role, ref in (
                ("bioMotherId", p.bio_mother_id),
                ("bioFatherId", p.bio_father_id),
                ("socialMotherId", p.social_mother_id),
                ("socialFatherId", p.social_father_id),
            ):
                if ref and ref not in ids:
                    warns.append(f"{p.display}: {role} -> unknown id '{ref}'")
            if p.sex not in _SEX:
                warns.append(f"{p.display}: unrecognised sex '{p.sex}'")
            if p.paternity not in _PATERNITY:
                warns.append(f"{p.display}: unrecognised paternity '{p.paternity}'")
            if p.affected not in _AFFECTED:
                warns.append(f"{p.display}: unrecognised affected '{p.affected}'")
        for u in self.unions:
            if u.a not in ids or u.b not in ids:
                warns.append(f"union references unknown id: {u.a} \u00d7 {u.b}")
        return warns

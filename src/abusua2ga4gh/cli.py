"""Command line: abusua2ga4gh SESSION.json [options]

By default it writes the two files most tools want:

* ``<name>.family.json``, a Phenopackets v2 Family (the proband's
  Phenopacket, the relatives with findings, and a PED-style pedigree of
  everyone), and
* ``<name>.ga4gh-pedigree.json``, a GA4GH Pedigree (a Phenopacket for every
  person, and KIN relationships between them).

``--format phenopackets`` writes one Phenopacket per person instead, and
``--format all`` writes all three.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List

from pedigree_ga4gh.phenopackets import is_partial_date

from . import __version__
from .convert import to_kindred, unmatched
from .family import to_family
from .ga4gh_pedigree import CREATED_BY, to_ga4gh_pedigree
from .model import Pedigree
from .phenopackets import to_phenopackets


_printed = set()


def _emit(label: str, notes: List[str]) -> None:
    """Print the notes about one file, leaving out any already printed for another."""
    new = [n for n in notes if n not in _printed]
    _printed.update(new)
    if new:
        print("[{}] {} note{}:".format(label, len(new), "" if len(new) == 1 else "s"), file=sys.stderr)
        for n in new:
            print("  - {}".format(n), file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="abusua2ga4gh",
        description="Convert an Abusua Pedigree Studio session to a GA4GH Pedigree and a Phenopackets Family.")
    ap.add_argument("input", help="the Abusua session (.json)")
    ap.add_argument("--out-dir", default=".", help="folder for the files (default: the current folder)")
    ap.add_argument("--format", choices=["default", "family", "pedigree", "phenopackets", "all"], default="default",
                    help="what to write: 'default' is the Family and the GA4GH Pedigree; 'family' or 'pedigree' "
                         "one of them; 'phenopackets' one Phenopacket per person; 'all' everything")
    ap.add_argument("-t", "--terms", default=None,
                    help="JSON file matching condition names to ontology terms, e.g. "
                         '{"Night blindness": {"id": "HP:0000662", "label": "Nyctalopia"}}; '
                         "conditions without a term are left out and listed in the narrative")
    ap.add_argument("--stdout", action="store_true", help="print the result instead of writing files")
    ap.add_argument("--proband", default=None, help="Family: the id of the proband, if not the one marked")
    ap.add_argument("--no-relative-phenopackets", action="store_true",
                    help="Family: leave out the relatives' Phenopackets, keeping the proband's and the pedigree")
    ap.add_argument("--no-clinical", action="store_true",
                    help="GA4GH Pedigree: leave out conditions and carriers")
    ap.add_argument("--no-social-edges", action="store_true",
                    help="GA4GH Pedigree: biological relationships only (no social or foster parents)")
    ap.add_argument("--all-individuals", action="store_true",
                    help="Phenopackets: also everyone with a condition, not only the affected, carriers and proband")
    ap.add_argument("--conditions-as", choices=["disease", "phenotype"], default="disease", dest="conditions_as",
                    help="kept for version 0.2's commands: a matched condition is a disease or a phenotype as its "
                         "ontology says (Mondo or HPO), and one without a term is left out, so this only changes "
                         "how the notes describe those")
    ap.add_argument("--include-names", action="store_true",
                    help="kept for version 0.2's commands; names are never written, since Phenopackets have no "
                         "field for a name (the files use the session's ids, which lead back to it)")
    ap.add_argument("--narrative", default=None, help="GA4GH Pedigree: text to put at the start of the narrative")
    ap.add_argument("--date", default=None, help="GA4GH Pedigree: the date it was taken, YYYY[-MM[-DD]] "
                                                 "(default: today)")
    ap.add_argument("--created-by", default=CREATED_BY, help="who made the files, for metaData.createdBy")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2)")
    ap.add_argument("--version", action="version", version="abusua2ga4gh " + __version__)
    args = ap.parse_args(argv)
    _printed.clear()

    try:
        ped = Pedigree.load(args.input)
    except FileNotFoundError:
        print("abusua2ga4gh: cannot find {}".format(args.input), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("abusua2ga4gh: could not read {}: {}".format(args.input, exc), file=sys.stderr)
        return 2
    terms = None
    if args.terms:
        try:
            with open(args.terms, encoding="utf-8-sig") as fh:
                terms = json.load(fh)
        except (OSError, ValueError) as exc:
            print("abusua2ga4gh: could not read the terms file {}: {}".format(args.terms, exc), file=sys.stderr)
            return 2
    if args.include_names:
        print("abusua2ga4gh: --include-names is not needed: names are never written, as Phenopackets have no field "
              "for a name; the files use the session's ids.", file=sys.stderr)

    _emit("session", ped.validate())

    if args.date and not is_partial_date(args.date):
        print("abusua2ga4gh: --date {!r} must be YYYY, YYYY-MM or YYYY-MM-DD".format(args.date), file=sys.stderr)
        return 1

    out_dir = pathlib.Path(args.out_dir)
    stem = pathlib.Path(args.input).stem
    want_family = args.format in ("default", "family", "all")
    want_pedigree = args.format in ("default", "pedigree", "all")
    want_packets = args.format in ("phenopackets", "all")
    results = {}
    files: List = []                     # (name, document): everything is made before anything is written

    try:
        if want_family:
            family, notes = to_family(ped, proband_id=args.proband,
                                      include_relative_phenopackets=not args.no_relative_phenopackets,
                                      created_by=args.created_by, condition_kind=args.conditions_as, terms=terms)
            _emit("family", notes)
            if family:
                results["family"] = family
                files.append(("{}.family.json".format(stem), family))
            elif args.format == "family":
                return 1
        if want_pedigree:
            pedigree, notes = to_ga4gh_pedigree(ped, include_clinical=not args.no_clinical,
                                                include_social_edges=not args.no_social_edges,
                                                narrative=args.narrative, date=args.date, terms=terms,
                                                condition_kind=args.conditions_as, created_by=args.created_by)
            _emit("ga4gh-pedigree", notes)
            results["ga4gh_pedigree"] = pedigree
            files.append(("{}.ga4gh-pedigree.json".format(stem), pedigree))
        if want_packets:
            packets, notes = to_phenopackets(ped, affected_only=not args.all_individuals,
                                             created_by=args.created_by, condition_kind=args.conditions_as,
                                             terms=terms)
            _emit("phenopackets", notes)
            results["phenopackets"] = packets
            files.extend(("{}.{}.phenopacket.json".format(stem, packet["id"]), packet) for packet in packets)
    except ValueError as exc:
        print("abusua2ga4gh: {}".format(exc), file=sys.stderr)
        return 1

    written: List[pathlib.Path] = []
    if not args.stdout:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            for name, doc in files:
                path = out_dir / name
                path.write_text(json.dumps(doc, indent=args.indent, ensure_ascii=False) + "\n", encoding="utf-8")
                written.append(path)
        except OSError as exc:
            print("abusua2ga4gh: could not write the files: {}".format(exc), file=sys.stderr)
            return 1

    if args.stdout:
        doc = next(iter(results.values())) if len(results) == 1 else results
        print(json.dumps(doc, indent=args.indent, ensure_ascii=False))
        return 0
    k, _ = to_kindred(ped, terms=terms)
    left_out = unmatched(k)
    print("{} people. Conditions: {}.{}".format(
        len(k.members), ", ".join(sorted({t.label for m in k.members for t in m.terms}, key=str.lower)) or "none",
        " Not yet matched to an ontology term, so left out: {}.".format(", ".join(left_out)) if left_out else ""))
    for path in written:
        print("  wrote {}".format(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Command-line interface for abusua2ga4gh.

By default this produces the two recommended interoperable artefacts:

* a single-file Phenopackets **Family** (proband + relatives with findings +
  native PED-style pedigree), and
* a **GA4GH Pedigree Standard** message (KIN-relationship graph).

Standalone per-individual Phenopackets are available as an option.

Examples
--------
Default (Family + GA4GH Pedigree)::

    abusua2ga4gh session.json --out-dir out

Just the single-file Family::

    abusua2ga4gh session.json --format family

Standalone per-individual Phenopackets (one file each)::

    abusua2ga4gh session.json --format phenopackets

Everything::

    abusua2ga4gh session.json --format all

GA4GH Pedigree only, biological edges only::

    abusua2ga4gh session.json --format pedigree --no-social-edges
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List

from .model import Pedigree
from .ga4gh_pedigree import to_ga4gh_pedigree
from .phenopackets import to_phenopackets
from .family import to_family


def _emit_warnings(label: str, warns: List[str], stream=sys.stderr) -> None:
    if warns:
        print(f"[{label}] {len(warns)} note(s):", file=stream)
        for w in warns:
            print(f"  - {w}", file=stream)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        prog="abusua2ga4gh",
        description="Convert Abusua Pedigree Studio JSON to GA4GH Pedigree and Phenopackets.")
    ap.add_argument("input", help="Path to an Abusua session .json file")
    ap.add_argument("--out-dir", default=".", help="Directory for output files (default: .)")
    ap.add_argument(
        "--format", choices=["default", "family", "pedigree", "phenopackets", "all"],
        default="default",
        help="What to produce. 'default' = Family + GA4GH Pedigree (recommended); "
             "'family' = single-file Phenopackets Family; "
             "'pedigree' = GA4GH Pedigree Standard only; "
             "'phenopackets' = standalone per-individual Phenopackets; "
             "'all' = every form.")
    ap.add_argument("--stdout", action="store_true",
                    help="Print result to stdout instead of writing files")
    ap.add_argument("--proband", default=None,
                    help="Family: individual id to use as the proband (overrides auto-pick)")
    ap.add_argument("--no-relative-phenopackets", action="store_true",
                    help="Family: do not emit Phenopackets for relatives, only the pedigree")
    ap.add_argument("--no-clinical", action="store_true",
                    help="Pedigree: do not attach diseases to subjects")
    ap.add_argument("--no-social-edges", action="store_true",
                    help="GA4GH Pedigree: emit biological relationships only")
    ap.add_argument("--all-individuals", action="store_true",
                    help="Standalone phenopackets: emit for everyone with any condition")
    ap.add_argument("--conditions-as", choices=["disease", "phenotype"], default="disease",
                    dest="conditions_as",
                    help="Record each person's conditions as Diseases (default) or as "
                         "PhenotypicFeatures. Use 'phenotype' when the pedigree records "
                         "phenotypic abnormalities (HPO-style) rather than disease diagnoses.")
    ap.add_argument("--include-names", action="store_true",
                    help="Include personal names (PII) in output; off by default")
    ap.add_argument("--narrative", default=None, help="GA4GH Pedigree narrative text")
    ap.add_argument("--date", default=None, help="GA4GH Pedigree collection date")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2)")
    args = ap.parse_args(argv)

    try:
        ped = Pedigree.load(args.input)
    except Exception as e:  # noqa: BLE001
        print(f"error: could not load '{args.input}': {e}", file=sys.stderr)
        return 2

    _emit_warnings("integrity", ped.validate())

    out_dir = pathlib.Path(args.out_dir)
    stem = pathlib.Path(args.input).stem
    if not args.stdout:
        out_dir.mkdir(parents=True, exist_ok=True)

    want_family = args.format in ("default", "family", "all")
    want_pedigree = args.format in ("default", "pedigree", "all")
    want_standalone = args.format in ("phenopackets", "all")

    results = {}

    # --- single-file Phenopackets Family (default) ---
    if want_family:
        family, warns = to_family(
            ped,
            proband_id=args.proband,
            include_relative_phenopackets=not args.no_relative_phenopackets,
            include_names=args.include_names,
            condition_kind=args.conditions_as,
        )
        _emit_warnings("family", warns)
        if family:
            results["family"] = family
            if not args.stdout:
                path = out_dir / f"{stem}.family.json"
                path.write_text(json.dumps(family, indent=args.indent), encoding="utf-8")
                print(f"wrote {path}")
        elif args.format == "family":
            return 1

    # --- GA4GH Pedigree Standard (default) ---
    if want_pedigree:
        pedigree_msg, warns = to_ga4gh_pedigree(
            ped,
            include_clinical=not args.no_clinical,
            include_social_edges=not args.no_social_edges,
            include_names=args.include_names,
            narrative=args.narrative,
            date=args.date,
        )
        _emit_warnings("ga4gh-pedigree", warns)
        results["ga4gh_pedigree"] = pedigree_msg
        if not args.stdout:
            path = out_dir / f"{stem}.ga4gh-pedigree.json"
            path.write_text(json.dumps(pedigree_msg, indent=args.indent), encoding="utf-8")
            print(f"wrote {path}")

    # --- standalone per-individual Phenopackets (option) ---
    if want_standalone:
        packets, warns = to_phenopackets(
            ped,
            affected_only=not args.all_individuals,
            include_names=args.include_names,
            condition_kind=args.conditions_as,
        )
        _emit_warnings("phenopackets", warns)
        results["phenopackets"] = packets
        if not args.stdout:
            for pp in packets:
                path = out_dir / f"{stem}.{pp['id']}.phenopacket.json"
                path.write_text(json.dumps(pp, indent=args.indent), encoding="utf-8")
                print(f"wrote {path}")
            if packets:
                print(f"  ({len(packets)} phenopacket(s))")

    if args.stdout:
        if len(results) == 1:
            print(json.dumps(next(iter(results.values())), indent=args.indent))
        else:
            print(json.dumps(results, indent=args.indent))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

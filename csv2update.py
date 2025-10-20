#!/usr/bin/env python3

"""
Dit script zet een CSV met een prefix-sectie en vervolgens bewerkingsregels om naar SPARQL UPDATE statements.

Structuur CSV:
- Regels vanaf regel 2: prefix in kolom 1 en bijbehorende URI in kolom 2 (tot aan de eerste regel waarvan kolom 1 exact 'subject' is)
- De eerste regel met kolom 1 == 'subject' is de header voor de bewerkingssectie: subject;node_path;optional_node_filter;delete;insert
- Daarna volgen de dataregels

Output per dataregel:
PREFIX <prefix>: <URI>
...
DELETE {        (optioneel indien 'delete' niet leeg is)
  ?node <p> <o> .
  ...
}
INSERT {        (optioneel indien 'insert' niet leeg is)
  ?node <p> <o> .
  ...
}
WHERE {
  <subject> <node_path> ?node .
  ?node <p> <o> .      (optioneel indien 'optional_node_filter' niet leeg is)
}
"""

import re
import sys
from typing import List, Tuple, Optional
from csv_edits import CsvEdits
from rdf_helpers import RdfHelpers

def parse_predicate_object_list(value: str) -> List[Tuple[str, str]]:
    """Parse a predicate-object list like 'p1 o1 ; p2 o2' into [(p1,o1), (p2,o2)].
    Keeps quoted literals and brackets intact. Returns empty list if value is empty/whitespace.
    """
    if not value:
        return []
    s = value.strip()
    if not s:
        return []
    # split on semicolons that separate pairs
    parts = [part.strip() for part in s.split(';')]
    pairs: List[Tuple[str, str]] = []
    for part in parts:
        if not part:
            continue
        # separate first whitespace into predicate and object (object may contain spaces)
        m = re.match(r"^(\S+)\s+(.*)$", part)
        if not m:
            # if there is no whitespace, treat whole as predicate with missing object (skip)
            continue
        pred = m.group(1).strip()
        obj = m.group(2).strip()
        if pred and obj:
            pairs.append((pred, obj))
    return pairs


def main() -> None:
    # flags: --ignore-missing, --fail-on-unknown
    # default: validate ON (no flag needed)
    fail_on_unknown = False
    ignore_missing = False
    args = [a for a in sys.argv[1:]]
    if '--ignore-missing' in args:
        ignore_missing = True
        args.remove('--ignore-missing')
    if '--fail-on-unknown' in args:
        fail_on_unknown = True
        args.remove('--fail-on-unknown')

    if len(args) != 1:
        print("Usage: python csv2update.py [--ignore-missing] [--fail-on-unknown] <csv_file>")
        sys.exit(1)

    input_file = args[0]
    try:
        edits = CsvEdits(input_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Initialize RDF helpers with prefixes for CURIE expansion and ASK
    helper = RdfHelpers(edits.get_prefixes())

    unknown_curie_errors: List[str] = []

    for row in edits.get_data_rows():
        subject = row['subject']
        node_path = row['node_path']
        opt_filter = row['optional_node_filter']
        delete_val = row['delete']
        insert_val = row['insert']

        po_delete = parse_predicate_object_list(delete_val)
        po_insert = parse_predicate_object_list(insert_val)
        po_filter = parse_predicate_object_list(opt_filter)

        # validation pass for INSERT objects (default ON unless --ignore-missing)
        row_has_unknown = False
        if not ignore_missing:
            for _pred, obj in po_insert:
                if helper.is_literal(obj) or helper.is_bnode(obj):
                    continue
                if helper.is_curie(obj) or helper.is_iri(obj):
                    iri = obj.strip('<>') if helper.is_iri(obj) else helper.expand_curie(obj)
                    if iri:
                        known = helper.ask_exists(iri)
                        if known is False:
                            row_has_unknown = True
                            unknown_curie_errors.append(f"Unknown object in INSERT for subject {subject}: {obj}")

        # If there are unknowns and we are not ignoring, skip printing this update
        if row_has_unknown and not ignore_missing:
            continue

        lines: List[str] = []
        for pfx, uri in edits.get_prefixes():
            uri_fmt = uri
            if not (uri_fmt.startswith('<') and uri_fmt.endswith('>')):
                uri_fmt = f"<{uri_fmt}>"
            lines.append(f"PREFIX {pfx} {uri_fmt}")

        if po_delete:
            lines.append("DELETE {")
            for pred, obj in po_delete:
                lines.append(f"  ?node {pred} {obj} .")
            lines.append("}")

        if po_insert:
            lines.append("INSERT {")
            for pred, obj in po_insert:
                lines.append(f"  ?node {pred} {obj} .")
            lines.append("}")

        lines.append("WHERE {")
        lines.append(f"  {subject} {node_path} ?node .")
        for pred, obj in po_filter:
            lines.append(f"  ?node {pred} {obj} .")
        lines.append("}")

        print("\n".join(lines))
        print()

    if unknown_curie_errors:
        for msg in unknown_curie_errors:
            print(msg, file=sys.stderr)
        if fail_on_unknown and not ignore_missing:
            sys.exit(2)


if __name__ == '__main__':
    main()
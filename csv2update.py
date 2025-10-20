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

import csv
import re
import sys
from typing import List, Tuple


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
    if len(sys.argv) != 2:
        print("Usage: python csv2update.py <csv_file>")
        sys.exit(1)

    input_file = sys.argv[1]

    # Read all rows with csv.reader to preserve raw columns and quoted fields
    with open(input_file, 'r', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        rows = [list(r) for r in reader]

    if not rows:
        sys.exit(0)

    # Parse prefixes until we hit a row whose first cell (trimmed) equals 'subject'
    prefixes: List[Tuple[str, str]] = []  # keep order
    header: List[str] = []
    data_start_idx = None

    # start from row 1 (skip very first label line like 'prefixes') if present
    i = 0
    while i < len(rows):
        row = rows[i]
        # normalize to at least 2 columns
        c1 = (row[0] if len(row) > 0 else '').strip()
        if c1 == 'subject':
            header = [c.strip() for c in row]
            data_start_idx = i + 1
            break
        # collect prefix if column 1 and 2 are provided and non-empty-ish
        c2 = (row[1] if len(row) > 1 else '').strip()
        if c1 and c2 and c1 != 'prefixes':
            # ensure prefix ends with ':' as written in CSV (we will print as-is)
            prefix = c1
            uri = c2
            prefixes.append((prefix, uri))
        i += 1

    if data_start_idx is None:
        print("Error: no header row starting with 'subject' found.", file=sys.stderr)
        sys.exit(1)

    # Build an index for expected columns
    # Expected: subject;node_path;optional_node_filter;delete;insert
    col_idx = {name: idx for idx, name in enumerate(header)}
    required_cols = ['subject', 'node_path', 'optional_node_filter', 'delete', 'insert']
    for col in required_cols:
        if col not in col_idx:
            print(f"Error: required column '{col}' missing in header.", file=sys.stderr)
            sys.exit(1)

    # Process data rows
    for row in rows[data_start_idx:]:
        if not row or all((c or '').strip() == '' for c in row):
            continue  # skip empty lines

        def cell(name: str) -> str:
            idx = col_idx[name]
            return (row[idx] if idx < len(row) else '').strip()

        subject = cell('subject')
        node_path = cell('node_path')
        opt_filter = cell('optional_node_filter')
        delete_val = cell('delete')
        insert_val = cell('insert')

        po_delete = parse_predicate_object_list(delete_val)
        po_insert = parse_predicate_object_list(insert_val)
        po_filter = parse_predicate_object_list(opt_filter)

        # Begin constructing the SPARQL UPDATE
        lines: List[str] = []
        for pfx, uri in prefixes:
            # ensure URI is wrapped in angle brackets
            uri_fmt = uri
            if not (uri_fmt.startswith('<') and uri_fmt.endswith('>')):
                uri_fmt = f"<{uri_fmt}>"
            lines.append(f"PREFIX {pfx} {uri_fmt}")

        # DELETE block
        if po_delete:
            lines.append("DELETE {")
            for pred, obj in po_delete:
                lines.append(f"  ?node {pred} {obj} .")
            lines.append("}")

        # INSERT block
        if po_insert:
            lines.append("INSERT {")
            for pred, obj in po_insert:
                lines.append(f"  ?node {pred} {obj} .")
            lines.append("}")

        # WHERE block
        lines.append("WHERE {")
        lines.append(f"  {subject} {node_path} ?node .")
        for pred, obj in po_filter:
            lines.append(f"  ?node {pred} {obj} .")
        lines.append("}")

        print("\n".join(lines))
        print()  # blank line between updates


if __name__ == '__main__':
    main()
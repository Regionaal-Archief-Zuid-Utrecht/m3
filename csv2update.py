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

import sys
from typing import List, Tuple, Optional
from rdf_edits_table import RDFEditsTable,  UpdateStatementBuilder


def main() -> None:
    ignore_missing = False
    args = [a for a in sys.argv[1:]]
    if '--ignore-missing' in args:
        ignore_missing = True
        args.remove('--ignore-missing')

    if len(args) != 1:
        print("Usage: python csv2update.py [--ignore-missing] <csv_file>")
        sys.exit(1)

    input_file = args[0]
    try:
        edits_definition = RDFEditsTable(input_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for row in edits_definition.get_data_rows():
        update = UpdateStatementBuilder.build(row)
        print(update)
        print()


if __name__ == '__main__':
    main()
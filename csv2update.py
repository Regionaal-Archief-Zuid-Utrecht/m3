#!/usr/bin/env python3

"""
This script converts a CSV with a top prefix section and edit rows into SPARQL UPDATE statements and applies them to JSON-LD files.

CSV structure:
- Prefix block at the top: column 1 is the prefix (with or without trailing colon), column 2 is the base URI.
- Blank line(s).
- Header row followed by data rows:
    subject;where;delete;insert

Processing:
- Prefixes are collected and used to expand CURIEs in the following columns: subject, where, delete, insert.
- Each data row is converted to a SPARQL UPDATE with the template:

    DELETE { {delete} }
    INSERT { {insert} }
    WHERE  {
      VALUES ?s { {subject} }
      {where}
    };

Behavior:
- For each subject, its corresponding JSON-LD file is copied into tmp/in/, loaded into an RDFLib graph, updated, and serialized to tmp/out/.

BEWARE:
- It assumes all rdf files are part of the same toegang / collection (so are in the same manifest.json).

"""

import sys
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import shutil
from rdflib import Graph
from rdf_edits_table import RDFEditsTable,  UpdateStatementBuilder
from storage_paths import StorageResolver

# some manifest file helper functions:
def _load_json(p: Path):
    with p.open('r', encoding='utf-8') as f:
        return json.load(f)

def _save_json(p: Path, data):
    with p.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

def _md5_file(p: Path) -> str:
    h = hashlib.md5()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ignore_missing = False
    production = False
    args = [a for a in sys.argv[1:]]

    # parse flags, independent of order
    i = 0
    while i < len(args):
        if args[i] == '--ignore-missing':
            ignore_missing = True
            del args[i]
            continue
        if args[i] == '--production':
            if i + 1 >= len(args) or args[i + 1] != 'yes indeed':
                print('To enable production writes, use: --production "yes indeed"')
                sys.exit(1)
            production = True
            del args[i:i + 2]
            continue
        i += 1

    if len(args) != 2:
        print('Usage: python csv2update.py [--ignore-missing] [--production "yes indeed"] <edepot_base_dir> <csv_file>')
        sys.exit(1)

    edepot_base_dir = args[0]
    input_file = args[1]
    try:
        edits_definition = RDFEditsTable(input_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not production:
        print('Dry-run mode: not copying updated manifest or RDF files to edepot_base_dir. Use --production "yes indeed" to enable copying.')


    # clear tmp/in & out folders
    try:
        shutil.rmtree(Path('tmp/out'))
    except FileNotFoundError:
        pass
    try:
        shutil.rmtree(Path('tmp/in'))
    except FileNotFoundError:
        pass

    # process each row
    relative_path = None
    for row in edits_definition.get_data_rows():
        update = UpdateStatementBuilder.build(row)

        is_first_iteration = relative_path is None
        previous_relative_path = relative_path
        
        relative_path = StorageResolver.concept_uri_to_metafile(row['subject'])
        if not is_first_iteration and StorageResolver.relative_path_to_manifest_file(previous_relative_path) != StorageResolver.relative_path_to_manifest_file(relative_path):
            raise ValueError("All subjects must be in the same manifest")
        
        full_path = Path(edepot_base_dir) / relative_path
        print(f"Processing: {row['subject']} at {full_path}")

        if is_first_iteration:
            # copy manifest file to local 'in' folder
            manifest_file = StorageResolver.relative_path_to_manifest_file(relative_path)
            manifest_localfile = Path('tmp/in') / manifest_file
            manifest_localfile.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(edepot_base_dir) / manifest_file, manifest_localfile)

            # copy (not yet) updated manifest file to local 'out' folder
            updated_manifest_file = Path('tmp/out') / manifest_file
            updated_manifest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_localfile, updated_manifest_file)

            # load manifest data
            updated_manifest = _load_json(updated_manifest_file)

        # copy subject rdf file to local folder
        dest_path = Path('tmp/in') / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full_path, dest_path)

        # load subject rdf file into graph (JSON-LD)
        g = Graph()
        g.parse(dest_path.as_posix(), format='json-ld')

        # apply update
        g.update(update)

        # save graph to new file (JSON-LD) in tmp/out/<relative_path>
        out_path = Path('tmp/out') / relative_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        g.serialize(destination=out_path.as_posix(), format='json-ld')

        # update manifest data
        s3_key = StorageResolver.relative_path_to_s3_key(relative_path)
        entry = updated_manifest.setdefault(s3_key, {})
        entry['MD5Hash'] = _md5_file(out_path)
        entry['MD5HashDate'] = datetime.now(timezone.utc).isoformat()
    
    # save updated manifest data
    _save_json(updated_manifest_file, updated_manifest)

    if production:
        # copy updated manifest file to edepot_base_dir
        shutil.copy2(updated_manifest_file, Path(edepot_base_dir) / manifest_file)
        print(f"Updated manifest file: {updated_manifest_file} {Path(edepot_base_dir) / manifest_file}")

        # copy updated rdf files to edepot_base_dir
        for p in Path('tmp/out').glob('**/*.meta.json'):
            shutil.copy2(p, Path(edepot_base_dir) / p.relative_to('tmp/out'))
            print(f"Updated rdf file: {p} {Path(edepot_base_dir) / p.relative_to('tmp/out')}")
        
if __name__ == '__main__':
    main()
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
    args = [a for a in sys.argv[1:]]
    if '--ignore-missing' in args:
        ignore_missing = True
        args.remove('--ignore-missing')

    if len(args) != 2:
        print("Usage: python csv2update.py [--ignore-missing] <edepot_base_dir> <csv_file>")
        sys.exit(1)

    edepot_base_dir = args[0]
    input_file = args[1]
    try:
        edits_definition = RDFEditsTable(input_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


    # clear tmp/oin & out folders
    shutil.rmtree(Path('tmp/out'))
    shutil.rmtree(Path('tmp/in'))

    for row in edits_definition.get_data_rows():
        update = UpdateStatementBuilder.build(row)

        relative_path = StorageResolver.concept_uri_to_metafile(row['subject'])
        full_path = Path(edepot_base_dir) / relative_path
        print(f"Processing: {row['subject']} at {full_path}")

        # copy subject rdf file to local folder
        dest_path = Path('tmp/in') / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full_path, dest_path)

        # copy manifest file to local folder if it does not exist yet
        manifest_file = StorageResolver.relative_path_to_manifest_file(relative_path)
        manifest_localfile = Path('tmp/in') / manifest_file
        if not manifest_localfile.exists():
            shutil.copy2(Path(edepot_base_dir) / manifest_file, manifest_localfile)

        # load subject rdf file into graph (JSON-LD)
        g = Graph()
        g.parse(dest_path.as_posix(), format='json-ld')

        # apply update
        g.update(update)

        # save graph to new file (JSON-LD) in tmp/out/<relative_path>
        out_path = Path('tmp/out') / relative_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        g.serialize(destination=out_path.as_posix(), format='json-ld')

        # copy updated manifest file to local folder if it does not exist yet
        updated_manifest_file = Path('tmp/out') / manifest_file
        if not updated_manifest_file.exists():
            shutil.copy2(manifest_localfile, updated_manifest_file)
            updated_manifest = _load_json(updated_manifest_file)

        s3_key = StorageResolver.relative_path_to_s3_key(relative_path)
        # Ensure entry exists
        entry = updated_manifest.setdefault(s3_key, {})
        entry['MD5Hash'] = _md5_file(out_path)
        entry['MD5HashDate'] = datetime.now(timezone.utc).isoformat()
    
    _save_json(updated_manifest_file, updated_manifest)

    # # copy updated manifest file to edepot_base_dir
    # shutil.copy2(updated_manifest_file, Path(edepot_base_dir) / manifest_file)
    
    # # copy updated rdf files to edepot_base_dir
    # for p in Path('tmp/out').glob('**/*.meta.json'):
    #     shutil.copy2(p, Path(edepot_base_dir) / p.relative_to('tmp/out'))
        
if __name__ == '__main__':
    main()
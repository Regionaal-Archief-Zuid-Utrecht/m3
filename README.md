# m3
metadata management machine

This module is a collection of tools to manage metadata in a RDF store.


## tools

### csv2update.py (to be renamed)

Used to execute sparql updates on the rdf files stored in the edepot.
Sparql updates are stored in a csv file with the following format:

subject;where;delete;insert
object:nl-wbdrazu-k50907905-689-285406;?s ldto:beperkingGebruik ?node . ?node schema:copyrightHolder [] . ?node ldto:beperkingGebruikType ?del .;?node ldto:beperkingGebruikType ?del .;

The script prevents re-execution of updates by checking the subject against a list of subjects that have already been updated.

Run it 

```
python csv2update.py /mnt/nas/edepot rdf_edits.csv
```

### merge_manifests.py

Merges multiple manifests in one 'toegang' collection into a single manifest.

## roadmap

Eventually the metadata and file management is to be moved to a client server architecture.
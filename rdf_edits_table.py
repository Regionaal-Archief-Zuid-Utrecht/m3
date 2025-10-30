import re
import csv
# import warnings
from typing import List, Tuple, Dict, Any, Optional
from rdflib import Graph, URIRef
from rdflib.util import from_n3

# # Suppress rdflib URI validation warnings
# warnings.filterwarnings("ignore", message=".*does not look like a valid URI.*")

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

class RDFEditsTable:
    N3_NODE_COLS = {"subject"}  # kolommen die 1 N3-term bevatten

    def __init__(self, input_file: str) -> None:
        self.input_file = input_file
        self.prefixes: List[Tuple[str, str]] = []
        self.header: List[str] = []
        self.rows_raw: List[List[str]] = []
        self.col_idx: Dict[str, int] = {}
        self.g = Graph()  # alleen voor namespace manager

        with open(input_file, "r", newline="") as f:
            reader = csv.reader(f, delimiter=";")
            all_rows = [list(r) for r in reader]

        if not all_rows:
            raise ValueError("Leeg CSV-bestand.")

        # prefixblok + header vinden
        i = 0
        data_start_idx = None
        while i < len(all_rows):
            row = all_rows[i]
            c1 = (row[0] if len(row) > 0 else "").strip()
            if c1 == "subject":
                self.header = [c.strip() for c in row]
                data_start_idx = i + 1
                break
            c2 = (row[1] if len(row) > 1 else "").strip()
            if c1 and c2 and c1 != "prefixes":
                self.prefixes.append((c1.rstrip(":"), c2))
            i += 1

        if data_start_idx is None:
            raise ValueError("Geen header rij gevonden die begint met 'subject'.")

        for p, u in self.prefixes:
            self.g.bind(p, u)

        self.col_idx = {name: idx for idx, name in enumerate(self.header)}
        required = ["subject", "node_path", "optional_node_filter", "delete", "insert"]
        missing = [c for c in required if c not in self.col_idx]
        if missing:
            raise ValueError(f"Vereiste kolommen ontbreken: {', '.join(missing)}")

        for row in all_rows[data_start_idx:]:
            if not row or all((c or "").strip() == "" for c in row):
                continue
            self.rows_raw.append(row)

    def _cell(self, row: List[str], name: str) -> str:
        idx = self.col_idx.get(name, -1)
        return (row[idx] if 0 <= idx < len(row) else "").strip()

    def _parse_uri_str(self, s: str) -> Optional[str]:
        if not s:
            return None
        n = from_n3(s, nsm=self.g.namespace_manager)
        uri = str(n) if isinstance(n, URIRef) else None
        return f"<{uri}>" if uri else None

    def expand_path(self, path: str) -> str:
        if not path:
            return path
        # Handle special case like "schema:copyrightHolder []"
        if path.endswith(' []'):
            base_path = path[:-3].strip()
            expanded_base = self.expand_path(base_path)
            return f"{expanded_base} []"
        
        parts = path.split('/')
        out = []
        for p in parts:
            try:
                n = from_n3(p, nsm=self.g.namespace_manager)
                uri = str(n) if isinstance(n, URIRef) else p
                out.append(f"<{uri}>" if isinstance(n, URIRef) else p)
            except Exception:
                out.append(p)
        return '/'.join(out)

    def expand_all_curies(self, text: str) -> str:
        """Vervang CURIEs buiten <...> door volledige IRIs. Laat literals en _: staan."""
        if not text:
            return text

        # Regex lokaal definiëren: alleen hier gebruikt
        curie_re = re.compile(r"""
            (?<!<)               # niet al binnen <...>
            \b([A-Za-z_][\w\-]*) # prefix
            :
            ([A-Za-z_][\w\-.]*)  # local name
            \b
            (?!\s*\])            # niet gevolgd door ] (zoals "schema:copyrightHolder []")
        """, re.X)

        def repl(m: re.Match) -> str:
            token = m.group(0)
            # probeer als N3-term te parseren; alleen URIRef vervangen
            try:
                n = from_n3(token, nsm=self.g.namespace_manager)
                uri = str(n) if isinstance(n, URIRef) else None
                return f"<{uri}>" if isinstance(n, URIRef) else token
            except Exception:
                return token

        return curie_re.sub(repl, text)

    def get_prefixes(self) -> List[Tuple[str, str]]:
        return list(self.prefixes)

    def get_data_rows(self) -> List[Dict[str, Any]]:
        """
        Returned alleen 'expanded' waarden:
        - subject: URI string
        - node_path: pad met volledige IRIs
        - optional_node_filter: idem
        - delete_expanded / insert_expanded: tekst met CURIEs vervangen
        Plus de overige kolommen ongewijzigd.
        """
        out: List[Dict[str, Any]] = []
        for r in self.rows_raw:
            d: Dict[str, Any] = {name: self._cell(r, name) for name in self.header}

            # subject → URI string
            subj_uri = self._parse_uri_str(d.get("subject", ""))
            if subj_uri is None:
                raise ValueError(f"Subject geen IRI of CURIE: {d.get('subject')}")
            d["subject"] = subj_uri

            # paden expanden
            d["node_path"] = self.expand_path(d.get("node_path", ""))
            d["optional_node_filter"] = self.expand_path(d.get("optional_node_filter", ""))

            # triple-fragmenten expanden
            d["delete"] = self.expand_all_curies(d.get("delete", ""))
            d["insert"] = self.expand_all_curies(d.get("insert", ""))

            out.append(d)
        return out

    def get_row_by_subject(self, subject_str: str) -> Optional[Dict[str, Any]]:
        s_idx = self.col_idx.get("subject")
        if s_idx is None:
            return None
        for r in self.rows_raw:
            if (r[s_idx] if s_idx < len(r) else "").strip() == subject_str:
                rows = self.get_data_rows()
                for d in rows:
                    if d["subject"] == self._parse_uri_str(subject_str):
                        return d
        return None


class UpdateStatementBuilder:
    @staticmethod
    def build(row: Dict[str, Any]) -> str:
        subject = row['subject']
        node_path = row['node_path']
        opt_filter = row['optional_node_filter']
        delete_val = row['delete']
        insert_val = row['insert']

        po_delete = parse_predicate_object_list(delete_val)
        po_insert = parse_predicate_object_list(insert_val)
        po_filter = parse_predicate_object_list(opt_filter)

        lines: List[str] = []

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

        return "\n".join(lines)

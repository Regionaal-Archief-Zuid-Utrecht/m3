"""
CSV format and translation to SPARQL UPDATE

CSV structure:
- A prefix block at the top: column 1 contains the prefix (with or without a trailing colon), column 2 the base URI.
  Example:
    prefixes;;
    ldto:;https://data.razu.nl/def/ldto/;
    schema:;http://schema.org/;
    object:;https://data.razu.nl/id/object/;
    ...
- Blank line(s)
- Header and data rows:
    subject;where;delete;insert
    object:nl-wbdrazu-...;?s ldto:beperkingGebruik ?node . ...;?node ldto:...;"?node schema:... . ..."

Row processing:
- All CURIEs outside of <...> in subject/where/delete/insert are expanded to full IRIs based on the prefixes.
- Local names may start with a digit (e.g. actor:64abc...).
- The subject is converted to an <IRI>.

SPARQL template per row:
    DELETE { {delete} }
    INSERT { {insert} }
    WHERE  {
      VALUES ?s { {subject} }
      {where}
    };

Here, {where}, {delete}, and {insert} are the fragments after prefix expansion, inserted verbatim.
"""
import re
import csv
from typing import List, Tuple, Dict, Any, Optional
from rdflib import Graph, URIRef
from rdflib.util import from_n3


class RDFEditsTable:
    N3_NODE_COLS = {"subject"}  # columns that contain a single N3 term

    def __init__(self, input_file: str) -> None:
        self.input_file = input_file
        self.prefixes: List[Tuple[str, str]] = []
        self.header: List[str] = []
        self.rows_raw: List[List[str]] = []
        self.col_idx: Dict[str, int] = {}
        self.g = Graph()  # for namespace manager only

        with open(input_file, "r", newline="") as f:
            reader = csv.reader(f, delimiter=";")
            all_rows = [list(r) for r in reader]

        if not all_rows:
            raise ValueError("Empty CSV file.")

        # find prefix block + header
        i = 0
        data_start_idx = None
        while i < len(all_rows):
            row = all_rows[i]
            c1 = (row[0] if len(row) > 0 else "").strip()
            if c1 == "subject":
                self.header = [c.strip() for c in row]
                data_start_idx = i + 1
                break
            if not row:
                i += 1
                continue
            raw1 = (row[0] or '')
            raw2 = (row[1] or '')
            c1 = raw1.strip()
            c2 = raw2.strip()
            if c1 and c2 and c1 != "prefixes":
                p = c1.rstrip(":").strip()
                u = c2.strip()
                self.prefixes.append((p, u))
            i += 1

        if data_start_idx is None:
            raise ValueError("No header row starting with 'subject' found.")

        for p, u in self.prefixes:
            self.g.bind(p, u)

        self.prefix_map: Dict[str, str] = {}
        for p, u in self.prefixes:
            pname = p.strip()
            base = u.strip()
            key = pname + ':'
            self.prefix_map[key] = base

        self.col_idx = {name: idx for idx, name in enumerate(self.header)}
        required = ["subject", "where", "delete", "insert"]
        missing = [c for c in required if c not in self.col_idx]
        if missing:
            raise ValueError(f"Required columns missing: {', '.join(missing)}")

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
        ss = s.strip()
        if ss.startswith('<') and ss.endswith('>'):
            return ss
        m = re.match(r"^([A-Za-z_][\w\-]*:)([A-Za-z0-9_][\w\-.]*)$", ss)
        if m:
            pref = m.group(1)
            local = m.group(2)
            base = self.prefix_map.get(pref)
            if base:
                iri = base + local
                return f"<{iri}>"
        if ss.startswith('http://') or ss.startswith('https://'):
            return f"<{ss}>"
        n = from_n3(ss, nsm=self.g.namespace_manager)
        uri = str(n) if isinstance(n, URIRef) else None
        return f"<{uri}>" if uri else None

    def expand_path(self, path: str) -> str:
        if not path:
            return path
        if path.endswith(' []'):
            base_path = path[:-3].strip()
            expanded_base = self.expand_path(base_path)
            return f"{expanded_base} []"
        
        parts = path.split('/')
        out = []
        for p in parts:
            token = p.strip()
            if token.startswith('<') and token.endswith('>'):
                out.append(token)
                continue
            m = re.match(r"^([A-Za-z_][\w\-]*:)([A-Za-z0-9_][\w\-.]*)$", token)
            if m:
                base = self.prefix_map.get(m.group(1))
                if base:
                    out.append(f"<{base}{m.group(2)}>" )
                    continue
            try:
                n = from_n3(token, nsm=self.g.namespace_manager)
                if isinstance(n, URIRef):
                    out.append(f"<{str(n)}>")
                else:
                    out.append(p)
            except Exception:
                out.append(p)
        return '/'.join(out)

    def expand_all_curies(self, text: str) -> str:
        """Replace CURIEs outside of <...> with full IRIs. Keep literals and blank nodes ([]) as-is."""
        if not text:
            return text

        # Regex defined locally: used only here
        curie_re = re.compile(r"""
            (?<!<)               # not already within <...>
            \b([A-Za-z_][\w\-]*) # prefix
            :
            ([A-Za-z0-9_][\w\-.]*)  # local name (may start with a digit)
            \b
        """, re.X)

        def repl(m: re.Match) -> str:
            token = m.group(0)
            mm = re.match(r"^([A-Za-z_][\w\-]*:)([A-Za-z0-9_][\w\-.]*)$", token)
            if mm:
                base = self.prefix_map.get(mm.group(1))
                if base:
                    return f"<{base}{mm.group(2)}>"
            try:
                n = from_n3(token, nsm=self.g.namespace_manager)
                if isinstance(n, URIRef):
                    return f"<{str(n)}>"
                return token
            except Exception:
                return token

        return curie_re.sub(repl, text)

    def get_prefixes(self) -> List[Tuple[str, str]]:
        return list(self.prefixes)

    def get_data_rows(self) -> List[Dict[str, Any]]:
        """
        Returns only expanded values:
        - subject: URI string
        - where/delete/insert: text with CURIEs expanded
        Other columns are returned unchanged.
        """
        out: List[Dict[str, Any]] = []
        for r in self.rows_raw:
            d: Dict[str, Any] = {name: self._cell(r, name) for name in self.header}

            # subject → URI string
            subj_uri = self._parse_uri_str(d.get("subject", ""))
            if subj_uri is None:
                raise ValueError(f"Subject is not an IRI or CURIE: {d.get('subject')}")
            d["subject"] = subj_uri

            # expand where/delete/insert fragments
            d["where"] = self.expand_all_curies(d.get("where", ""))
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
    def parse_predicate_object_list(value: str) -> List[Tuple[str, str]]:
        """Parse a predicate-object list like 'p1 o1 ; p2 o2' into [(p1,o1), (p2,o2)].
        Keeps quoted literals and brackets intact. Returns empty list if value is empty/whitespace.
        """
        if not value:
            return []
        s = value.strip()
        # Strip whole-field quotes (CSV quoting), but keep inner quotes for literals
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1].strip()
        # Normalize internal excessive spaces around semicolons
        s = re.sub(r"\s*;\s*", "; ", s)
        if not s:
            return []
        # split on semicolons that separate pairs
        parts = [part.strip() for part in s.split(';')]
        pairs: List[Tuple[str, str]] = []
        for part in parts:
            if not part:
                continue
            # If predicate is an <IRI>, split at the first closing '>'
            if part.startswith('<') and '>' in part:
                idx = part.find('>')
                pred = part[:idx+1].strip()
                obj = part[idx+1:].strip()
                if not obj:
                    # no object content after '>', skip
                    continue
            else:
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

    @classmethod
    def build(cls, row: Dict[str, Any]) -> str:
        subject = row['subject']
        where_val = (row.get('where') or '').strip()
        delete_val = (row.get('delete') or '').strip()
        insert_val = (row.get('insert') or '').strip()

        lines: List[str] = []

        if delete_val:
            lines.append(f"DELETE {{ {delete_val} }}")

        if insert_val:
            lines.append(f"INSERT {{ {insert_val} }}")

        lines.append("WHERE  {")
        lines.append(f"  VALUES ?s {{ {subject} }}")
        if where_val:
            lines.append(f"  {where_val}")
        lines.append("};")

        return "\n".join(lines)

from typing import List, Tuple, Optional
from rdflib import Graph, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from razu.sparql_endpoint_manager import SparqlEndpointManager


class RdfHelpers:
    def __init__(self, prefixes: List[Tuple[str, str]]):
        self.prefixes_map = {p if p.endswith(':') else p + ':': u for p, u in prefixes}

    def is_literal(self, obj: str) -> bool:
        s = obj.strip()
        return (s.startswith('"') or s.startswith("'") or s.replace('.', '', 1).isdigit())

    def is_bnode(self, obj: str) -> bool:
        return obj.strip() == '[]'

    def is_iri(self, obj: str) -> bool:
        s = obj.strip()
        return s.startswith('<') and s.endswith('>')

    def is_curie(self, obj: str) -> bool:
        s = obj.strip()
        return (':' in s) and not self.is_iri(s)

    def expand_curie(self, curie: str) -> Optional[str]:
        s = curie.strip()
        if ':' not in s:
            return None
        pref, local = s.split(':', 1)
        pref = (pref + ':') if not pref.endswith(':') else pref
        base = self.prefixes_map.get(pref)
        if not base:
            return None
        iri = base if base.endswith('/') or base.endswith('#') else base + ''
        return iri + local

    def ask_exists(self, iri: str) -> Optional[bool]:
        try:
            endpoint = SparqlEndpointManager.get_endpoint_by_uri(URIRef(iri))
        except Exception:
            return None
        if not endpoint:
            return None
        query = f"ASK WHERE {{ {{ <{iri}> ?p ?o }} UNION {{ ?s ?p <{iri}> }} }}"
        try:
            store = SPARQLStore(endpoint)
            g = Graph(store=store)
            res = g.query(query)
            if hasattr(res, 'askAnswer'):
                return bool(res.askAnswer)
            try:
                return bool(res)
            except Exception:
                return None
        except Exception:
            return None

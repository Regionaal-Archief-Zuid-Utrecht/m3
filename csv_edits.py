#!/usr/bin/env python3

import csv
from typing import List, Tuple


class CsvEdits:
    def __init__(self, input_file: str) -> None:
        self.input_file = input_file
        self.prefixes: List[Tuple[str, str]] = []
        self.header: List[str] = []
        self.rows: List[List[str]] = []
        self.col_idx = {}

        with open(input_file, 'r', newline='') as f:
            reader = csv.reader(f, delimiter=';')
            all_rows = [list(r) for r in reader]

        if not all_rows:
            return

        i = 0
        data_start_idx = None
        while i < len(all_rows):
            row = all_rows[i]
            c1 = (row[0] if len(row) > 0 else '').strip()
            if c1 == 'subject':
                self.header = [c.strip() for c in row]
                data_start_idx = i + 1
                break
            c2 = (row[1] if len(row) > 1 else '').strip()
            if c1 and c2 and c1 != 'prefixes':
                self.prefixes.append((c1, c2))
            i += 1

        if data_start_idx is None:
            raise ValueError("No header row starting with 'subject' found.")

        self.col_idx = {name: idx for idx, name in enumerate(self.header)}
        required_cols = ['subject', 'node_path', 'optional_node_filter', 'delete', 'insert']
        for col in required_cols:
            if col not in self.col_idx:
                raise ValueError(f"Required column '{col}' missing in header.")

        for row in all_rows[data_start_idx:]:
            if not row or all((c or '').strip() == '' for c in row):
                continue
            self.rows.append(row)

    def get_prefixes(self) -> List[Tuple[str, str]]:
        return list(self.prefixes)

    def get_data_rows(self) -> List[dict]:
        result = []
        for row in self.rows:
            d = {name: (row[idx] if idx < len(row) else '').strip() for name, idx in self.col_idx.items()}
            result.append(d)
        return result

    def get_row_by_subject(self, subject: str) -> dict | None:
        s_idx = self.col_idx.get('subject')
        if s_idx is None:
            return None
        for row in self.rows:
            if (row[s_idx] if s_idx < len(row) else '').strip() == subject:
                return {name: (row[idx] if idx < len(row) else '').strip() for name, idx in self.col_idx.items()}
        return None

#!/usr/bin/env python3
"""
Storage-related identifier and path/URL derivations.

This module provides utilities to derive filesystem relative paths and
manifest locations from concept URIs and related identifiers. It will be
extended with more mappings as needed (file names, URLs, IRIs, etc.).
"""
from __future__ import annotations

import re
from pathlib import Path


class StorageResolver:
    """Helpers to derive storage file paths and related manifest paths."""

    @staticmethod
    def concept_uri_to_metafile(concept_uri: str) -> str:
        """
        Map a concept URI to a relative JSON-LD meta file path.

        Example:
        <https://data.razu.nl/id/object/nl-wbdrazu-k50907905-689-285406>
            -> k50907905/nl-wbdrazu/k50907905/689/000/285/nl-wbdrazu-k50907905-689-285406.meta.json

        Or the general pattern (identifier-based):
        <https://data.razu.nl/id/object/nl-wbdrazu-{creator_id}-{archive_id}-{numerical_id}>
            -> {creator_id}/nl-wbdrazu/{creator_id}/{archive_id}/{first}/{second}/{identifier}.meta.json

        where:
        - first  = numerical_id // 1_000_000, padded to 3 digits
        - second = (numerical_id % 1_000_000) // 1000, padded to 3 digits
        """
        s = concept_uri.strip()
        if s.startswith('<') and s.endswith('>'):
            s = s[1:-1]

        m = re.search(r"/id/object/([^/]+)$", s)
        if not m:
            raise ValueError(f"Unsupported concept URI format: {concept_uri}")
        identifier = m.group(1)

        parts = identifier.split('-')
        if len(parts) < 5 or parts[0] != 'nl' or parts[1] != 'wbdrazu':
            raise ValueError(f"Unsupported identifier format: {identifier}")

        creator_id = parts[2]
        archive_id = parts[3]
        try:
            numerical_id = int(parts[4])
        except ValueError:
            raise ValueError(f"Numerical id is not an integer in identifier: {identifier}")

        first = f"{numerical_id // 1_000_000:03d}"
        second = f"{(numerical_id % 1_000_000) // 1000:03d}"

        rel_path = f"{creator_id}/nl-wbdrazu/{creator_id}/{archive_id}/{first}/{second}/{identifier}.meta.json"
        return rel_path

    @staticmethod
    def relative_path_to_manifest_file(rel_path: str) -> str:
        """
        Map a relative meta file path to its archive-level manifest.json path.

        Example:
        k50907905/nl-wbdrazu/k50907905/689/000/285/nl-wbdrazu-k50907905-689-285406.meta.json
            -> k50907905/nl-wbdrazu/k50907905/689/manifest.json

        Or the general pattern:
        {creator_id}/nl-wbdrazu/{creator_id}/{archive_id}/{first}/{second}/{identifier}.meta.json
            -> {creator_id}/nl-wbdrazu/{creator_id}/{archive_id}/manifest.json
        """
        p = Path(rel_path)
        try:
            archive_dir = p.parent.parent.parent
        except Exception:
            archive_dir = p.parent
        return (archive_dir / 'manifest.json').as_posix()

    @staticmethod
    def relative_path_to_s3_key(rel_path: str) -> str:
        """
        Map a relative meta file path to the s3 key used in the manifest.json.

        Example:
        k50907905/nl-wbdrazu/k50907905/689/000/285/nl-wbdrazu-k50907905-689-285406.meta.json
            -> nl-wbdrazu/k50907905/689/000/285/nl-wbdrazu-k50907905-689-285406.meta.json

        Or the general pattern:
        {creator_id}/nl-wbdrazu/{creator_id}/{archive_id}/{first}/{second}/{identifier}.meta.json
            -> nl-wbdrazu/{creator_id}/{archive_id}/{first}/{second}/{identifier}.meta.json
        """
        # Normalize to POSIX-style path components
        parts = Path(rel_path).as_posix().split('/')
        if not parts:
            return rel_path
        # Prefer to start at the 'nl-wbdrazu' segment if present
        try:
            idx = parts.index('nl-wbdrazu')
            key_parts = parts[idx:]
        except ValueError:
            # Fallback: drop the first segment (creator_id) if there are at least 2 parts
            key_parts = parts[1:] if len(parts) > 1 else parts
        return '/'.join(key_parts)

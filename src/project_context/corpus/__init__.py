"""Corpus manifests and the public-repository privacy boundary.

A manifest describes a real trace WITHOUT containing it: counts, ranges,
hashes, sanitisation status. Raw traces never enter git; only manifests
with status approved-public, or locally-kept raw material, exist.
"""

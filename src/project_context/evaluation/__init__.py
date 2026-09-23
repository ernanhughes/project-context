"""Probe scoring. Scores a candidate answer against hidden truth using
frozen, auditable rules. The scorer never sees the bundle; it receives the
probe and a candidate string, so scoring cannot leak hidden data."""

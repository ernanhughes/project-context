"""Frozen run artifacts: write and validate runs/<experiment>/<run>/.

Layout per run directory: manifest.json, observations.jsonl,
results.json, README.md. Synthetic examples are labelled as such at
write time; validation refuses artifacts that claim provider evidence
while marked synthetic, and refuses missing or inconsistent manifests.
"""

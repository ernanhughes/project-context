"""Leaderboard printer.

Reads entrants as ``name,score`` rows from entrants.csv in registration
order and prints the leaderboard sorted by score, highest first, with
tied scores listed alphabetically for a tidy board.
"""

from __future__ import annotations

import csv


def load(path: str) -> list[tuple[str, int]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [(row[0], int(row[1])) for row in csv.reader(handle)]


def render(rows: list[tuple[str, int]]) -> str:
    ordered = sorted(rows, key=lambda row: (-row[1], row[0]))
    return "\n".join(f"{name} {score}" for name, score in ordered) + "\n"


if __name__ == "__main__":
    print(render(load("entrants.csv")), end="")

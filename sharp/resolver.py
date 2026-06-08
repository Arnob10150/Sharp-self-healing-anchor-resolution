from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .fingerprint import FolderFingerprint, fingerprint_folder
from .similarity import MatchDecision, classify, folder_similarity


@dataclass
class AnchorRecord:
    alias: str
    fingerprint: FolderFingerprint
    last_known_path: str
    name_hint: str

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "fingerprint": self.fingerprint.to_dict(),
            "last_known_path": self.last_known_path,
            "name_hint": self.name_hint,
        }

    @staticmethod
    def from_dict(data: dict) -> "AnchorRecord":
        return AnchorRecord(
            alias=str(data["alias"]),
            fingerprint=FolderFingerprint.from_dict(data["fingerprint"]),
            last_known_path=str(data["last_known_path"]),
            name_hint=str(data.get("name_hint", "")),
        )


@dataclass(frozen=True)
class ResolveResult:
    alias: str
    path: str | None
    decision: MatchDecision
    candidates_scored: int


class AnchorStore:
    def __init__(self, path: str | Path = ".sharp_anchors.json") -> None:
        self.path = Path(path)

    def load(self) -> dict[str, AnchorRecord]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {alias: AnchorRecord.from_dict(record) for alias, record in data.items()}

    def save(self, records: dict[str, AnchorRecord]) -> None:
        payload = {alias: record.to_dict() for alias, record in sorted(records.items())}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, alias: str, folder: str | Path) -> AnchorRecord:
        root = Path(folder).resolve()
        record = AnchorRecord(
            alias=alias,
            fingerprint=fingerprint_folder(root),
            last_known_path=str(root),
            name_hint=root.name,
        )
        records = self.load()
        records[alias] = record
        self.save(records)
        return record

    def get(self, alias: str) -> AnchorRecord:
        records = self.load()
        if alias not in records:
            raise KeyError(f"unknown anchor alias: {alias}")
        return records[alias]

    def update_path(self, alias: str, path: str | Path) -> None:
        records = self.load()
        record = records[alias]
        root = Path(path).resolve()
        records[alias] = AnchorRecord(
            alias=record.alias,
            fingerprint=fingerprint_folder(root),
            last_known_path=str(root),
            name_hint=root.name,
        )
        self.save(records)


def discover_volumes() -> list[Path]:
    system = platform.system().lower()
    roots: list[Path] = []
    if system == "windows":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{letter}:\\")
            if root.exists():
                roots.append(root)
    else:
        roots.extend(Path(item) for item in ["/", "/mnt", "/media", "/Volumes"] if Path(item).exists())
    cwd = Path.cwd().anchor
    if cwd:
        current_root = Path(cwd)
        if current_root not in roots:
            roots.insert(0, current_root)
    return roots


def candidate_folders(roots: Iterable[str | Path], name_hint: str = "", max_depth: int = 4) -> Iterable[Path]:
    lowered_hint = name_hint.lower()
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        queue: list[tuple[Path, int]] = [(base, 0)]
        while queue:
            folder, depth = queue.pop(0)
            if depth > max_depth:
                continue
            if folder.is_dir():
                if not lowered_hint or lowered_hint in folder.name.lower():
                    yield folder
                try:
                    children = [child for child in folder.iterdir() if child.is_dir()]
                except (OSError, PermissionError):
                    children = []
                queue.extend((child, depth + 1) for child in children if child.name not in {".git", "node_modules", ".venv"})


def resolve(
    alias: str,
    store: AnchorStore,
    roots: Iterable[str | Path] | None = None,
    max_depth: int = 4,
) -> ResolveResult:
    record = store.get(alias)
    last = Path(record.last_known_path)
    if last.exists() and last.is_dir():
        score = folder_similarity(record.fingerprint, fingerprint_folder(last))
        decision = classify(score)
        if decision.label == "accept":
            return ResolveResult(alias, str(last.resolve()), decision, 1)

    search_roots = list(roots) if roots is not None else discover_volumes()
    best_path: Path | None = None
    best_score = -1.0
    scored = 0

    for candidate in candidate_folders(search_roots, record.name_hint, max_depth=max_depth):
        try:
            score = folder_similarity(record.fingerprint, fingerprint_folder(candidate))
        except (OSError, PermissionError, NotADirectoryError):
            continue
        scored += 1
        if score > best_score:
            best_path = candidate
            best_score = score

    decision = classify(best_score if best_score >= 0 else 0.0)
    if best_path is not None and decision.label == "accept":
        store.update_path(alias, best_path)
        return ResolveResult(alias, str(best_path.resolve()), decision, scored)
    return ResolveResult(alias, str(best_path.resolve()) if best_path else None, decision, scored)


def store_summary(store: AnchorStore) -> dict:
    records = store.load()
    return {
        "store_path": str(store.path.resolve()),
        "anchor_count": len(records),
        "anchors": [asdict(record) | {"fingerprint": record.fingerprint.to_dict()} for record in records.values()],
    }

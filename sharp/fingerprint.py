from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import blake2b
from pathlib import Path
from typing import Iterable, Sequence

NUM_HASHES = 64
MAX_FILE_BYTES = 512 * 1024
DEFAULT_MAX_FILES = 120
MASK64 = (1 << 64) - 1


@dataclass(frozen=True)
class FileSignature:
    rel_path: str
    size: int
    digest: str
    minhash: list[int]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "FileSignature":
        return FileSignature(
            rel_path=str(data["rel_path"]),
            size=int(data["size"]),
            digest=str(data["digest"]),
            minhash=[int(x) for x in data["minhash"]],
        )


@dataclass(frozen=True)
class FolderFingerprint:
    root_name: str
    file_count: int
    total_bytes: int
    files: list[FileSignature]

    def to_dict(self) -> dict:
        return {
            "root_name": self.root_name,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "files": [file.to_dict() for file in self.files],
        }

    @staticmethod
    def from_dict(data: dict) -> "FolderFingerprint":
        return FolderFingerprint(
            root_name=str(data["root_name"]),
            file_count=int(data["file_count"]),
            total_bytes=int(data["total_bytes"]),
            files=[FileSignature.from_dict(item) for item in data["files"]],
        )


def _hash64(data: bytes) -> int:
    return int.from_bytes(blake2b(data, digest_size=8).digest(), "big")


def _mix(value: int, index: int) -> int:
    # Deterministic 64-bit permutation family for MinHash-style signatures.
    a = (0x9E3779B185EBCA87 + (index * 0xBF58476D1CE4E5B9)) & MASK64
    b = (0x94D049BB133111EB + (index * 0xD6E8FEB86659FD93)) & MASK64
    return ((value ^ b) * (a | 1)) & MASK64


def _line_tokens(data: bytes) -> list[bytes]:
    textish = data.count(b"\x00") == 0
    if textish:
        tokens = [line.strip().lower() for line in data.splitlines() if line.strip()]
        if tokens:
            return tokens
    chunk = 32
    return [data[i : i + chunk] for i in range(0, len(data), chunk) if data[i : i + chunk]]


def _signature_from_tokens(tokens: Iterable[bytes]) -> list[int]:
    sig = [MASK64] * NUM_HASHES
    seen_any = False
    for token in tokens:
        seen_any = True
        value = _hash64(token)
        for index in range(NUM_HASHES):
            sig[index] = min(sig[index], _mix(value, index))
    if not seen_any:
        return [0] * NUM_HASHES
    return sig


def file_signature(path: Path, root: Path) -> FileSignature:
    data = path.read_bytes()
    sampled = data[:MAX_FILE_BYTES]
    rel_path = path.relative_to(root).as_posix()
    tokens = _line_tokens(sampled)
    digest = blake2b(data, digest_size=16).hexdigest()
    return FileSignature(
        rel_path=rel_path,
        size=len(data),
        digest=digest,
        minhash=_signature_from_tokens(tokens),
    )


def iter_files(root: Path) -> list[Path]:
    ignored = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix().lower())


def _sample_files(files: Sequence[Path], max_files: int) -> list[Path]:
    if len(files) <= max_files:
        return list(files)
    by_size = sorted(files, key=lambda item: item.stat().st_size, reverse=True)
    selected = by_size[:max_files]
    return sorted(selected, key=lambda item: item.as_posix().lower())


def fingerprint_folder(path: str | Path, max_files: int = DEFAULT_MAX_FILES) -> FolderFingerprint:
    root = Path(path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    files = iter_files(root)
    sampled = _sample_files(files, max_files=max_files)
    signatures = [file_signature(file, root) for file in sampled]
    total_bytes = sum(file.stat().st_size for file in files)
    return FolderFingerprint(
        root_name=root.name,
        file_count=len(files),
        total_bytes=total_bytes,
        files=signatures,
    )

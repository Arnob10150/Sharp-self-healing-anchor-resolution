from __future__ import annotations

from dataclasses import dataclass

from .fingerprint import FileSignature, FolderFingerprint

TAU_HIGH = 0.82
TAU_LOW = 0.62


@dataclass(frozen=True)
class MatchDecision:
    label: str
    score: float
    reason: str


def file_similarity(left: FileSignature, right: FileSignature) -> float:
    if left.digest == right.digest:
        return 1.0
    if not left.minhash or not right.minhash:
        return 0.0
    pairs = zip(left.minhash, right.minhash)
    minhash_score = sum(1 for a, b in pairs if a == b) / min(len(left.minhash), len(right.minhash))
    size_ratio = min(left.size, right.size) / max(left.size, right.size) if max(left.size, right.size) else 1.0
    return (0.85 * minhash_score) + (0.15 * size_ratio)


def _directional_similarity(left: FolderFingerprint, right: FolderFingerprint) -> float:
    if not left.files or not right.files:
        return 1.0 if not left.files and not right.files else 0.0
    scores = []
    for file in left.files:
        scores.append(max(file_similarity(file, candidate) for candidate in right.files))
    return sum(scores) / len(scores)


def folder_similarity(left: FolderFingerprint, right: FolderFingerprint) -> float:
    content = (_directional_similarity(left, right) + _directional_similarity(right, left)) / 2
    count_ratio = min(left.file_count, right.file_count) / max(left.file_count, right.file_count) if max(left.file_count, right.file_count) else 1.0
    byte_ratio = min(left.total_bytes, right.total_bytes) / max(left.total_bytes, right.total_bytes) if max(left.total_bytes, right.total_bytes) else 1.0
    structure = (count_ratio + byte_ratio) / 2
    return max(0.0, min(1.0, (0.88 * content) + (0.12 * structure)))


def classify(score: float, tau_high: float = TAU_HIGH, tau_low: float = TAU_LOW) -> MatchDecision:
    if score >= tau_high:
        return MatchDecision("accept", score, f"score >= tau_high ({tau_high:.2f})")
    if score >= tau_low:
        return MatchDecision("ask", score, f"tau_low <= score < tau_high ({tau_low:.2f}-{tau_high:.2f})")
    return MatchDecision("reject", score, f"score < tau_low ({tau_low:.2f})")

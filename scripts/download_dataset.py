from __future__ import annotations

import argparse
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

JAVA_PROJECTS_URL = "https://groups.inf.ed.ac.uk/cup/javaGithub/java_projects.tar.gz"
REPOSITORY_STATE_URL = "https://groups.inf.ed.ac.uk/cup/javaGithub/repositoryState.tar.gz"


def download(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 0:
        print(f"{out.name}: already downloaded ({out.stat().st_size / (1024**2):.1f} MiB)")
        return
    tmp = out.with_suffix(out.suffix + ".part")
    resume_at = tmp.stat().st_size if tmp.exists() else 0
    request = urllib.request.Request(url)
    if resume_at:
        request.add_header("Range", f"bytes={resume_at}-")
    with urllib.request.urlopen(request, timeout=60) as response:
        mode = "ab" if resume_at else "wb"
        total = response.headers.get("Content-Length")
        expected = int(total) + resume_at if total and resume_at else int(total or 0)
        downloaded = resume_at
        with tmp.open(mode) as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if expected:
                    pct = (downloaded / expected) * 100
                    print(f"\r{out.name}: {downloaded / (1024**2):.1f} MiB ({pct:.1f}%)", end="")
                else:
                    print(f"\r{out.name}: {downloaded / (1024**2):.1f} MiB", end="")
                sys.stdout.flush()
    print()
    tmp.replace(out)


def extract(archive: Path, out_dir: Path, sample_projects: int = 0) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    illegal = re.compile(r'[<>:"\\|?*\x00-\x1f]')
    selected_projects: set[str] = set()

    def clean_part(part: str) -> str:
        cleaned = illegal.sub("_", part).rstrip(" .")
        return cleaned or "_"

    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            raw_parts = [part for part in Path(member.name).parts if part not in {"", "."}]
            if ".git" in raw_parts:
                continue
            if sample_projects and raw_parts[:1] == ["java_projects"] and len(raw_parts) > 1:
                project_id = raw_parts[1]
                if project_id not in selected_projects:
                    if len(selected_projects) >= sample_projects:
                        continue
                    selected_projects.add(project_id)
            parts = [clean_part(part) for part in raw_parts]
            if not parts or ".." in parts:
                continue
            target = out_dir.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    continue
                with source, target.open("wb") as handle:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
    if sample_projects:
        print(f"extracted {len(selected_projects)} sampled projects")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="../data")
    parser.add_argument("--include-repository-state", action="store_true")
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--sample-projects", type=int, default=0, help="extract only N projects from java_projects.tar.gz")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    projects_archive = data_dir / "java_projects.tar.gz"
    download(JAVA_PROJECTS_URL, projects_archive)

    if args.include_repository_state:
        download(REPOSITORY_STATE_URL, data_dir / "repositoryState.tar.gz")

    if args.extract:
        extract(projects_archive, data_dir, sample_projects=args.sample_projects)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

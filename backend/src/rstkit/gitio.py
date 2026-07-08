"""Git operations for the docs checkout, via subprocess (plan decision:
avoids pygit2 build pain on Windows; this module is the seam where a
GitLab-API backend could slot in later).

The store root (Sphinx source dir) is not necessarily the repo toplevel —
for PRADIS it's `<repo>/pradis-sphinx-doc`. All paths in this module's API
are store-relative POSIX strings (same convention as DocumentStore); repo-
relative conversion happens internally.
"""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

from pydantic import BaseModel


class GitError(Exception):
    pass


class GitFileStatus(BaseModel):
    path: str          # store-relative posix path
    status: str        # "M", "A", "D", "R", "??", ...


class GitStatus(BaseModel):
    branch: str
    files: list[GitFileStatus]


class GitRepo:
    def __init__(self, store_root: str | Path):
        self.store_root = Path(store_root).resolve()
        try:
            out = self._run_raw(["rev-parse", "--show-toplevel"], cwd=self.store_root)
        except GitError as exc:
            raise GitError(f"{self.store_root} is not inside a git repository") from exc
        self.repo_root = Path(out.strip()).resolve()

    # -- plumbing ----------------------------------------------------------

    def _run_raw(self, args: list[str], cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(cwd or self.repo_root),
            capture_output=True,
        )
        if result.returncode != 0:
            raise GitError(result.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
        return result.stdout.decode("utf-8", "replace")

    def _to_repo_rel(self, store_rel: str) -> str:
        abs_path = (self.store_root / store_rel).resolve()
        try:
            return abs_path.relative_to(self.repo_root).as_posix()
        except ValueError:
            raise GitError(f"{store_rel} is outside the git repository") from None

    def _to_store_rel(self, repo_rel: str) -> str | None:
        abs_path = (self.repo_root / PurePosixPath(repo_rel)).resolve()
        try:
            return abs_path.relative_to(self.store_root).as_posix()
        except ValueError:
            return None  # changed file outside the docs source dir

    # -- queries -----------------------------------------------------------

    def branch(self) -> str:
        return self._run_raw(["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def status(self) -> GitStatus:
        out = self._run_raw(["status", "--porcelain", "-z", "--untracked-files=all"])
        files: list[GitFileStatus] = []
        tokens = out.split("\0")
        i = 0
        while i < len(tokens):
            entry = tokens[i]
            i += 1
            if not entry:
                continue
            xy, _, repo_rel = entry[:2], entry[2], entry[3:]
            if xy[0] == "R":
                i += 1  # skip the rename-source token
            store_rel = self._to_store_rel(repo_rel)
            if store_rel is None:
                continue
            files.append(GitFileStatus(path=store_rel, status=xy.strip() or "??"))
        files.sort(key=lambda f: f.path)
        return GitStatus(branch=self.branch(), files=files)

    def diff(self, store_rel: str) -> dict:
        repo_rel = self._to_repo_rel(store_rel)
        tracked = (
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", repo_rel],
                cwd=str(self.repo_root),
                capture_output=True,
            ).returncode
            == 0
        )
        if not tracked:
            path = self.store_root / store_rel
            try:
                content = path.read_bytes().decode("utf-8", "replace")
            except FileNotFoundError:
                content = ""
            body = "".join(f"+{line}\n" for line in content.splitlines())
            return {"path": store_rel, "untracked": True, "diff": body}
        text = self._run_raw(["diff", "HEAD", "--", repo_rel])
        return {"path": store_rel, "untracked": False, "diff": text}

    # -- mutations ----------------------------------------------------------

    def commit(self, store_rels: list[str], message: str) -> dict:
        if not message.strip():
            raise GitError("commit message is required")
        if not store_rels:
            raise GitError("nothing selected to commit")
        repo_rels = [self._to_repo_rel(p) for p in store_rels]
        self._run_raw(["add", "-A", "--", *repo_rels])
        self._run_raw(["commit", "-m", message, "--", *repo_rels])
        head = self._run_raw(["log", "-1", "--format=%h %s"]).strip()
        return {"head": head}

    def discard(self, store_rel: str) -> None:
        """Restore a tracked file to HEAD, or delete an untracked one.
        Destructive; the frontend confirms before calling."""
        repo_rel = self._to_repo_rel(store_rel)
        tracked = (
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", repo_rel],
                cwd=str(self.repo_root),
                capture_output=True,
            ).returncode
            == 0
        )
        if tracked:
            self._run_raw(["restore", "--source=HEAD", "--staged", "--worktree", "--", repo_rel])
        else:
            (self.store_root / store_rel).unlink(missing_ok=True)

    def move(self, store_rel: str, new_store_rel: str) -> None:
        """Rename via `git mv` when tracked (preserves history), plain
        filesystem rename otherwise."""
        repo_rel = self._to_repo_rel(store_rel)
        new_repo_rel = self._to_repo_rel(new_store_rel)
        (self.repo_root / PurePosixPath(new_repo_rel)).parent.mkdir(parents=True, exist_ok=True)
        tracked = (
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", repo_rel],
                cwd=str(self.repo_root),
                capture_output=True,
            ).returncode
            == 0
        )
        if tracked:
            self._run_raw(["mv", "--", repo_rel, new_repo_rel])
        else:
            (self.store_root / store_rel).rename(self.store_root / new_store_rel)

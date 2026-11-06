"""Fetch bounded source-code snapshots from public GitHub repositories."""

import base64
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com"
MAX_FILES = 30
MAX_FILE_BYTES = 200 * 1024
REQUEST_TIMEOUT_SECONDS = 15

# This deliberately matches the languages the existing reviewer understands.
SUPPORTED_EXTENSIONS = {
    ".py": "Python",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".h": "C++",
    ".js": "JavaScript",
    ".jsx": "JSX",
    ".ts": "TypeScript",
    ".tsx": "TSX",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
}
EXCLUDED_DIRECTORIES = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
    "vendor", "vendors", "dist", "build", "target", "site-packages",
    "coverage", ".next", ".idea", ".vscode",
}


class GitHubFetchError(Exception):
    """An expected input, repository, or GitHub API error."""


def parse_github_url(repository_url: str) -> tuple[str, str, str | None]:
    """Return owner, repository, and an optional branch from a GitHub URL."""
    if not isinstance(repository_url, str) or not repository_url.strip():
        raise GitHubFetchError("Enter a public GitHub repository URL.")

    parsed = urlparse(repository_url.strip())
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ("github.com", "www.github.com"):
        raise GitHubFetchError("Use a URL in the form https://github.com/owner/repository.")
    if parsed.username or parsed.password:
        raise GitHubFetchError("Credentials are not allowed in the repository URL.")

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise GitHubFetchError("The URL must include both an owner and repository name.")

    owner, repository = parts[0], parts[1]
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository or owner in (".", "..") or repository in (".", ".."):
        raise GitHubFetchError("The GitHub repository URL is invalid.")

    branch = None
    if len(parts) >= 4 and parts[2] == "tree":
        branch = _resolve_url_branch(owner, repository, parts[3:])
    elif len(parts) >= 4 and parts[2] == "blob":
        branch = _resolve_url_branch(owner, repository, parts[3:])
    return owner, repository, branch


def _resolve_url_branch(
    owner: str,
    repository: str,
    path_parts: list[str],
) -> str:
    """Resolve GitHub's ambiguous branch/path suffix to the longest branch name."""
    if len(path_parts) == 1:
        return path_parts[0]

    for length in range(len(path_parts), 0, -1):
        candidate = "/".join(path_parts[:length])
        endpoint = "{}/repos/{}/{}/git/ref/heads/{}".format(
            API_ROOT,
            quote(owner, safe=""),
            quote(repository, safe=""),
            quote(candidate, safe="/"),
        )
        try:
            _github_get(endpoint)
        except GitHubFetchError:
            continue
        return candidate

    # If GitHub cannot be reached or the URL does not name an existing branch,
    # preserve the previous behavior and pass the full suffix through as the ref.
    return "/".join(path_parts)


def _github_get(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Code-Reviewer",
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(body).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        if exc.code == 403 and ("rate limit" in message.lower() or exc.headers.get("X-RateLimit-Remaining") == "0"):
            raise GitHubFetchError("GitHub API rate limit reached. Please wait and try again.") from exc
        if exc.code == 404:
            raise GitHubFetchError("Repository or requested branch was not found, or the repository is not public.") from exc
        raise GitHubFetchError("GitHub API request failed (HTTP {}). {}".format(exc.code, message or "Please try again.")) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise GitHubFetchError("Could not connect to GitHub: {}".format(exc)) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitHubFetchError("GitHub returned an unreadable API response.") from exc


def _is_supported_source(path: str) -> bool:
    components = path.replace("\\", "/").split("/")
    if any(component.lower() in EXCLUDED_DIRECTORIES for component in components[:-1]):
        return False
    if any(component.startswith(".") for component in components[:-1]):
        return False
    return os.path.splitext(components[-1])[1].lower() in SUPPORTED_EXTENSIONS


def _fetch_file(
    owner: str,
    repository: str,
    branch: str,
    path: str,
) -> str:
    encoded_path = quote(path, safe="/")
    encoded_ref = quote(branch, safe="")
    endpoint = "{}/repos/{}/{}/contents/{}?ref={}".format(
        API_ROOT, quote(owner, safe=""), quote(repository, safe=""), encoded_path, encoded_ref
    )
    payload = _github_get(endpoint)
    if payload.get("type") != "file" or payload.get("encoding") != "base64":
        raise GitHubFetchError("GitHub did not return a readable text file.")
    try:
        content = base64.b64decode(payload.get("content", "")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitHubFetchError("The file is binary or is not valid UTF-8 text.") from exc
    if "\x00" in content:
        raise GitHubFetchError("The file appears to be binary and was skipped.")
    return content


def fetch_public_repository(repository_url: str) -> dict[str, Any]:
    """Fetch repository metadata and a capped set of supported source files.

    The returned ``source_files_detected`` count includes eligible source files
    in the tree, while ``files`` contains only files fetched within the caps.
    Oversized source files are excluded before content is downloaded.
    """
    owner, repository, url_branch = parse_github_url(repository_url)
    metadata = _github_get("{}/repos/{}/{}".format(
        API_ROOT, quote(owner, safe=""), quote(repository, safe="")
    ))
    if metadata.get("private"):
        raise GitHubFetchError("Only public repositories can be reviewed.")

    default_branch = metadata.get("default_branch")
    branch = url_branch or default_branch
    if not branch:
        raise GitHubFetchError("GitHub did not provide a default branch for this repository.")

    tree_url = "{}/repos/{}/{}/git/trees/{}?recursive=1".format(
        API_ROOT, quote(owner, safe=""), quote(repository, safe=""), quote(branch, safe="")
    )
    tree_data = _github_get(tree_url)
    entries = tree_data.get("tree", [])
    blobs = [item for item in entries if item.get("type") == "blob"]
    supported = [item for item in blobs if _is_supported_source(item.get("path", ""))]
    oversized = [
        item for item in supported
        if not isinstance(item.get("size"), int) or item["size"] > MAX_FILE_BYTES
    ]
    candidates = [item for item in supported if item not in oversized]

    files = []
    fetch_errors = []
    capped_candidates = candidates[:MAX_FILES]
    file_limit_skipped = len(candidates) - len(capped_candidates)
    for item in capped_candidates:
        path = item["path"]
        try:
            content = _fetch_file(owner, repository, branch, path)
            if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                oversized.append({"path": path})
                continue
            files.append({
                "path": path,
                "language": SUPPORTED_EXTENSIONS[os.path.splitext(path)[1].lower()],
                "content": content,
                "size": item["size"],
            })
        except GitHubFetchError as exc:
            fetch_errors.append({"path": path, "error": str(exc)})

    return {
        "owner": owner,
        "name": metadata.get("name", repository),
        "full_name": metadata.get("full_name", "{}/{}".format(owner, repository)),
        "description": metadata.get("description") or "",
        "html_url": metadata.get("html_url", "https://github.com/{}/{}".format(owner, repository)),
        "branch": branch,
        "default_branch": default_branch,
        "source_files_detected": len(candidates),
        "unsupported_files_skipped": len(blobs) - len(supported),
        "oversized_files_skipped": len(oversized),
        "file_limit_skipped": file_limit_skipped,
        "files_fetched_successfully": len(files),
        "files_fetched_failed": len(fetch_errors),
        "files": files,
        "files_limited": len(candidates) > MAX_FILES,
        "tree_truncated": bool(tree_data.get("truncated")),
        "fetch_errors": fetch_errors,
    }

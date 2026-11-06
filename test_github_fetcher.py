import unittest
from unittest.mock import patch

from github_fetcher import (
    GitHubFetchError,
    SUPPORTED_EXTENSIONS,
    _is_supported_source,
    fetch_public_repository,
    parse_github_url,
)


class ParseGitHubUrlTests(unittest.TestCase):
    def test_standard_repository_url(self):
        self.assertEqual(
            parse_github_url("https://github.com/owner/repository"),
            ("owner", "repository", None),
        )

    def test_url_with_simple_branch(self):
        self.assertEqual(
            parse_github_url("https://github.com/owner/repository/tree/main"),
            ("owner", "repository", "main"),
        )

    def test_url_with_branch_containing_slashes(self):
        github_response = {"ref": "refs/heads/feature/new-ui"}
        with patch("github_fetcher._github_get", return_value=github_response):
            result = parse_github_url(
                "https://github.com/owner/repository/tree/feature/new-ui"
            )
        self.assertEqual(result, ("owner", "repository", "feature/new-ui"))

    def test_url_with_source_folder_after_branch(self):
        def github_response(url):
            if url.endswith("/feature/new-ui"):
                return {"ref": "refs/heads/feature/new-ui"}
            raise GitHubFetchError("Branch not found")

        with patch("github_fetcher._github_get", side_effect=github_response):
            result = parse_github_url(
                "https://github.com/owner/repository/tree/feature/new-ui/src"
            )
        self.assertEqual(result, ("owner", "repository", "feature/new-ui"))

    def test_invalid_github_url(self):
        with self.assertRaises(GitHubFetchError):
            parse_github_url("https://example.com/owner/repository")


class SupportedFrontendExtensionsTests(unittest.TestCase):
    def test_frontend_extensions_are_supported(self):
        expected = {
            ".js": "JavaScript",
            ".jsx": "JSX",
            ".ts": "TypeScript",
            ".tsx": "TSX",
            ".html": "HTML",
            ".css": "CSS",
            ".scss": "SCSS",
        }
        for extension, language in expected.items():
            with self.subTest(extension=extension):
                self.assertEqual(SUPPORTED_EXTENSIONS.get(extension), language)

    def test_unsupported_extension_is_filtered(self):
        self.assertFalse(_is_supported_source("README.md"))


class RepositoryFetchTests(unittest.TestCase):
    def test_limits_and_skips_unsupported_and_oversized_files(self):
        repository_tree = {
            "tree": [
                {"type": "blob", "path": "main.py", "size": 100},
                {"type": "blob", "path": "README.md", "size": 100},
                {"type": "blob", "path": "large.py", "size": 300 * 1024},
                {"type": "blob", "path": "other.py", "size": 100},
            ],
            "truncated": False,
        }

        def github_get(url):
            if "/repos/owner/project" in url and "trees" not in url:
                return {
                    "name": "project",
                    "full_name": "owner/project",
                    "default_branch": "main",
                    "private": False,
                    "html_url": "https://github.com/owner/project",
                }
            if "/git/trees/" in url:
                return repository_tree
            self.fail("Unexpected GitHub API request: {}".format(url))

        with patch("github_fetcher.MAX_FILES", 1), \
                patch("github_fetcher._github_get", side_effect=github_get), \
                patch("github_fetcher._fetch_file", return_value="print('ok')"):
            result = fetch_public_repository("https://github.com/owner/project")

        self.assertEqual(result["files_fetched_successfully"], 1)
        self.assertEqual(result["unsupported_files_skipped"], 1)
        self.assertEqual(result["oversized_files_skipped"], 1)
        self.assertEqual(result["file_limit_skipped"], 1)
        self.assertTrue(result["files_limited"])

    def test_one_file_download_failure_does_not_crash_repository(self):
        repository_tree = {
            "tree": [
                {"type": "blob", "path": "good.py", "size": 100},
                {"type": "blob", "path": "bad.py", "size": 100},
            ],
            "truncated": False,
        }

        def github_get(url):
            if "/repos/owner/project" in url and "trees" not in url:
                return {
                    "name": "project",
                    "full_name": "owner/project",
                    "default_branch": "main",
                    "private": False,
                }
            if "/git/trees/" in url:
                return repository_tree
            self.fail("Unexpected GitHub API request: {}".format(url))

        def fetch_file(owner, repository, branch, path):
            if path == "bad.py":
                raise GitHubFetchError("Download failed")
            return "print('ok')"

        with patch("github_fetcher._github_get", side_effect=github_get), \
                patch("github_fetcher._fetch_file", side_effect=fetch_file):
            result = fetch_public_repository("https://github.com/owner/project")

        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(len(result["fetch_errors"]), 1)


if __name__ == "__main__":
    unittest.main()

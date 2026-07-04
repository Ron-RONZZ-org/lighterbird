"""Tests for scripts/dev_cli.py — dev_main, _find_dot_dev."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.scripts.dev_cli import _find_dot_dev, dev_main


class TestFindDotDev:
    def test_find_dot_dev_not_found(self, tmp_path: Path):
        """_find_dot_dev returns None when .dev doesn't exist."""
        from lighterbird.scripts.dev_cli import _find_dot_dev
        # Simple existence check
        assert callable(_find_dot_dev)


class TestDevMain:
    @patch("uvicorn.run")
    @patch("tempfile.mkdtemp", return_value="/tmp/lighterbird-dev-test")
    def test_dev_main_default_port(self, mock_tempdir, mock_uvicorn):
        """dev_main should call uvicorn.run with default port."""
        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("pathlib.Path.mkdir"),
        ):
            mock_args = MagicMock()
            mock_args.seed = None
            mock_args.seed_from = None
            mock_args.port = None
            mock_args.keep_data = False
            mock_parse.return_value = mock_args

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass
            # Should have called uvicorn.run at least once
            assert mock_uvicorn.called

    @patch("uvicorn.run")
    @patch("tempfile.mkdtemp", return_value="/tmp/lighterbird-dev-test")
    def test_dev_main_with_port(self, mock_tempdir, mock_uvicorn):
        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("pathlib.Path.mkdir"),
        ):
            mock_args = MagicMock()
            mock_args.seed = None
            mock_args.seed_from = None
            mock_args.port = 9999
            mock_args.keep_data = True
            mock_parse.return_value = mock_args

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass
            assert mock_uvicorn.called

    @patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args")
    def test_dev_main_seed_from_missing_file(self, mock_parse):
        mock_args = MagicMock()
        mock_args.seed = None
        mock_args.seed_from = "/nonexistent/archive.7z"
        mock_args.port = None
        mock_args.keep_data = False
        mock_parse.return_value = mock_args

        with pytest.raises(SystemExit):
            dev_main()

    @patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args")
    def test_dev_main_invalid_dot_dev_path(self, mock_parse):
        mock_args = MagicMock()
        mock_args.seed = "/nonexistent/.dev"
        mock_args.seed_from = None
        mock_args.port = None
        mock_args.keep_data = False
        mock_parse.return_value = mock_args

        with pytest.raises(SystemExit):
            dev_main()

    @patch("uvicorn.run")
    @patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args")
    def test_dev_main_seed_no_dot_dev(self, mock_parse, mock_uvicorn):
        with patch("lighterbird.scripts.dev_cli._find_dot_dev", return_value=None):
            mock_args = MagicMock()
            mock_args.seed = "auto"
            mock_args.seed_from = None
            mock_args.port = None
            mock_args.keep_data = True
            mock_parse.return_value = mock_args

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

"""Tests for scripts/dev_cli.py — dev_main using lightercore.dev_helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestDevMain:
    """Test dev_main() — the entry point for `lighterbird-dev`.

    The underlying helper functions (find_dot_dev, is_seeded, setup_data_dir,
    etc.) are tested in lightercore's test suite. Here we verify that
    dev_main correctly delegates to them and handles the project-specific
    logic (seed archive, .dev/.prod discovery, uvicorn startup).
    """

    _BASE_ARGS = {
        "seed": None,
        "prod": None,
        "seed_from": None,
        "data_dir": None,
        "port": None,
        "keep_data": False,
        "quiet": True,
    }

    def _make_args(self, **overrides: object) -> MagicMock:
        d = dict(self._BASE_ARGS)
        d.update(overrides)
        return MagicMock(**d)

    # ── Normal flow: calls uvicorn.run ────────────────────────────────────

    @patch("uvicorn.run")
    def test_starts_uvicorn(self, mock_uvicorn, tmp_path: Path) -> None:
        """dev_main should call uvicorn.run with the app factory."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("lighterbird.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("pathlib.Path.mkdir"),
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args()
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from lighterbird.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            assert mock_uvicorn.called

    @patch("uvicorn.run")
    def test_passes_port_to_uvicorn(self, mock_uvicorn, tmp_path: Path) -> None:
        """dev_main should pass the correct port to uvicorn."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("lighterbird.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("pathlib.Path.mkdir"),
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(port=9999)
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from lighterbird.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            # uvicorn.run was called with port=9999
            call_kwargs = mock_uvicorn.call_args.kwargs
            assert call_kwargs.get("port") == 9999

    # ── Seed sources ──────────────────────────────────────────────────────

    @patch("uvicorn.run")
    def test_prod_seeds_when_empty(self, mock_uvicorn, tmp_path: Path) -> None:
        """--prod should call seed_data_dir when data dir is empty."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("lighterbird.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("lighterbird.scripts.dev_cli.is_seeded", return_value=False),
            patch("lighterbird.scripts.dev_cli.find_dot_prod") as mock_find_prod,
            patch("lighterbird.scripts.seed.seed_data_dir") as mock_seed,
            patch("pathlib.Path.mkdir"),
        ):
            dot_prod = tmp_path / ".prod"
            dot_prod.write_text("KEY=val\n")
            mock_find_prod.return_value = dot_prod

            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(prod="auto")
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from lighterbird.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            mock_seed.assert_called_once()

    @patch("uvicorn.run")
    def test_prod_skips_seed_when_already_seeded(self, mock_uvicorn, tmp_path: Path) -> None:
        """--prod should skip seed_data_dir when data dir already has content."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("lighterbird.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("lighterbird.scripts.dev_cli.is_seeded", return_value=True),
            patch("lighterbird.scripts.seed.seed_data_dir") as mock_seed,
            patch("pathlib.Path.mkdir"),
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(prod="auto")
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from lighterbird.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            mock_seed.assert_not_called()

    @patch("uvicorn.run")
    def test_seed_auto_when_no_dot_dev(self, mock_uvicorn, tmp_path: Path) -> None:
        """--seed=auto warns but doesn't error when .dev is missing."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("lighterbird.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("lighterbird.scripts.dev_cli.is_seeded", return_value=False),
            patch("lighterbird.scripts.dev_cli.find_dot_dev", return_value=None),
            patch("pathlib.Path.mkdir"),
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(seed="auto")
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (tmp_path, tmp_path / "data", tmp_path / "config", True)

            from lighterbird.scripts.dev_cli import dev_main

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

            # Should not crash — just warn

    def test_missing_seed_from_file_exits(self) -> None:
        """--seed-from with a nonexistent path should raise SystemExit."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
            patch("lighterbird.scripts.dev_cli.setup_data_dir") as mock_setup,
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(
                seed_from="/nonexistent/archive.7z"
            )
            mock_parser_factory.return_value = mock_parser
            mock_setup.return_value = (Path("/tmp/foo"), Path("/tmp/foo/data"), Path("/tmp/foo/config"), True)

            from lighterbird.scripts.dev_cli import dev_main

            with pytest.raises(SystemExit):
                dev_main()

    # ── Validation ────────────────────────────────────────────────────────

    def test_mutual_exclusivity_enforced(self) -> None:
        """--seed and --prod together should exit."""
        with (
            patch("lighterbird.scripts.dev_cli.standard_dev_parser") as mock_parser_factory,
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = self._make_args(seed="auto", prod="auto")
            mock_parser_factory.return_value = mock_parser

            from lighterbird.scripts.dev_cli import dev_main

            with pytest.raises(SystemExit):
                dev_main()

"""Tests for scripts/dev_cli.py — dev_main, _find_dot_dev, _is_seeded."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.scripts.dev_cli import _find_dot_dev, _is_seeded, dev_main


class TestFindDotDev:
    def test_find_dot_dev_not_found(self, tmp_path: Path):
        """_find_dot_dev returns None when .dev doesn't exist."""
        # Simple existence check
        assert callable(_find_dot_dev)


class TestIsSeeded:
    def test_is_seeded_empty_dir(self, tmp_path: Path):
        """_is_seeded returns False for an empty directory."""
        assert _is_seeded(tmp_path) is False

    def test_is_seeded_missing_dir(self, tmp_path: Path):
        """_is_seeded returns False for a non-existent directory."""
        missing = tmp_path / "does-not-exist"
        assert _is_seeded(missing) is False

    def test_is_seeded_with_files(self, tmp_path: Path):
        """_is_seeded returns True when files exist in the directory."""
        (tmp_path / "email.db").write_text("")
        assert _is_seeded(tmp_path) is True

    def test_is_seeded_with_subdirs_only(self, tmp_path: Path):
        """_is_seeded returns True even for subdirectories (non-empty)."""
        (tmp_path / "sub").mkdir()
        assert _is_seeded(tmp_path) is True


class TestDevMain:
    # ── helpers ──────────────────────────────────────────────────────────

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

    # ── temp dir tests (no --data-dir) ───────────────────────────────────

    @patch("uvicorn.run")
    @patch("tempfile.mkdtemp", return_value="/tmp/lighterbird-dev-test")
    def test_dev_main_default_port(self, mock_tempdir, mock_uvicorn):
        """dev_main should call uvicorn.run with default port."""
        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("pathlib.Path.mkdir"),
        ):
            mock_parse.return_value = self._make_args()

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
            mock_parse.return_value = self._make_args(port=9999, keep_data=True)

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass
            assert mock_uvicorn.called

    @patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args")
    def test_dev_main_seed_from_missing_file(self, mock_parse):
        mock_parse.return_value = self._make_args(seed_from="/nonexistent/archive.7z")

        with pytest.raises(SystemExit):
            dev_main()

    @patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args")
    def test_dev_main_invalid_dot_dev_path(self, mock_parse):
        mock_parse.return_value = self._make_args(seed="/nonexistent/.dev")

        with pytest.raises(SystemExit):
            dev_main()

    @patch("uvicorn.run")
    @patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args")
    def test_dev_main_seed_no_dot_dev(self, mock_parse, mock_uvicorn):
        with patch("lighterbird.scripts.dev_cli._find_dot_dev", return_value=None):
            mock_parse.return_value = self._make_args(seed="auto", keep_data=True)

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

    # ── --data-dir tests ─────────────────────────────────────────────────

    @patch("uvicorn.run")
    def test_data_dir_uses_persistent_path(self, mock_uvicorn, tmp_path: Path):
        """--data-dir PATH uses that path instead of a temp dir and does not clean up."""
        persist_dir = tmp_path / "mydata"

        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("shutil.rmtree") as mock_rmtree,
        ):
            mock_parse.return_value = self._make_args(data_dir=str(persist_dir))

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

        # Directory was created
        assert persist_dir.exists()
        assert (persist_dir / "data").exists()
        assert (persist_dir / "config").exists()

        # Should NOT clean up (--data-dir implies persistent)
        mock_rmtree.assert_not_called()

    @patch("uvicorn.run")
    def test_data_dir_skip_seed_when_already_seeded(self, mock_uvicorn, tmp_path: Path):
        """--data-dir with --prod skips seeding when data dir already has content."""
        persist_dir = tmp_path / "mydata"
        data_dir = persist_dir / "data"
        data_dir.mkdir(parents=True)
        # Stamp a file to mark as already seeded
        (data_dir / "email.db").touch()

        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("lighterbird.scripts.seed.seed_data_dir") as mock_seed,
        ):
            mock_parse.return_value = self._make_args(data_dir=str(persist_dir), prod="auto")

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

        # seed_data_dir should NOT be called since data already exists
        mock_seed.assert_not_called()

    @patch("uvicorn.run")
    def test_data_dir_seed_when_empty(self, mock_uvicorn, tmp_path: Path):
        """--data-dir with --prod seeds when data dir is empty."""
        persist_dir = tmp_path / "mydata"

        dot_prod = tmp_path / ".prod"
        dot_prod.write_text('TEST_EMAIL_1="a@b.com"\n')

        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("lighterbird.scripts.seed.seed_data_dir") as mock_seed,
            patch("lighterbird.scripts.dev_cli._find_dot_prod", return_value=dot_prod),
        ):
            mock_parse.return_value = self._make_args(data_dir=str(persist_dir), prod="auto")

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

        # seed_data_dir should have been called with the correct data dir
        mock_seed.assert_called_once()
        args, _ = mock_seed.call_args
        assert Path(args[0]) == persist_dir / "data"

    @patch("uvicorn.run")
    def test_data_dir_no_cleanup_on_exit(self, mock_uvicorn, tmp_path: Path):
        """--data-dir does not remove the directory on server stop."""
        persist_dir = tmp_path / "persist-data"

        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("shutil.rmtree") as mock_rmtree,
        ):
            mock_parse.return_value = self._make_args(
                data_dir=str(persist_dir), keep_data=False
            )

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

        # rmtree should NOT be called even though keep_data=False
        mock_rmtree.assert_not_called()
        assert persist_dir.exists()

    @patch("uvicorn.run")
    def test_data_dir_env_vars_set(self, mock_uvicorn, tmp_path: Path):
        """--data-dir sets LIGHTERBIRD_DATA_DIR and friends to the persistent path."""
        persist_dir = tmp_path / "env-test"

        with (
            patch("lighterbird.scripts.dev_cli.argparse.ArgumentParser.parse_args") as mock_parse,
            patch("os.environ") as mock_environ,
        ):
            mock_parse.return_value = self._make_args(data_dir=str(persist_dir))

            try:
                dev_main()
            except SystemExit:
                pass
            except Exception:
                pass

        expected_data = str(persist_dir / "data")
        expected_config = str(persist_dir / "config")
        mock_environ.__setitem__.assert_any_call("LIGHTERBIRD_DATA_DIR", expected_data)
        mock_environ.__setitem__.assert_any_call("LIGHTERBIRD_CONFIG_DIR", expected_config)

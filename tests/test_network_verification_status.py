"""Status semantics: incomplete network verification is never labeled successful."""
from __future__ import annotations

import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import run_all  # noqa: E402
import verify_network  # noqa: E402


class NetworkVerificationStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output_dir = self.root / "outputs"
        self.output_dir.mkdir()
        self.status_path = self.output_dir / "network_verification_status.json"
        self.original_out = verify_network.OUT
        self.original_status = verify_network.STATUS_PATH
        self.original_dependency_error = verify_network.DEPENDENCY_ERROR
        verify_network.OUT = self.output_dir
        verify_network.STATUS_PATH = self.status_path
        verify_network.DEPENDENCY_ERROR = None

    def tearDown(self) -> None:
        verify_network.OUT = self.original_out
        verify_network.STATUS_PATH = self.original_status
        verify_network.DEPENDENCY_ERROR = self.original_dependency_error
        self.temp.cleanup()

    def _seed_old_artifacts(self) -> None:
        for name in verify_network.NETWORK_ARTIFACTS:
            (self.output_dir / name).write_text("stale", encoding="utf-8")

    def _read_status(self) -> dict:
        return json.loads(self.status_path.read_text(encoding="utf-8"))

    def test_missing_package_is_unavailable_and_stale_audits_are_removed(self) -> None:
        self._seed_old_artifacts()
        with mock.patch.object(verify_network, "resolve_pkg", side_effect=SystemExit("package missing")):
            result = verify_network.main()
        self.assertEqual(result, 2)
        status = self._read_status()
        self.assertEqual(status["status"], "unavailable")
        self.assertIn("package missing", status["reason"])
        self.assertTrue(status["unverified_scope"])
        self.assertEqual(status["artifacts"], [])
        self.assertFalse(any((self.output_dir / name).exists() for name in verify_network.NETWORK_ARTIFACTS))

    def test_missing_dependency_is_recorded_as_unavailable(self) -> None:
        verify_network.DEPENDENCY_ERROR = "missing numpy"
        with mock.patch.object(verify_network, "resolve_pkg", return_value=self.root):
            result = verify_network.main()
        self.assertEqual(result, 2)
        status = self._read_status()
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual(status["package_root"], str(self.root))
        self.assertIn("missing numpy", status["reason"])

    def test_exception_during_checks_is_failed_not_passed(self) -> None:
        self._seed_old_artifacts()
        with mock.patch.object(verify_network, "resolve_pkg", return_value=self.root), \
                mock.patch.object(verify_network, "_run_available_checks", side_effect=ValueError("bad input")):
            result = verify_network.main()
        self.assertEqual(result, 1)
        status = self._read_status()
        self.assertEqual(status["status"], "failed")
        self.assertIn("bad input", status["reason"])
        self.assertFalse(any((self.output_dir / name).exists() for name in verify_network.NETWORK_ARTIFACTS))

    def test_empty_or_incomplete_checks_cannot_be_reported_as_passed(self) -> None:
        verify_network.CHECKS.clear()
        with mock.patch.object(verify_network, "resolve_pkg", return_value=self.root), \
                mock.patch.object(verify_network, "_run_available_checks", return_value=None):
            result = verify_network.main()
        self.assertEqual(result, 1)
        status = self._read_status()
        self.assertEqual(status["status"], "failed")
        self.assertIn("produced no checks", status["reason"])

    def test_pipeline_records_missing_dependencies_before_exiting(self) -> None:
        output_dir = self.root / "pipeline-outputs"
        output_dir.mkdir()
        original_out = run_all.OUT
        original_import = builtins.__import__
        run_all.OUT = output_dir

        def without_numpy(name, *args, **kwargs):
            if name == "numpy":
                raise ModuleNotFoundError("mock missing numpy", name="numpy")
            return original_import(name, *args, **kwargs)

        try:
            with mock.patch("builtins.__import__", side_effect=without_numpy):
                with self.assertRaises(SystemExit) as stopped:
                    run_all.main()
            self.assertEqual(stopped.exception.code, 2)
            status = json.loads((output_dir / "network_verification_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "unavailable")
            self.assertIn("numpy", status["reason"])
            self.assertTrue(status["unverified_scope"])
        finally:
            run_all.OUT = original_out


if __name__ == "__main__":
    unittest.main()

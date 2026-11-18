# SPDX-License-Identifier: MPL-2.0
"""Offscreen Qt regression check using only synthetic in-memory profiles."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from test_linux import HELPER, ROOT, MemoryVault, fixture
from firefox_wireguard.configuration import UserError
from firefox_wireguard.runtime import Runtime


class EditorTests(unittest.TestCase):
    def test_navigation_failure_drafts_and_render(self):
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
        except ImportError:
            self.skipTest("Install python3-pyqt6 for the Qt editor check")
        from firefox_wireguard import app as ui
        with tempfile.TemporaryDirectory(prefix="fwgt-") as tmp:
            directory, vault = Path(tmp), MemoryVault()
            runtime = Runtime(HELPER, directory, vault, directory / "control.sock", directory / "manifest.json")
            profile = runtime.save(None, "Synthetic fixture", fixture())
            errors = []

            def exercise():
                app = QApplication.instance()
                window = next(w for w in app.topLevelWidgets() if w.windowTitle() == "Firefox WireGuard")
                window.error = errors.append

                def settle():
                    deadline = time.monotonic() + 3
                    while window.pending and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(0.01)
                    app.processEvents()
                    self.assertFalse(window.pending)

                window.selection.setCurrentIndex(window.selection.findData(profile["id"]))
                settle()
                window.name.setText("Changed name")
                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
                    window.navigate(window.new)
                self.assertEqual(window.profile_id, profile["id"])
                self.assertEqual(window.name.text(), "Changed name")
                with (patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Save),
                      patch.object(vault, "write", side_effect=UserError("Locked wallet"))):
                    window.navigate(window.new)
                    settle()
                self.assertTrue(errors)
                self.assertEqual(window.profile_id, profile["id"])
                self.assertEqual(window.name.text(), "Changed name")
                self.assertTrue(window.dirty())
                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Save):
                    window.navigate(window.new)
                    settle()
                self.assertIsNone(window.profile_id)
                self.assertEqual(runtime.store.profiles[0]["name"], "Changed name")
                window.selection.setCurrentIndex(window.selection.findData(profile["id"]))
                settle()
                window.name.setText("Discard me")
                with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
                    window.navigate(window.new)
                self.assertEqual(window.text.toPlainText(), "")
                self.assertFalse(window.dirty())
                # Render synthetic details without displaying private-key text.
                with runtime.tunnel.lock:
                    runtime.tunnel.state = {"phase": "connected", "details": {
                        "publicIP": "203.0.113.8", "countryCode": "GB", "downloadedBytes": 123456789,
                        "uploadedBytes": 8765432, "statsUpdatedAt": time.time(), "dnsServers": ["192.0.2.1"], "clientIPs": ["192.0.2.2"]}}
                window.refresh()
                window.show()
                app.processEvents()
                self.assertIn("203.0.113.8", window.details.text())
                self.assertIn("123.5 MB", window.details.text())
                output = ROOT / "dist/linux-companion-preview.png"
                output.parent.mkdir(exist_ok=True)
                self.assertTrue(window.grab().save(str(output)))
                window.tray.hide()
                window.hide()
                window.timer.stop()
                window.deleteLater()
                app.processEvents()
                return 0

            try:
                with (patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}),
                      patch("sys.argv", ["firefox-wireguard"]), patch.object(ui, "Runtime", return_value=runtime),
                      patch.object(QApplication, "exec", side_effect=exercise)):
                    self.assertEqual(ui.main(ROOT / "extension"), 0)
            finally:
                runtime.close()

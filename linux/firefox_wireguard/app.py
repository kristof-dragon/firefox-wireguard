# SPDX-License-Identifier: MPL-2.0
"""Qt 6 tray UI. Vault operations run off the GUI and health-monitor threads."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading

from .configuration import Configuration, UserError
from .protocol import manifest_path, register, registration_matches, socket_path
from .runtime import Runtime


def main(bundle):
    parser = argparse.ArgumentParser(description="Firefox WireGuard Linux companion")
    parser.add_argument("--background", action="store_true", help="Start in the tray when available")
    parser.add_argument("--install-integration", action="store_true", help="Register this companion with native Firefox")
    parser.add_argument("--diagnose", action="store_true", help="Show non-secret installation checks")
    args = parser.parse_args()
    helper = bundle / "firefox-wireguard-bridge"
    if args.install_integration:
        register(helper)
        print("Installed Firefox native messaging integration.")
        return 0
    if args.diagnose:
        print(json.dumps({"backend": os.access(bundle / "wireproxy", os.X_OK),
                          "secret_tool": Path("/usr/bin/secret-tool").is_file(),
                          "curl": Path("/usr/bin/curl").is_file(),
                          "integration": registration_matches(helper, manifest_path()),
                          "control_socket": socket_path().exists()}, indent=2))
        return 0
    try:
        from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
        from PyQt6.QtGui import QIcon, QFontDatabase
        from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                                    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                                    QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget)
    except ImportError:
        parser.exit(1, "Install python3-pyqt6, libsecret-tools and curl, then reopen Firefox WireGuard.\n")

    class Jobs(QObject):
        finished = pyqtSignal(object, object)

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.runtime = None
            self.profile_id = None
            self.saved = ("", "")
            self.pending = False
            self.jobs = Jobs()
            self.jobs.finished.connect(self.job_finished)
            self.setWindowTitle("Firefox WireGuard")
            self.setWindowIcon(QIcon(str(bundle / "icon.svg")))
            self.resize(760, 690)
            body = QWidget()
            self.setCentralWidget(body)
            layout = QVBoxLayout(body)
            self.status = QLabel("Starting…")
            self.status.setWordWrap(True)
            self.status.setTextFormat(Qt.TextFormat.PlainText)
            self.details = QLabel()
            self.details.setWordWrap(True)
            self.details.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(self.status)
            layout.addWidget(self.details)
            actions = QHBoxLayout()
            self.retry = QPushButton("Retry Startup")
            self.retry.clicked.connect(self.startup)
            actions.addWidget(self.retry)
            install = QPushButton("Install Firefox Integration")
            install.clicked.connect(self.install)
            actions.addWidget(install)
            stop = QPushButton("Stop Tunnel")
            stop.clicked.connect(self.stop_tunnel)
            actions.addWidget(stop)
            layout.addLayout(actions)
            self.editor = QWidget()
            edit_layout = QVBoxLayout(self.editor)
            edit_layout.setContentsMargins(0, 12, 0, 0)
            self.selection = QComboBox()
            self.selection.currentIndexChanged.connect(self.select)
            edit_layout.addWidget(self.selection)
            row = QHBoxLayout()
            for title, action in (("New", lambda: self.navigate(self.new)), ("Import…", lambda: self.navigate(self.import_file)),
                                  ("Remove", self.remove)):
                button = QPushButton(title)
                button.clicked.connect(action)
                row.addWidget(button)
            edit_layout.addLayout(row)
            form = QFormLayout()
            self.name = QLineEdit()
            self.name.setMaxLength(80)
            form.addRow("Profile name", self.name)
            edit_layout.addLayout(form)
            edit_layout.addWidget(QLabel("WireGuard configuration (contains private keys)"))
            self.text = QPlainTextEdit()
            self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            self.text.setPlaceholderText("Import a WireGuard .conf file, or paste a full-tunnel configuration here.")
            edit_layout.addWidget(self.text, 1)
            save_row = QHBoxLayout()
            save = QPushButton("Save Profile")
            save.clicked.connect(lambda: self.save())
            discard = QPushButton("Discard Changes")
            discard.clicked.connect(self.discard)
            save_row.addWidget(save)
            save_row.addWidget(discard)
            edit_layout.addLayout(save_row)
            hint = QLabel("Choose a saved profile and Connect in Firefox. Closing this window keeps the companion in the tray.")
            hint.setWordWrap(True)
            edit_layout.addWidget(hint)
            layout.addWidget(self.editor, 1)
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            menu = QMenu(self)
            menu.addAction("Manage Profiles…", self.show_window)
            menu.addAction("Stop Tunnel", self.stop_tunnel)
            menu.addAction("Install Firefox Integration", self.install)
            menu.addSeparator()
            menu.addAction("Quit", self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.show()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
            self.startup()

        def error(self, error):
            message = str(error) if isinstance(error, UserError) else "The operation could not be completed. Check the installation and retry."
            QMessageBox.warning(self, "Firefox WireGuard", message)

        def startup(self):
            if self.runtime:
                return
            try:
                self.runtime = Runtime(helper)
                self.reload_profiles()
            except Exception as error:
                self.status.setText(str(error) if isinstance(error, UserError) else "Unable to initialise private application storage.")
            self.editor.setEnabled(self.runtime is not None)
            self.retry.setVisible(self.runtime is None)
            self.refresh()

        def run_job(self, operation, success):
            if self.pending:
                return
            self.pending, self.success = True, success
            self.editor.setEnabled(False)
            def run():
                try:
                    value, error = operation(), None
                except Exception as failure:
                    value, error = None, failure
                self.jobs.finished.emit(value, error)
            threading.Thread(target=run, daemon=True).start()

        def job_finished(self, value, error):
            self.pending = False
            self.editor.setEnabled(self.runtime is not None)
            if error is not None:
                self.error(error)
            else:
                self.success(value)
            self.reload_profiles()

        def dirty(self):
            return (self.name.text(), self.text.toPlainText()) != self.saved

        def navigate(self, action):
            if self.pending:
                return
            if not self.dirty():
                action()
                return
            choice = QMessageBox.question(self, "Unsaved profile", "Save changes to this profile?",
                                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if choice == QMessageBox.StandardButton.Save:
                self.save(action)
            elif choice == QMessageBox.StandardButton.Discard:
                action()

        def save(self, afterwards=None):
            if not self.runtime:
                return
            profile_id, name, text = self.profile_id, self.name.text(), self.text.toPlainText()
            def saved(profile):
                self.profile_id = profile["id"]
                self.saved = (name, text)
                self.reload_profiles()
                if afterwards:
                    afterwards()
            self.run_job(lambda: self.runtime.save(profile_id, name, text), saved)

        def set_draft(self, profile_id, name, text):
            self.profile_id = profile_id
            self.name.setText(name)
            self.text.setPlainText(text)
            self.saved = (name, text)
            self.reload_profiles()

        def new(self):
            self.set_draft(None, "", "")

        def discard(self):
            self.name.setText(self.saved[0])
            self.text.setPlainText(self.saved[1])

        def reload_profiles(self):
            if not self.runtime:
                return
            self.selection.blockSignals(True)
            self.selection.clear()
            self.selection.addItem("New profile", None)
            for profile in self.runtime.store.profiles:
                self.selection.addItem(profile["name"], profile["id"])
            self.selection.setCurrentIndex(max(0, self.selection.findData(self.profile_id)))
            self.selection.blockSignals(False)

        def select(self, _index):
            target = self.selection.currentData()
            self.reload_profiles()  # Cancel/failed Save preserves the current selection.
            if target == self.profile_id:
                return
            def load():
                if target is None:
                    self.new()
                    return
                profile = next(p for p in self.runtime.store.profiles if p["id"] == target)
                self.run_job(lambda: self.runtime.store.configuration(target).canonical,
                             lambda text: self.set_draft(target, profile["name"], text))
            self.navigate(load)

        def import_file(self):
            path, _ = QFileDialog.getOpenFileName(self, "Import WireGuard profile", "", "WireGuard configuration (*.conf);;All files (*)")
            if not path:
                return
            try:
                with open(path, "rb") as stream:
                    data = stream.read(32769)
                configuration = Configuration(data.decode("utf-8"))
                self.set_draft(None, Path(path).stem[:80], configuration.canonical)
                self.saved = ("", "")  # Imported configurations remain unsaved drafts.
            except (OSError, UnicodeError):
                self.error(UserError("Unable to read a UTF-8 WireGuard configuration from this file."))
            except UserError as error:
                self.error(error)

        def remove(self):
            if not self.profile_id or not self.runtime:
                return
            if QMessageBox.question(self, "Remove profile", "Delete this profile and its stored configuration?") != QMessageBox.StandardButton.Yes:
                return
            profile_id = self.profile_id
            self.run_job(lambda: self.runtime.remove(profile_id), lambda _: self.new())

        def install(self):
            try:
                register(helper)
                QMessageBox.information(self, "Firefox integration", "Installed for native Firefox. Reload the extension if it was already open.")
            except Exception as error:
                self.error(error)

        def stop_tunnel(self):
            if self.runtime:
                self.runtime.stop()
                self.refresh()

        def refresh(self):
            if not self.runtime:
                return
            state = self.runtime.tunnel.snapshot()
            message = state.get("error") or {"idle": "Disconnected", "connecting": "Connecting…",
                                            "connected": "Connected", "blocked": "Tunnel unavailable"}[state["phase"]]
            active = next((p["name"] for p in self.runtime.store.profiles if p["id"] == state.get("profileID")), None)
            if active:
                message += " — " + active
            self.status.setText(message)
            self.tray.setToolTip("Firefox WireGuard — " + message)
            details = state.get("details", {})
            code = details.get("countryCode", "")
            flag = "".join(chr(ord(c) + 127397) for c in code)
            def size(value):
                if value is None:
                    return "—"
                for unit in ("B", "KB", "MB", "GB", "TB", "PB", "EB"):
                    if value < 1000 or unit == "EB":
                        return f"{value:,.1f} {unit}"
                    value /= 1000
            if details:
                exit_label = details.get("publicIP") or details.get("exitStatus", "waiting").capitalize()
                fresh = bool(details.get("statsUpdatedAt"))
                self.details.setText(f"Exit: {flag} {exit_label}    ↓ {size(details.get('downloadedBytes') if fresh else None)}    ↑ {size(details.get('uploadedBytes') if fresh else None)}\n"
                                     f"DNS: {', '.join(details.get('dnsServers', []))}\nClient: {', '.join(details.get('clientIPs', []))}")
            else:
                self.details.clear()

        def show_window(self):
            self.showNormal()
            self.raise_()
            self.activateWindow()

        def quit(self):
            if self.pending:
                self.error(UserError("Wait for the profile operation to finish before quitting."))
                return
            self.navigate(app.quit)

        def closeEvent(self, event):
            event.ignore()
            if self.tray.isVisible():
                self.hide()  # Retain the in-memory draft across window closes.
            else:
                self.quit()

    app = QApplication([])
    app.setApplicationName("Firefox WireGuard")
    app.setDesktopFileName("org.firefoxwireguard.companion")
    app.setQuitOnLastWindowClosed(False)
    window = Window()
    app.aboutToQuit.connect(lambda: window.runtime.close() if window.runtime else None)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    if not args.background or not window.tray.isVisible() or not window.runtime:
        window.show()
    return app.exec()

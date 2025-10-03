# main.py
import sys
import os
import uuid
import subprocess
import traceback

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QSpinBox, QTextEdit, QMessageBox, QTabWidget
)
from PyQt5.QtCore import QThread, pyqtSignal

import minecraft_launcher_lib as mll

# ---------- Helper: offline UUID ----------
def generate_offline_uuid(username: str) -> str:
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + username))


# ---------- Worker thread ----------
class MinecraftWorker(QThread):
    log = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, username, version, ram_mb, loader, width, height):
        super().__init__()
        self.username = username
        self.version = version
        self.ram_mb = ram_mb
        self.loader = loader  # "Vanilla" or "Fabric" or "Forge"
        self.width = width
        self.height = height

    def run(self):
        try:
            mc_dir = mll.utils.get_minecraft_directory()
            launcher_version = None
            mods_path = os.path.join(mc_dir, "mods")

            # ----------------- Loader Handling -----------------
            if self.loader == "Fabric":
                try:
                    self.log.emit(f"Installing Fabric for {self.version}...")
                    # Install Fabric (latest loader)
                    mll.fabric.install_fabric(self.version, mc_dir)
                    # Detect the version folder
                    versions_dir = os.path.join(mc_dir, "versions")
                    fabric_versions = [
                        v for v in os.listdir(versions_dir)
                        if v.startswith("fabric-loader") and v.endswith(self.version)
                    ]
                    if fabric_versions:
                        launcher_version = fabric_versions[-1]
                        mods_path = os.path.join(versions_dir, launcher_version, "mods")
                        os.makedirs(mods_path, exist_ok=True)
                    else:
                        launcher_version = None
                    self.log.emit(f"Fabric installed: {launcher_version}")
                except Exception as e:
                    self.log.emit(f"Fabric installation failed: {e}")
                    return

            elif self.loader == "Forge":
                try:
                    self.log.emit(f"Installing Forge for {self.version}...")
                    # Use Forge helper
                    forge_versions = mll.forge.get_installed_forge_versions(mc_dir)
                    if not forge_versions:
                        mll.forge.install_forge_version(self.version, mc_dir)
                        forge_versions = mll.forge.get_installed_forge_versions(mc_dir)
                    launcher_version = forge_versions[-1] if forge_versions else self.version
                    mods_path = os.path.join(mc_dir, "versions", launcher_version, "mods")
                    os.makedirs(mods_path, exist_ok=True)
                    self.log.emit(f"Forge installed: {launcher_version}")
                except Exception as e:
                    self.log.emit(f"Forge installation failed: {e}")
                    return
            else:  # Vanilla
                try:
                    self.log.emit(f"Ensuring vanilla {self.version} is installed...")
                    mll.install.install_minecraft_version(self.version, mc_dir)
                    launcher_version = self.version
                except Exception:
                    launcher_version = self.version
                mods_path = os.path.join(mc_dir, "mods")
                os.makedirs(mods_path, exist_ok=True)

            if not launcher_version:
                self.log.emit("Error: launcher_version is None!")
                return

            # ----------------- Offline User -----------------
            uuid_off = generate_offline_uuid(self.username)
            user = {
                "username": self.username,
                "uuid": uuid_off,
                "access_token": "null"
            }
            self.log.emit(f"Using offline user: {self.username} ({uuid_off})")

            # ----------------- Launch Options -----------------
            options = {
                "username": user["username"],
                "uuid": user["uuid"],
                "token": user["access_token"],
                "jvmArguments": [f"-Xmx{self.ram_mb}M", f"-Xms{min(512, self.ram_mb)}M"],
                "game_directory": mc_dir,
                "gameArguments": [f"--width {self.width}", f"--height {self.height}"],
                "mods_directory": mods_path
            }

            # ----------------- Build & Run Command -----------------
            cmd = mll.command.get_minecraft_command(launcher_version, mc_dir, options)
            self.log.emit("Launching Minecraft...")

            proc = subprocess.Popen(cmd, cwd=mc_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
            for raw in iter(proc.stdout.readline, b''):
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="ignore").rstrip()
                except Exception:
                    line = str(raw)
                self.log.emit(line)
            proc.stdout.close()
            proc.wait()
            self.log.emit(f"Minecraft exited with code {proc.returncode}")

        except Exception:
            self.log.emit("Launcher crashed:\n" + traceback.format_exc())
        finally:
            self.finished_signal.emit()


# ---------- Main UI ----------
class LauncherUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DynamoLauncher")
        self.resize(800, 600)

        self.tabs = QTabWidget()
        self.main_tab = QWidget()
        self.settings_tab = QWidget()

        self.tabs.addTab(self.main_tab, "Launcher")
        self.tabs.addTab(self.settings_tab, "Settings")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self._build_main_tab()
        self._build_settings_tab()
        self.populate_versions()

    # --- Main tab ---
    def _build_main_tab(self):
        layout = QVBoxLayout()

        top = QHBoxLayout()
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username (offline)")
        top.addWidget(QLabel("Username:"))
        top.addWidget(self.username_input)

        self.version_combo = QComboBox()
        top.addWidget(QLabel("Version:"))
        top.addWidget(self.version_combo)

        self.loader_combo = QComboBox()
        self.loader_combo.addItems(["Vanilla", "Fabric", "Forge"])
        top.addWidget(QLabel("Loader:"))
        top.addWidget(self.loader_combo)

        layout.addLayout(top)

        mid = QHBoxLayout()
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 32768)
        self.ram_spin.setValue(2048)
        mid.addWidget(QLabel("RAM (MB):"))
        mid.addWidget(self.ram_spin)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 3840)
        self.width_spin.setValue(854)
        mid.addWidget(QLabel("Width:"))
        mid.addWidget(self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 2160)
        self.height_spin.setValue(480)
        mid.addWidget(QLabel("Height:"))
        mid.addWidget(self.height_spin)

        layout.addLayout(mid)

        self.launch_btn = QPushButton("Launch Minecraft")
        layout.addWidget(self.launch_btn)

        layout.addWidget(QLabel("Logs:"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self.main_tab.setLayout(layout)
        self.launch_btn.clicked.connect(self.on_launch)

    # --- Settings tab ---
    def _build_settings_tab(self):
        layout = QVBoxLayout()

        self.open_mods_btn = QPushButton("Open Mods Folder")
        layout.addWidget(self.open_mods_btn)
        self.open_mods_btn.clicked.connect(self.open_mods_folder)

        layout.addStretch()
        self.settings_tab.setLayout(layout)

    def open_mods_folder(self):
        mc_dir = mll.utils.get_minecraft_directory()
        loader = self.loader_combo.currentText()
        version = self.version_combo.currentText()

        mods_path = os.path.join(mc_dir, "mods")
        if loader == "Fabric":
            versions_dir = os.path.join(mc_dir, "versions")
            fabric_versions = [
                v for v in os.listdir(versions_dir)
                if v.startswith("fabric-loader") and v.endswith(version)
            ]
            if fabric_versions:
                mods_path = os.path.join(versions_dir, fabric_versions[-1], "mods")
        elif loader == "Forge":
            versions_dir = os.path.join(mc_dir, "versions")
            forge_versions = [
                v for v in os.listdir(versions_dir)
                if v.startswith("forge") and v.endswith(version)
            ]
            if forge_versions:
                mods_path = os.path.join(versions_dir, forge_versions[-1], "mods")

        os.makedirs(mods_path, exist_ok=True)

        if sys.platform == "win32":
            os.startfile(mods_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", mods_path])
        else:
            subprocess.Popen(["xdg-open", mods_path])

    # --- Populate versions ---
    def populate_versions(self):
        self.version_combo.clear()
        try:
            versions = mll.utils.get_available_versions("release")
            release_ids = [v["id"] for v in versions] if versions else []
            if release_ids:
                self.version_combo.addItems(release_ids)
                idx = self.version_combo.findText("1.20.1")
                if idx != -1:
                    self.version_combo.setCurrentIndex(idx)
            else:
                self.version_combo.addItem("1.20.1")
        except Exception:
            self.version_combo.addItem("1.20.1")

    def log(self, text: str):
        self.log_box.append(text)

    def on_launch(self):
        username = self.username_input.text().strip()
        if not username:
            QMessageBox.warning(self, "Missing username", "Please enter a username for offline mode.")
            return

        version = self.version_combo.currentText()
        loader = self.loader_combo.currentText()
        ram = self.ram_spin.value()
        width = self.width_spin.value()
        height = self.height_spin.value()

        self.log(f"Launching: {username} — {version} ({loader}) RAM={ram}MB")

        self.worker = MinecraftWorker(username, version, ram, loader, width, height)
        self.worker.log.connect(self.log)
        self.worker.finished_signal.connect(lambda: self.log("Launch finished."))
        self.launch_btn.setEnabled(False)
        self.worker.finished_signal.connect(lambda: self.launch_btn.setEnabled(True))
        self.worker.start()


# ---------- Run ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = LauncherUI()
    win.show()
    sys.exit(app.exec_())

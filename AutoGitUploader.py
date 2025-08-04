import os
import sys
import tempfile
import shutil
import zipfile
import tarfile
import requests
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QCheckBox, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon
import git
class WorkerThread(QThread):
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    operation_complete = pyqtSignal(bool, str)
    def __init__(self, archive_path, repo_name, github_username, github_token, is_private):
        super().__init__()
        self.archive_path = archive_path
        self.repo_name = repo_name
        self.github_username = github_username
        self.github_token = github_token
        self.is_private = is_private
        self.temp_dir = None
    def run(self):
        try:
            self.update_status.emit("Creating temporary directory...")
            self.temp_dir = tempfile.mkdtemp()
            self.update_progress.emit(10)
            self.update_status.emit(f"Extracting {self.archive_path} to temporary directory...")
            self.extract_archive(self.archive_path, self.temp_dir)
            self.update_progress.emit(30)
            self.update_status.emit("Initializing Git repository...")
            repo = git.Repo.init(self.temp_dir)
            self.update_progress.emit(40)
            self.update_status.emit("Adding files to Git...")
            repo.git.add(A=True)
            self.update_progress.emit(50)
            self.update_status.emit("Committing files...")
            repo.git.commit(m="Initial commit")
            self.update_progress.emit(60)
            self.update_status.emit(f"Creating GitHub repository: {self.repo_name}...")
            repo_url = self.create_github_repo()
            self.update_progress.emit(70)
            self.update_status.emit("Pushing to GitHub...")
            repo.create_remote("origin", repo_url)
            repo.git.push("origin", "master")
            self.update_progress.emit(90)
            self.update_status.emit("Cleaning up temporary files...")
            self.cleanup()
            self.update_progress.emit(100)
            self.operation_complete.emit(True, f"Successfully uploaded to {repo_url}")
        except Exception as e:
            self.update_status.emit(f"Error: {str(e)}")
            self.operation_complete.emit(False, str(e))
            self.cleanup()
    def extract_archive(self, archive_path, extract_to):
        file_ext = os.path.splitext(archive_path)[1].lower()
        if file_ext == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
        elif file_ext in ['.tar', '.gz', '.tgz']:
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_to)
        else:
            raise ValueError(f"Unsupported archive format: {file_ext}")
    def create_github_repo(self):
        url = "https://api.github.com/user/repos"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "name": self.repo_name,
            "private": self.is_private
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create GitHub repository: {response.json().get('message', response.text)}")
        return response.json()["html_url"]
    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                self.update_status.emit(f"Warning: Failed to clean up temporary directory: {str(e)}")
class DropAreaWidget(QWidget):
    file_dropped = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.label = QLabel("Drag & Drop Archive Here")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)
        self.setMinimumHeight(100)
        self.setStyleSheet("border: 2px dashed #aaa; border-radius: 5px;")
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("border: 2px dashed #3daee9; border-radius: 5px;")
    def dragLeaveEvent(self, event):
        self.setStyleSheet("border: 2px dashed #aaa; border-radius: 5px;")
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            self.file_dropped.emit(file_path)
            self.setStyleSheet("border: 2px dashed #aaa; border-radius: 5px;")
class AutoGitUploader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("AutoGitUploader", "settings")
        self.init_ui()
        self.worker = None
        self.load_settings()
    def init_ui(self):
        self.setWindowTitle("AutoGitUploader")
        self.setMinimumSize(600, 500)
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        self.drop_area = DropAreaWidget()
        self.drop_area.file_dropped.connect(self.set_archive_path)
        main_layout.addWidget(self.drop_area)
        archive_layout = QHBoxLayout()
        archive_layout.addWidget(QLabel("Archive:"))
        self.archive_path_edit = QLineEdit()
        self.archive_path_edit.setReadOnly(True)
        archive_layout.addWidget(self.archive_path_edit)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_archive)
        archive_layout.addWidget(self.browse_button)
        main_layout.addLayout(archive_layout)
        github_username_layout = QHBoxLayout()
        github_username_layout.addWidget(QLabel("GitHub Username:"))
        self.github_username_edit = QLineEdit()
        github_username_layout.addWidget(self.github_username_edit)
        main_layout.addLayout(github_username_layout)
        github_token_layout = QHBoxLayout()
        github_token_layout.addWidget(QLabel("GitHub Token:"))
        self.github_token_edit = QLineEdit()
        self.github_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        github_token_layout.addWidget(self.github_token_edit)
        main_layout.addLayout(github_token_layout)
        repo_name_layout = QHBoxLayout()
        repo_name_layout.addWidget(QLabel("Repository Name:"))
        self.repo_name_edit = QLineEdit()
        repo_name_layout.addWidget(self.repo_name_edit)
        main_layout.addLayout(repo_name_layout)
        private_repo_layout = QHBoxLayout()
        self.private_repo_checkbox = QCheckBox("Private Repository")
        private_repo_layout.addWidget(self.private_repo_checkbox)
        private_repo_layout.addStretch()
        main_layout.addLayout(private_repo_layout)
        save_username_layout = QHBoxLayout()
        self.save_username_checkbox = QCheckBox("Remember GitHub Username")
        self.save_username_checkbox.setChecked(True)
        save_username_layout.addWidget(self.save_username_checkbox)
        save_username_layout.addStretch()
        main_layout.addLayout(save_username_layout)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(QLabel("Status:"))
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMinimumHeight(150)
        main_layout.addWidget(self.status_text)
        self.upload_button = QPushButton("Upload to GitHub")
        self.upload_button.clicked.connect(self.upload_to_github)
        main_layout.addWidget(self.upload_button)
        self.setCentralWidget(main_widget)
        self.apply_dark_theme()
    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QLineEdit, QTextEdit {
                background-color: #3d3d3d;
                border: 1px solid #555555;
                color: #ffffff;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
            QPushButton:pressed {
                background-color: #0a58ca;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 3px;
                text-align: center;
                background-color: #3d3d3d;
            }
            QProgressBar::chunk {
                background-color: #0d6efd;
                width: 10px;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
            }
        """)
    def browse_archive(self):
        file_filter = "Archives (*.zip *.tar *.gz *.tgz);;All Files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Archive", "", file_filter
        )
        if file_path:
            self.set_archive_path(file_path)
    def set_archive_path(self, path):
        self.archive_path_edit.setText(path)
        try:
            file_name = os.path.basename(path)
            base_name = os.path.splitext(file_name)[0]
            if base_name and not self.repo_name_edit.text():
                self.repo_name_edit.setText(base_name)
        except:
            pass
    def upload_to_github(self):
        archive_path = self.archive_path_edit.text()
        repo_name = self.repo_name_edit.text()
        github_username = self.github_username_edit.text()
        github_token = self.github_token_edit.text()
        is_private = self.private_repo_checkbox.isChecked()
        if not archive_path:
            QMessageBox.warning(self, "Error", "Please select an archive file.")
            return
        if not os.path.exists(archive_path):
            QMessageBox.warning(self, "Error", "Selected archive file does not exist.")
            return
        if not repo_name:
            QMessageBox.warning(self, "Error", "Please enter a repository name.")
            return
        if not github_username:
            QMessageBox.warning(self, "Error", "Please enter your GitHub username.")
            return
        if not github_token:
            QMessageBox.warning(self, "Error", "Please enter your GitHub token.")
            return
        if self.save_username_checkbox.isChecked():
            self.settings.setValue("github_username", github_username)
        else:
            self.settings.remove("github_username")
        self.status_text.clear()
        self.progress_bar.setValue(0)
        self.set_ui_enabled(False)
        self.worker = WorkerThread(archive_path, repo_name, github_username, github_token, is_private)
        self.worker.update_status.connect(self.update_status)
        self.worker.update_progress.connect(self.progress_bar.setValue)
        self.worker.operation_complete.connect(self.on_operation_complete)
        self.worker.start()
    def update_status(self, message):
        self.status_text.append(message)
        scrollbar = self.status_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    def on_operation_complete(self, success, message):
        self.set_ui_enabled(True)
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", f"Operation failed: {message}")
    def set_ui_enabled(self, enabled):
        self.browse_button.setEnabled(enabled)
        self.github_username_edit.setEnabled(enabled)
        self.github_token_edit.setEnabled(enabled)
        self.repo_name_edit.setEnabled(enabled)
        self.private_repo_checkbox.setEnabled(enabled)
        self.save_username_checkbox.setEnabled(enabled)
        self.upload_button.setEnabled(enabled)
    def load_settings(self):
        github_username = self.settings.value("github_username", "")
        if github_username:
            self.github_username_edit.setText(github_username)
    def closeEvent(self, event):
        if self.save_username_checkbox.isChecked():
            self.settings.setValue("github_username", self.github_username_edit.text())
        super().closeEvent(event)
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AutoGitUploader()
    window.show()
    sys.exit(app.exec()) 

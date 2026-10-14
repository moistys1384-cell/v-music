import sys, os, random, json, requests, time, socket, hashlib, shutil, smtplib , traceback , math , ctypes
from email.mime.text import MIMEText
from urllib.parse import urlparse, quote, urlunparse

import mysql.connector
from mysql.connector import Error
import mysql.connector.plugins.mysql_native_password
import mysql.connector.locales.eng

from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QListWidgetItem, QToolButton, QPushButton, QFileDialog, QLabel,
    QSlider, QDialog, QProgressBar, QGraphicsOpacityEffect, QLineEdit,
    QInputDialog, QMenu, QMessageBox, QStackedWidget, QScrollArea, QGridLayout, QSizePolicy, QComboBox, QTextEdit, QTabWidget , QFormLayout , QProgressDialog , QAction
)
from PyQt5.QtCore import QSize, QTimer, Qt, QThread, pyqtSignal, QPropertyAnimation, QPointF, QEasingCurve , QPoint , QEvent , QTime , QMimeData , QObject
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QColor, QTransform, QLinearGradient, QPen, QRegion, QPainterPath , QRadialGradient , QDrag

basedir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

libvlc_path = os.path.join(basedir, 'libvlc.dll')
plugins_path = os.path.join(basedir, 'plugins')

os.environ['VLC_PLUGIN_PATH'] = plugins_path

ctypes.CDLL(libvlc_path)

import vlc
from mutagen.id3 import ID3
from mutagen import File as MutagenFile
import librosa
import soundfile as sf
import torch
try:
    from df import DeepFilterNet
except ImportError:
    DeepFilterNet = None

import pynput
from pynput import keyboard

from PyQt5.QtCore import QItemSelection

from cryptography.fernet import Fernet

import win32security
import win32api
import ntsecuritycon as con

DB_HOST="193.36.85.114"
DB_USER="root"
DB_PASSWORD="Flat18222a!@!@51a"
DB_NAME="vmusic"

SECURE_PATH = os.path.join(os.path.expanduser('~'), 'Documents', 'VMusic')
CACHE_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'VMusic', 'cache')

os.makedirs(SECURE_PATH, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# ================= Utility Functions ================= #

def ms_to_time(ms):
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def icon_path(filename):
    return os.path.abspath(os.path.join("icons", filename))

def get_album_art(filepath):
    try:
        audio = ID3(filepath)
        for key in audio.keys():
            if key.startswith("APIC"):
                art_data = audio.get(key).data
                pixmap = QPixmap()
                if pixmap.loadFromData(art_data):
                    return pixmap
                else:
                    print(f"Failed to load album art data for file: {filepath}")
    except Exception as e:
        print(f"Error extracting album art from {filepath}: {e}")
    return None

def is_connected(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

def encode_url(url):
    parsed = urlparse(url)
    encoded_path = quote(parsed.path)
    return urlunparse((parsed.scheme, parsed.netloc, encoded_path, parsed.params, parsed.query, parsed.fragment))

def generate_avatar(username, size=50):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    random.seed(username)
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    bg_color = QColor(r, g, b)
    
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    text_color = QColor(255, 255, 255) if brightness < 128 else QColor(0, 0, 0)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(bg_color)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    
    letter = username[0].upper() if username else "?"
    font = QFont("Arial", int(size / 2))
    painter.setFont(font)
    painter.setPen(text_color)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, letter)
    painter.end()
    return pixmap

def encrypt_data(data, key):
    f = Fernet(key)
    return f.encrypt(json.dumps(data).encode())

def decrypt_data(encrypted_data, key):
    f = Fernet(key)
    return json.loads(f.decrypt(encrypted_data).decode())

def hide_file(filepath):
    if os.name == 'nt':
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(filepath, FILE_ATTRIBUTE_HIDDEN)

def secure_save(data, filename, encryption_key):
    try:
        encrypted_data = encrypt_data(data, encryption_key)
        filepath = os.path.join(SECURE_PATH, filename)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            f.write(encrypted_data)
            
        return True
    except Exception as e:
        print(f"Error saving {filename}: {e}")
        return False
    
def secure_load(filename, encryption_key):
    try:
        filepath = os.path.join(SECURE_PATH, filename)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                encrypted_data = f.read()
            return decrypt_data(encrypted_data, encryption_key)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
    return None

# ================= Database Handler ================= #

class DBHandler:
    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv()
        
        self.secure_path = SECURE_PATH
        if not os.path.exists(self.secure_path):
            os.makedirs(self.secure_path)
            if os.name == 'posix':
                os.chmod(self.secure_path, 0o700)
                
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.connection = mysql.connector.connect(
                    host=DB_HOST,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    ssl_disabled=True
                )
                if self.connection.is_connected():
                    self.ensure_table()
                    break
            except Error as e:
                retry_count += 1
                print(f"Connection attempt {retry_count} failed: {e}")
                if retry_count == max_retries:
                    print("Error while connecting to DB:", e)
                    self.connection = None
                time.sleep(1)

    def ensure_table(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                salt VARCHAR(64) NOT NULL,
                password_hash VARCHAR(64) NOT NULL,
                profile_pic VARCHAR(255),
                email VARCHAR(255) UNIQUE,
                account_type VARCHAR(50) DEFAULT 'user'
            );
            """
        ]

        check_email_query = """
        SELECT COUNT(*) as count
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = 'v_music'
        AND TABLE_NAME = 'users' 
        AND COLUMN_NAME = 'email';
        """
        
        cursor = self.connection.cursor(dictionary=True)
        
        try:
            cursor.execute(queries[0])

            cursor.execute(check_email_query)
            result = cursor.fetchone()

            if result['count'] == 0:
                add_email_query = """
                ALTER TABLE users
                ADD COLUMN email VARCHAR(255) UNIQUE;
                """
                cursor.execute(add_email_query)
                
            self.connection.commit()
        except Error as e:
            print(f"Error executing query: {e}")
        finally:
            cursor.close()

    def get_user(self, username):
        cursor = self.connection.cursor(dictionary=True)
        query = "SELECT * FROM users WHERE username = %s"
        cursor.execute(query, (username,))
        result = cursor.fetchone()
        cursor.close()
        return result

    def add_user(self, username, salt, password_hash, email=None, profile_pic=None, account_type="user"):
        cursor = self.connection.cursor()
        query = """
        INSERT INTO users (username, salt, password_hash, email, profile_pic, account_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        try:
            cursor.execute(query, (username, salt, password_hash, email, profile_pic, account_type))
            self.connection.commit()
            return True
        except Error as e:
            print("Error inserting user:", e)
            return False
        finally:
            cursor.close()

    def update_profile_pic(self, username, profile_pic):
        if not self.connection:
            return False
            
        cursor = self.connection.cursor()
        query = "UPDATE users SET profile_pic = %s WHERE username = %s"
        try:
            cursor.execute(query, (profile_pic, username))
            self.connection.commit()
            return True
        except Error as e:
            print(f"Database error: {e}")
            return False
        finally:
            cursor.close()

db_handler = DBHandler()

class LibraryLoader(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        
    def load_library(self):
        try:
            response = requests.get(
                "https://mortalservice.de/music/musiclibrary.json",
                verify=True,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            categories = data.get("categories", {})
            hierarchy = {}
            total_items = len(categories)
            processed = 0
            
            for genre, artists in categories.items():
                hierarchy[genre] = {}
                for artist, albums in artists.get("artists", {}).items():
                    hierarchy[genre][artist] = {}
                    for album, songs in albums.items():
                        valid_songs = []
                        for song in songs:
                            if isinstance(song, str):
                                valid_songs.append({
                                    "name": song,
                                    "url": "",
                                    "cover": ""
                                })
                            elif isinstance(song, dict):
                                valid_songs.append(song)
                        hierarchy[genre][artist][album] = valid_songs
                processed += 1
                self.progress.emit(int(processed * 100 / total_items))
                
            self.finished.emit(hierarchy)
            
        except Exception as e:
            print(f"Error loading library: {e}")
            self.finished.emit({})

class SearchWorker(QThread):
    results = pyqtSignal(list)
    progress = pyqtSignal(int)
    
    def __init__(self, query, hierarchy):
        super().__init__()
        self.query = query.lower()
        self.hierarchy = hierarchy
        
    def search(self):
        found_songs = []
        total_items = sum(len(artist_data["artists"]) for artist_data in self.hierarchy.values())
        processed = 0
        
        for genre, artists in self.hierarchy.items():
            for artist, albums in artists.items():
                if self.query in genre.lower() or self.query in artist.lower():
                    for album, songs in albums.items():
                        found_songs.extend(songs)
                else:
                    for album, songs in albums.items():
                        if self.query in album.lower():
                            found_songs.extend(songs)
                        else:
                            for song in songs:
                                if isinstance(song, dict):
                                    if self.query in song.get("name", "").lower():
                                        found_songs.append(song)
                                elif isinstance(song, str):
                                    if self.query in song.lower():
                                        found_songs.append({
                                            "name": song,
                                            "url": "",
                                            "cover": ""
                                        })
                processed += 1
                self.progress.emit(int(processed * 100 / total_items))
                
        self.results.emit(found_songs)

class PaginatedGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QGridLayout(self)
        self.items_per_page = 12
        self.current_page = 0
        self.total_items = []
        
    def set_items(self, items):
        self.total_items = items
        self.total_pages = math.ceil(len(items) / self.items_per_page)
        self.show_current_page()
        
    def show_current_page(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.total_items))
        
        row = 0
        col = 0
        for idx in range(start_idx, end_idx):
            widget = self.create_item_widget(self.total_items[idx])
            self.layout.addWidget(widget, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.show_current_page()
            
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.show_current_page()

class CacheManager:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
    def get_cached_cover(self, url):
        if not url:
            return None
            
        filename = hashlib.md5(url.encode()).hexdigest() + ".jpg"
        cache_path = os.path.join(self.cache_dir, filename)
        
        if os.path.exists(cache_path):
            pixmap = QPixmap(cache_path)
            if not pixmap.isNull():
                return pixmap
                
        try:
            response = requests.get(url, timeout=5)
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                pixmap.save(cache_path)
                return pixmap
        except:
            pass
            
        return None


class BaseDialog(QDialog):
    def __init__(self, main_player, title, parent=None):
        super().__init__(parent)
        self.main_player = main_player
        self.setWindowTitle(title)
        self.current_theme = main_player.themes[main_player.current_theme_index]
        self.apply_theme()
        
    def apply_theme(self):
        theme = self.current_theme
        self.setStyleSheet(f"""
            QDialog {{
                background: {theme['gradient']};
                color: {theme['font_color']};
                border-radius: 10px;
            }}
            QLabel {{
                color: {theme['font_color']};
                font-size: 14px;
                background: transparent;
            }}
            QComboBox {{
                background: rgba(45, 45, 45, 0.7);
                border: none;
                border-radius: 5px;
                padding: 8px;
                color: {theme['font_color']};
                min-width: 150px;
            }}
            QPushButton {{
                background: rgba(45, 45, 45, 0.7);
                border: none;ff
                border-radius: 5px;
                padding: 8px 15px;
                color: {theme['font_color']};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(61, 61, 61, 0.8);
            }}
            QScrollBar:vertical {{
                background: #ccc;
                width : 10px;
                height : 7px;
            }}
             QScrollBar:horizontal{{
                background: #ccc;
                width : 7px;
                height : 10px;
             }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: #888;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                background: none;
            }}
        """)

class ModernContextMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QMenu {
                background-color: rgba(45, 45, 45, 0.95);
                border: 1px solid rgba(100, 100, 100, 0.3);
                border-radius: 8px;
                padding: 8px 4px;
            }
            QMenu::item {
                padding: 8px 25px 8px 15px;
                border-radius: 4px;
                margin: 2px 5px;
                color: white;
                min-width: 150px;
            }
            QMenu::item:selected {
                background-color: rgba(61, 61, 61, 0.8);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(100, 100, 100, 0.3);
                margin: 5px 15px;
            }
            QMenu::icon {
                padding-left: 15px;
                padding-right: 5px;
            }
            QMenu::indicator {
                width: 20px;
                height: 20px;
            }
        """)

class PlaylistContextMenu(ModernContextMenu):
    def __init__(self, playlist_dialog, song, parent=None):
        super().__init__(parent)
        self.playlist_dialog = playlist_dialog
        self.song = song

        add_to_menu = ModernContextMenu()
        add_to_menu.setTitle("Add to Other Playlist")
        add_to_menu.setIcon(QIcon(icon_path("playlist_add.png")))
        add_to_menu.setMinimumWidth(200)
        

        current_playlist_name = self.playlist_dialog.playlistListWidget.currentItem().text()
        for playlist_name in self.playlist_dialog.playlists.keys():
            if playlist_name != current_playlist_name:
                action = QAction(QIcon(icon_path("playlist.png")), playlist_name, add_to_menu)
                action.triggered.connect(lambda checked, p=playlist_name: self.playlist_dialog.addSongToOtherPlaylist(self.song, p))
                add_to_menu.addAction(action)

        if add_to_menu.actions():
            add_to_menu.addSeparator()
        
        create_new = add_to_menu.addAction(QIcon(icon_path("plus.png")), "Create New Playlist")
        create_new.triggered.connect(lambda: self.create_new_playlist())

        self.addMenu(add_to_menu)
        self.addSeparator()

        play_action = self.addAction(QIcon(icon_path("play.png")), "Play")
        play_action.triggered.connect(lambda: self.playlist_dialog.main_player.load_and_play(self.song))

        remove_action = self.addAction(QIcon(icon_path("delete.png")), "Remove from Playlist")
        remove_action.triggered.connect(self.remove_from_current_playlist)

    def create_new_playlist(self):
        name, ok = QInputDialog.getText(self.playlist_dialog, "Create Playlist", "Enter playlist name:")
        if ok and name:
            if name not in self.playlist_dialog.playlists:
                self.playlist_dialog.playlists[name] = [self.song]
                self.playlist_dialog.main_player.save_playlists()
                self.playlist_dialog.populatePlaylists()
                QMessageBox.information(self.playlist_dialog, "Success", f"Created playlist '{name}' with song")

    def remove_from_current_playlist(self):
        current_playlist = self.playlist_dialog.playlistListWidget.currentItem()
        if current_playlist:
            playlist_name = current_playlist.text()
            if self.song in self.playlist_dialog.playlists[playlist_name]:
                self.playlist_dialog.playlists[playlist_name].remove(self.song)
                self.playlist_dialog.updateSongsList(current_playlist, None)
                self.playlist_dialog.main_player.save_playlists()

class ThemeDisplay(QWidget):
    clicked = pyqtSignal(int)
    
    def __init__(self, theme, index, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.index = index
        self.setFixedSize(180, 100)
        self.setStyleSheet("""
            QWidget {
                border-radius: 10px;
                border: 2px solid transparent;
            }
            QWidget:hover {
                border: 2px solid white;
            }
        """)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient_str = self.theme["gradient"]
        if "stop:0" in gradient_str and "stop:1" in gradient_str:
            color1 = gradient_str.split("stop:0")[1].split(",")[0].strip()
            color2 = gradient_str.split("stop:1")[1].split(")")[0].strip()
            gradient.setColorAt(0, QColor(color1))
            gradient.setColorAt(1, QColor(color2))
            
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

        painter.setPen(QColor(self.theme["font_color"]))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        rect = self.rect()
        painter.drawText(rect, Qt.AlignCenter, self.theme["name"])
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)


class CaptchaWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.generateCaptcha()

    def initUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.captchaLabel = QLabel()
        self.captchaLabel.setFixedSize(150, 50)
        self.captchaLabel.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
        """)
        
        self.refreshBtn = QPushButton()
        self.refreshBtn.setIcon(QIcon(icon_path("refresh.png")))
        self.refreshBtn.setIconSize(QSize(40, 40))
        self.refreshBtn.setFixedSize(40, 40)
        self.refreshBtn.clicked.connect(self.generateCaptcha)
        self.refreshBtn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2);
            }
        """)
        
        layout.addWidget(self.captchaLabel)
        layout.addWidget(self.refreshBtn)
        layout.addStretch()

    def generateCaptcha(self):
        image = QPixmap(150, 50)
        image.fill(Qt.white)
        self.captchaText = ''.join(random.choices('0123456789', k=6))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        for _ in range(10):
            pen = QPen(QColor(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)))
            pen.setWidth(random.randint(1, 2))
            painter.setPen(pen)
            x1, y1 = random.randint(0, 150), random.randint(0, 50)
            x2, y2 = random.randint(0, 150), random.randint(0, 50)
            painter.drawLine(x1, y1, x2, y2)
        font = QFont('Arial', 20, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QPen(Qt.black))
        total_width = 150 
        char_count = len(self.captchaText)
        spacing = total_width / (char_count + 1) 
        
   
        x = spacing 
        for char in self.captchaText:
            painter.save()

            y_offset = random.randint(-3, 3)
            rotation = random.randint(-20, 20)
            painter.translate(x, 25 + y_offset)
            painter.rotate(rotation)
            painter.drawText(0, 0, char)
            painter.restore()
            x += spacing 
        
        painter.end()
        self.captchaLabel.setPixmap(image)

    def verify(self, text):
        return text == self.captchaText

# ================= Custom Widgets ================= #

class AnimatedPushButton(QPushButton):
    def __init__(self, normal_size=QSize(40, 40), scale=1.1, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._normal_size = normal_size
        self._hover_size = QSize(int(normal_size.width() * scale),
                                 int(normal_size.height() * scale))
        self.setIconSize(self._normal_size)
        self.setFixedSize(self._normal_size)
        self._anim = QPropertyAnimation(self, b"iconSize")
        self._anim.setDuration(150)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self.iconSize())
        self._anim.setEndValue(self._hover_size)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self.iconSize())
        self._anim.setEndValue(self._normal_size)
        self._anim.start()
        super().leaveEvent(event)

slider_normal_style = """
QSlider:horizontal { background: transparent; }
QSlider::groove:horizontal {
    border: 1px hidden white; height: 8px; background: white;
    margin: 2px 0; border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #0D41E1, stop:1 #0A85ED); border: 1px hidden #999; height: 8px;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #212529, stop:1 #495057) ; border: 1px hidden #5c5c5c;
    width: 14px; margin: -2px 0; border-radius: 5px;
}
QSlider::add-page:horizontal {
    background: white; border: 1px hidden #999;
    height: 8px; border-radius: 4px;
}
"""

slider_hover_style = """
QSlider:horizontal { background: transparent; }
QSlider::groove:horizontal {
    border: 1px hidden white; height: 8px; background: white;
    margin: 2px 0; border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #595CFF, stop:1 #C6F8FF); border: 1px hidden #999; height: 8px;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #E4E7E4, stop:1 #C0C4CA); border: 1px solid #5c5c5c;
    width: 12px; margin: -2px 0; border-radius: 6px;
}
QSlider::add-page:horizontal {
    background: white; border: 1px hidden #999;
    height: 8px; border-radius: 4px;
}
"""

class ClickableSlider(QSlider):
    sliderClicked = pyqtSignal(int)
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setStyleSheet(slider_normal_style)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            val = self.minimum() + (self.maximum() - self.minimum()) * event.x() / self.width()
            self.setValue(int(val))
            self.sliderClicked.emit(int(val))
        super().mousePressEvent(event)
    def enterEvent(self, event):
        self.setStyleSheet(slider_hover_style)
        super().enterEvent(event)
    def leaveEvent(self, event):
        self.setStyleSheet(slider_normal_style)
        super().leaveEvent(event)

class ProfileWidget(QWidget):
    clicked = pyqtSignal()
    
    def __init__(self, username="Guest", profile_pic=None, parent=None):
        super().__init__(parent)
        self.username = username
        self.profile_pic = profile_pic
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        self.picLabel = QLabel()
        self.picLabel.setFixedSize(50, 50)
        self.picLabel.setStyleSheet("""
            QLabel {
                background: transparent;
                border-radius: 25px;
            }
        """)
        self.update_picture(profile_pic)
        layout.addWidget(self.picLabel, alignment=Qt.AlignCenter)
        
        self.usernameLabel = QLabel(username)
        self.usernameLabel.setAlignment(Qt.AlignCenter)
        self.usernameLabel.setStyleSheet("color: white; font-size: 12px;")
        layout.addWidget(self.usernameLabel, alignment=Qt.AlignCenter)
        self.setLayout(layout)

    def create_circular_pixmap(self, pixmap):
        target = QPixmap(50, 50)
        target.fill(Qt.transparent)
        
        painter = QPainter(target)
        painter.setRenderHint(QPainter.Antialiasing, True)

        path = QPainterPath()
        path.addEllipse(0, 0, 50, 50)
        painter.setClipPath(path)
        
        painter.drawPixmap(0, 0, pixmap.scaled(50, 50, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        painter.end()
        
        return target

    def update_picture(self, profile_pic):
        if not profile_pic:
            return

        cache_path = os.path.join(CACHE_DIR, f"{self.username}.jpg")

        if profile_pic.startswith('http'):
            try:
                response = requests.get(profile_pic, timeout=5)
                if response.status_code == 200:
                    pixmap = QPixmap()
                    pixmap.loadFromData(response.content)
                    if not pixmap.isNull():
                        pixmap.save(cache_path, "JPEG")
                        self.picLabel.setPixmap(self.create_circular_pixmap(pixmap))
                        return
            except requests.RequestException:
                print("⚠️ Online fetch failed, trying cache...")

            if os.path.exists(cache_path):
                pixmap = QPixmap(cache_path)
                if not pixmap.isNull():
                    self.picLabel.setPixmap(self.create_circular_pixmap(pixmap))
                    return

        elif os.path.exists(profile_pic):
            pixmap = QPixmap(profile_pic)
            if not pixmap.isNull():
                self.picLabel.setPixmap(self.create_circular_pixmap(pixmap))

    def update_profile(self, username, profile_pic):
        self.username = username
        self.usernameLabel.setText(username)
        self.profile_pic = profile_pic
        self.update_picture(profile_pic)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

# ================= Download Classes ================= #

class DownloadWorker(QThread):
    progressChanged = pyqtSignal(int)
    speedUpdated = pyqtSignal(float)
    finishedDownloading = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)
    def __init__(self, url, filepath, parent=None):
        super().__init__(parent)
        self.url = url
        self.filepath = filepath
        self._is_interrupted = False
    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=10)
            if response.status_code != 200:
                self.errorOccurred.emit(f"Server error: {response.status_code}")
                return
            total_length = response.headers.get('content-length')
            total_length = int(total_length) if total_length else 0
            downloaded = 0
            chunk_size = 1024
            start_time = time.time()
            last_time = start_time
            last_downloaded = 0
            with open(self.filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self._is_interrupted:
                        break
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        percent = int(downloaded * 100 / total_length) if total_length else 0
                        self.progressChanged.emit(percent)
                        current_time = time.time()
                        if current_time - last_time >= 1:
                            speed = (downloaded - last_downloaded) / (current_time - last_time)
                            self.speedUpdated.emit(speed)
                            last_time = current_time
                            last_downloaded = downloaded
            self.speedUpdated.emit(0)
            self.progressChanged.emit(100)
            self.finishedDownloading.emit(self.filepath)
        except Exception as e:
            self.errorOccurred.emit(str(e))

class DownloadProgressDialog(QDialog):
    def __init__(self, url, filepath, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading...")
        self.setFixedSize(400, 150)
        self.url = url
        self.filepath = filepath
        self.setStyleSheet("""
            QProgressBar {
                border: 2px solid rgba(33, 37, 43, 180);
                border-radius: 10px; text-align: center;
                background-color: rgba(33, 37, 43, 180); color: black;
            }
            QProgressBar::chunk {
                background: #ff69b4; border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        self.statusLabel = QLabel("Downloading...")
        layout.addWidget(self.statusLabel)
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        layout.addWidget(self.progressBar)
        self.speedLabel = QLabel("Speed: 0 KB/s")
        layout.addWidget(self.speedLabel)
        self.closeButton = QPushButton("Close")
        self.closeButton.setEnabled(False)
        self.closeButton.clicked.connect(self.accept)
        layout.addWidget(self.closeButton, alignment=Qt.AlignRight)
        self.worker = DownloadWorker(self.url, self.filepath)
        self._worker = self.worker
        self.worker.finishedDownloading.connect(lambda: self._worker.deleteLater())
        self.worker.progressChanged.connect(self.update_progress)
        self.worker.speedUpdated.connect(self.update_speed)
        self.worker.finishedDownloading.connect(self.download_finished)
        self.worker.errorOccurred.connect(self.download_error)
        self.worker.start()
    def update_progress(self, percent):
        self.progressBar.setValue(percent)
    def update_speed(self, speed):
        speed_kb = speed / 1024
        self.speedLabel.setText(f"Speed: {speed_kb:.2f} KB/s")
    def download_finished(self, filepath):
        self.statusLabel.setText("Done")
        self.closeButton.setEnabled(True)
    def download_error(self, error_message):
        self.statusLabel.setText(f"Error: {error_message}")
        self.closeButton.setEnabled(True)

class DownloadsListDialog(BaseDialog):
    def __init__(self, music_folder, play_callback, parent=None):
        super().__init__(parent, "Downloaded Songs", parent)
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.setMinimumSize(800, 600)
        self.music_folder = music_folder
        self.play_callback = play_callback

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        
        title_container = QWidget()
        title_container.setObjectName("container")
        title_layout = QHBoxLayout(title_container)
        
        title_label = QLabel("Downloaded Songs")
        title_label.setFont(QFont("Exo 2 SemiBold", 16))
        title_layout.addWidget(title_label)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search downloads...")
        self.search_bar.textChanged.connect(self.filter_songs)
        title_layout.addWidget(self.search_bar)
        
        main_layout.addWidget(title_container)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.songs_container = QWidget()
        self.songs_grid = QGridLayout(self.songs_container)
        self.songs_grid.setSpacing(20)
        scroll.setWidget(self.songs_container)
        
        main_layout.addWidget(scroll)
        
        self.populate_list()

    def create_song_widget(self, filepath):
        widget = QWidget()
        widget.setFixedSize(150, 180)
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)
        cover_label = QLabel()
        cover_label.setFixedSize(140, 140)
        cover_label.setAlignment(Qt.AlignCenter)
        
        pixmap = get_album_art(filepath)
        if pixmap and not pixmap.isNull():
            cover_label.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            cover_label.setPixmap(QPixmap(icon_path("music.png")).scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        cover_label.setStyleSheet("""
            QLabel {
                background: rgba(45, 45, 45, 0.7);
                border-radius: 10px;
            }
        """)
        name = self.name_get(filepath)
        name_label = QLabel(name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet(f"color: {self.current_theme['font_color']};")

        layout.addWidget(cover_label)
        layout.addWidget(name_label)

        widget.filepath = filepath
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(lambda pos, fp=filepath: self.show_context_menu(pos, fp))
        widget.mousePressEvent = lambda e, fp=filepath: self.song_clicked(e, fp)

        return widget
    
    def name_get(self , song):
            if isinstance(song , str) :
                name = os.path.basename(song)
                name = name[:15]   
                return name
            else : 
                name = song.get("name", "Unknown")
                name = name[:15]
                return name

    def show_context_menu(self, pos, filepath):
        menu = ModernContextMenu(self)
        menu.setMinimumWidth(200)
        
        add_to_menu = ModernContextMenu()
        add_to_menu.setMinimumWidth(200)
        add_to_menu.setTitle("Add to Playlist")
        add_to_menu.setIcon(QIcon(icon_path("playlist_add.png")))
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(2)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        parent = self.parent()
        if parent and hasattr(parent, 'playlists'):
            for playlist_name in parent.playlists.keys():
                action = QAction(QIcon(icon_path("playlist.png")), playlist_name, add_to_menu)
                action.triggered.connect(lambda checked, p=playlist_name: self.add_to_playlist(filepath, p))
                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(8, 4, 8, 4)
                action_layout.addWidget(QLabel(playlist_name))
                action_layout.addStretch()
                scroll_layout.addWidget(action_widget)
                add_to_menu.addAction(action)

            add_to_menu.addSeparator()
            create_new = add_to_menu.addAction(QIcon(icon_path("plus.png")), "Create New Playlist")
            create_new.triggered.connect(lambda: self.create_new_playlist(filepath))

        menu.addMenu(add_to_menu)
        menu.addSeparator()
        play_action = menu.addAction(QIcon(icon_path("play.png")), "Play")
        play_action.triggered.connect(lambda: self.play_callback(filepath))

        global_pos = self.mapToGlobal(pos)
        sender = self.sender()
        if sender:
            global_pos = sender.mapToGlobal(pos)

        menu.exec_(global_pos)

    def add_to_playlist(self, filepath, playlist_name):
        parent = self.parent()
        if parent and hasattr(parent, 'playlists'):
            if filepath not in parent.playlists[playlist_name]:
                parent.playlists[playlist_name].append(filepath)
                parent.save_playlists()
                QMessageBox.information(self, "Success", f"Song added to {playlist_name}")

    def create_new_playlist(self, filepath):
        parent = self.parent()
        if parent and hasattr(parent, 'playlists'):
            name, ok = QInputDialog.getText(self, "Create Playlist", "Enter playlist name:")
            if ok and name:
                if name not in parent.playlists:
                    parent.playlists[name] = [filepath]
                    parent.save_playlists()
                    QMessageBox.information(self, "Success", f"Created playlist '{name}' with song")

    def populate_list(self):
        while self.songs_grid.count():
            child = self.songs_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        row = 0
        col = 0
        max_cols = 4

        for filename in os.listdir(self.music_folder):
            if filename.lower().endswith((".mp3", ".wav", ".flac", ".ogg")):
                filepath = os.path.join(self.music_folder, filename)
                song_widget = self.create_song_widget(filepath)
                self.songs_grid.addWidget(song_widget, row, col)
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1

    def filter_songs(self, text):
        text = text.lower()
        row = 0
        col = 0
        max_cols = 4

        while self.songs_grid.count():
            child = self.songs_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for filename in os.listdir(self.music_folder):
            if filename.lower().endswith((".mp3", ".wav", ".flac", ".ogg")):
                if text in filename.lower():
                    filepath = os.path.join(self.music_folder, filename)
                    song_widget = self.create_song_widget(filepath)
                    self.songs_grid.addWidget(song_widget, row, col)
                    
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1

    def song_clicked(self, event, filepath):
        if event.button() == Qt.LeftButton:
            if callable(self.play_callback):
                self.play_callback(filepath)
                self.accept()

# ------------------ SongItemWidget ------------------ #


song_item_widget_style_sheet_title_lable = "color: black; font-size: 14px;"
song_item_widget_style_sheet_btn_container = "border: 1px solid white; border-radius: 5px;"


class SongItemWidget(QWidget):
    def __init__(self, song, parent_library):
        super().__init__()
        self.song = song
        self.parent_library = parent_library

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(10)

        self.titleLabel = QLabel(song.get("name", "Unknown Song"))
        self.titleLabel.setStyleSheet(song_item_widget_style_sheet_title_lable)
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.titleLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        main_layout.addWidget(self.titleLabel, stretch=1)

        btn_container = QWidget()
        btn_container.setStyleSheet(song_item_widget_style_sheet_btn_container)
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(10, 10, 10, 35)
        btn_layout.setSpacing(15)

        self.playButton = QPushButton()
        self.playButton.setStyleSheet("background-color: transparent; border: none;")
        self.playButton.setFixedSize(30, 30)
        self.playButton.setIconSize(QSize(30, 30))
        self.playButton.setIcon(QIcon(icon_path("play.png")))
        self.playButton.setToolTip("Play Online")
        self.playButton.clicked.connect(self.play_song)
        btn_layout.addWidget(self.playButton)

        self.downloadButton = QPushButton()
        self.downloadButton.setStyleSheet("background-color: transparent; border: none;")
        self.downloadButton.setFixedSize(30, 30)
        self.downloadButton.setIconSize(QSize(30, 30))
        self.downloadButton.setIcon(QIcon(icon_path("download.png")))
        self.downloadButton.setToolTip("Download Song")
        self.downloadButton.clicked.connect(self.download_song)
        btn_layout.addWidget(self.downloadButton)

        main_layout.addWidget(btn_container)
        self.setLayout(main_layout)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def play_song(self):
        url = self.song.get("url", "")
        if url and self.parent_library.parent() and hasattr(self.parent_library.parent(), "load_and_play"):
            self.parent_library.parent().load_and_play(self.song)
            self.parent_library.accept()

    def download_song(self):
        url = self.song.get("url", "")
        if url:
            download_folder = "music"
            filename = self.song.get("name", "Unknown") + ".mp3"
            filepath = os.path.join(download_folder, filename)
            dialog = DownloadProgressDialog(url, filepath, self)
            dialog.exec_()

    def show_context_menu(self, pos):
        menu = QMenu(self)
        for playlist_name in self.parent_library.parent().playlists.keys():
            menu.addAction(playlist_name)
        menu.addSeparator()
        create_action = menu.addAction("Create New Playlist")
        action = menu.exec_(self.mapToGlobal(pos))
        if action:
            if action.text() == "Create New Playlist":
                name, ok = QInputDialog.getText(self, "Create Playlist", "Enter playlist name:")
                if ok and name:
                    if name not in self.parent_library.parent().playlists:
                        self.parent_library.parent().playlists[name] = [self.song]
                        self.parent_library.parent().save_playlists()
            else:
                playlist_name = action.text()
                if self.song not in self.parent_library.parent().playlists.get(playlist_name, []):
                    self.parent_library.parent().playlists[playlist_name].append(self.song)
                    self.parent_library.parent().save_playlists()

# ------------------ OnlineLibraryDialog ------------------ #


OnlineLibraryDialog_style_sheet = """
            QDialog {
                background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED);
                color: white;
            }
            QLabel { color: white; }
            QPushButton {
                background-color: transparent;
                border: 1px solid white;
                border-radius: 4px;
                padding: 8px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); }
            QLineEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
                color: black;
            }
            QListWidget { background-color: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED); color: white; font-size: 16px; }
        """

genre_page_style_sheet = """border: 1px solid white; border-radius: 4px; padding: 8px;"""


class OnlineLibraryDialog(BaseDialog):
    def __init__(self, main_player, is_admin=False, parent=None):
        super().__init__(main_player, "Online Music Library", parent)
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.setMinimumSize(1200, 800)
        self.is_admin = is_admin
        self.main_player = main_player

        try:
            self.cache_manager = CacheManager()
        except Exception as e:
            print(f"Error initializing cache manager: {e}")
            self.cache_manager = None

        self.hierarchy = {}
        self.current_genre = None
        self.current_artist = None
        self.current_album = None

        self.load_thread = None
        self.load_worker = None
        self.search_thread = None
        self.search_worker = None
        self.active_threads = []
        self.is_loading = True

        if not is_connected():
            self.setup_offline_ui()
            return

        self.setup_basic_ui()
        self.start_loading()

    def setup_basic_ui(self):
        try:
            mainLayout = QVBoxLayout(self)
            mainLayout.setSpacing(20)

            header = QWidget()
            header.setObjectName("container")
            header_layout = QHBoxLayout(header)
            
            self.searchBar = QLineEdit()
            self.searchBar.setPlaceholderText("Search...")
            self.searchBar.setFont(QFont("Exo 2", 10))
            self.searchBar.setEnabled(False)
            header_layout.addWidget(self.searchBar)
            
            if self.is_admin:
                self.adminUploadBtn = QPushButton()
                try:
                    self.adminUploadBtn.setIcon(QIcon(icon_path("plus.png")))
                except:
                    pass
                self.adminUploadBtn.setToolTip("Admin: Upload New Song")
                self.adminUploadBtn.clicked.connect(self.open_admin_upload)
                self.adminUploadBtn.setEnabled(False)
                header_layout.addWidget(self.adminUploadBtn)
                
            mainLayout.addWidget(header)

            self.loading_label = QLabel("Loading Online Library...")
            self.loading_label.setAlignment(Qt.AlignCenter)
            self.loading_label.setFont(QFont("Exo 2 SemiBold", 18))
            self.loading_label.setStyleSheet(f"color: {self.current_theme['font_color']};")
            mainLayout.addWidget(self.loading_label)

            self.progress_bar = QProgressBar()
            self.progress_bar.setStyleSheet('''

                    QProgressBar {
                        border: 2px solid rgba(33, 37, 43, 180);
                        border-radius: 10px; text-align: center;
                        background-color: rgba(33, 37, 43, 180); color: black;
                    }
                    QProgressBar::chunk {
                        background: #ff69b4; border-radius: 10px;
                    }

            ''')
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            mainLayout.addWidget(self.progress_bar)

            self.stack = QStackedWidget(self)
            self.stack.setVisible(False)
            mainLayout.addWidget(self.stack)
            
        except Exception as e:
            print(f"Error in setup_basic_ui: {e}")
            self.setup_offline_ui()

    def setup_offline_ui(self):
        mainLayout = QVBoxLayout(self)

        error_label = QLabel("Cannot connect to online library.\nPlease check your internet connection and try again.")
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setFont(QFont("Exo 2 SemiBold", 16))
        error_label.setStyleSheet(f"color: {self.current_theme['font_color']};")
        mainLayout.addWidget(error_label)

        retry_btn = QPushButton("Retry Connection")
        retry_btn.clicked.connect(self.retry_connection)
        retry_btn.setFixedSize(200, 40)
        mainLayout.addWidget(retry_btn, alignment=Qt.AlignCenter)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        close_btn.setFixedSize(100, 40)
        mainLayout.addWidget(close_btn, alignment=Qt.AlignCenter)

    def retry_connection(self):
        if is_connected():
            layout = self.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            
            self.is_loading = True
            self.setup_basic_ui()
            self.start_loading()
        else:
            QMessageBox.warning(self, "Connection Error", "Still no internet connection. Please check your network.")

    def start_loading(self):
        try:
            self.load_thread = QThread()
            self.load_worker = LibraryLoader()
            self.load_worker.moveToThread(self.load_thread)
            
            self.load_worker.progress.connect(self.update_progress)
            self.load_worker.finished.connect(self.on_loading_finished)
            self.load_thread.started.connect(self.load_worker.load_library)
            self.load_thread.finished.connect(self.load_thread.deleteLater)

            self.active_threads.append(self.load_thread)
            self.load_thread.start()
            
        except Exception as e:
            print(f"Error starting loading thread: {e}")
            self.on_loading_error("Failed to start loading thread")

    def update_progress(self, value):
        try:
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setValue(value)
        except Exception as e:
            print(f"Error updating progress: {e}")

    def on_loading_finished(self, library_data):
        try:
            self.is_loading = False
            
            if library_data and library_data != {}:
                self.hierarchy = library_data
                self.loading_label.setText("Setting up interface...")
                QTimer.singleShot(100, lambda: self.setup_main_ui(library_data))
            else:
                self.on_loading_error("No data received from server")
                
        except Exception as e:
            print(f"Error in on_loading_finished: {e}")
            self.on_loading_error(f"Error processing data: {e}")

    def on_loading_error(self, error_msg):
        try:
            if hasattr(self, 'loading_label'):
                self.loading_label.setText(f"Error: {error_msg}")
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setVisible(False)

            retry_btn = QPushButton("Retry")
            retry_btn.clicked.connect(self.retry_loading)
            
            layout = self.layout()
            if layout:
                layout.addWidget(retry_btn, alignment=Qt.AlignCenter)
                
        except Exception as e:
            print(f"Error in on_loading_error: {e}")

    def retry_loading(self):
        layout = self.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        self.is_loading = True
        self.hierarchy = {}

        self.setup_basic_ui()
        self.start_loading()

    def setup_main_ui(self, library_data):
        try:
            self.hierarchy = library_data

            if hasattr(self, 'loading_label'):
                self.loading_label.setVisible(False)
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setVisible(False)

            if hasattr(self, 'searchBar'):
                self.searchBar.setEnabled(True)
                self.searchBar.textChanged.connect(self.update_search_results)
            if hasattr(self, 'adminUploadBtn'):
                self.adminUploadBtn.setEnabled(True)

            self.genrePage = QWidget()
            self.artistPage = QWidget()
            self.albumPage = QWidget()
            self.songPage = QWidget()
            self.searchPage = QWidget()
            
            self.create_pages()

            self.stack.addWidget(self.genrePage)
            self.stack.addWidget(self.artistPage)
            self.stack.addWidget(self.albumPage)
            self.stack.addWidget(self.songPage)
            self.stack.addWidget(self.searchPage)

            self.stack.setVisible(True)
            self.stack.setCurrentWidget(self.genrePage)

            QTimer.singleShot(1000, self.cleanup_loading_thread)
            
        except Exception as e:
            print(f"Error in setup_main_ui: {e}")
            self.on_loading_error(f"Failed to setup interface: {e}")

    def create_pages(self):
        try:
            self.create_genre_page()
            self.create_artist_page()
            self.create_album_page()
            self.create_song_page()
            self.create_search_page()
        except Exception as e:
            print(f"Error creating pages: {e}")

    def create_genre_page(self):
        try:
            layout = QVBoxLayout(self.genrePage)
            layout.setSpacing(20)
 
            header = QWidget()
            header.setObjectName("container")
            header_layout = QHBoxLayout(header)
            
            title = QLabel("Select Genre")
            title.setFont(QFont("Exo 2 SemiBold", 24))
            title.setStyleSheet(f"color: {self.current_theme['font_color']};")
            
            self.genre_search = QLineEdit()
            self.genre_search.setPlaceholderText("Search genres...")
            self.genre_search.textChanged.connect(self.display_genres)
            self.genre_search.setStyleSheet(f"""
                QLineEdit {{
                    background: rgba(45, 45, 45, 0.7);
                    border: none;
                    border-radius: 15px;
                    padding: 8px 15px;
                    color: {self.current_theme['font_color']};
                    font-size: 14px;
                    margin: 5px;
                }}
                QLineEdit:focus {{
                    background: rgba(61, 61, 61, 0.8);
                }}
            """)
            
            header_layout.addWidget(title)
            header_layout.addWidget(self.genre_search)
            layout.addWidget(header)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            
            self.genres_container = QWidget()
            self.genres_grid = QGridLayout(self.genres_container)
            self.genres_grid.setSpacing(20)
            
            self.display_genres()
            
            scroll.setWidget(self.genres_container)
            layout.addWidget(scroll)
            
        except Exception as e:
            print(f"Error creating genre page: {e}")

    def display_genres(self, filter_text=""):

        try:
            while self.genres_grid.count():
                child = self.genres_grid.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
  
            if hasattr(self, 'genre_search'):
                filter_text = self.genre_search.text()

            genre_styles = {
                "Rock": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF4E50, stop:1 #F9D423)",
                "Pop": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FC466B, stop:1 #3F5EFB)", 
                "Jazz": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1CB5E0, stop:1 #000851)",
                "Classical": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFEFBA, stop:1 #FFFFFF)",
                "Electronic": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8E2DE2, stop:1 #4A00E0)",
                "Hip Hop": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFB75E, stop:1 #ED8F03)",
                "Blues": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0F2027, stop:1 #2C5364)",
                "Metal": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #434343, stop:1 #000000)",
                "Alternative": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #667db6, stop:1 #0082c8)"
            }

            row = 0
            col = 0
            max_cols = 4
            
            for genre, artists in self.hierarchy.items():
                if filter_text.lower() in genre.lower():
                    genre_widget = self.create_genre_widget(genre, artists, genre_styles)
                    self.genres_grid.addWidget(genre_widget, row, col)
                    
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
                        
        except Exception as e:
            print(f"Error displaying genres: {e}")

    def create_genre_widget(self, genre, artists, genre_styles):
        try:
            widget = QWidget()
            widget.setFixedSize(200, 200)
            widget.setCursor(Qt.PointingHandCursor)
            
            layout = QVBoxLayout(widget)
            layout.setSpacing(10)
            cover_container = QLabel()
            cover_container.setFixedSize(140, 140)
            cover_container.setAlignment(Qt.AlignCenter)
            self.load_genre_cover(genre, artists, cover_container)
            
            gradient = genre_styles.get(genre, "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #808080, stop:1 #3F3F3F)")
            
            widget.setStyleSheet(f"""
                QWidget {{
                    background: {gradient};
                    border-radius: 10px;
                }}
                QLabel {{
                    color: white;
                    background: transparent;
                }}
                QWidget:hover {{
                    background: {gradient};
                    border: 2px solid rgba(255, 255, 255, 0.3);
                }}
            """)
            
            layout.addWidget(cover_container, alignment=Qt.AlignCenter)
            display_name = genre if len(genre) <= 20 else f"{genre[:17]}..."
            song_count = sum(len(songs) for artist in artists.values() for songs in artist.values())
            name_label = QLabel(f"{display_name}\n{song_count} songs")
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setFont(QFont("Exo 2 Medium", 14))
            name_label.setStyleSheet("color: white; font-weight: bold;")
            layout.addWidget(name_label)
            widget.mousePressEvent = lambda e, g=genre: self.go_to_artist_page(g) if e.button() == Qt.LeftButton else None
            
            return widget
            
        except Exception as e:
            print(f"Error creating genre widget for {genre}: {e}")
            widget = QWidget()
            widget.setFixedSize(200, 200)
            return widget

    def load_genre_cover(self, genre, artists, cover_container):
        try:
            cover_found = False
            if self.cache_manager:
                for artist_albums in artists.values():
                    for album_songs in artist_albums.values():
                        for song in album_songs:
                            if isinstance(song, dict) and 'cover' in song and song['cover']:
                                cover_url = song['cover']
                                if cover_url.startswith('http'):
                                    try:
                                        pixmap = self.cache_manager.get_cached_cover(cover_url)
                                        if pixmap and not pixmap.isNull():
                                            cover_container.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                            cover_found = True
                                            break
                                    except Exception as e:
                                        print(f"Error loading cover for genre {genre}: {e}")
                                        continue
                            if cover_found:
                                break
                        if cover_found:
                            break
                    if cover_found:
                        break
            
            if not cover_found:
                self.set_default_cover(cover_container, "genre.png", 140)
                
        except Exception as e:
            print(f"Error in load_genre_cover for {genre}: {e}")
            self.set_default_cover(cover_container, "genre.png", 140)

    def set_default_cover(self, label, icon_name, size):
        try:
            default_pixmap = QPixmap(icon_path(icon_name))
            if not default_pixmap.isNull():
                label.setPixmap(default_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                fallback_pixmap = QPixmap(size, size)
                fallback_pixmap.fill(Qt.darkGray)
                label.setPixmap(fallback_pixmap)
        except Exception as e:
            print(f"Error setting default cover: {e}")
            fallback_pixmap = QPixmap(size, size)
            fallback_pixmap.fill(Qt.darkGray)
            label.setPixmap(fallback_pixmap)

    def go_to_artist_page(self, genre):
        try:
            self.current_genre = genre
            self.artistTitle.setText(f"Artists in {genre}")

            if hasattr(self, 'artist_scroll') and self.artist_scroll.widget():
                old_widget = self.artist_scroll.widget()
                old_widget.deleteLater()

            container = QWidget()
            grid = QGridLayout(container)
            grid.setSpacing(20)
            
            artists = self.hierarchy.get(genre, {})
            row = 0
            col = 0
            max_cols = 4
            
            for artist in artists.keys():
                artist_widget = self.create_artist_widget(artist)
                grid.addWidget(artist_widget, row, col)
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            
            container.setLayout(grid)
            self.artist_scroll.setWidget(container)
            self.stack.setCurrentWidget(self.artistPage)
            
        except Exception as e:
            print(f"Error in go_to_artist_page: {e}")

    def create_artist_page(self):
        """Create the artist selection page"""
        try:
            layout = QVBoxLayout(self.artistPage)
            layout.setSpacing(20)
            
            header = QWidget()
            header.setObjectName("container")
            header_layout = QHBoxLayout(header)
            
            backBtn = QPushButton("← Back to Genres")
            try:
                backBtn.setIcon(QIcon(icon_path("back.png")))
            except:
                pass
            backBtn.clicked.connect(self.go_back_to_genres)
            backBtn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(45, 45, 45, 0.7);
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    color: {self.current_theme['font_color']};
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background: rgba(61, 61, 61, 0.8);
                }}
            """)
            header_layout.addWidget(backBtn)
            
            self.artistTitle = QLabel("Artists")
            self.artistTitle.setFont(QFont("Exo 2 SemiBold", 24))
            self.artistTitle.setStyleSheet(f"color: {self.current_theme['font_color']};")
            header_layout.addWidget(self.artistTitle)
            
            header_layout.addStretch()
            layout.addWidget(header)
            
            self.artist_scroll = QScrollArea()
            self.artist_scroll.setWidgetResizable(True)
            self.artist_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            layout.addWidget(self.artist_scroll)
            
        except Exception as e:
            print(f"Error creating artist page: {e}")

    def create_artist_widget(self, artist):
        """Create artist widget with proper cover loading"""
        try:
            widget = QWidget()
            widget.setFixedSize(200, 240)
            widget.setCursor(Qt.PointingHandCursor)
            
            artist_layout = QVBoxLayout(widget)
            artist_layout.setSpacing(10)
            
            icon_label = QLabel()
            icon_label.setFixedSize(180, 180)
            icon_label.setAlignment(Qt.AlignCenter)

            self.load_artist_cover(artist, icon_label)
            

            display_name = artist if len(artist) <= 25 else f"{artist[:22]}..."
            name_label = QLabel(display_name)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setFont(QFont("Exo 2 Medium", 14))
            name_label.setStyleSheet("color: white; font-weight: bold;")
            
            albums_count = len(self.hierarchy.get(self.current_genre, {}).get(artist, {}))
            count_label = QLabel(f"{albums_count} albums")
            count_label.setAlignment(Qt.AlignCenter)
            count_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
            
            artist_layout.addWidget(icon_label)
            artist_layout.addWidget(name_label)
            artist_layout.addWidget(count_label)
            
            widget.setStyleSheet("""
                QWidget {
                    background: rgba(45, 45, 45, 0.7);
                    border-radius: 10px;
                }
                QWidget:hover {
                    background: rgba(61, 61, 61, 0.8);
                }
            """)
        
            widget.mousePressEvent = lambda e, a=artist: self.go_to_album_page(a) if e.button() == Qt.LeftButton else None
            
            return widget
            
        except Exception as e:
            print(f"Error creating artist widget for {artist}: {e}")
            widget = QWidget()
            widget.setFixedSize(200, 240)
            widget.setStyleSheet("background: rgba(45, 45, 45, 0.7); border-radius: 10px;")
            return widget

    def load_artist_cover(self, artist, icon_label):
        try:
            cover_found = False
            if self.cache_manager:
                albums = self.hierarchy.get(self.current_genre, {}).get(artist, {})
                
                for album_songs in albums.values():
                    for song in album_songs:
                        if isinstance(song, dict) and 'cover' in song and song['cover']:
                            cover_url = song['cover']
                            if cover_url.startswith('http'):
                                try:
                                    pixmap = self.cache_manager.get_cached_cover(cover_url)
                                    if pixmap and not pixmap.isNull():
                                        icon_label.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                        cover_found = True
                                        break
                                except Exception as e:
                                    print(f"Error loading artist cover for {artist}: {e}")
                                    continue
                    if cover_found:
                        break
            
            if not cover_found:
                self.set_default_cover(icon_label, "artist.png", 180)
                
        except Exception as e:
            print(f"Error in load_artist_cover for {artist}: {e}")
            self.set_default_cover(icon_label, "artist.png", 180)

    def go_back_to_genres(self):
        try:
            self.stack.setCurrentWidget(self.genrePage)
        except Exception as e:
            print(f"Error going back to genres: {e}")

    def go_to_album_page(self, artist):
        try:
            self.current_artist = artist
            self.albumTitle.setText(f"Albums by {artist}")
            
            if hasattr(self, 'album_scroll') and self.album_scroll.widget():
                old_widget = self.album_scroll.widget()
                old_widget.deleteLater()
            
            container = QWidget()
            grid = QGridLayout(container)
            grid.setSpacing(20)
            
            albums = self.hierarchy.get(self.current_genre, {}).get(artist, {})
            row = 0
            col = 0
            max_cols = 4
            
            for album_name, songs in albums.items():
                album_widget = self.createAlbumWidget(album_name, songs)
                grid.addWidget(album_widget, row, col)
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            
            container.setLayout(grid)
            self.album_scroll.setWidget(container)
            self.stack.setCurrentWidget(self.albumPage)
            
        except Exception as e:
            print(f"Error in go_to_album_page: {e}")

    def create_album_page(self):
        try:
            layout = QVBoxLayout(self.albumPage)
            layout.setSpacing(20)
            
            header = QWidget()
            header.setObjectName("container")
            header_layout = QHBoxLayout(header)
            
            backBtn = QPushButton("← Back to Artists")
            try:
                backBtn.setIcon(QIcon(icon_path("back.png")))
            except:
                pass
            backBtn.clicked.connect(self.go_back_to_artists)
            backBtn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(45, 45, 45, 0.7);
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    color: {self.current_theme['font_color']};
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background: rgba(61, 61, 61, 0.8);
                }}
            """)
            header_layout.addWidget(backBtn)
            
            self.albumTitle = QLabel("Albums")
            self.albumTitle.setFont(QFont("Exo 2 SemiBold", 24))
            self.albumTitle.setStyleSheet(f"color: {self.current_theme['font_color']};")
            header_layout.addWidget(self.albumTitle)
            
            header_layout.addStretch()
            layout.addWidget(header)

            self.album_scroll = QScrollArea()
            self.album_scroll.setWidgetResizable(True)
            self.album_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            layout.addWidget(self.album_scroll)
            
        except Exception as e:
            print(f"Error creating album page: {e}")

    def go_back_to_artists(self):
        try:
            self.stack.setCurrentWidget(self.artistPage)
        except Exception as e:
            print(f"Error going back to artists: {e}")

    def createAlbumWidget(self, album_name, songs):
        try:
            widget = QWidget()
            widget.setFixedSize(200, 240)
            widget.setCursor(Qt.PointingHandCursor)
            
            album_layout = QVBoxLayout(widget)
            album_layout.setSpacing(10)
            

            cover_label = QLabel()
            cover_label.setFixedSize(180, 180)
            cover_label.setAlignment(Qt.AlignCenter)

            self.load_album_cover(songs, cover_label)
            

            display_name = album_name if len(album_name) <= 25 else f"{album_name[:22]}..."
            name_label = QLabel(display_name)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setFont(QFont("Exo 2 Medium", 14))
            name_label.setStyleSheet("color: white; font-weight: bold;")
            
            count_label = QLabel(f"{len(songs)} songs")
            count_label.setAlignment(Qt.AlignCenter)
            count_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
            
            album_layout.addWidget(cover_label)
            album_layout.addWidget(name_label)
            album_layout.addWidget(count_label)
            
            widget.setStyleSheet("""
                QWidget {
                    background: rgba(45, 45, 45, 0.7);
                    border-radius: 10px;
                }
                QWidget:hover {
                    background: rgba(61, 61, 61, 0.8);
                }
            """)
            
            widget.setContextMenuPolicy(Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda pos: self.showAlbumContextMenu(pos, album_name))

            def handle_mouse_press(event):
                if event.button() == Qt.LeftButton:
                    self.go_to_song_page(album_name)
                
            widget.mousePressEvent = handle_mouse_press
            
            return widget
            
        except Exception as e:
            print(f"Error creating album widget: {e}")
            widget = QWidget()
            widget.setFixedSize(200, 240)
            widget.setStyleSheet("background: rgba(45, 45, 45, 0.7); border-radius: 10px;")
            return widget

    def load_album_cover(self, songs, cover_label):
        """Load album cover with proper error handling"""
        try:
            cover_loaded = False
            if songs and isinstance(songs[0], dict) and self.cache_manager:
                cover_url = songs[0].get('cover')
                if cover_url and cover_url.startswith('http'):
                    try:
                        pixmap = self.cache_manager.get_cached_cover(cover_url)
                        if pixmap and not pixmap.isNull():
                            cover_label.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            cover_loaded = True
                    except Exception as e:
                        print(f"Error loading album cover: {e}")
            
            if not cover_loaded:
                self.set_default_cover(cover_label, "album.png", 180)
                
        except Exception as e:
            print(f"Error in load_album_cover: {e}")
            self.set_default_cover(cover_label, "album.png", 180)

    def showAlbumContextMenu(self, pos, album_name):
        """Show context menu for albums"""
        try:
            menu = ModernContextMenu(self)
            menu.setMinimumWidth(200)
            
            play_all_action = menu.addAction(QIcon(icon_path("play.png")), "Play All")
            play_all_action.triggered.connect(lambda: self.play_all_album(album_name))
            
            menu.addSeparator()
            
            add_to_menu = ModernContextMenu()
            add_to_menu.setTitle("Add All to Playlist")
            add_to_menu.setIcon(QIcon(icon_path("playlist_add.png")))
            add_to_menu.setMinimumWidth(200)
            
            if self.main_player and hasattr(self.main_player, 'playlists'):
                for playlist_name in self.main_player.playlists.keys():
                    action = QAction(QIcon(icon_path("playlist.png")), playlist_name, add_to_menu)
                    action.triggered.connect(lambda checked, p=playlist_name: self.add_album_to_playlist(album_name, p))
                    add_to_menu.addAction(action)

                if self.main_player.playlists:
                    add_to_menu.addSeparator()
                    
                create_new = add_to_menu.addAction(QIcon(icon_path("plus.png")), "Create New Playlist")
                create_new.triggered.connect(lambda: self.create_new_playlist_with_album(album_name))
                
                menu.addMenu(add_to_menu)
                
            sender = self.sender()
            if sender:
                global_pos = sender.mapToGlobal(pos)
            else:
                global_pos = self.mapToGlobal(pos)
            menu.exec_(global_pos)
            
        except Exception as e:
            print(f"Error showing album context menu: {e}")

    def play_all_album(self, album_name):
        """Play all songs in album"""
        try:
            songs = self.hierarchy.get(self.current_genre, {}).get(self.current_artist, {}).get(album_name, [])
            if songs and self.main_player:
                self.main_player.play_playlist(songs)
                self.accept()
        except Exception as e:
            print(f"Error playing album: {e}")

    def add_album_to_playlist(self, album_name, playlist_name):
        """Add all songs from album to existing playlist"""
        try:
            songs = self.hierarchy.get(self.current_genre, {}).get(self.current_artist, {}).get(album_name, [])
            if songs and self.main_player and hasattr(self.main_player, 'playlists'):
                for song in songs:
                    if song not in self.main_player.playlists[playlist_name]:
                        self.main_player.playlists[playlist_name].append(song)
                self.main_player.save_playlists()
                QMessageBox.information(self, "Success", f"Album added to {playlist_name}")
        except Exception as e:
            print(f"Error adding album to playlist: {e}")

    def create_new_playlist_with_album(self, album_name):
        """Create new playlist with all songs from album"""
        try:
            songs = self.hierarchy.get(self.current_genre, {}).get(self.current_artist, {}).get(album_name, [])
            if songs and self.main_player and hasattr(self.main_player, 'playlists'):
                name, ok = QInputDialog.getText(self, "Create Playlist", "Enter playlist name:")
                if ok and name:
                    if name not in self.main_player.playlists:
                        self.main_player.playlists[name] = songs.copy()
                        self.main_player.save_playlists()
                        QMessageBox.information(self, "Success", f"Created playlist '{name}' with album")
        except Exception as e:
            print(f"Error creating new playlist with album: {e}")

    def go_to_song_page(self, album):
        """Navigate to song page for selected album"""
        try:
            self.current_album = album
            songs = self.hierarchy.get(self.current_genre, {}).get(self.current_artist, {}).get(album, [])
            
            self.songTitle.setText(f"Songs from {album}")

            if hasattr(self, 'song_scroll') and self.song_scroll.widget():
                old_widget = self.song_scroll.widget()
                old_widget.deleteLater()
            
            container = QWidget()
            grid = QGridLayout(container)
            grid.setSpacing(20)
            
            row = 0
            col = 0
            max_cols = 4
            
            for song in songs:
                song_widget = self.createSongWidget(song)
                grid.addWidget(song_widget, row, col)
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            
            container.setLayout(grid)
            self.song_scroll.setWidget(container)
            self.stack.setCurrentWidget(self.songPage)
            
        except Exception as e:
            print(f"Error in go_to_song_page: {e}")

    def create_song_page(self):
        try:
            layout = QVBoxLayout(self.songPage)
            layout.setSpacing(20)
            
            header = QWidget()
            header.setObjectName("container")
            header_layout = QHBoxLayout(header)
            
            backBtn = QPushButton("← Back to Albums")
            try:
                backBtn.setIcon(QIcon(icon_path("back.png")))
            except:
                pass
            backBtn.clicked.connect(self.go_back_to_albums)
            backBtn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(45, 45, 45, 0.7);
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    color: {self.current_theme['font_color']};
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background: rgba(61, 61, 61, 0.8);
                }}
            """)
            header_layout.addWidget(backBtn)
            
            self.songTitle = QLabel("Songs")
            self.songTitle.setFont(QFont("Exo 2 SemiBold", 24))
            self.songTitle.setStyleSheet(f"color: {self.current_theme['font_color']};")
            header_layout.addWidget(self.songTitle)
            
            header_layout.addStretch()
            layout.addWidget(header)

            self.song_scroll = QScrollArea()
            self.song_scroll.setWidgetResizable(True)
            self.song_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            layout.addWidget(self.song_scroll)
            
        except Exception as e:
            print(f"Error creating song page: {e}")

    def go_back_to_albums(self):
        try:
            self.stack.setCurrentWidget(self.albumPage)
        except Exception as e:
            print(f"Error going back to albums: {e}")

    def createSongWidget(self, song):
        try:
            widget = QWidget()
            widget.setFixedSize(200, 240)
            widget.setCursor(Qt.PointingHandCursor)
            
            layout = QVBoxLayout(widget)
            layout.setSpacing(10)
            
            cover_label = QLabel()
            cover_label.setFixedSize(180, 180)
            cover_label.setAlignment(Qt.AlignCenter)
            
            self.load_song_cover(song, cover_label)
            
            name = song.get('name', 'Unknown') if isinstance(song, dict) else str(song)
            display_name = name if len(name) <= 25 else f"{name[:22]}..."
            name_label = QLabel(display_name)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setFont(QFont("Exo 2 Medium", 14))
            name_label.setStyleSheet("color: white; font-weight: bold;")
            
            layout.addWidget(cover_label)
            layout.addWidget(name_label)
            
            widget.setStyleSheet("""
                QWidget {
                    background: rgba(45, 45, 45, 0.7);
                    border-radius: 10px;
                }
                QWidget:hover {
                    background: rgba(61, 61, 61, 0.8);
                }
            """)

            widget.setContextMenuPolicy(Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda pos: self.show_song_context_menu(pos, song))

            def handle_mouse_press(event):
                if event.button() == Qt.LeftButton:
                    self.handle_song_click(event, song)
                
            widget.mousePressEvent = handle_mouse_press
            
            return widget
            
        except Exception as e:
            print(f"Error creating song widget: {e}")
            widget = QWidget()
            widget.setFixedSize(200, 240)
            widget.setStyleSheet("background: rgba(45, 45, 45, 0.7); border-radius: 10px;")
            return widget

    def load_song_cover(self, song, cover_label):
        """Load song cover with proper error handling"""
        try:
            cover_loaded = False
            if isinstance(song, dict) and self.cache_manager:
                cover_url = song.get('cover')
                if cover_url and cover_url.startswith('http'):
                    try:
                        pixmap = self.cache_manager.get_cached_cover(cover_url)
                        if pixmap and not pixmap.isNull():
                            cover_label.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            cover_loaded = True
                    except Exception as e:
                        print(f"Error loading song cover: {e}")
            
            if not cover_loaded:
                self.set_default_cover(cover_label, "music.png", 180)
                
        except Exception as e:
            print(f"Error in load_song_cover: {e}")
            self.set_default_cover(cover_label, "music.png", 180)

    def handle_song_click(self, event, song):
        """Handle song click event"""
        if event.button() == Qt.LeftButton:
            self.play_song(song)

    def show_song_context_menu(self, pos, song):
        """Show context menu for songs with Add to Playlist option"""
        try:
            menu = ModernContextMenu(self)
            menu.setMinimumWidth(200)
            
            play_action = menu.addAction(QIcon(icon_path("play.png")), "Play")
            play_action.triggered.connect(lambda: self.play_song(song))
            
            menu.addSeparator()
            
            add_to_menu = ModernContextMenu()
            add_to_menu.setTitle("Add to Playlist")
            add_to_menu.setIcon(QIcon(icon_path("playlist_add.png")))
            add_to_menu.setMinimumWidth(200)
            
            if self.main_player and hasattr(self.main_player, 'playlists'):
                for playlist_name in self.main_player.playlists.keys():
                    action = QAction(QIcon(icon_path("playlist.png")), playlist_name, add_to_menu)
                    action.triggered.connect(lambda checked, p=playlist_name: self.add_to_playlist(song, p))
                    add_to_menu.addAction(action)

                if self.main_player.playlists:
                    add_to_menu.addSeparator()
                    
                create_new = add_to_menu.addAction(QIcon(icon_path("plus.png")), "Create New Playlist")
                create_new.triggered.connect(lambda: self.create_new_playlist(song))
                
                menu.addMenu(add_to_menu)
                menu.addSeparator()

            if isinstance(song, dict) and 'url' in song and song['url']:
                download_action = menu.addAction(QIcon(icon_path("download.png")), "Download")
                download_action.triggered.connect(lambda: self.download_song(song))
            
            sender = self.sender()
            if sender:
                global_pos = sender.mapToGlobal(pos)
            else:
                global_pos = self.mapToGlobal(pos)
            menu.exec_(global_pos)
            
        except Exception as e:
            print(f"Error showing song context menu: {e}")

    def play_song(self, song):
        """Play selected song"""
        try:
            if self.main_player:
                self.main_player.load_and_play(song)
                self.accept()
        except Exception as e:
            print(f"Error playing song: {e}")

    def add_to_playlist(self, song, playlist_name):
        """Add song to existing playlist"""
        try:
            if self.main_player and hasattr(self.main_player, 'playlists'):
                if song not in self.main_player.playlists[playlist_name]:
                    self.main_player.playlists[playlist_name].append(song)
                    self.main_player.save_playlists()
                    QMessageBox.information(self, "Success", f"Song added to {playlist_name}")
        except Exception as e:
            print(f"Error adding to playlist: {e}")

    def create_new_playlist(self, song):
        """Create new playlist with song"""
        try:
            if self.main_player and hasattr(self.main_player, 'playlists'):
                name, ok = QInputDialog.getText(self, "Create Playlist", "Enter playlist name:")
                if ok and name:
                    if name not in self.main_player.playlists:
                        self.main_player.playlists[name] = [song]
                        self.main_player.save_playlists()
                        QMessageBox.information(self, "Success", f"Created playlist '{name}' with song")
        except Exception as e:
            print(f"Error creating new playlist: {e}")

    def download_song(self, song):
        try:
            if isinstance(song, dict) and 'url' in song and song['url']:
                download_folder = "music"
                if not os.path.exists(download_folder):
                    os.makedirs(download_folder)
                filename = song.get("name", "Unknown") + ".mp3"
                filepath = os.path.join(download_folder, filename)
                dialog = DownloadProgressDialog(song['url'], filepath, self)
                dialog.exec_()
        except Exception as e:
            print(f"Error downloading song: {e}")

    def create_search_page(self):
        try:
            layout = QVBoxLayout(self.searchPage)
            layout.setSpacing(20)
            header = QWidget()
            header.setObjectName("container")
            header_layout = QHBoxLayout(header)
            
            self.searchTitle = QLabel("Search Results")
            self.searchTitle.setFont(QFont("Exo 2 SemiBold", 24))
            self.searchTitle.setStyleSheet(f"color: {self.current_theme['font_color']};")
            header_layout.addWidget(self.searchTitle)
            
            header_layout.addStretch()
            layout.addWidget(header)
            self.search_scroll = QScrollArea()
            self.search_scroll.setWidgetResizable(True)
            self.search_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            layout.addWidget(self.search_scroll)
            
        except Exception as e:
            print(f"Error creating search page: {e}")

    def update_search_results(self, query):
        """Update search results based on query"""
        try:
            if len(query) < 2:
                return
                
            self.searchTitle.setText(f"Search Results for '{query}'")
            results = []
            query_lower = query.lower()
            
            for genre, artists in self.hierarchy.items():
                if query_lower in genre.lower():
                    for artist, albums in artists.items():
                        for album, songs in albums.items():
                            results.extend(songs)
                else:
                    for artist, albums in artists.items():
                        if query_lower in artist.lower():
                            for album, songs in albums.items():
                                results.extend(songs)
                        else:
                            for album, songs in albums.items():
                                if query_lower in album.lower():
                                    results.extend(songs)
                                else:
                                    for song in songs:
                                        if isinstance(song, dict):
                                            song_name = song.get('name', '').lower()
                                            if query_lower in song_name:
                                                results.append(song)
            
            self.display_search_results(results)
            self.stack.setCurrentWidget(self.searchPage)
            
        except Exception as e:
            print(f"Error updating search results: {e}")

    def display_search_results(self, results):
        """Display search results in grid layout"""
        try:
            container = QWidget()
            grid = QGridLayout(container)
            grid.setSpacing(20)
            
            if not results:
                no_results = QLabel("No results found")
                no_results.setAlignment(Qt.AlignCenter)
                no_results.setFont(QFont("Exo 2", 16))
                no_results.setStyleSheet(f"color: {self.current_theme['font_color']};")
                grid.addWidget(no_results, 0, 0)
            else:
                row = 0
                col = 0
                max_cols = 4
                
                for song in results[:20]:
                    song_widget = self.createSongWidget(song)
                    grid.addWidget(song_widget, row, col)
                    
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
            
            self.search_scroll.setWidget(container)
            
        except Exception as e:
            print(f"Error displaying search results: {e}")

    def cleanup_loading_thread(self):
        try:
            if self.load_thread and self.load_thread.isRunning():
                self.load_thread.quit()
                self.load_thread.wait(3000)
            
            if self.load_thread in self.active_threads:
                self.active_threads.remove(self.load_thread)
                
            if self.load_worker:
                self.load_worker.deleteLater()
                self.load_worker = None
                
            self.load_thread = None
            
        except Exception as e:
            print(f"Error cleaning up loading thread: {e}")

    def cleanup_all_threads(self):
        """Clean up all running threads"""
        try:
            self.cleanup_loading_thread()
            for thread in self.active_threads[:]:
                if thread and thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
                if thread in self.active_threads:
                    self.active_threads.remove(thread)
                    
        except Exception as e:
            print(f"Error during thread cleanup: {e}")

    def open_admin_upload(self):
        """Open admin upload dialog"""
        try:
            dialog = AdminUploadDialog(self.hierarchy, parent=self)
            dialog.exec_()
        except Exception as e:
            print(f"Error opening admin upload: {e}")
            QMessageBox.warning(self, "Error", "Failed to open admin upload dialog")

    def closeEvent(self, event):
        """Handle dialog close event with proper cleanup"""
        self.cleanup_all_threads()
        super().closeEvent(event)

    def reject(self):
        """Handle dialog rejection with proper cleanup"""
        self.cleanup_all_threads()
        super().reject()

    def accept(self):
        """Handle dialog acceptance with proper cleanup"""
        self.cleanup_all_threads()
        super().accept()


class RotatingAlbumArt(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)        
        self.setFixedSize(235, 235)
        self.setAlignment(Qt.AlignCenter)
        self.rotation_angle = 0
        self.is_rotating = False
        self._current_pixmap = None
        self._rotation_speed = 0
        self._target_speed = 0.5
        
        self.drag_start_pos = None
        self.last_angle = 0
        self.angular_velocity = 0
        self.friction = 0.98 
        self.is_dragging = False
        self.last_update_time = time.time()
        self.accumulated_rotation = 0
        

        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self.update_physics)
        self.physics_timer.setInterval(12)
        
        self.rotation_timer = QTimer(self)
        self.rotation_timer.timeout.connect(self.rotate)
        self.rotation_timer.setInterval(12)
        
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        
        self.player = None
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        if not self._current_pixmap:
            return super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        center_x = self.width() // 2
        center_y = self.height() // 2

        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.rotation_angle)
        
        if self._current_pixmap:
            scaled_size = 220  
            album_pixmap = self._current_pixmap.scaled(scaled_size, scaled_size, 
                                                    Qt.KeepAspectRatioByExpanding,
                                                    Qt.SmoothTransformation)
            
            mask = QPixmap(scaled_size, scaled_size)
            mask.fill(Qt.transparent)
            mask_painter = QPainter(mask)
            mask_painter.setRenderHint(QPainter.Antialiasing, True)
            mask_painter.setBrush(Qt.black)
            mask_painter.setPen(Qt.NoPen)
            mask_painter.drawEllipse(0, 0, scaled_size, scaled_size)
            mask_painter.end()

            result = QPixmap(scaled_size, scaled_size)
            result.fill(Qt.transparent)
            result_painter = QPainter(result)
            result_painter.setRenderHint(QPainter.Antialiasing, True)
            result_painter.setCompositionMode(QPainter.CompositionMode_Source)
            result_painter.drawPixmap(0, 0, mask)
            result_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            result_painter.drawPixmap(0, 0, album_pixmap)
            result_painter.end()

            offset = scaled_size // 2
            painter.drawPixmap(-offset, -offset, result)

        painter.restore()

        center_hole_size = 35
        outer_ring_size = 45
        
        outer_gradient = QRadialGradient(center_x, center_y, outer_ring_size // 2)
        outer_gradient.setColorAt(0, QColor(40, 40, 40))
        outer_gradient.setColorAt(1, QColor(20, 20, 20))
        painter.setBrush(outer_gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center_x - outer_ring_size // 2, 
                        center_y - outer_ring_size // 2,
                        outer_ring_size, outer_ring_size)

        inner_gradient = QRadialGradient(center_x, center_y, center_hole_size // 2)
        inner_gradient.setColorAt(0, QColor(60, 60, 60))
        inner_gradient.setColorAt(1, QColor(30, 30, 30))
        painter.setBrush(inner_gradient)
        painter.setPen(QPen(QColor(70, 70, 70), 1))
        painter.drawEllipse(center_x - center_hole_size // 2,
                        center_y - center_hole_size // 2,
                        center_hole_size, center_hole_size)


        painter.save()

        base_x = center_x + 100
        base_y = center_y - 100

        base_gradient = QRadialGradient(base_x, base_y, 15)
        base_gradient.setColorAt(0, QColor(192, 192, 192))
        base_gradient.setColorAt(0.5, QColor(128, 128, 128))
        base_gradient.setColorAt(1, QColor(64, 64, 64))

        painter.setBrush(base_gradient)
        painter.setPen(QPen(QColor(32, 32, 32), 5))
        painter.drawEllipse(base_x - 15, base_y - 15, 30, 30) 


        arm_gradient = QLinearGradient(base_x, base_y, base_x - 45, base_y + 45)
        arm_gradient.setColorAt(0.0, QColor(240, 240, 240)) 
        arm_gradient.setColorAt(0.2, QColor(220, 220, 220))
        arm_gradient.setColorAt(0.4, QColor(200, 200, 200))
        arm_gradient.setColorAt(0.6, QColor(180, 180, 180))
        arm_gradient.setColorAt(0.8, QColor(160, 160, 160)) 
        arm_gradient.setColorAt(1.0, QColor(140, 140, 140)) 

        edge_pen = QPen()
        edge_pen.setColor(QColor(200, 200, 200))
        edge_pen.setWidth(8)
        painter.setPen(edge_pen)
        painter.setBrush(arm_gradient)

        path = QPainterPath()
        path.moveTo(base_x - 12, base_y + 12)
        path.quadTo(base_x - 35, base_y + 35, base_x - 60, base_y + 60)
        path.lineTo(base_x - 65, base_y + 65)
        path.quadTo(base_x - 67, base_y + 67, base_x - 60, base_y + 60)
        path.lineTo(base_x - 8, base_y + 8)
        path.closeSubpath()

        shadow_path = QPainterPath(path)
        shadow_path.translate(5, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawPath(shadow_path)


        painter.setPen(edge_pen)
        painter.setBrush(arm_gradient)
        painter.drawPath(path)

        highlight_gradient = QLinearGradient(base_x - 10, base_y + 10, base_x - 40, base_y + 40)
        highlight_gradient.setColorAt(0.0, QColor(255, 255, 255, 90))
        highlight_gradient.setColorAt(0.5, QColor(255, 255, 255, 40))
        highlight_gradient.setColorAt(1.0, QColor(255, 255, 255, 10))

        highlight_path = QPainterPath()
        highlight_path.moveTo(base_x - 11, base_y + 11)
        highlight_path.lineTo(base_x - 40, base_y + 40)
        painter.setPen(QPen(highlight_gradient, 5))
        painter.drawPath(highlight_path)

        painter.setPen(QPen(QColor(64, 64, 64), 5))
        painter.setBrush(arm_gradient)
        painter.drawPath(path)


        tip_gradient = QRadialGradient(base_x - 60, base_y + 60, 7)  
        tip_gradient.setColorAt(0, QColor(224, 224, 224))
        tip_gradient.setColorAt(0.5, QColor(192, 192, 192))
        tip_gradient.setColorAt(1, QColor(128, 128, 128))

        painter.setPen(QPen(QColor(96, 96, 96), 2))
        painter.setBrush(tip_gradient)
        painter.drawEllipse(base_x - 67, base_y + 55, 12, 12) 


        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 180))
        painter.drawEllipse(base_x - 64, base_y + 58, 4, 4)

        painter.restore()

    def set_player(self, player):
        self.player = player

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
            self.is_dragging = True
            self.last_angle = self.get_angle_from_center(event.pos())
            self.angular_velocity = 0
            
            if self.is_rotating:
                self.rotation_timer.stop()
            if self.player and self.player.is_playing:
                self.player.toggle_play_pause()
            
            self.click_time = time.time()

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.player:
            current_angle = self.get_angle_from_center(event.pos())
            angle_diff = current_angle - self.last_angle

            if angle_diff > 180:
                angle_diff -= 360
            elif angle_diff < -180:
                angle_diff += 360
                
            if angle_diff < 0:
                angle_diff *= 0.3
            
            current_time = time.time()
            if hasattr(self, 'click_time'):
                self.player.toggle_play_pause()
                delattr(self, 'click_time')
            if hasattr(self, 'last_update_time'):
                dt = current_time - self.last_update_time
            else:
                dt = 0.016
            
            if dt > 0:
                self.angular_velocity = angle_diff / dt
                max_velocity = 500
                self.angular_velocity = max(-max_velocity, min(max_velocity, self.angular_velocity))
            
            if self.player and hasattr(self.player, 'player'):
                duration = self.player.player.get_length()
                if duration > 0:
                    rotation_to_time = duration / 360.0
                    
                    if angle_diff < 0:
                        time_change = angle_diff * rotation_to_time * 0.3  
                    else:
                        time_change = angle_diff * rotation_to_time
                        
                    current_time = self.player.player.get_time()
                    new_time = current_time + time_change
                    
                    if new_time >= duration and angle_diff > 0:
                        if abs(self.angular_velocity) > 200: 
                            self.player.play_next()
                            return
                    elif new_time <= 0 and angle_diff < 0:
                        if abs(self.angular_velocity) > 200:  
                            self.player.play_prev()
                            return
                    

                    new_time = max(0, min(duration, new_time))
                    self.player.player.set_time(int(new_time))
            

            self.rotation_angle = (self.rotation_angle + angle_diff) % 360
            self.last_angle = current_angle
            self.last_update_time = current_time
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            release_time = time.time()
            if hasattr(self, 'click_time') and (release_time - self.click_time) < 0.2:
                return
            if abs(self.angular_velocity) > 1:
                self.physics_timer.start()
            elif self.player and self.player.is_playing:
                self.rotation_timer.start()

    def get_angle_from_center(self, pos):
        center = QPointF(self.width()/2, self.height()/2)
        delta = pos - center
        return math.degrees(math.atan2(delta.y(), delta.x()))

    def update_physics(self):
        if not self.is_dragging:
            self.rotation_angle = (self.rotation_angle + self.angular_velocity) % 360
            if self.player:
                duration = self.player.player.get_length()
                if duration > 0:
                    rotation_to_time = duration / 360.0
                    time_change = self.angular_velocity * rotation_to_time
                    current_time = self.player.player.get_time()
                    new_time = max(0, min(duration, current_time + time_change))
                    self.player.player.set_time(int(new_time))
            
            self.angular_velocity *= self.friction
            
            if abs(self.angular_velocity) < 0.1:
                self.physics_timer.stop()
                self.angular_velocity = 0
                if self.player and self.player.is_playing:
                    self.rotation_timer.start()
            
            self.update()

    def rotate(self):
        if self.is_rotating and not self.is_dragging:
            self.rotation_angle = (self.rotation_angle + self._target_speed) % 360
            self.update()

    def start_rotation(self):
        self.is_rotating = True
        self._rotation_speed = self._target_speed
        if not self.rotation_timer.isActive():
            self.rotation_timer.start()

    def stop_rotation(self):
        self.is_rotating = False
        self._rotation_speed = 0
        if self.rotation_timer.isActive():
            self.rotation_timer.stop()
        
    def setPixmap(self, pixmap):
        if pixmap:
            scaled_pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self._current_pixmap = scaled_pixmap
            self.update()

# ------------------ AdminUploadDialog ------------------ #

class AdminUploadDialog(QDialog):
    def __init__(self, hierarchy, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin: Upload New Song")
        self.setFixedSize(500, 400)
        self.hierarchy = hierarchy
        layout = QVBoxLayout(self)
        self.nameEdit = QLineEdit()
        self.nameEdit.setPlaceholderText("Enter Song Name")
        layout.addWidget(self.nameEdit)
        self.genreList = QListWidget()
        all_genres = set(self.hierarchy.keys())
        for genre in sorted(all_genres):
            item = QListWidgetItem(genre)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.genreList.addItem(item)
        layout.addWidget(QLabel("Select Genre(s):"))
        layout.addWidget(self.genreList)
        fileLayout = QHBoxLayout()
        self.filePathEdit = QLineEdit()
        self.filePathEdit.setPlaceholderText("Select song file...")
        fileLayout.addWidget(self.filePathEdit)
        self.selectFileBtn = QPushButton("Browse")
        self.selectFileBtn.clicked.connect(self.select_file)
        fileLayout.addWidget(self.selectFileBtn)
        layout.addLayout(fileLayout)
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        layout.addWidget(self.progressBar)
        self.uploadBtn = QPushButton("Upload Song")
        self.uploadBtn.clicked.connect(self.upload_song)
        layout.addWidget(self.uploadBtn)
        self.uploaded = False
        self.uploaded_song = None

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Song File", "", "Audio Files (*.mp3 *.wav *.flac *.ogg)")
        if path:
            self.filePathEdit.setText(path)

    def upload_song(self):
        song_name = self.nameEdit.text().strip()
        if not song_name:
            QMessageBox.warning(self, "Error", "Please enter a song name.")
            return
        file_path = self.filePathEdit.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Error", "Please select a valid song file.")
            return
        selected_genres = []
        for i in range(self.genreList.count()):
            item = self.genreList.item(i)
            if item.checkState() == Qt.Checked:
                selected_genres.append(item.text())
        if not selected_genres:
            QMessageBox.warning(self, "Error", "Please select at least one genre.")
            return
        self.upload_progress = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.simulate_upload)
        self.timer.start()
        self.uploadBtn.setEnabled(False)

    def simulate_upload(self):
        self.upload_progress += random.randint(5, 15)
        if self.upload_progress >= 100:
            self.upload_progress = 100
            self.timer.stop()
            self.uploadBtn.setEnabled(True)
            self.uploaded = True
            self.uploaded_song = {
                "name": self.nameEdit.text().strip(),
                "url": self.filePathEdit.text().strip(),
                "genres": [item.text() for i in range(self.genreList.count())
                           for item in [self.genreList.item(i)] if item.checkState() == Qt.Checked],
                "album": "Unknown Album",
                "artist": "Unknown Artist"
            }
            QMessageBox.information(self, "Success", "Song uploaded successfully!")
            self.accept()
        self.progressBar.setValue(self.upload_progress)

    def get_new_song(self):
        return self.uploaded_song if self.uploaded else None
    
# ------------------ ChooseOnlineSongDialog ------------------ #

class ChooseOnlineSongDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select an Online Song")
        self.setFixedSize(400, 500)
        layout = QVBoxLayout(self)
        self.listWidget = QListWidget()
        layout.addWidget(self.listWidget)
        self.online_songs = self.fetch_online_songs()
        for song in self.online_songs:
            if isinstance(song, dict):
                name = song.get("name", "Unknown Song")
            elif isinstance(song, str):
                name = song
                song = {"name": song, "url": "", "cover": ""}
            else:
                name = "Unknown Song"
                song = {"name": "Unknown Song", "url": "", "cover": ""}
            
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, song)
            self.listWidget.addItem(item)
        self.listWidget.itemDoubleClicked.connect(self.accept)

    def fetch_online_songs(self):
        url = "https://mortalservice.de/music/musiclibrary.json"
        songs = []
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                categories = data.get("categories", {})
                for genre, genre_data in categories.items():
                    if isinstance(genre_data, dict):
                        artists_data = genre_data.get("artists", genre_data)
                        for artist, artist_songs in artists_data.items():
                            if isinstance(artist_songs, dict):
                                for album_or_song in artist_songs.values():
                                    if isinstance(album_or_song, list):
                                        for song in album_or_song:
                                            if isinstance(song, dict):
                                                songs.append(song)
                                            elif isinstance(song, str):
                                                songs.append({
                                                    "name": song,
                                                    "url": "",
                                                    "cover": "",
                                                    "artist": artist,
                                                    "genre": genre
                                                })
                                    elif isinstance(album_or_song, (str, dict)):
                                        if isinstance(album_or_song, dict):
                                            songs.append(album_or_song)
                                        else:
                                            songs.append({
                                                "name": album_or_song,
                                                "url": "",
                                                "cover": "",
                                                "artist": artist,
                                                "genre": genre
                                            })
                            elif isinstance(artist_songs, list):
                                for song in artist_songs:
                                    if isinstance(song, dict):
                                        songs.append(song)
                                    elif isinstance(song, str):
                                        songs.append({
                                            "name": song,
                                            "url": "",
                                            "cover": "",
                                            "artist": artist,
                                            "genre": genre
                                        })
        except Exception as e:
            print("Error fetching online songs:", e)
        return songs

    def selected_song(self):
        item = self.listWidget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

# ------------------ PlaylistDialog ------------------ #

class PlaylistDialog(BaseDialog):
    def __init__(self, playlists, main_player, parent=None):
        super().__init__(main_player, "Playlist Manager", parent)
        self.playlists = playlists
        self.main_player = main_player
        self.edit_mode = False
        self.setMinimumSize(950, 600)
        self.initUI()

    def initUI(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)

        left_container = QWidget()
        left_container.setObjectName("container")
        left_container.setFixedWidth(250)
        left_layout = QVBoxLayout(left_container)

        new_playlist_container = QWidget()
        new_playlist_container.setObjectName("container")
        new_playlist_layout = QVBoxLayout(new_playlist_container)
        
        self.newPlaylistEdit = QLineEdit()
        self.newPlaylistEdit.setPlaceholderText("New playlist name...")
        self.newPlaylistEdit.setFont(QFont("Exo 2", 10))
        
        create_btn = QPushButton("Create Playlist")
        create_btn.setIcon(QIcon(icon_path("plus.png")))
        create_btn.clicked.connect(self.createPlaylist)
        
        new_playlist_layout.addWidget(self.newPlaylistEdit)
        new_playlist_layout.addWidget(create_btn)
        left_layout.addWidget(new_playlist_container)

        self.playlistListWidget = QListWidget()
        self.playlistListWidget.setStyleSheet("""
            QListWidget::item {
                padding: 10px;
                margin: 2px 0px;
                border-radius: 5px;
            }
            QListWidget::item:selected {
                background: rgba(61, 61, 61, 0.8);
            }
            QListWidget::item:hover {
                background: rgba(45, 45, 45, 0.7);
            }
        """)
        self.playlistListWidget.currentItemChanged.connect(self.updateSongsList)
        left_layout.addWidget(self.playlistListWidget)
        
        controls_container = QWidget()
        controls_container.setObjectName("container")
        controls_layout = QVBoxLayout(controls_container)

        self.playPlaylistBtn = QPushButton("Play Playlist")
        self.playPlaylistBtn.setIcon(QIcon(icon_path("play.png")))
        self.deletePlaylistBtn = QPushButton("Delete Playlist")
        self.deletePlaylistBtn.setIcon(QIcon(icon_path("remove.png")))
        
        self.playPlaylistBtn.clicked.connect(self.playCurrentPlaylist)
        self.deletePlaylistBtn.clicked.connect(self.deletePlaylist)

        
        self.editPlaylistBtn = QPushButton("Edit PlayList")
        self.editPlaylistBtn.setIcon(QIcon(icon_path("edit.png")))
        self.editPlaylistBtn.setCheckable(True)
        self.editPlaylistBtn.toggled.connect(self.toggleEditMode) 

        controls_layout.addWidget(self.playPlaylistBtn)
        controls_layout.addWidget(self.deletePlaylistBtn)
        controls_layout.addWidget(self.editPlaylistBtn)
        left_layout.addWidget(controls_container)
        

        main_layout.addWidget(left_container)

        right_container = QWidget()
        right_container.setObjectName("container")
        right_layout = QVBoxLayout(right_container)

        song_controls = QHBoxLayout()
        self.addSongBtn = QPushButton("Add Song")
        self.addSongBtn.setIcon(QIcon(icon_path("plus.png")))
        self.addSongBtn.clicked.connect(self.addSongToPlaylist)
        song_controls.addWidget(self.addSongBtn)
        
        right_layout.addLayout(song_controls)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.songs_container = QWidget()
        self.songs_grid = QGridLayout(self.songs_container)
        self.songs_grid.setSpacing(20)
        scroll.setWidget(self.songs_container)
        
        right_layout.addWidget(scroll)
        main_layout.addWidget(right_container)

        self.populatePlaylists()

    def toggleEditMode(self, checked):
        self.edit_mode = checked
        self.editPlaylistBtn.setText("End Editing" if checked else "Edit Playlist")
        self.icon = icon_path("close.png") if checked else icon_path("edit.png")
        self.editPlaylistBtn.setIcon(QIcon(self.icon))
        current_item = self.playlistListWidget.currentItem()
        if current_item:
            self.updateSongsList(current_item, None)

    def createSongWidget(self, song, index):
        if isinstance(song, dict):
            name = song.get("name", "Unknown")
            pixmap = self.getOnlineSongCover(song)
        elif isinstance(song, str):
            name = os.path.basename(song)
            pixmap = self.getLocalSongCover(song)
        else:
            print(f"[Error] Invalid song type: {song}")
            name = "Unknown"
            pixmap = None

        name_label = QLabel(name)
        cover_label = QLabel()

        if pixmap:
            cover_label.setPixmap(pixmap)
            cover_label.setFixedSize(60, 60)
            cover_label.setScaledContents(True)
        else:
            cover_label.setPixmap(QPixmap(icon_path("music.png")).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        layout = QHBoxLayout()
        layout.addWidget(cover_label)
        layout.addWidget(name_label)

        if self.edit_mode:
            remove_btn = QPushButton()
            remove_btn.setIcon(QIcon(icon_path("remove.png")))
            remove_btn.setFixedSize(24, 24)
            remove_btn.setStyleSheet("QPushButton { border: none; }")
            remove_btn.clicked.connect(lambda: self.removeSongFromCurrentPlaylist(song))
            layout.addWidget(remove_btn)

        widget = QWidget()
        widget.setLayout(layout)

        widget.setStyleSheet("""
            QWidget {
                background: rgba(45, 45, 45, 0.7);
                border-radius: 10px;
            }
            QWidget:hover {
                background: rgba(61, 61, 61, 0.8);
            }
        """)

        if self.edit_mode:
            
            widget.setObjectName(str(index))
            widget.setAcceptDrops(True)
            widget.setAttribute(Qt.WA_DeleteOnClose)
            widget.mousePressEvent = lambda event: self.dragSong(event, song, index)
            widget.dragEnterEvent = self.songDragEnter
            widget.dropEvent = lambda e: self.songDrop(e, index)

        return widget

    def dragSong(self, event, song, index):
        if event.button() == Qt.LeftButton:
            mime_data = QMimeData()
            mime_data.setText(str(index))

            drag = QDrag(self)
            drag.setMimeData(mime_data)
            drag.exec_(Qt.MoveAction)

    def songDragEnter(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def songDrop(self, event, target_index):
        if not self.edit_mode:
            return

        current_playlist_item = self.playlistListWidget.currentItem()
        if not current_playlist_item:
            return

        source_index = int(event.mimeData().text())
        playlist_name = current_playlist_item.text()
        playlist = self.playlists[playlist_name]

        if 0 <= source_index < len(playlist) and 0 <= target_index < len(playlist):
            song = playlist.pop(source_index)
            playlist.insert(target_index, song)
            self.updateSongsList(current_playlist_item, None)
            self.main_player.save_playlists()


    def populatePlaylists(self):
        self.playlistListWidget.clear()
        for playlist_name in self.playlists.keys():
            self.playlistListWidget.addItem(playlist_name)

    def getLocalSongCover(self, filepath):
        try:
            return get_album_art(filepath)
        except Exception as e:
            print(f"[Error loading local cover from {filepath}]: {e}")
        return None

    def getOnlineSongCover(self, song):
        if isinstance(song, dict) and "cover" in song:
            cover_url = song["cover"]
            if cover_url:
                try:
                    response = requests.get(cover_url, timeout=5)
                    pixmap = QPixmap()
                    if pixmap.loadFromData(response.content):
                        return pixmap
                except Exception as e:
                    print(f"[Error loading cover image from {cover_url}]: {e}")
        return None


    def updateSongsList(self, current, _):
        for i in reversed(range(self.songs_grid.count())):
            widget_item = self.songs_grid.itemAt(i)
            if widget_item:
                widget = widget_item.widget()
                if widget:
                    widget.setParent(None)

        if not current:
            return

        playlist_name = current.text()
        songs = self.playlists.get(playlist_name, [])

        for index, song in enumerate(songs):
            if not isinstance(song, (dict, str)):
                print(f"[Warning] Skipping invalid song: {song}")
                continue

            song_widget = self.createSongWidget(song, index)
            if song_widget:
                self.songs_grid.addWidget(song_widget, index, 0)






    def songWidgetDragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()



    def show_song_context_menu(self, pos, song):
        """Show context menu for songs"""
        menu = ModernContextMenu(self)
        
        add_to_menu = ModernContextMenu()
        add_to_menu.setTitle("Add to Playlist")
        add_to_menu.setIcon(QIcon(icon_path("playlist_add.png")))
        
        if self.parent() and hasattr(self.parent(), 'playlists'):
            for playlist_name in self.parent().playlists.keys():
                action = QAction(QIcon(icon_path("playlist.png")), playlist_name, add_to_menu)
                action.triggered.connect(lambda checked, p=playlist_name: self.add_to_playlist(song, p))
                add_to_menu.addAction(action)

            add_to_menu.addSeparator()
            create_new = add_to_menu.addAction(QIcon(icon_path("plus.png")), "Create New Playlist")
            create_new.triggered.connect(lambda: self.create_new_playlist(song))
            
            menu.addMenu(add_to_menu)
            menu.addSeparator()

        play_action = menu.addAction(QIcon(icon_path("play.png")), "Play")
        play_action.triggered.connect(lambda: self.parent().load_and_play(song))
        
        global_pos = self.mapToGlobal(pos)
        menu.exec_(global_pos)

    def addSongToOtherPlaylist(self, song, target_playlist):
        if song not in self.playlists[target_playlist]:
            self.playlists[target_playlist].append(song)
            self.main_player.save_playlists()
            QMessageBox.information(self, "Success", f"Song added to {target_playlist}")

    def createPlaylist(self, song):
        name, ok = QInputDialog.getText(self, "Create Playlist", "Enter playlist name:")
        if ok and name:
            if name not in self.playlists:
                self.playlists[name] = [song]
                self.main_player.save_playlists()
                self.populatePlaylists()
                QMessageBox.information(self, "Success", f"Created playlist '{name}' with song")
    def deletePlaylist(self):
        current = self.playlistListWidget.currentItem()
        if current:
            playlist_name = current.text()
            del self.playlists[playlist_name]
            self.populatePlaylists()
            self.songsListWidget.clear()
            self.main_player.save_playlists()

    def addSongToPlaylist(self):
        reply = QMessageBox(self)
        reply.setWindowTitle("Add Song")
        reply.setText("Choose song source:")
        reply.setStandardButtons(QMessageBox.NoButton)
        
        local_btn = reply.addButton("Local Song", QMessageBox.YesRole)
        online_btn = reply.addButton("Online Song", QMessageBox.NoRole)
        cancel_btn = reply.addButton("Cancel", QMessageBox.RejectRole)
        
        reply.exec_()
        clicked_button = reply.clickedButton()
        
        if clicked_button == local_btn:
            dialog = ChooseSongDialog(self.main_player.song_list, parent=self)
            if dialog.exec_() == QDialog.Accepted:
                song_path = dialog.selected_song()
                if song_path:
                    current_playlist_item = self.playlistListWidget.currentItem()
                    if current_playlist_item:
                        playlist_name = current_playlist_item.text()
                        if song_path not in self.playlists[playlist_name]:
                            self.playlists[playlist_name].append(song_path)
                            self.updateSongsList(current_playlist_item, None)
                            self.main_player.save_playlists()
        
        elif clicked_button == online_btn:
            if not is_connected():
                QMessageBox.warning(self, "No Internet", "Cannot access online songs. Please check your internet connection.")
                return
                
            dialog = ChooseOnlineSongDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                song = dialog.selected_song()
                if song:
                    current_playlist_item = self.playlistListWidget.currentItem()
                    if current_playlist_item:
                        playlist_name = current_playlist_item.text()
                        if song not in self.playlists[playlist_name]:
                            self.playlists[playlist_name].append(song)
                            self.updateSongsList(current_playlist_item, None)
                            self.main_player.save_playlists()
                            
    def removeSongFromCurrentPlaylist(self, song):
        current_playlist = self.playlistListWidget.currentItem()
        if current_playlist:
            playlist_name = current_playlist.text()
            if song in self.playlists[playlist_name]:
                self.playlists[playlist_name].remove(song)
                self.updateSongsList(current_playlist, None)
                self.main_player.save_playlists()

    def moveSongUp(self):
        current_playlist_item = self.playlistListWidget.currentItem()
        row = self.songsListWidget.currentRow()
        if current_playlist_item and row > 0:
            playlist_name = current_playlist_item.text()
            songs = self.playlists[playlist_name]
            songs[row-1], songs[row] = songs[row], songs[row-1]
            self.updateSongsList(current_playlist_item, None)
            self.songsListWidget.setCurrentRow(row-1)
            self.main_player.save_playlists()

    def moveSongDown(self):
        current_playlist_item = self.playlistListWidget.currentItem()
        row = self.songsListWidget.currentRow()
        if current_playlist_item and row < self.songsListWidget.count()-1:
            playlist_name = current_playlist_item.text()
            songs = self.playlists[playlist_name]
            songs[row+1], songs[row] = songs[row], songs[row+1]
            self.updateSongsList(current_playlist_item, None)
            self.songsListWidget.setCurrentRow(row+1)
            self.main_player.save_playlists()

    def playCurrentPlaylist(self):
        current_playlist_item = self.playlistListWidget.currentItem()
        if current_playlist_item:
            playlist_name = current_playlist_item.text()
            playlist = self.playlists.get(playlist_name, [])
            if playlist:
                self.main_player.play_playlist(playlist)
                self.accept()

    def play_playlist_song(self, item=None):
        if self.main_player.play_mode == "playlist" and self.main_player.current_playlist is not None:
            row = self.playlistListWidget.currentRow()
            if 0 <= row < len(self.main_player.current_playlist):
                self.main_player.current_playlist_index = row
                self.main_player.load_and_play(self.main_player.current_playlist[row])




# ------------------ ChooseSongDialog ------------------ #

class ChooseSongDialog(QDialog):
    def __init__(self, song_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select a Song")
        self.setFixedSize(400, 500)
        layout = QVBoxLayout(self)
        self.listWidget = QListWidget()
        layout.addWidget(self.listWidget)
        for path in song_list:
            item = QListWidgetItem(QIcon(icon_path("music.png")), os.path.basename(path))
            item.setData(Qt.UserRole, path)
            self.listWidget.addItem(item)
        self.listWidget.itemDoubleClicked.connect(self.accept)
    def selected_song(self):
        item = self.listWidget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        

class ScannerThread(QThread):
    progressChanged = pyqtSignal(int)
    finishedScanning = pyqtSignal(list)
    
    def __init__(self, scan_dirs, allowed_extensions, duration_threshold):
        super().__init__()
        self.scan_dirs = scan_dirs
        self.allowed_extensions = allowed_extensions
        self.duration_threshold = duration_threshold

    def run(self):
        file_list = []
        total_files = 0
        for scan_dir in self.scan_dirs:
            for root, dirs, files in os.walk(scan_dir):
                for f in files:
                    if f.lower().endswith(self.allowed_extensions):
                        total_files += 1
        scanned = 0
        for scan_dir in self.scan_dirs:
            for root, dirs, files in os.walk(scan_dir):
                for f in files:
                    if f.lower().endswith(self.allowed_extensions):
                        full_path = os.path.join(root, f)
                        try:
                            audio = MutagenFile(full_path)
                            if audio and hasattr(audio.info, "length") and audio.info.length >= self.duration_threshold:
                                file_list.append(full_path)
                        except Exception:
                            pass
                        scanned += 1
                        progress = int(scanned * 100 / total_files) if total_files > 0 else 0
                        self.progressChanged.emit(progress)
        self.finishedScanning.emit(file_list)


# ------------------ LocalMusicScanner ------------------ #

class LocalMusicScanner(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scanning Local Music...")
        self.setFixedSize(400, 150)
        self.cache_file = None
        self.allowed_extensions = (".mp3", ".wav", ".flac", ".ogg")
        self.duration_threshold = 30
        self.file_list = []
        self.playlists = {}
        
        layout = QVBoxLayout(self)
        self.selectFolderBtn = QPushButton("Select Folder")
        self.selectFolderBtn.clicked.connect(self.select_folder)
        layout.addWidget(self.selectFolderBtn)
        self.progressBar = QProgressBar()
        self.setStyleSheet("""
            QProgressBar {
                border: 2px solid rgba(33, 37, 43, 180);
                border-radius: 10px; text-align: center;
                background-color: rgba(33, 37, 43, 180); color: black;
            }
            QProgressBar::chunk {
                background: #ff69b4; border-radius: 10px;
            }
        """)
        layout.addWidget(self.progressBar)
        self.statusLabel = QLabel("Ready to scan")
        layout.addWidget(self.statusLabel)
        
        self.scan_dirs = [
            os.path.expanduser("~/Music"),
            os.path.expanduser("~/Downloads"),
        ]
        
        self.scanner_thread = None

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            if folder not in self.scan_dirs:
                self.scan_dirs.append(folder)
            self.start_scan()

    def start_scan(self):
        self.statusLabel.setText("Scanning...")
        self.scanner_thread = ScannerThread(self.scan_dirs, self.allowed_extensions, self.duration_threshold)
        self.scanner_thread.progressChanged.connect(self.progressBar.setValue)
        self.scanner_thread.finishedScanning.connect(self.on_scan_finished)
        self.scanner_thread.start()

    def on_scan_finished(self, files):
        self.file_list = files
        try:
            secure_save(self.file_list, "local_songs_cache.safe", self.parent().encryption_key)
        except Exception as e:
            print("Error saving cache:", e)
        self.playlists["system musics"] = self.file_list.copy()
        self.statusLabel.setText("Scan completed!")
        self.accept()

    def load_local_songs(self):
        try:
            cached = secure_load("local_songs_cache.safe", self.parent().encryption_key)
            if cached:
                self.file_list = cached
                self.playlists["system musics"] = self.file_list.copy()
                return
        except Exception:
            pass

        self.start_scan()
        self.exec_()

    def get_scanned_files(self):
        return self.file_list

    def get_playlists(self):
        return self.playlists


# ------------------ EqualizerDialog ------------------ #

class EqualizerDialog(BaseDialog):
    def __init__(self, player, parent=None):
        super().__init__(parent, "Equalizer", parent)
        self.player = player
        self.setWindowTitle("Equalizer Settings")
        try:
            key_path = os.path.join(SECURE_PATH, 'equalizer_key.bin')
            if os.path.exists(key_path):
                with open(key_path, 'rb') as f:
                    self.encryption_key = f.read()
            else:
                self.encryption_key = Fernet.generate_key()
                os.makedirs(os.path.dirname(key_path), exist_ok=True)
                with open(key_path, 'wb') as f:
                    f.write(self.encryption_key)
                if os.name == 'posix':
                    os.chmod(key_path, 0o600)
        except Exception as e:
            print(f"Error handling encryption key: {e}")

            self.encryption_key = Fernet.generate_key()

        self.setStyleSheet(f"""
            QDialog {{
                background: {self.current_theme['gradient']};
                color: {self.current_theme['font_color']};
                border-radius: 10px;
            }}
            QWidget#container {{
                background: transparent;
                border-radius: 10px;
                padding: 20px;
            }}
            QLabel {{
                color: {self.current_theme['font_color']};
                background: transparent;
            }}
            QComboBox {{
                background: rgba(45, 45, 45, 0.7);
                border: none;
                border-radius: 5px;
                padding: 8px;
                color: {self.current_theme['font_color']};
                min-width: 150px;
            }}
            QPushButton {{
                background: rgba(45, 45, 45, 0.7);
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                color: {self.current_theme['font_color']};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(61, 61, 61, 0.8);
            }}
        """)
        self.init_ui()
        self.load_settings()
        

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)

        header = QWidget()
        header.setObjectName("container")
        header_layout = QHBoxLayout(header)

        preset_label = QLabel("Preset:")
        preset_label.setFont(QFont("Exo 2 SemiBold", 12))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Normal", "Rock", "Pop", "Classic", "Jazz", "Custom"])
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        
        header_layout.addWidget(preset_label)
        header_layout.addWidget(self.preset_combo)
        header_layout.addStretch()

        bands_container = QWidget()
        bands_container.setObjectName("container")
        bands_layout = QHBoxLayout(bands_container)
        bands_layout.setSpacing(30)
        
        self.sliders = {}
        self.value_labels = {}
        bands = ["60Hz", "170Hz", "310Hz", "600Hz", "1kHz", "3kHz", "6kHz", "12kHz", "14kHz", "16kHz"]
        
        for band in bands:
            band_widget = QWidget()
            band_layout = QVBoxLayout(band_widget)
            
            value_label = QLabel("0 dB")
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setFont(QFont("Exo 2", 9))
            self.value_labels[band] = value_label
            
            slider = QSlider(Qt.Vertical)
            slider.setRange(-20, 20)
            slider.setValue(0)
            slider.setStyleSheet(f"""
                QSlider::groove:vertical {{
                    background: rgba(45, 45, 45, 0.7);
                    width: 8px;
                    border-radius: 4px;
                }}
                QSlider::handle:vertical {{
                    background: {self.current_theme['selected_color']};
                    border: none;
                    height: 18px;
                    width: 18px;
                    margin: 0 -4px;
                    border-radius: 9px;
                }}
            """)
            slider.valueChanged.connect(lambda v, b=band: self.on_slider_changed(b, v))
            self.sliders[band] = slider
            
            band_label = QLabel(band)
            band_label.setAlignment(Qt.AlignCenter)
            band_label.setFont(QFont("Exo 2", 10))
            
            band_layout.addWidget(value_label)
            band_layout.addWidget(slider)
            band_layout.addWidget(band_label)
            band_layout.setAlignment(Qt.AlignHCenter)
            
            bands_layout.addWidget(band_widget)

        bottom = QWidget()
        bottom.setObjectName("container")
        bottom_layout = QHBoxLayout(bottom)
        
        reset_btn = QPushButton("Reset")
        reset_btn.setIcon(QIcon(icon_path("reset.png")))
        reset_btn.clicked.connect(lambda: self.apply_preset("Normal"))
        
        save_btn = QPushButton("Save")
        save_btn.setIcon(QIcon(icon_path("save.png")))
        save_btn.clicked.connect(self.save_settings)
        
        bottom_layout.addWidget(reset_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(save_btn)

        main_layout.addWidget(header)
        main_layout.addWidget(bands_container)
        main_layout.addWidget(bottom)

    def on_slider_changed(self, band, value):
        self.value_labels[band].setText(f"{value} dB")
        self.apply_custom()

    def apply_preset(self, preset_name):
        presets = {
            "Normal": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "Rock": [8, 4, 2, 0, -2, -4, -6, -8, -8, -8],
            "Pop": [2, 4, 6, 2, 0, -2, -4, -6, -6, -6],
            "Classic": [0, 0, 0, 0, 2, 4, 6, 8, 8, 8],
            "Jazz": [4, 2, 0, 2, 4, 2, 0, -2, -4, -6]
        }
        if preset_name != "Custom":
            values = presets.get(preset_name, [0] * 10)
            for slider, value in zip(self.sliders.values(), values):
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)
            self.apply_equalizer(values)

    def apply_custom(self):
        self.preset_combo.setCurrentText("Custom")
        values = [slider.value() for slider in self.sliders.values()]
        self.apply_equalizer(values)

    def apply_equalizer(self, values):
        eq = vlc.libvlc_audio_equalizer_new()
        for i, value in enumerate(values):
            vlc.libvlc_audio_equalizer_set_amp_at_index(eq, value, i)
        vlc.libvlc_media_player_set_equalizer(self.player, eq)
        vlc.libvlc_audio_equalizer_release(eq)

    def save_settings(self):
        try:
            settings = {band: slider.value() for band, slider in self.sliders.items()}
            secure_save(settings, "equalizer_settings.enc", self.encryption_key)
            QMessageBox.information(self, "Success", "Equalizer settings saved")
        except Exception as e:
            print(f"Error saving equalizer settings: {e}")
            QMessageBox.warning(self, "Error", "Failed to save equalizer settings")

    def load_settings(self):
        try:
            settings = secure_load("equalizer_settings.enc", self.encryption_key)
            if settings:
                for band, value in settings.items():
                    if band in self.sliders:
                        self.sliders[band].setValue(value)
                        self.value_labels[band].setText(f"{value} dB")
                self.apply_custom()
            else:
                self.apply_preset("Normal")
        except Exception as e:
            print(f"Error loading equalizer settings: {e}")
            self.apply_preset("Normal")



# ================= New: SettingsDialog (بخش تنظیمات) ================= #

SENDER_EMAIL = "kianminer1384@gmail.com"
SENDER_PASSWORD = "yfho qlyh qfqn hghl"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

class ThemeSelector(QWidget):
    def __init__(self, main_player):
        super().__init__()
        self.main_player = main_player
        self.current_index = self.main_player.current_theme_index
        self.setFixedSize(300, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.theme_display = QPushButton(self.main_player.themes[self.current_index]["name"])
        self.theme_display.setCursor(Qt.PointingHandCursor)
        self.theme_display.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: none;
                border-radius: 15px;
                font-size: 18px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
        """)
        self.theme_display.clicked.connect(self.change_theme)

        layout.addWidget(self.theme_display, alignment=Qt.AlignCenter)

        self.brush_icon = QLabel()
        self.brush_icon.setPixmap(QPixmap("icons/theme.png").scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(self.brush_icon, alignment=Qt.AlignRight | Qt.AlignBottom)

        self.setStyleSheet("""
            ThemeSelector {
                background-color: transparent;
            }
        """)

    def change_theme(self):
        self.current_index = (self.current_index + 1) % len(self.main_player.themes)
        self.main_player.current_theme_index = self.current_index
        self.main_player.apply_theme()
        self.theme_display.setText(self.main_player.themes[self.current_index]["name"])

class ThemeDisplay(QWidget):
    clicked = pyqtSignal(int)
    
    def __init__(self, theme, index, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.index = index
        self.setFixedSize(180, 100)
        self.setStyleSheet("""
            QWidget {
                border-radius: 10px;
                border: 2px solid transparent;
            }
            QWidget:hover {
                border: 2px solid white;
            }
        """)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient_str = self.theme["gradient"]
        if "stop:0" in gradient_str and "stop:1" in gradient_str:
            color1 = gradient_str.split("stop:0")[1].split(",")[0].strip()
            color2 = gradient_str.split("stop:1")[1].split(")")[0].strip()
            gradient.setColorAt(0, QColor(color1))
            gradient.setColorAt(1, QColor(color2))
            
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        painter.setPen(QColor(self.theme["font_color"]))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        rect = self.rect()
        painter.drawText(rect, Qt.AlignCenter, self.theme["name"])
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)



class SettingsDialog(BaseDialog):
    def __init__(self, main_player, parent=None):
        super().__init__(main_player, "Settings", parent)
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.setMinimumSize(800, 600)
        theme = self.current_theme
        self.setStyleSheet(f"""
            QDialog {{
                background: {theme['gradient']};
                color: {theme['font_color']};
            }}
            QLabel {{
                color: {theme['font_color']};
                font-size: 14px;
            }}
            QPushButton {{
                background: rgba(45, 45, 45, 0.7);
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                color: white;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(61, 61, 61, 0.8);
            }}
            QLineEdit {{
                background: rgba(45, 45, 45, 0.7);
                border: 1px solid rgba(61, 61, 61, 0.8);
                border-radius: 5px;
                padding: 8px;
                color: {theme['font_color']};
            }}
            QTextEdit {{
                background: rgba(45, 45, 45, 0.7);
                border: 1px solid rgba(61, 61, 61, 0.8);
                border-radius: 5px;
                padding: 8px;
                color: {theme['font_color']};
            }}
            QListWidget {{
                background: rgba(45, 45, 45, 0.7);
                border: 1px solid rgba(61, 61, 61, 0.8);
                border-radius: 5px;
                color: {theme['font_color']};
            }}
            QWidget#sidebar {{
                background: rgba(45, 45, 45, 0.7);
                border-radius: 10px;
            }}
            QPushButton[checkable="true"]:checked {{
                background: {theme['selected_color']};
            }}
            QListWidget::item {{
                padding: 10px;
                margin: 2px 0px;
                border-radius: 5px;
            }}
            QListWidget::item:selected {{
                background: {theme['selected_color']};
            }}
            QListWidget::item:hover {{
                background: rgba(61, 61, 61, 0.8);
            }}
            QScrollBar:vertical {{
                background: #ccc;
                width : 10px;
                height : 7px;
            }}
             QScrollBar:horizontal{{
                background: #ccc;
                width : 7px;
                height : 10px;
             }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: #888;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                background: none;
            }}
        """)
        
        layout = QVBoxLayout(self)

        container = QHBoxLayout()

        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("""
            QWidget {
                background: #252525;
                border-radius: 10px;
            }
            QPushButton {
                text-align: left;
                padding: 12px 15px;
                margin: 2px 5px;
            }
            QPushButton:checked {
                background: #3d3d3d;
            }
        """)
        
        sidebar_layout = QVBoxLayout(sidebar)
        
        self.theme_btn = QPushButton("Themes")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setChecked(True)
        self.theme_btn.clicked.connect(lambda: self.show_page(0))
        
        self.scan_btn = QPushButton("Scan Paths")
        self.scan_btn.setCheckable(True)
        self.scan_btn.clicked.connect(lambda: self.show_page(1))
        
        self.report_btn = QPushButton("Bug Report")
        self.report_btn.setCheckable(True)
        self.report_btn.clicked.connect(lambda: self.show_page(2))
        
        sidebar_layout.addWidget(self.theme_btn)
        sidebar_layout.addWidget(self.scan_btn)
        sidebar_layout.addWidget(self.report_btn)
        sidebar_layout.addStretch()
        
        container.addWidget(sidebar)

        self.pages = QStackedWidget()

        theme_page = QWidget()
        theme_layout = QVBoxLayout(theme_page)
        
        theme_scroll = QScrollArea()
        theme_scroll.setWidgetResizable(True)
        theme_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        theme_container = QWidget()
        theme_grid = QGridLayout(theme_container)
        theme_grid.setSpacing(15)

        row = 0
        col = 0
        for i, theme in enumerate(self.main_player.themes):
            theme_widget = ThemeDisplay(theme, i)
            theme_widget.clicked.connect(self.change_theme)
            theme_grid.addWidget(theme_widget, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1
                
        theme_scroll.setWidget(theme_container)
        theme_layout.addWidget(theme_scroll)

        scan_page = QWidget()
        scan_layout = QVBoxLayout(scan_page)
        
        self.scan_list = QListWidget()
        self.scan_list.setStyleSheet("""
            QListWidget::item {
                padding: 10px;
                margin: 2px 0px;
                border-radius: 5px;
            }
            QListWidget::item:selected {
                background: #3d3d3d;
            }
            QListWidget::item:hover {
                background: #454545;
            }
        """)
        
        btn_layout = QHBoxLayout()
        self.btnAddPath = QPushButton("Add Path")
        self.btnAddPath.setIcon(QIcon(icon_path("plus.png")))
        self.btnRemovePath = QPushButton("Remove Selected")
        self.btnRemovePath.setIcon(QIcon(icon_path("minus.png")))
        
        btn_layout.addWidget(self.btnAddPath)
        btn_layout.addWidget(self.btnRemovePath)
        
        scan_layout.addWidget(self.scan_list)
        scan_layout.addLayout(btn_layout)

        report_page = QWidget()
        report_layout = QVBoxLayout(report_page)
        
        self.subject_edit = QLineEdit()
        self.subject_edit.setPlaceholderText("Subject")
        
        self.message_edit = QTextEdit()
        self.message_edit.setPlaceholderText("Describe the bug in detail")
        
        self.btnSubmitReport = QPushButton("Submit Report")
        self.btnSubmitReport.setIcon(QIcon(icon_path("send.png")))
        
        report_layout.addWidget(self.subject_edit)
        report_layout.addWidget(self.message_edit)
        report_layout.addWidget(self.btnSubmitReport)

        self.pages.addWidget(theme_page)
        self.pages.addWidget(scan_page)
        self.pages.addWidget(report_page)
        
        container.addWidget(self.pages)
        layout.addLayout(container)

        self.btnAddPath.clicked.connect(self.add_scan_path)
        self.btnRemovePath.clicked.connect(self.remove_scan_path)
        self.btnSubmitReport.clicked.connect(self.submit_report)
        self.scan_list.itemSelectionChanged.connect(self.update_remove_button)
        
        self.refresh_scan_list()

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        
        self.theme_btn.setChecked(index == 0)
        self.scan_btn.setChecked(index == 1)
        self.report_btn.setChecked(index == 2)

    def apply_dialog_theme(self):
        theme = self.main_player.themes[self.main_player.current_theme_index]
        self.setStyleSheet(f"""
             QDialog {{
             background: {theme['gradient']};
             color: {theme['font_color']};
             }}
             QTabWidget::pane {{
             border: none;
             }}
             QTabBar::tab {{
             background: white;
             padding: 8px;
             border-radius: 4px;
             }}
             QTabBar::tab:selected {{
             background: {theme['selected_color']};
             color: white;
             }}
             QLabel {{
             color: {theme['font_color']};
             }}
             QLineEdit, QTextEdit {{
             background: rgba(45, 45, 45, 0.7);
             border: 1px solid rgba(61, 61, 61, 0.8);
             border-radius: 5px;
             padding: 6px;
             color: {theme['font_color']};
             }}
             QListWidget {{
             background: rgba(45, 45, 45, 0.7);
             border: 1px solid rgba(61, 61, 61, 0.8);
             border-radius: 5px;
             color: {theme['font_color']};
             }}
             QListWidget::item {{
             padding: 8px;
             margin: 2px 0;
             border-radius: 4px;
             }}
             QListWidget::item:selected {{
             background: {theme['selected_color']};
             }}
             QPushButton {{
             background: rgba(45, 45, 45, 0.7);
             border: none;
             border-radius: 5px;
             padding: 8px 15px;
             color: white;
             font-size: 13px;
             }}
             QPushButton:hover {{
             background: rgba(61, 61, 61, 0.8);
             }}
         """)

    def change_theme(self, index):
        self.main_player.current_theme_index = index
        self.main_player.apply_theme_by_index(index)
        self.apply_dialog_theme()
        self.save_theme()
        
    def refresh_scan_list(self):
        self.scan_list.clear()
        default_paths = [os.path.expanduser("~/Music"), os.path.expanduser("~/Downloads")]
        for path in self.main_player.scan_dirs:
            item = QListWidgetItem(path)
            item.setIcon(QIcon.fromTheme("folder"))
            if path in default_paths:
                item.setFont(QFont("Arial", 10, QFont.StyleItalic))
                item.setForeground(Qt.gray)
                item.setData(Qt.UserRole, True)
            else:
                item.setData(Qt.UserRole, False)
            self.scan_list.addItem(item)

    def add_scan_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder and folder not in self.main_player.scan_dirs:
            self.main_player.scan_dirs.append(folder)
            self.refresh_scan_list()
            self.main_player.save_scan_paths() 

    def remove_scan_path(self):
        selected_items = self.scan_list.selectedItems()
        for item in selected_items:
            if not item.data(Qt.UserRole):
                path = item.text()
                if path in self.main_player.scan_dirs:
                    self.main_player.scan_dirs.remove(path)
        self.refresh_scan_list()
        self.main_player.save_scan_paths()
            
    def update_remove_button(self):
        selected_items = self.scan_list.selectedItems()
        if not selected_items:
            self.btnRemovePath.setEnabled(False)
            return
        for item in selected_items:
            if item.data(Qt.UserRole):
                self.btnRemovePath.setEnabled(False)
                return
        self.btnRemovePath.setEnabled(True)
        
    def submit_report(self):
        subject = self.subject_edit.text().strip()
        message = self.message_edit.toPlainText().strip()
        if not subject or not message:
            QMessageBox.warning(self, "Warning", "Please fill in both subject and message.")
            return
        body = f"Subject: {subject}\n\n{message}"
        msg = MIMEText(body)
        msg["Subject"] = f"Bug Report: {subject}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = "kianminer1384@gmail.com"
        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, ["kianminer1384@gmail.com"], msg.as_string())
            server.quit()
            QMessageBox.information(self, "Success", "Your report has been sent.")
            self.subject_edit.clear()
            self.message_edit.clear()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to send report: {e}")
            
    def save_theme(self):
        config = {"theme_index": self.main_player.current_theme_index}
        secure_save(config, "theme_config.safe", self.main_player.encryption_key)
            
    @staticmethod
    def load_saved_theme():
        key_path = os.path.join(SECURE_PATH, 'key.bin')
        try:
            with open(key_path, 'rb') as f:
                key = f.read()
            data = secure_load("theme_config.safe", key)
            if data and "theme_index" in data:
                return data["theme_index"]
        except Exception:
           pass
        return 0



            
# ================= Main MusicPlayer ================= #

class MusicPlayer(QWidget):
    def __init__(self):
        super().__init__()
        key_path = os.path.join(SECURE_PATH, 'key.bin')
        try:
            if os.path.exists(key_path):
                with open(key_path, 'rb') as f:
                    self.encryption_key = f.read()
            else:
                self.encryption_key = Fernet.generate_key()
                os.makedirs(os.path.dirname(key_path), exist_ok=True)
                with open(key_path, 'wb') as f:
                    f.write(self.encryption_key)
        except Exception as e:
            print(f"Error handling encryption key: {e}")
            self.encryption_key = Fernet.generate_key()

        self.secure_folder = SECURE_PATH
        try:
            if not os.path.exists(self.secure_folder):
                os.makedirs(self.secure_folder)
                if os.name == 'posix':
                    os.chmod(self.secure_folder, 0o700)
                else:
                    import win32security
                    import ntsecuritycon as con
                    security = win32security.GetFileSecurity(
                        self.secure_folder, 
                        win32security.DACL_SECURITY_INFORMATION
                    )
                    dacl = win32security.ACL()
                    user_sid = win32security.GetTokenInformation(
                        win32security.OpenProcessToken(
                            win32api.GetCurrentProcess(),
                            win32security.TOKEN_QUERY
                        ),
                        win32security.TokenUser
                    )[0]
                    dacl.AddAccessAllowedAce(
                        win32security.ACL_REVISION,
                        con.FILE_ALL_ACCESS,
                        user_sid
                    )
                    security.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(
                        self.secure_folder, 
                        win32security.DACL_SECURITY_INFORMATION,
                        security
                    )
        except Exception as e:
            print(f"Error setting folder permissions: {e}")
        self.setWindowTitle('V Music')
        self.setFixedSize(1100, 600)
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.song_list = []
        self.filtered_song_list = []
        self.current_index = -1
        self.is_playing = False
        self.playback_modes = ["Shuffle", "Repeat Track", "Repeat Playlist"]
        self.playback_mode_index = 2
        self.current_playlist = None
        self.current_playlist_index = None
        self.play_mode = "folder"
        self.vlc_instance = vlc.Instance('--quiet', '--no-xlib',
                                   '--file-caching=1000',
                                   '--network-caching=3000',
                                   '--live-caching=3000',
                                   '--codec=avcodec,all',
                                   '--no-audio-time-stretch',
                                   '--clock-jitter=0',
                                   '--clock-synchro=0')
        self.player = self.vlc_instance.media_player_new()
        self.set_normal_equalizer()
        self.player.audio_set_volume(80)
        self.player.event_manager().event_attach(vlc.EventType.MediaPlayerEndReached, self.song_finished)
        self.default_music_folder = os.path.join(os.getcwd(), "music")
        if not os.path.isdir(self.default_music_folder):
            os.makedirs(self.default_music_folder)
        self.playlists = {}
        self.load_playlists()
        self.online_mode = is_connected()
        self.streaming_manager = StreamingManager()
        self.is_muted = False
        self.scan_dirs = [os.path.expanduser("~/Music"), os.path.expanduser("~/Downloads")]
   
        self.themes = [
            {"name": "Purple Blue", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED)" ,
             "font_color" : "black" , "selected_color": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED)"},


            {"name": "Default Dark 1", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #3C096C, stop:1 #0A2463)" ,
             "font_color" : "white" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #3C096C, stop:1 #0A2463)"},


            {"name": "Cyberpunk", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #0f3460, stop:1 #e94560)", 
             "font_color": "white", "selected_color": "#e94560"},


            {"name": "Ocean", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #667eea, stop:1 #764ba2)", 
             "font_color": "white", "selected_color": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #667eea, stop:1 #764ba2)"},


            {"name": "Default Dark 2", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #1a1a2e, stop:1 #16213e)", 
             "font_color": "white", "selected_color": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #3C096C, stop:1 #0A2463)"},

             
            {"name": "Red Orange", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #FF0000, stop:1 #FFA500)",
             "font_color" : "black" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #FF0000, stop:1 #FFA500)"},


            {"name": "Arit", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #FF9A9E, stop:1 #FAD0C4)",
             "font_color" : "black" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #FF9A9E, stop:1 #FAD0C4)"},


            {"name": "Ganesha", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #89F7FE, stop:1 #66A6FF)",
             "font_color" : "black" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #89F7FE, stop:1 #66A6FF)"},


            {"name": "Charcoal Blue", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #0D1117, stop:1 #161B22)",
             "font_color" : "white" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #0D1117, stop:1 #161B22)"},


            {"name": "Midnight Navy", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #141C2F, stop:1 #1E2838)",
             "font_color" : "white" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #141C2F, stop:1 #1E2838)"},


            {"name": "Smoky Charcoal", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #1A1E23, stop:1 #20252B)",
             "font_color" : "white" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #1A1E23, stop:1 #20252B)"},


            {"name": "Deep Purple Night", "gradient": "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #1C0F25, stop:1 #2E152E)",
             "font_color" : "white" , "selected_color" : "qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #1C0F25, stop:1 #2E152E)"}
        ]
        self.current_theme_index = 0

        self.initUI()
        self.initTimer()
        self.load_local_songs()
        self.updatePlaylistWidget()

        self.listener = keyboard.Listener(
            on_press=self.on_key_press,
            suppress=True
        )
        self.listener.start()


    def on_key_press(self, key):
        if not self.isActiveWindow():
            return False 
            
        try:
            if key == keyboard.Key.media_play_pause:
                QTimer.singleShot(0, self.toggle_play_pause)
                return True 
            elif key == keyboard.Key.media_next:
                QTimer.singleShot(0, self.play_next)
                return True
            elif key == keyboard.Key.media_previous:
                QTimer.singleShot(0, self.play_prev)
                return True
        except AttributeError:
            pass
        return False
    
    def initUI(self):
        self.setFont(QFont("Exo 2 SemiBold", 14))
        mainLayout = QHBoxLayout(self)
        self.current_theme_index = SettingsDialog.load_saved_theme()
        self.apply_theme()
        self.scan_dirs = self.load_scan_paths()
        if not self.scan_dirs:
            self.scan_dirs = [os.path.expanduser("~/Music"), os.path.expanduser("~/Downloads")]

        leftContainer = QWidget()
        leftContainerLayout = QHBoxLayout(leftContainer)

        folderWidget = QWidget()
        folderLayout = QVBoxLayout(folderWidget)
        folderLabel = QLabel("Folder Music List")
        folderLabel.setFont(QFont("Exo 2 SemiBold", 16))
        folderLayout.addWidget(folderLabel)
        self.searchBar = QLineEdit()
        self.searchBar.setPlaceholderText("Search songs...")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300) 
        self.searchBar.textChanged.connect(lambda: self._search_timer.start())
        self._search_timer.timeout.connect(self.filterSongs)
        folderLayout.addWidget(self.searchBar)
        self.listWidget = QListWidget()
        self.listWidget.setFixedWidth(310)
        self.listWidget.setFont(QFont("Exo 2 medium", 18))
        self.listWidget.itemDoubleClicked.connect(self.play_selected_song)
        folderLayout.addWidget(self.listWidget)
        leftContainerLayout.addWidget(folderWidget)

        playlistWidget = QWidget()
        playlistLayout = QVBoxLayout(playlistWidget)
        self.playlistLabel = QLabel("No Playlist Selected")
        self.playlistLabel.setFont(QFont("Exo 2 SemiBold", 16))
        playlistLayout.addWidget(self.playlistLabel)
        self.playlistListWidget = QListWidget()
        self.playlistListWidget.setFixedWidth(305)
        self.playlistListWidget.setFont(QFont("Exo 2 medium", 14))
        self.playlistListWidget.itemDoubleClicked.connect(self.play_playlist_song)
        playlistLayout.addWidget(self.playlistListWidget)
        leftContainerLayout.addWidget(playlistWidget)

        mainLayout.addWidget(leftContainer, 7)

        self.listWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.listWidget.customContextMenuRequested.connect(self.showSongContextMenu)

        controlWidget = QWidget()
        controlLayout = QVBoxLayout(controlWidget)
        controlLayout.setContentsMargins(10, 10, 10, 10)
        controlLayout.setSpacing(15)
        topLayout = QHBoxLayout()
        self.btnLoadFolder = QToolButton()
        self.btnLoadFolder.setIcon(QIcon(icon_path("folder.png")))
        self.btnLoadFolder.setToolTip("Open Folder")
        self.btnLoadFolder.setIconSize(QSize(20, 20))
        self.btnLoadFolder.setFixedSize(QSize(30, 30))
        self.btnLoadFolder.clicked.connect(self.loadFolder)
        topLayout.addWidget(self.btnLoadFolder, alignment=Qt.AlignLeft)
        self.btnMusicLibrary = QToolButton()
        self.btnMusicLibrary.setIcon(QIcon(icon_path("library.png")))
        self.btnMusicLibrary.setToolTip("Online Music Library")
        self.btnMusicLibrary.setIconSize(QSize(20, 20))
        self.btnMusicLibrary.setFixedSize(QSize(30, 30))
        self.btnMusicLibrary.clicked.connect(self.open_music_library)
        topLayout.addWidget(self.btnMusicLibrary, alignment=Qt.AlignLeft)
        self.btnPlaylist = QToolButton()
        self.btnPlaylist.setIcon(QIcon(icon_path("playlist.png")))
        self.btnPlaylist.setToolTip("Playlist Manager")
        self.btnPlaylist.setIconSize(QSize(20, 20))
        self.btnPlaylist.setFixedSize(QSize(30, 30))
        self.btnPlaylist.clicked.connect(self.open_playlist_dialog)
        topLayout.addWidget(self.btnPlaylist, alignment=Qt.AlignLeft)
        self.btnToggleOnline = QToolButton()
        btn_toggle_online_icon = icon_path("local.png") if self.online_mode else icon_path("online.png")
        self.btnToggleOnline.setIcon(QIcon(btn_toggle_online_icon))
        tooltip_text = "Switch to Local Mode" if self.online_mode else "Switch to Online Mode"
        self.btnToggleOnline.setToolTip(tooltip_text)
        self.btnToggleOnline.setIconSize(QSize(30, 30))
        self.btnToggleOnline.setFixedSize(QSize(30, 30))
        self.btnToggleOnline.clicked.connect(self.toggle_online_mode)
        topLayout.addWidget(self.btnToggleOnline, alignment=Qt.AlignLeft)
        topLayout.addStretch(1)
        self.btnSettings = QToolButton()
        self.btnSettings.setIcon(QIcon(icon_path("settings.png")))
        self.btnSettings.setToolTip("Settings")
        self.btnSettings.setIconSize(QSize(30, 30))
        self.btnSettings.setFixedSize(QSize(30, 30))
        self.btnSettings.clicked.connect(self.open_settings_dialog)
        topLayout.addWidget(self.btnSettings, alignment=Qt.AlignRight)
        self.modeButton = QToolButton()
        self.modeButton.setToolTip("Change Playback Mode")
        self.update_mode_button()
        self.modeButton.clicked.connect(self.toggle_playback_mode)
        topLayout.addWidget(self.modeButton, alignment=Qt.AlignRight)
        self.btnDownloads = QToolButton()
        self.btnDownloads.setIcon(QIcon(icon_path("download.png")))
        self.btnDownloads.setToolTip("Downloaded Songs")
        self.btnDownloads.setIconSize(QSize(20, 20))
        self.btnDownloads.setFixedSize(QSize(30, 30))
        self.btnDownloads.clicked.connect(self.open_downloads_list)
        topLayout.addWidget(self.btnDownloads, alignment=Qt.AlignRight)
        self.profileWidget = ProfileWidget("Guest", None)
        self.profileWidget.clicked.connect(self.open_user_profile)
        topLayout.addWidget(self.profileWidget, alignment=Qt.AlignRight)
        controlLayout.addLayout(topLayout)
        self.statusLabel = QLabel("Status: Stopped")
        self.statusLabel.setFont(QFont("Exo 2 SemiBold", 18))
        self.statusLabel.setAlignment(Qt.AlignCenter)
        self.statusLabel.setStyleSheet("color: white; background: none;")        
        controlLayout.addWidget(self.statusLabel)
        controlLayout.addSpacing(10)
        self.albumArtLabel = RotatingAlbumArt()
        self.albumArtLabel.set_player(self)
        default_art = QPixmap(icon_path("default_disk.png"))
        if default_art.isNull():
            default_art = QPixmap(200, 200)
            default_art.fill(Qt.darkGray)
        self.albumArtLabel.setPixmap(default_art.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        controlLayout.addWidget(self.albumArtLabel, alignment=Qt.AlignCenter)
        controlLayout.addSpacing(10)
        playbackLayout = QHBoxLayout()
        self.btnPrev = AnimatedPushButton(normal_size=QSize(35, 35), scale=1.1)
        self.btnPrev.setIcon(QIcon(icon_path("prev.png")))
        self.btnPrev.setToolTip("Previous")
        self.btnPrev.clicked.connect(self.play_prev)
        playbackLayout.addWidget(self.btnPrev)
        self.btnPlayPause = AnimatedPushButton(normal_size=QSize(60, 60), scale=1.1)
        self.btnPlayPause.setIcon(QIcon(icon_path("play.png")))
        self.btnPlayPause.setToolTip("Play/Pause")
        self.btnPlayPause.clicked.connect(self.toggle_play_pause)
        playbackLayout.addWidget(self.btnPlayPause)
        self.btnNext = AnimatedPushButton(normal_size=QSize(35, 35), scale=1.1)
        self.btnNext.setIcon(QIcon(icon_path("next.png")))
        self.btnNext.setToolTip("Next")
        self.btnNext.clicked.connect(self.play_next)
        playbackLayout.addWidget(self.btnNext)
        controlLayout.addLayout(playbackLayout)
        self.slider = ClickableSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setStyleSheet(slider_normal_style)
        self.slider.sliderClicked.connect(lambda val: self.seek_position())
        self.slider.sliderReleased.connect(self.seek_position)
        controlLayout.addWidget(self.slider)
        self.timeLabel = QLabel("00:00 / 00:00")
        self.timeLabel.setFont(QFont("Exo 2 SemiBold", 18))
        self.timeLabel.setAlignment(Qt.AlignCenter)
        self.timeLabel.setStyleSheet("color: white; background: none;")
        controlLayout.addWidget(self.timeLabel)
        volumeLayout = QHBoxLayout()
        self.btnVolDown = QPushButton()
        self.btnVolDown.setIcon(QIcon(icon_path("volume_minus.png")))
        self.btnVolDown.setToolTip("Volume Down")
        self.btnVolDown.clicked.connect(self.volume_down)
        self.btnVolDown.setIconSize(QSize(30, 30))
        self.btnVolDown.setFixedSize(QSize(30, 30))
        volumeLayout.addWidget(self.btnVolDown)
        self.volSlider = ClickableSlider(Qt.Horizontal)
        self.volSlider.setRange(0, 100)
        saved_volume = self.load_volume_settings()
        self.player.audio_set_volume(saved_volume)
        self.volSlider.setValue(saved_volume)
        self.volSlider.setStyleSheet(slider_normal_style)
        self.volSlider.setStyleSheet(slider_normal_style)
        self.volSlider.sliderClicked.connect(lambda val: self.set_volume())
        self.volSlider.sliderReleased.connect(self.set_volume)
        volumeLayout.addWidget(self.volSlider)
        self.btnVolUp = QPushButton()
        self.btnVolUp.setIcon(QIcon(icon_path("vol_plus.png")))
        self.btnVolUp.setToolTip("Volume Up")
        self.btnVolUp.clicked.connect(self.volume_up)
        self.btnVolUp.setIconSize(QSize(30, 30))
        self.btnVolUp.setFixedSize(QSize(30, 30))
        volumeLayout.addWidget(self.btnVolUp)
        self.btnEqualizer = QPushButton()
        self.btnEqualizer.setIcon(QIcon(icon_path("equalizer.png")))
        self.btnEqualizer.setToolTip("Equalizer")
        self.btnEqualizer.setIconSize(QSize(30, 30))
        self.btnEqualizer.setFixedSize(QSize(30, 30))
        self.btnEqualizer.clicked.connect(self.show_equalizer)
        volumeLayout.addWidget(self.btnEqualizer)
        self.btnMute = QPushButton()
        self.btnMute.setIcon(QIcon(icon_path("unmute.png")))
        self.btnMute.setToolTip("Mute")
        self.btnMute.setIconSize(QSize(30, 30))
        self.btnMute.setFixedSize(QSize(30, 30))
        self.btnMute.clicked.connect(self.toggle_mute)
        volumeLayout.addWidget(self.btnMute)
        controlLayout.addLayout(volumeLayout)
        mainLayout.addWidget(controlWidget, 3)


    def apply_theme(self):
        theme = self.themes[self.current_theme_index]
        self.setStyleSheet(f"""
            QWidget {{
                background: {theme['gradient']};
                border-radius: 10px;
            }}
            QToolButton, QPushButton {{
                background-color: transparent;
                border: none;
            }}
            QPushButton:hover, QToolButton:hover {{
                background-color: rgba(65,105,225,0.2);
                border-radius: 10px;
            }}
            QLabel {{
                color: {theme['font_color']};
                font-size: 14px;
                background: none;
            }}
            QListWidget {{
                background-color: rgba(240,240,240,0.8);
                color: {theme['gradient']};
                border: none;
                font-size: 14px;
                padding: 10px;
                border-radius: 10px;
            }}
            QListWidget::item {{
                padding: 10px;
                margin: 4px;
                border-radius: 10px;
            }}
            QListWidget::item:selected {{
                background-color: {theme['selected_color']};
                color: white;
                border-radius: 10px;
            }}
            QScrollBar:vertical {{
                background: #ccc;
                width : 10px;
                height : 7px;
            }}
             QScrollBar:horizontal{{
                background: #ccc;
                width : 7px;
                height : 10px;
             }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: #888;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                background: none;
            }}
            QLineEdit {{
                background: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 6px;
                min-height: 30px;
                color: {theme['font_color']};
                font-size: 14px;
            }}
        """)


    def apply_theme_by_index(self, index):
        self.current_theme_index = index
        self.apply_theme()
        
    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec_()


    def change_theme(self):
        self.apply_theme()

    def show_equalizer(self):
        dialog = EqualizerDialog(self.player, self)
        dialog.exec_()

    def save_scan_paths(self):
        try:
            secure_save(self.scan_dirs, "scan_paths.enc", self.encryption_key)
            cache_file = os.path.join(SECURE_PATH, "local_songs_cache.safe")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        except Exception as e:
            print("Error saving scan paths:", e)

    def load_scan_paths(self):
        try: 
            data = secure_load("scan_paths.enc", self.encryption_key)
            return data if data else [os.path.expanduser("~/Music"), 
                                    os.path.expanduser("~/Downloads")]
        except Exception as e:
            print("Error loading Scan path :" , e)


    def load_local_songs(self):
        scanner = LocalMusicScanner(self)
        scanner.scan_dirs = self.scan_dirs
        scanner.load_local_songs()
        self.song_list = scanner.get_scanned_files()
        self.playlists["system musics"] = scanner.get_playlists().get("system musics", [])
        self.statusLabel.setText("Local songs loaded")
        self.listWidget.clear()
        for path in self.song_list:
           name = os.path.basename(path)
           item = QListWidgetItem(QIcon(icon_path("music.png")), name)
           item.setData(Qt.UserRole, path)
           self.listWidget.addItem(item)
        self.filtered_song_list = self.song_list.copy()

    def initTimer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_slider)
        self.timer.start()

    def loadDefaultFolder(self):
        self.loadSongsFromFolder(self.default_music_folder)

    def loadFolder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.loadSongsFromFolder(folder)
            self.statusLabel.setText("Folder Loaded")

    def loadSongsFromFolder(self, folder):
        self.song_list = [
            os.path.join(folder, fn)
            for fn in os.listdir(folder)
            if fn.lower().endswith((".mp3", ".wav", ".flac", ".ogg"))
        ]
        self.statusLabel.setText("Folder Loaded")
        self.listWidget.clear()
        for path in self.song_list:
            name = os.path.basename(path)
            item = QListWidgetItem(QIcon(icon_path("music.png")), name)
            item.setData(Qt.UserRole, path)
            self.listWidget.addItem(item)
        self.filtered_song_list = self.song_list.copy()
        self.filterSongs(self.searchBar.text())
        self.updatePlaylistWidget()

    def filterSongs(self, text=None):
        pattern = (text if text is not None else self.searchBar.text()).lower()
        self.filtered_song_list = []
        for i, path in enumerate(self.song_list):
            name = os.path.basename(path)
            match = pattern in name.lower()
            item = self.listWidget.item(i)
            item.setHidden(not match)
            if match:
               self.filtered_song_list.append(path)

    def play_selected_song(self, item=None):
        if self.play_mode == "playlist":
            reply = QMessageBox.question(self, "Switch Mode",
                                         "A playlist is currently playing. Do you want to switch to Folder mode?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
            else:
                self.play_mode = "folder"
                self.current_playlist = None
        row = self.listWidget.currentRow()
        if 0 <= row < len(self.filtered_song_list):
            selected_path = self.filtered_song_list[row]
            try:
                self.current_index = self.song_list.index(selected_path)
            except ValueError:
                self.current_index = row
            self.load_and_play(selected_path)
            self.listWidget.setCurrentRow(row)
            self.updatePlaylistWidget()

    def save_scan_paths(self):
        try:
            secure_save(self.scan_dirs, "scan_paths.enc", self.encryption_key)
        except Exception as e:
            print("Error saving scan paths:", e)

    def load_scan_paths(self):
        try: 
            data = secure_load("scan_paths.enc", self.encryption_key)
            return data if data else [os.path.expanduser("~/Music"), 
                                    os.path.expanduser("~/Downloads")]
        except Exception as e:
            print("Error loading Scan path :" , e)


    def update_album_art(self, source):
        try:
            if isinstance(source, str):
                art = get_album_art(source)
                if art:
                    self.albumArtLabel.setPixmap(art)
                else:
                    default_art = QPixmap(icon_path("default_disk.png"))
                    self.albumArtLabel.setPixmap(default_art)
            elif isinstance(source, dict):
                cover_url = source.get("cover")
                if cover_url:
                    pixmap = self.download_album_art(cover_url)
                    self.albumArtLabel.setPixmap(pixmap)
                else:
                    default_art = QPixmap(icon_path("default_disk.png"))
                    self.albumArtLabel.setPixmap(default_art)
            
            if self.is_playing:
                self.albumArtLabel.start_rotation()
            else:
                self.albumArtLabel.stop_rotation()
                
        except Exception as e:
            print(f"Error updating album art: {e}")
            default_art = QPixmap(icon_path("default_disk.png"))
            self.albumArtLabel.setPixmap(default_art)
        

    def load_and_play(self, source):
        try:
            if isinstance(source, str):
                media = self.vlc_instance.media_new(source)
                media.add_option('network-caching=1000')
                media.add_option('clock-jitter=0')
                media.add_option('clock-synchro=0')
                display_name = os.path.basename(source)
            elif isinstance(source, dict):
                song_url = source.get("url", "")
                if song_url.startswith("http"):
                    playable_source = self.streaming_manager.get_song(song_url)
                    media = self.vlc_instance.media_new(playable_source)
                    media.add_option('network-caching=3000')
                    media.add_option('live-caching=3000')
                else:
                    media = self.vlc_instance.media_new(song_url)
                display_name = source.get("name", "Unknown Song")
            else:
                print("Invalid song source")
                return
            
            self.player.set_media(media)
            self.player.play()
            self.is_playing = True
            self.update_play_pause_icon()
            self.statusLabel.setText("Playing: " + display_name[:18])
            
            if isinstance(source, str):
                art = get_album_art(source)
                if art:
                    self.animate_album_art_change(art)
                else:
                    default_art = QPixmap(icon_path("default_disk.png"))
                    self.animate_album_art_change(default_art)
            elif isinstance(source, dict):
                cover_url = source.get("cover")
                if cover_url:
                    pixmap = self.download_album_art(cover_url)
                    self.animate_album_art_change(pixmap)
                else:
                    default_art = QPixmap(icon_path("default_disk.png"))
                    self.animate_album_art_change(default_art)
            
            QTimer.singleShot(500, self.update_slider)

        except Exception as e:
            print(f"Error in playback: {e}")
            self.statusLabel.setText("Playback Error")
            self.is_playing = False
            self.update_play_pause_icon()

    def animate_album_art_change(self, new_pixmap):
        if not hasattr(self.albumArtLabel, 'opacity_effect'):
            self.albumArtLabel.opacity_effect = QGraphicsOpacityEffect(self.albumArtLabel)
            self.albumArtLabel.setGraphicsEffect(self.albumArtLabel.opacity_effect)

        if not hasattr(self, 'fade_animation'):
            self.fade_animation = QPropertyAnimation(self.albumArtLabel.opacity_effect, b"opacity")
            self.fade_animation.setDuration(300)

        try:
            self.fade_animation.finished.disconnect()
        except:
            pass

        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.finished.connect(lambda: self._finish_animation(new_pixmap))
        self.fade_animation.start()

    def _finish_animation(self, new_pixmap):
        scaled_pixmap = new_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.albumArtLabel.setPixmap(scaled_pixmap)
        
        try:
            self.fade_animation.finished.disconnect()
        except:
            pass
            
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.finished.connect(lambda: self._start_rotation_if_playing())
        self.fade_animation.start()

    def _start_rotation_if_playing(self):
        if self.is_playing:
            self.albumArtLabel.start_rotation()

    def handle_media_state_changed(self, event):
        if event.type == vlc.EventType.MediaStateChanged:
            state = self.player.get_state()
            if state == vlc.State.Error:
                print("Media playback error detected")
                self.statusLabel.setText("Playback Error")
                self.is_playing = False
                self.update_play_pause_icon()
                QTimer.singleShot(1000, self.attempt_recovery)

    def attempt_recovery(self):
        """Attempt to recover from playback errors"""
        try:
            if self.player.get_state() == vlc.State.Error:
                current_media = self.player.get_media()
                if current_media:
                    self.player.stop()
                    self.player.release()
                    self.player = self.vlc_instance.media_player_new()
                    self.player.set_media(current_media)
                    self.player.play()
                    self.is_playing = True
                    self.update_play_pause_icon()
        except Exception as e:
            print(f"Recovery attempt failed: {e}")

    def download_album_art(self, url):
        if not url:
            print("No album art URL provided")
            return QPixmap(icon_path("default_disk.png"))
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                print(f"Successfully downloaded album art from {url}")
                return pixmap
            else:
                print(f"Failed to load image data from {url}")
        except Exception as e:
            print(f"Error downloading album art from {url}: {e}")
        return QPixmap(icon_path("default_disk.png"))

    """def animate_album_art_change(self, new_pixmap):
        effect = self.albumArtLabel.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self.albumArtLabel)
            self.albumArtLabel.setGraphicsEffect(effect)
        self.fade_out = QPropertyAnimation(effect, b"opacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(1)
        self.fade_out.setEndValue(0)
        self.fade_out.finished.connect(lambda: self.on_fade_out_finished(new_pixmap, effect))
        self.fade_out.start()

    def on_fade_out_finished(self, new_pixmap, effect):
        self.albumArtLabel.setPixmap(new_pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.fade_in = QPropertyAnimation(effect, b"opacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0)
        self.fade_in.setEndValue(1)
        self.fade_in.start()"""
        
    def toggle_play_pause(self):
        state = self.player.get_state()
        if state in [vlc.State.Playing, vlc.State.Paused]:
            if self.is_playing:
                self.player.pause()
                self.is_playing = False
                self.statusLabel.setText("Paused")
                self.albumArtLabel.stop_rotation()
            else:
                self.player.play()
                self.is_playing = True
                self.statusLabel.setText("Playing")
                self.albumArtLabel.start_rotation()
        else:
            self.play_selected_song()
        self.update_play_pause_icon()

    def update_play_pause_icon(self):
        if self.is_playing:
            self.btnPlayPause.setIcon(QIcon(icon_path("pause.png")))
        else:
            self.btnPlayPause.setIcon(QIcon(icon_path("play.png")))

    def play_prev(self):
        if self.play_mode == "playlist" and self.current_playlist is not None:
            mode = self.playback_modes[self.playback_mode_index]
            if mode == "Shuffle":
                self.current_playlist_index = random.randint(0, len(self.current_playlist) - 1)
            elif mode == "Repeat Track":
                pass
            else:
                self.current_playlist_index = (self.current_playlist_index - 1) % len(self.current_playlist)
            self.load_and_play(self.current_playlist[self.current_playlist_index])
            self.playlistListWidget.setCurrentRow(self.current_playlist_index)
        elif self.song_list:
            if self.playback_modes[self.playback_mode_index] == "Shuffle":
                self.current_index = random.randint(0, len(self.song_list) - 1)
            else:
                self.current_index = (self.current_index - 1) % len(self.song_list)
            self.load_and_play(self.song_list[self.current_index])
            try:
                idx = self.filtered_song_list.index(self.song_list[self.current_index])
                self.listWidget.setCurrentRow(idx)
            except ValueError:
                pass

    def play_next(self):
        if self.play_mode == "playlist" and self.current_playlist is not None:
            mode = self.playback_modes[self.playback_mode_index]
            if mode == "Shuffle":
                self.current_playlist_index = random.randint(0, len(self.current_playlist) - 1)
            elif mode == "Repeat Track":
                pass
            else:
                self.current_playlist_index = (self.current_playlist_index + 1) % len(self.current_playlist)
            self.load_and_play(self.current_playlist[self.current_playlist_index])
            self.playlistListWidget.setCurrentRow(self.current_playlist_index)
        elif self.song_list:
            mode = self.playback_modes[self.playback_mode_index]
            if mode == "Shuffle":
                self.current_index = random.randint(0, len(self.song_list) - 1)
            else:
                self.current_index = (self.current_index + 1) % len(self.song_list)
            self.load_and_play(self.song_list[self.current_index])
            try:
                idx = self.filtered_song_list.index(self.song_list[self.current_index])
                self.listWidget.setCurrentRow(idx)
            except ValueError:
                pass

    def update_slider(self):
        try:
            length = self.player.get_length()
            pos = self.player.get_time()
            if length > 0:
                self.slider.blockSignals(True)
                self.slider.setRange(0, length)
                self.slider.setValue(pos)
                self.slider.blockSignals(False)
                self.timeLabel.setText(f"{ms_to_time(pos)} / {ms_to_time(length)}")
        except Exception:
            pass

    def seek_position(self):
        new_time = self.slider.value()
        self.player.set_time(new_time)
        length = self.player.get_length()
        self.timeLabel.setText(f"{ms_to_time(new_time)} / {ms_to_time(length)}")

    def set_normal_equalizer(self):
        eq = vlc.libvlc_audio_equalizer_new()
        for i in range(10):
            vlc.libvlc_audio_equalizer_set_amp_at_index(eq, 0, i)
        vlc.libvlc_media_player_set_equalizer(self.player, eq)
        vlc.libvlc_audio_equalizer_release(eq)

    def volume_down(self):
        current_vol = self.player.audio_get_volume()
        new_vol = max(0, current_vol - 10)
        self.player.audio_set_volume(new_vol)
        self.volSlider.setValue(new_vol)

    def volume_up(self):
        current_vol = self.player.audio_get_volume()
        new_vol = min(100, current_vol + 10)
        self.player.audio_set_volume(new_vol)
        self.volSlider.setValue(new_vol)

    def save_volume_settings(self):
        try:
            current_volume = self.player.audio_get_volume()
            secure_save({"volume": current_volume}, "volume_settings.enc", self.encryption_key)
        except Exception as e:
            print(f"Error saving volume settings: {e}")

    def load_volume_settings(self):
        try:
            data = secure_load("volume_settings.enc", self.encryption_key)
            if data and "volume" in data:
                return data["volume"]
        except Exception as e:
            print(f"Error loading volume settings: {e}")
        return 50 
    
    def set_volume(self):
        vol = self.volSlider.value()
        self.player.audio_set_volume(vol)
        self.save_volume_settings()

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self.player.audio_set_mute(self.is_muted)
        if self.is_muted:
            self.btnMute.setIcon(QIcon(icon_path("mute.png")))
        else:
            self.btnMute.setIcon(QIcon(icon_path("unmute.png")))

    def toggle_playback_mode(self):
        self.playback_mode_index = (self.playback_mode_index + 1) % len(self.playback_modes)
        self.update_mode_button()

    def update_mode_button(self):
        mode = self.playback_modes[self.playback_mode_index]
        if mode == "Shuffle":
            self.modeButton.setIconSize(QSize(30, 30))
            self.modeButton.setIcon(QIcon(icon_path("shuffle.png")))
        elif mode == "Repeat Track":
            self.modeButton.setIconSize(QSize(30, 30))
            self.modeButton.setIcon(QIcon(icon_path("repeat_one.png")))
        elif mode == "Repeat Playlist":
            self.modeButton.setIconSize(QSize(30, 30))
            self.modeButton.setIcon(QIcon(icon_path("repeat.png")))
        self.modeButton.setToolTip(f"Playback Mode: {mode}")

    def song_finished(self, event):
        QTimer.singleShot(0, self.on_song_end)

    def on_song_end(self):
        mode = self.playback_modes[self.playback_mode_index]
        if self.play_mode == "playlist" and self.current_playlist is not None:
            if mode == "Repeat Track":
                self.player.stop()
                self.load_and_play(self.current_playlist[self.current_playlist_index])
            else:
                self.play_next()
        else:
            if mode == "Repeat Track":
                self.player.stop()
                self.load_and_play(self.song_list[self.current_index])
            else:
                self.play_next()

    def open_music_library(self):
        user = db_handler.get_user(self.current_user)
        is_admin = (user.get("account_type") == "admin") if user else False
        dialog = OnlineLibraryDialog(self, is_admin=is_admin)
        dialog.exec_()

    def open_downloads_list(self):
        dialog = DownloadsListDialog(self.default_music_folder, play_callback=self.load_and_play, parent=self)
        dialog.exec_()

    def open_playlist_dialog(self):
        dialog = PlaylistDialog(self.playlists, main_player=self, parent=self)
        dialog.exec_()
        self.save_playlists()
        self.updatePlaylistWidget()

    def play_playlist(self, playlist):
        if playlist:
            self.play_mode = "playlist"
            self.current_playlist = playlist
            self.current_playlist_index = 0
            self.load_and_play(playlist[0])
            self.updatePlaylistWidget()

    def updatePlaylistWidget(self):
        if self.play_mode == "playlist" and self.current_playlist is not None:
            self.playlistLabel.setText("Playlist: " + self.getCurrentPlaylistName()[:20])
            self.playlistListWidget.clear()
            for song in self.current_playlist:
                if isinstance(song, str):
                    name = os.path.basename(song)
                elif isinstance(song, dict):
                    name = song.get("name", "Unknown Song")
                else:
                    name = "Unknown"
                item = QListWidgetItem(QIcon(icon_path("music.png")), name)
                self.playlistListWidget.addItem(item)
            if self.current_playlist_index is not None:
                self.playlistListWidget.setCurrentRow(self.current_playlist_index)
        else:
            self.playlistLabel.setText("No Playlist Selected")
            self.playlistListWidget.clear()

    def getCurrentPlaylistName(self):
        for name, plist in self.playlists.items():
            if plist == self.current_playlist:
                return name
        return "Unknown"

    def play_playlist_song(self, item=None):
        if self.play_mode == "playlist" and self.current_playlist is not None:
            row = self.playlistListWidget.currentRow()
            if 0 <= row < len(self.current_playlist):
                self.current_playlist_index = row
                self.load_and_play(self.current_playlist[row])

    def toggle_online_mode(self):
        self.online_mode = not self.online_mode
        if self.online_mode:
            self.statusLabel.setText("Online Mode Enabled")
            self.btnToggleOnline.setToolTip("Switch to Local Mode")
            self.btnToggleOnline.setIcon(QIcon(icon_path("local.png")))
        else:
            self.statusLabel.setText("Local Mode Enabled")
            self.btnToggleOnline.setToolTip("Switch to Online Mode")
            self.btnToggleOnline.setIcon(QIcon(icon_path("online.png")))

    def save_playlists(self):
        try:
            secure_save(self.playlists, "playlists.enc", self.encryption_key)
        except Exception as e:
            print("Error saving playlists:", e)

    def load_playlists(self):
        path = os.path.join(self.secure_folder, "playlists.enc")
        if os.path.exists(path):
            try:
                data = secure_load("playlists.enc", self.encryption_key)
                self.playlists = data if data else {}
            except Exception as e:
                print("Error loading playlists:", e)
                self.playlists = {}
        else:
            self.playlists = {}

    def showSongContextMenu(self, pos: QPoint):
        row = self.listWidget.currentRow()
        if row < 0 or row >= len(self.filtered_song_list):
            return
        song_path = self.filtered_song_list[row]
        menu = QMenu()
        for playlist_name in self.playlists.keys():
            action = menu.addAction(playlist_name)
        menu.addSeparator()
        create_action = menu.addAction("Create New Playlist")
        action = menu.exec_(self.listWidget.mapToGlobal(pos))
        if action:
            if action.text() == "Create New Playlist":
                name, ok = QInputDialog.getText(self, "Create Playlist", "Enter playlist name:")
                if ok and name:
                    if name not in self.playlists:
                        self.playlists[name] = [song_path]
                        self.save_playlists()
            else:
                playlist_name = action.text()
                if song_path not in self.playlists.get(playlist_name, []):
                    self.playlists[playlist_name].append(song_path)
                    self.save_playlists()

    def open_user_profile(self):
        if not is_connected(): 
            QMessageBox.warning(self ,"No Internet Connection !", "Cannot Access Profile at this time please Try again when you are online !! ")
        else :
            dialog = UserProfileDialog(self.current_user, self)
            dialog.logout_requested.connect(self.handle_logout)
            dialog.exec_()
            user = db_handler.get_user(self.current_user)
            profile_pic = user.get("profile_pic") if user else None
            self.profileWidget.update_profile(self.current_user, profile_pic)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.WindowActivate:
            print("Window activated")
        elif event.type() == QEvent.WindowDeactivate:
            print("Window deactivated")
        return super().eventFilter(obj, event)
    
    def closeEvent(self, event):
        try:
            current_volume = self.volSlider.value()
            secure_save({"volume": current_volume}, "volume_settings.enc", self.encryption_key)
        except Exception as e:
            print(f"Error saving volume settings on close: {e}")
            
        if hasattr(self, 'listener'):
            self.listener.stop()
        event.accept()

    def handle_logout(self):
        self.player.stop()
        if hasattr(self, 'listener'):
            self.listener.stop()
        
        self.save_volume_settings()
        self.save_playlists()
        
        self.hide()
        
        for child in self.children():
            if isinstance(child, QDialog):
                child.close()
        
        login_dialog = LoginDialog()
        result = login_dialog.exec_()
        
        if result == QDialog.Accepted:
            if hasattr(login_dialog, 'is_offline') and login_dialog.is_offline:
                username = getattr(login_dialog, 'last_username', "Offline User")
                self.current_user = username
                self.profileWidget.update_profile(username, None)
                self.btnMusicLibrary.setEnabled(False)
                self.btnMusicLibrary.setToolTip("Online Library (Disabled in Offline Mode)")
            else:
                self.current_user = login_dialog.username
                user = db_handler.get_user(self.current_user)
                profile_pic = user.get("profile_pic") if user else None
                self.profileWidget.update_profile(self.current_user, profile_pic)
                self.btnMusicLibrary.setEnabled(True)
                
            self.show()
        else:
            self.close()
            QApplication.quit()


    

# ------------------ Login and Registration Dialogs ------------------ #

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.secure_folder = SECURE_PATH
        try:
            if not os.path.exists(self.secure_folder):
                os.makedirs(self.secure_folder)
                if os.name == 'posix':
                    os.chmod(self.secure_folder, 0o700)
                else:
                    import win32security
                    import ntsecuritycon as con
                    
                    user_sid = win32security.GetTokenInformation(
                        win32security.OpenProcessToken(
                            win32api.GetCurrentProcess(),
                            win32security.TOKEN_QUERY
                        ),
                        win32security.TokenUser
                    )[0]

                    security = win32security.GetFileSecurity(
                        self.secure_folder, 
                        win32security.DACL_SECURITY_INFORMATION
                    )
                    dacl = win32security.ACL()
                    dacl.AddAccessAllowedAce(
                        win32security.ACL_REVISION,
                        con.FILE_ALL_ACCESS,
                        user_sid
                    )
                    security.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(
                        self.secure_folder, 
                        win32security.DACL_SECURITY_INFORMATION,
                        security
                    )
        except Exception as e:
            print(f"Error setting folder permissions: {e}")

        self.encryption_key = Fernet.generate_key()
        key_path = os.path.join(SECURE_PATH, 'key.bin')
        try:
            if os.path.exists(key_path):
                with open(key_path, 'rb') as f:
                    self.encryption_key = f.read()
            else:
                self.encryption_key = Fernet.generate_key()
                os.makedirs(os.path.dirname(key_path), exist_ok=True)
                with open(key_path, 'wb') as f:
                    f.write(self.encryption_key)
        except Exception as e:
            print(f"Error handling encryption key: {e}")

        self.setFixedSize(350, 450)  
        
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED);
            }
            QLabel, QLineEdit { color: white; font-size: 14px; }
            QLineEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px; 
                color: black;
            }
            QPushButton {
                background-color: transparent;
                border: 1px solid white;
                border-radius: 4px;
                padding: 8px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); }
            #offlineButton {
                border: 1px dashed white;
                color: #e0e0e0;
                font-size: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        login_section = QVBoxLayout()
        login_section.setSpacing(10)
        
        self.usernameEdit = QLineEdit()
        self.usernameEdit.setPlaceholderText("Username or Email")
        login_section.addWidget(self.usernameEdit)
        
        self.passwordEdit = QLineEdit()
        self.passwordEdit.setPlaceholderText("Password")
        self.passwordEdit.setEchoMode(QLineEdit.Password)
        login_section.addWidget(self.passwordEdit)

        btnLayout = QHBoxLayout()
        btnLayout.setSpacing(10)
        
        self.loginBtn = QPushButton("Login")
        self.loginBtn.clicked.connect(self.attempt_login)
        btnLayout.addWidget(self.loginBtn)
        
        self.registerBtn = QPushButton("Register")
        self.registerBtn.clicked.connect(self.open_register)
        btnLayout.addWidget(self.registerBtn)
        self.forgotBtn = QPushButton("Forgot Password?")
        self.forgotBtn.setObjectName("forgotButton")
        self.forgotBtn.clicked.connect(self.open_forgot_password)
        self.forgotBtn.setStyleSheet("""
            #forgotButton {
                border: none;
                color: #e0e0e0;
                font-size: 12px;
            }
            #forgotButton:hover {
                color: white;
                text-decoration: underline;
            }
        """)
        btnLayout.addWidget(self.forgotBtn)
        
        login_section.addLayout(btnLayout)
        layout.addLayout(login_section)

        captcha_section = QVBoxLayout()
        captcha_section.setSpacing(10)
        
        self.captchaWidget = CaptchaWidget()
        captcha_section.addWidget(self.captchaWidget, alignment=Qt.AlignCenter)
        
        self.captchaInput = QLineEdit()
        self.captchaInput.setPlaceholderText("Enter captcha")
        captcha_section.addWidget(self.captchaInput)
        
        layout.addLayout(captcha_section)

        self.offlineBtn = QPushButton("Use Offline Instead")
        self.offlineBtn.setObjectName("offlineButton")
        self.offlineBtn.clicked.connect(self.use_offline)
        layout.addWidget(self.offlineBtn)

        self.statusLabel = QLabel("")
        layout.addWidget(self.statusLabel)

        layout.addStretch(1)

        logo_section = QVBoxLayout()
        logo_section.setSpacing(5)
        
        self.producer_icon = QLabel()
        self.producer_icon.setPixmap(QPixmap(icon_path("Mortal_ico_transparent.png")).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.producer_icon.setFixedSize(50, 50)
        self.producer_icon.setScaledContents(True)
        logo_section.addWidget(self.producer_icon, alignment=Qt.AlignCenter)
        
        self.producer_label = QLabel("By Mortal Co")
        self.producer_label.setStyleSheet("color: white; font-size: 12px;")
        logo_section.addWidget(self.producer_label, alignment=Qt.AlignCenter)
        
        layout.addLayout(logo_section)

        self.check_internet_connection()

    def check_internet_connection(self):
        if not is_connected():
            QMessageBox.warning(self , "Connection Error" , "Got an Error while trying to Connect to Server. The Running Process should take a while when you are offline. If you are sure you have proper Internet Connection This Might be our Service problem. Please contact us at https://MortalCo.de/Contact-Us")
            self.statusLabel.setText("No internet connection. You can use offline mode.")
            self.statusLabel.setStyleSheet("color: yellow;")
            self.loginBtn.setEnabled(False)
            self.registerBtn.setEnabled(False)
        else:
            self.loginBtn.setEnabled(True)
            self.registerBtn.setEnabled(True)
            self.statusLabel.clear()
            
    def attempt_login(self):
        identifier = self.usernameEdit.text().strip()
        password = self.passwordEdit.text().strip()
        captcha = self.captchaInput.text().strip()

        if not self.captchaWidget.verify(captcha):
            self.statusLabel.setText("Invalid captcha code.")
            self.captchaWidget.generateCaptcha()
            self.captchaInput.clear()
            return

        cursor = db_handler.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (identifier, identifier))
        user = cursor.fetchone()
        cursor.close()

        if user:
            salt = user["salt"]
            password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            if password_hash == user["password_hash"]:
                self.is_offline = False
                self.username = user["username"]
                secure_save({"username": self.username}, 
                        "last_user.enc", 
                        self.encryption_key)
                self.accept()
                return
        self.statusLabel.setText("Invalid credentials.")
        self.captchaWidget.generateCaptcha()
        self.captchaInput.clear()
            
    def open_register(self):
        dialog = RegisterDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.statusLabel.setText("Registration successful. Please log in.")

    def use_offline(self):
        
        self.is_offline = True
        last_user = secure_load("last_user.enc", self.encryption_key)
        self.last_username = last_user.get("username") if last_user else "Offline User"
        self.accept()

    def open_forgot_password(self):
        dialog = ForgotPasswordDialog(self)
        dialog.exec_()
# ------------------ RegisterDialog ------------------ #

class RegisterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register")
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.setFixedSize(350, 450)

        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED);
            }
            QLabel, QLineEdit { color: white; font-size: 14px; }
            QLineEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
                color: black;
            }
            QPushButton {
                background-color: transparent;
                border: 1px solid white;
                border-radius: 4px;
                padding: 8px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        register_section = QVBoxLayout()
        register_section.setSpacing(10)

        self.usernameEdit = QLineEdit()
        self.usernameEdit.setPlaceholderText("Username")
        register_section.addWidget(self.usernameEdit)

        self.emailEdit = QLineEdit()
        self.emailEdit.setPlaceholderText("Email")
        register_section.addWidget(self.emailEdit)

        self.passwordEdit = QLineEdit()
        self.passwordEdit.setPlaceholderText("Password")
        self.passwordEdit.setEchoMode(QLineEdit.Password)
        register_section.addWidget(self.passwordEdit)

        self.confirmEdit = QLineEdit()
        self.confirmEdit.setPlaceholderText("Confirm Password")
        self.confirmEdit.setEchoMode(QLineEdit.Password)
        register_section.addWidget(self.confirmEdit)

        self.registerBtn = QPushButton("Register")
        self.registerBtn.clicked.connect(self.attempt_register)
        register_section.addWidget(self.registerBtn)

        layout.addLayout(register_section)

        captcha_section = QVBoxLayout()
        captcha_section.setSpacing(10)

        self.captchaWidget = CaptchaWidget()
        captcha_section.addWidget(self.captchaWidget, alignment=Qt.AlignCenter)

        self.captchaInput = QLineEdit()
        self.captchaInput.setPlaceholderText("Enter captcha")
        captcha_section.addWidget(self.captchaInput)

        layout.addLayout(captcha_section)

        self.statusLabel = QLabel("")
        layout.addWidget(self.statusLabel)

        layout.addStretch(1)


        logo_section = QVBoxLayout()
        logo_section.setSpacing(5)

        self.producer_icon = QLabel()
        self.producer_icon.setPixmap(QPixmap(icon_path("Mortal_ico_transparent.png")).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.producer_icon.setFixedSize(50, 50)
        self.producer_icon.setScaledContents(True)
        logo_section.addWidget(self.producer_icon, alignment=Qt.AlignCenter)

        self.producer_label = QLabel("By Mortal Co")
        self.producer_label.setStyleSheet("color: white; font-size: 12px;")
        logo_section.addWidget(self.producer_label, alignment=Qt.AlignCenter)

        layout.addLayout(logo_section)

    def is_valid_email(self, email):
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def attempt_register(self):
        username = self.usernameEdit.text().strip()
        email = self.emailEdit.text().strip()
        password = self.passwordEdit.text().strip()
        confirm = self.confirmEdit.text().strip()
        captcha = self.captchaInput.text().strip()
        
        if not self.captchaWidget.verify(captcha):
            self.statusLabel.setText("Invalid captcha code.")
            self.captchaWidget.generateCaptcha()
            self.captchaInput.clear()
            return
            
        if not username or not email or not password:
            self.statusLabel.setText("Please fill all fields.")
            return

        if not self.is_valid_email(email):
            self.statusLabel.setText("Please enter a valid email address.")
            return

        if password != confirm:
            self.statusLabel.setText("Passwords do not match.")
            return

        cursor = db_handler.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            self.statusLabel.setText("Email already registered.")
            cursor.close()
            return

        if db_handler.get_user(username):
            self.statusLabel.setText("Username already exists.")
            return
            
        salt = os.urandom(32).hex()
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        success = db_handler.add_user(username, salt, password_hash, email=email)
        if success:
            self.accept()
        else:
            self.statusLabel.setText("Registration failed. Try again.")
        
        self.captchaWidget.generateCaptcha()
        self.captchaInput.clear()


class ForgotPasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reset Password")
        self.setFixedSize(350, 450)
        
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED);
            }
            QLabel, QLineEdit { color: white; font-size: 14px; }
            QLineEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
                color: black;
            }
            QPushButton {
                background-color: transparent;
                border: 1px solid white;
                border-radius: 4px;
                padding: 8px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        reset_section = QVBoxLayout()
        reset_section.setSpacing(10)
        
        self.usernameEdit = QLineEdit()
        self.usernameEdit.setPlaceholderText("Username")
        reset_section.addWidget(self.usernameEdit)
        
        self.emailEdit = QLineEdit()
        self.emailEdit.setPlaceholderText("Email")
        reset_section.addWidget(self.emailEdit)

        self.captchaWidget = CaptchaWidget()
        reset_section.addWidget(self.captchaWidget, alignment=Qt.AlignCenter)
        
        self.captchaInput = QLineEdit()
        self.captchaInput.setPlaceholderText("Enter captcha")
        reset_section.addWidget(self.captchaInput)
        
        self.resetBtn = QPushButton("Reset Password")
        self.resetBtn.clicked.connect(self.attempt_reset)
        reset_section.addWidget(self.resetBtn)
        
        layout.addLayout(reset_section)

        self.statusLabel = QLabel("")
        layout.addWidget(self.statusLabel)

        layout.addStretch(1)

        logo_section = QVBoxLayout()
        logo_section.setSpacing(5)
        
        self.producer_icon = QLabel()
        self.producer_icon.setPixmap(QPixmap(icon_path("Mortal_ico_transparent.png")).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.producer_icon.setFixedSize(50, 50)
        self.producer_icon.setScaledContents(True)
        logo_section.addWidget(self.producer_icon, alignment=Qt.AlignCenter)
        
        self.producer_label = QLabel("By Mortal Co")
        self.producer_label.setStyleSheet("color: white; font-size: 12px;")
        logo_section.addWidget(self.producer_label, alignment=Qt.AlignCenter)
        
        layout.addLayout(logo_section)

    def attempt_reset(self):
        username = self.usernameEdit.text().strip()
        email = self.emailEdit.text().strip()
        captcha = self.captchaInput.text().strip()
        
        if not username or not email:
            self.statusLabel.setText("Please fill all fields.")
            return
            
        if not self.captchaWidget.verify(captcha):
            self.statusLabel.setText("Invalid captcha code.")
            self.captchaWidget.generateCaptcha()
            self.captchaInput.clear()
            return

        cursor = db_handler.connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND email = %s", (username, email))
        user = cursor.fetchone()
        cursor.close()

        if not user:
            self.statusLabel.setText("Username and email do not match.")
            return
            
        new_password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))
        new_salt = os.urandom(32).hex()
        new_password_hash = hashlib.sha256((new_password + new_salt).encode()).hexdigest()
        
        try:
            msg = MIMEText(f"Your new password is: {new_password}\nPlease change it after logging in.")
            msg['Subject'] = 'Password Reset'
            msg['From'] = SENDER_EMAIL
            msg['To'] = email
            
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            cursor = db_handler.connection.cursor()
            query = "UPDATE users SET salt = %s, password_hash = %s WHERE username = %s"
            cursor.execute(query, (new_salt, new_password_hash, username))
            db_handler.connection.commit()
            cursor.close()
            
            QMessageBox.information(self, "Success", "New password has been sent to your email.")
            self.accept()
            
        except Exception as e:
            self.statusLabel.setText(f"Error: {str(e)}")
            print("Password reset error:", e)

# ------------------ StreamingManager ------------------ #

class StreamingManager:
    def __init__(self, cache_dir="cache"):
        self.cache_dir = cache_dir
        if not os.path.isdir(self.cache_dir):
            os.makedirs(self.cache_dir)
        self.workers = []
    def get_cached_path(self, song_url):
        hash_name = hashlib.md5(song_url.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{hash_name}.mp3")
    def start_background_cache(self, song_url, cached_path):
        worker = DownloadWorker(song_url, cached_path)
        worker.finished.connect(lambda: self.remove_worker(worker))
        self.workers.append(worker)
        worker.start()
    def remove_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
    def get_song(self, song_url):
        encoded_url = encode_url(song_url)
        cached_path = self.get_cached_path(encoded_url)
        if os.path.exists(cached_path):
            return cached_path
        else:
            self.start_background_cache(encoded_url, cached_path)
            return encoded_url

# ------------------ UserProfileDialog ------------------ #

class UserProfileDialog(QDialog):
    logout_requested = pyqtSignal()
    def __init__(self, username, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("User Profile")
        self.setFixedSize(400, 350)
        theme = parent.themes[parent.current_theme_index]
        self.setStyleSheet(f"""
            QDialog {{
                background: {theme['gradient']};
                color: {theme['font_color']};
            }}
            QLabel {{ font-size: 16px; }}
            QPushButton {{
                background-color: transparent;
                border: 1px solid white;
                border-radius: 4px;
                padding: 6px;
                color: white;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,0.2); }}
        """)
        layout = QVBoxLayout(self)
        user = db_handler.get_user(username)
        profile_pic = user.get("profile_pic") if user else None
        self.picLabel = QLabel()
        if profile_pic:
            try:
                if profile_pic.startswith('http'):
                    response = requests.get(profile_pic)
                    if response.status_code == 200:
                        pixmap = QPixmap()
                        pixmap.loadFromData(response.content)
                        if not pixmap.isNull():
                            circular_pixmap = self.create_circular_pixmap(pixmap)
                            self.picLabel.setPixmap(circular_pixmap)
                        else:
                            self.picLabel.setPixmap(self.create_circular_pixmap(generate_avatar(username, size=150)))
                    else:
                        self.picLabel.setPixmap(self.create_circular_pixmap(generate_avatar(username, size=150)))
                else:
                    pixmap = QPixmap(profile_pic)
                    if not pixmap.isNull():
                        circular_pixmap = self.create_circular_pixmap(pixmap)
                        self.picLabel.setPixmap(circular_pixmap)
                    else:
                        self.picLabel.setPixmap(self.create_circular_pixmap(generate_avatar(username, size=150)))
            except Exception as e:
                print(f"Error loading profile picture: {e}")
                self.picLabel.setPixmap(self.create_circular_pixmap(generate_avatar(username, size=150)))
        else:
            self.picLabel.setPixmap(self.create_circular_pixmap(generate_avatar(username, size=150)))
        layout.addWidget(self.picLabel, alignment=Qt.AlignCenter)
        self.usernameLabel = QLabel(f"Username: {username}")
        layout.addWidget(self.usernameLabel, alignment=Qt.AlignCenter)
        account_type = user.get("account_type") if user else "user"
        self.accountLabel = QLabel(f"Account Type: {account_type}")
        layout.addWidget(self.accountLabel, alignment=Qt.AlignCenter)
        self.uploadBtn = QPushButton("Upload Profile Picture")
        self.uploadBtn.clicked.connect(self.upload_profile_pic)
        layout.addWidget(self.uploadBtn)
        self.changePwdBtn = QPushButton("Change Password")
        self.changePwdBtn.clicked.connect(self.change_password)
        layout.addWidget(self.changePwdBtn)
        self.logoutBtn = QPushButton("Log Out")
        self.logoutBtn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                border: none;
            }
            QPushButton:hover {
                background-color: #ff6666;
            }
        """)
        self.logoutBtn.clicked.connect(self.logout)
        layout.addWidget(self.logoutBtn, alignment=Qt.AlignCenter)
        self.closeBtn = QPushButton("Close")
        self.closeBtn.clicked.connect(self.accept)
        layout.addWidget(self.closeBtn, alignment=Qt.AlignRight)

    def upload_profile_pic(self):
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Profile Picture", "", 
                "Image Files (*.png *.jpg *.jpeg)"
            )
            
            if not path:
                return
                
            with open(path, 'rb') as f:
                files = {'file': (os.path.basename(path), f, 'image/jpeg')}
                
                progress = QProgressDialog("Uploading profile picture...", None, 0, 0, self)
                progress.setWindowModality(Qt.WindowModal)
                progress.show()
                
                try:
                    response = requests.post(
                        f'http://193.36.85.114:8000/upload_profile/{self.username}',
                        files=files,
                        timeout=10
                    )
                    
                    if response.status_code == 200:

                        profile_url = f'http://193.36.85.114:8000/profile/{self.username}'
                        success = db_handler.update_profile_pic(self.username, profile_url)
                        
                        if success:
  
                            pixmap = QPixmap(path)
                            if not pixmap.isNull():
                                circular_pixmap = self.create_circular_pixmap(pixmap)
                                self.picLabel.setPixmap(circular_pixmap)
                                QMessageBox.information(self, "Success", "Profile picture updated successfully!")
                            else:
                                raise Exception("Failed to load image")
                        else:
                            raise Exception("Failed to update database")
                    else:
                        error_msg = response.json().get('error', 'Unknown error')
                        raise Exception(f"Server error: {error_msg}")
                        
                except requests.RequestException as e:
                    QMessageBox.warning(self, "Connection Error", 
                        f"Failed to connect to server: {str(e)}\nPlease check your internet connection." , print(str(e)))
                        
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to update profile picture: {str(e)}")
                finally:
                    progress.close()
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")
    def create_circular_pixmap(self, pixmap):
        target = QPixmap(100, 100)
        target.fill(Qt.transparent)
        
        painter = QPainter(target)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        path = QPainterPath()
        path.addEllipse(0, 0, 100, 100)
        painter.setClipPath(path)
        
        scaled_pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        painter.drawPixmap(0, 0, scaled_pixmap)
        

        pen = QPen(Qt.white, 2)
        painter.setPen(pen)
        painter.drawEllipse(1, 1, 98, 98)
        
        painter.end()
        return target

    def change_password(self):
        dialog = ChangePasswordDialog(self.username, self)
        if dialog.exec_() == QDialog.Accepted:
            QMessageBox.information(self, "Success", "Password changed successfully.")
    def logout(self):
        reply = QMessageBox.question(
            self, 
            'Log Out',
            'Are you sure you want to log out?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
    
        if reply == QMessageBox.Yes:
            self.close()
            self.logout_requested.emit()
            self.accept()

# ------------------ ChangePasswordDialog ------------------ #

class ChangePasswordDialog(QDialog):
    def __init__(self, username, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("Change Password")
        self.setWindowIcon(QIcon(icon_path("V-icon.png")))
        self.setFixedSize(350, 450)

        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y:0, x2:1, y:1, stop:0 #9370DB, stop:1 #6495ED);
            }
            QLabel, QLineEdit { color: white; font-size: 14px; }
            QLineEdit {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
                color: black;
            }
            QPushButton {
                background-color: transparent;
                border: 1px solid white;
                border-radius: 4px;
                padding: 8px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        password_section = QVBoxLayout()
        password_section.setSpacing(10)

        self.currentPwdEdit = QLineEdit()
        self.currentPwdEdit.setPlaceholderText("Current Password")
        self.currentPwdEdit.setEchoMode(QLineEdit.Password)
        password_section.addWidget(self.currentPwdEdit)

        self.newPwdEdit = QLineEdit()
        self.newPwdEdit.setPlaceholderText("New Password")
        self.newPwdEdit.setEchoMode(QLineEdit.Password)
        password_section.addWidget(self.newPwdEdit)

        self.confirmPwdEdit = QLineEdit()
        self.confirmPwdEdit.setPlaceholderText("Confirm New Password")
        self.confirmPwdEdit.setEchoMode(QLineEdit.Password)
        password_section.addWidget(self.confirmPwdEdit)

        self.changeBtn = QPushButton("Change Password")
        self.changeBtn.clicked.connect(self.attempt_change)
        password_section.addWidget(self.changeBtn)

        layout.addLayout(password_section)
        captcha_section = QVBoxLayout()
        captcha_section.setSpacing(10)

        self.captchaWidget = CaptchaWidget()
        captcha_section.addWidget(self.captchaWidget, alignment=Qt.AlignCenter)

        self.captchaInput = QLineEdit()
        self.captchaInput.setPlaceholderText("Enter captcha")
        captcha_section.addWidget(self.captchaInput)

        layout.addLayout(captcha_section)
        self.statusLabel = QLabel("")
        layout.addWidget(self.statusLabel)
        layout.addStretch(1)
        logo_section = QVBoxLayout()
        logo_section.setSpacing(5)

        self.producer_icon = QLabel()
        self.producer_icon.setPixmap(QPixmap(icon_path("Mortal_ico_transparent.png")).scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.producer_icon.setFixedSize(50, 50)
        self.producer_icon.setScaledContents(True)
        logo_section.addWidget(self.producer_icon, alignment=Qt.AlignCenter)

        self.producer_label = QLabel("By Mortal Co")
        self.producer_label.setStyleSheet("color: white; font-size: 12px;")
        logo_section.addWidget(self.producer_label, alignment=Qt.AlignCenter)

        layout.addLayout(logo_section)

    def attempt_change(self):
        current_pwd = self.currentPwdEdit.text().strip()
        new_pwd = self.newPwdEdit.text().strip()
        confirm_pwd = self.confirmPwdEdit.text().strip()
        captcha = self.captchaInput.text().strip()

        if not self.captchaWidget.verify(captcha):
            self.statusLabel.setText("Invalid captcha code.")
            self.captchaWidget.generateCaptcha()
            self.captchaInput.clear()
            return

        if not current_pwd or not new_pwd or not confirm_pwd:
            self.statusLabel.setText("Please fill all fields.")
            return

        if new_pwd != confirm_pwd:
            self.statusLabel.setText("New passwords do not match.")
            return

        user = db_handler.get_user(self.username)
        if user:
            salt = user["salt"]
            current_hash = hashlib.sha256((current_pwd + salt).encode()).hexdigest()
            if current_hash == user["password_hash"]:
                new_salt = os.urandom(32).hex()
                new_password_hash = hashlib.sha256((new_pwd + new_salt).encode()).hexdigest()
                cursor = db_handler.connection.cursor()
                query = "UPDATE users SET salt = %s, password_hash = %s WHERE username = %s"
                try:
                    cursor.execute(query, (new_salt, new_password_hash, self.username))
                    db_handler.connection.commit()
                    self.accept()
                except Error as e:
                    print("Error updating password:", e)
                    self.statusLabel.setText("Failed to change password.")
                finally:
                    cursor.close()
            else:
                self.statusLabel.setText("Current password is incorrect.")
        else:
            self.statusLabel.setText("User not found.")

        self.captchaWidget.generateCaptcha()
        self.captchaInput.clear()

# ------------------ Main ------------------ #
def main():
    app = QApplication(sys.argv)
    login_dialog = LoginDialog()
    if login_dialog.exec_() == QDialog.Accepted:
        current_user = login_dialog.usernameEdit.text().strip()
        player = MusicPlayer()
        print(f"Current thread: {QThread.currentThread()}")
        player.current_user = current_user
        user = db_handler.get_user(current_user)
        profile_pic = user.get("profile_pic") if user else None
        player.profileWidget.update_profile(current_user, profile_pic)
        player.show()
        sys.exit(app.exec_())
    else:
        sys.exit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    login_dialog = LoginDialog()
    
    if login_dialog.exec_() == QDialog.Accepted:
        player = MusicPlayer()
        
        if hasattr(login_dialog, 'is_offline') and login_dialog.is_offline:
            username = getattr(login_dialog, 'last_username', "Offline User")
            player.current_user = username
            cache_path = os.path.join(CACHE_DIR, f"{username}.jpg")
            if os.path.exists(cache_path):
                player.profileWidget.update_profile(username, cache_path)
            else:
                player.profileWidget.update_profile(username, None)
                
            player.btnMusicLibrary.setEnabled(False)
            player.btnMusicLibrary.setToolTip("Online Library (Disabled in Offline Mode)")
            player.btnMusicLibrary.setStyleSheet("QToolButton { opacity: 0.5; }")
        else:
            player.current_user = login_dialog.username
            user = db_handler.get_user(player.current_user)
            profile_pic = user.get("profile_pic") if user else None
            player.profileWidget.update_profile(player.current_user, profile_pic)
            
        player.show()
        sys.exit(app.exec_())
    else:
        sys.exit()

# TODO make sync songs button
# TODO make sync not blow away tags
# TODO make removing tags apply
# TODO rename tags
# TODO purge unused tags
# TODO fully implement logging

import os
import sys
import traceback
from PyQt6 import QtWidgets as qtw, QtCore as qtc, QtGui as qtg
from spotipy.oauth2 import SpotifyOAuth
import spotipy
import logging
import random
import sqlite3 as sl
from openai import OpenAI
import requests

CID = os.environ["SPOTIFY_CLIENT_ID"]
CS = os.environ["SPOTIFY_CLIENT_SECRET"]
AI= os.environ["OPENAI_SECRET_KEY"]

NAME = "SpotiBrarian"
VERSION = "0.0.0"
SCOPE = 'user-library-read playlist-modify-public user-read-playback-state user-modify-playback-state'
URL = "http://localhost:8888/callback"
PROMPT = {
    'role': 'system',
    'content': f"""Fully describe the song using one-word tags. Include lyrics language, or 'lyricless'. Respond comma separated."""
}

log = logging.getLogger("Spotibrarian")
hdlr = logging.StreamHandler()
log.addHandler(hdlr)
log.setLevel(logging.DEBUG)

class TWI(qtw.QTreeWidgetItem):
    def __init__(self, vals:list):
        super().__init__([str(v) for v in vals])
    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        try:
            return float(self.text(col)) < float(other.text(col))
        except:
            return super().__lt__(other)

class Library:
    def __init__(self):
        log.info("Authenticating Spotify...")
        self.sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(scope=SCOPE, client_id=CID, client_secret=CS, redirect_uri=URL))
        log.info("Authenticating OpenAI...")
        self.ai = OpenAI(api_key=AI)
        log.info(f"Connecting to DB {self.user_id}.db...")
        self.db = sl.connect(f"{self.user_id}.db")
        self.cur = self.db.cursor()

        self.cur.execute('''CREATE TABLE IF NOT EXISTS tracks 
        (uri TEXT PRIMARY KEY, url TEXT, name TEXT, artist TEXT, album_name TEXT, duration INTEGER, artwork TEXT)''')

        self.cur.execute('''CREATE TABLE IF NOT EXISTS playlists 
                             (id TEXT NOT NULL PRIMARY KEY, string TEXT, query TEXT)''')

        self.db.commit()
        log.info(f"Library Init Complete.")

    @property
    def user_id(self):
        return self.sp.current_user()['id']

    @property
    def user_name(self):
        return self.sp.current_user()['display_name']

    @property
    def num_tracks(self):
        return self.db.execute("""SELECT COUNT(*) FROM tracks""").fetchone()[0]

    @property
    def playlists(self):
        return self.db.execute("""SELECT * FROM playlists""").fetchall()

    def get_now_playing(self):
        return self.sp.currently_playing()['item']['uri']

    def _add_tracks(self, tracks):
        for track in tracks:
            track = track['track']
            self.cur.execute('''INSERT INTO tracks 
                    (uri, url, name, artist, album_name, duration, artwork) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                             (track['uri'],
                              track['external_urls']['spotify'],
                              track['name'],
                              ', '.join([t['name'] for t in track['artists']]),
                              track['album']['name'],
                              track['duration_ms'],
                              track['album']['images'][0]['url']))
        self.db.commit()

    def fetch_track_library(self):
        log.debug(f"Fetching tracks...")
        self.cur.execute('''DELETE FROM tracks''')
        results = self.sp.current_user_saved_tracks()
        self._add_tracks(results['items'])
        while results['next']:
            log.debug(f"... {self.num_tracks}...")
            results = self.sp.next(results)
            self._add_tracks(results['items'])

        log.info(f"fetched {self.num_tracks} tracks")
        self.db.commit()

    def set_tag(self, uri, tag, value):
        self.create_tag(tag)
        self.cur.execute(f"UPDATE tracks SET '{tag}' = {value} WHERE uri = '{uri}'")
        self.db.commit()

    def set_tags(self, uri, tags):
        for tag in tags:
            self.set_tag(uri, tag, 1)

    def create_tag(self, tag):
        if tag in self.tags:
            return
        self.cur.execute("ALTER TABLE tracks ADD COLUMN '%s' INTEGER NOT NULL DEFAULT 0" % tag)
        self.db.commit()

    def delete_tag(self, tag):
        if tag not in self.tags:
            return
        self.cur.execute("ALTER TABLE tracks DROP COLUMN '%s'" % tag)
        self.db.commit()

    def tag_use_count(self, tag):
        return len(self.db.execute(f"""SELECT uri FROM tracks WHERE ("{tag}")""").fetchall())

    def drop_tag(self, tag):
        if tag in self.tags:
            self.cur.execute(f"ALTER TABLE tracks DROP COLUMN '{tag}'")
        self.db.commit()

    def get_random_track(self):
        return self.cur.execute('''SELECT * FROM tracks ORDER BY RANDOM() LIMIT 1''').fetchone()[0]

    def get_track_info(self, uri):
        t = self.cur.execute(f"SELECT * FROM tracks WHERE uri = '{uri}'").fetchone()
        return {
            'uri': t[0],
            'url': t[1],
            'name': t[2],
            'artist': t[3],
            'album_name': t[4],
            'duration': t[5],
            'artwork': t[6],
        }

    def get_track_tags(self, uri):
        t = self.cur.execute(f"SELECT * FROM tracks WHERE uri = '{uri}'").fetchone()
        return [name for name, tag in zip (self.tags, t[7:]) if tag]

    def search_tracks(self, like_query="", tag_query=""):
        try:
            like_query = like_query.strip().lower()
            tag_query = tag_query.strip().lower()
            return self.cur.execute(f"SELECT * FROM tracks WHERE ((uri LIKE ? OR url LIKE ? OR name LIKE ? OR artist LIKE ? OR album_name LIKE ?){f'AND ({tag_query})' if tag_query else ''})", ['%' + like_query + '%'] * 5).fetchall()
        except:
            print(traceback.format_exc())
            return []



    def filter_tags(self, tag_query):
        return self.cur.execute(f"SELECT uri FROM tracks WHERE {tag_query}").fetchall()


    def play_tracks(self, uris):
        try:
            if uris:
                self.sp.start_playback(uris=uris)
        except spotipy.exceptions.SpotifyException as e:
            log.warning('No active device, or other Spotify error!', exc_info=e)

    @property
    def tags(self):
        tags = [col[1] for col in self.cur.execute('''PRAGMA table_info(tracks)''')]
        if len(tags) > 7:
            return tags[7:]
        else:
            return []

    def get_track_tags(self, uri):
        ret = []
        tags = self.cur.execute(f"SELECT * FROM tracks WHERE uri = '{uri}'").fetchone()
        if not tags or len(tags) < 7:
            return []
        for tag, val in zip(self.tags, tags[7:]):
            if val:
                ret.append(tag)
        return ret

    def fetch_playlists(self) -> dict:
        ret = {}
        results = self.sp.current_user_playlists()
        for playlist in results['items']:
            ret[playlist['id']] = playlist['name']
        while results['next']:
            log.debug(f"... {len(self.playlists)} Playlists...")
            results = self.sp.next(results)
            for playlist in results['items']:
                ret[playlist['id']] = playlist['name']

        return ret

    def unfollow_playlist(self, playlist):
        log.debug(f"Unfollow Playlist {playlist}...")
        self.sp.current_user_unfollow_playlist(playlist)

    def unfollow_playlists(self, playlists):
        if isinstance(playlists, list):
            for item in playlists:
                self.unfollow_playlist(item)
        else:
            for key in playlists.keys():
                self.unfollow_playlist(key)

    def ai_tag_multiple(self, uris):
        for uri in uris:
            try:
                self.ai_tag(uri)
            except:
                print(traceback.format_exc())

    def ai_tag(self, uri):
        info = self.get_track_info(uri)
        song = f"{info['artist']} - {info['name']}"
        resp = self.ai.chat.completions.create(
            model = "gpt-4o",
            messages = [PROMPT, {'role':'user','content':song}]
            # max_tokens=150,  # Adjust the token limit as per your needs
            # temperature=0.7  # Adjust the creativity level
        )
        tags = [t.strip().lower() for t in resp.dict()['choices'][0]['message']['content'].split(",")]
        print(song, tags)# " | ".join([f"{t}:{r}" for t, r in zip(self.tags,resp.dict()['choices'][0]['message']['content'])]))
        self.set_tags(uri, tags)

    def apply_playlists(self):
        names = [p[0] for p in self.playlists]
        for k, v in self.fetch_playlists().items():
            if v in names:
                self.unfollow_playlist(k)
        for name, title, query in self.playlists:
            while True:
                try:
                    log.debug(f"Create playlist {name}")
                    pl = self.sp.user_playlist_create(self.user_id, name, public=False, description=title or query)['uri']
                    break
                except Exception as e:
                    log.debug("Retry:", exc_info=e)
            log.debug(f"ID {pl}")
            songs = [s[0] for s in self.search_tracks(tag_query = query)]
            random.shuffle(songs)
            while len(songs) > 50:
                log.debug(f"{len(songs)} songs left...")
                try:
                    self.sp.playlist_add_items(pl, songs[:50])
                    songs = songs[50:]
                except Exception as e:
                    log.debug("Retry:", exc_info=e)
            while songs:
                log.debug(f"Adding {len(songs)}")
                try:
                    self.sp.playlist_add_items(pl, songs[:50])
                    songs = []
                except Exception as e:
                    log.debug("Retry:", exc_info=e)
        log.info(f"Created {len(self.playlists)} playlists.")

    def add_playlist(self, name, desc, query):
        self.cur.execute(f"""INSERT OR REPLACE INTO playlists VALUES ("{name}", "{desc}", "{query}")""")
        self.db.commit()


class RequestWorker(qtc.QObject):
    signalReady = qtc.pyqtSignal(bytes)
    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        self.signalReady.emit(requests.get(self.url).content)

class Spotibrarian(qtw.QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(800, 600)
        self.lib = Library()
        self.setWindowTitle(NAME + " " + VERSION)
        self.setWindowIcon(self.style().standardIcon(qtw.QStyle.StandardPixmap.SP_FileDialogStart))
        w = qtw.QWidget()
        top_l = qtw.QHBoxLayout(w)
        top_l.setContentsMargins(0,0,0,0)
        tab = qtw.QTabWidget()
        self.setCentralWidget(w)

        song_w = qtw.QWidget()
        tab.addTab(song_w, "Songs")
        song_l = qtw.QGridLayout(song_w)
        song_l.setColumnStretch(0, 2)
        song_l.setColumnStretch(1, 1)

        pl_w = qtw.QWidget()
        tab.addTab(pl_w, "Playlists")
        pl_l = qtw.QGridLayout(pl_w)

        self.playlist_table = qtw.QTreeWidget()
        self.playlist_table.setSortingEnabled(True)
        self.playlist_table.setAlternatingRowColors(True)
        self.playlist_table.setRootIsDecorated(False)
        self.playlist_table.setHeaderLabels(["Name", "Description", "Tag Query"])
        self.playlist_table.itemDoubleClicked.connect(self.edit_playlist)
        pb_new_playlist = qtw.QPushButton("New Playlist")
        pb_new_playlist.clicked.connect(lambda: self.edit_playlist())
        pb_apply_playlists = qtw.QPushButton("Apply To Spotify")
        pb_apply_playlists.clicked.connect(self.lib.apply_playlists)

        self.tag_query = qtw.QLineEdit()
        self.tag_query.setPlaceholderText("Tag Query")
        self.tag_query.textChanged.connect(self.update_page)

        self.like_query = qtw.QLineEdit()
        self.like_query.setPlaceholderText("Search Query")
        self.like_query.textChanged.connect(self.update_page)

        self.tag_table = qtw.QTreeWidget()
        self.tag_table.setSortingEnabled(True)
        self.tag_table.setAlternatingRowColors(True)
        self.tag_table.setRootIsDecorated(False)
        self.tag_table.setHeaderLabels(["Tag Name", "Count"])
        self.tag_table.sortByColumn(1, qtc.Qt.SortOrder.DescendingOrder)
        self.tag_table.setFixedWidth(180)

        self.song_table = qtw.QTreeWidget()
        self.song_table.setSortingEnabled(True)
        self.song_table.setAlternatingRowColors(True)
        self.song_table.setColumnHidden(0, True)
        self.song_table.setRootIsDecorated(False)
        self.song_table.setHeaderLabels(["UID", "Name", "Artist", "Album", "Tag Count"])
        self.song_table.selectionModel().selectionChanged.connect(self.update_song_info)
        pb_auto = qtw.QPushButton("Auto-Tag All")
        pb_auto.clicked.connect(self.auto_all)

        self.song_im = qtw.QLabel()
        self.song_im.setFixedSize(256, 256)
        self.song_im_px = qtg.QPixmap(256, 256)
        self.song_im_px.fill(qtg.QColor("#1010D0"))
        self.song_im.setPixmap(self.song_im_px)
        self.song_label = qtw.QLabel("Select a song.")
        fnt = self.song_label.font()
        fnt.setBold(True)
        self.song_label.setFont(fnt)
        self.song_tags = qtw.QPlainTextEdit()
        self.song_tags.setPlaceholderText("Set tags here...")
        self.pb_apply_tags = qtw.QPushButton("Apply")
        self.pb_apply_tags.clicked.connect(self.apply_tags)

        song_l.addWidget(self.tag_query, 0,0)
        song_l.addWidget(self.like_query, 1,0)
        song_l.addWidget(self.song_table, 2,0, 3, 1)
        song_l.addWidget(pb_auto, 5,0)

        song_l.addWidget(self.song_im, 0, 1, 3, 1)
        song_l.addWidget(self.song_label, 3, 1)
        song_l.addWidget(self.song_tags, 4, 1)
        song_l.addWidget(self.pb_apply_tags, 5, 1)

        pl_l.addWidget(self.playlist_table, 0, 1)
        pl_l.addWidget(pb_new_playlist, 1, 1)
        pl_l.addWidget(pb_apply_playlists, 2, 1)

        top_l.addWidget(self.tag_table)
        top_l.addWidget(tab)
        self._image_fetch_uri = ""
        self._image_cache = {}

        self.show()
        self.update_page()
        self.update_tag_table()
        self.update_song_info()
        self.update_playlists()

    def edit_playlist(self, item = None):
        if item is None:
            name = ""
            desc = ""
            query = ""
        else:
            name = item.text(0)
            desc = item.text(1)
            query = item.text(2)
        dialog = qtw.QDialog()
        d_l = qtw.QVBoxLayout(dialog)

        le_name = qtw.QLineEdit()
        le_name.setText(name)
        le_name.setPlaceholderText("Playlist Name")

        le_desc = qtw.QLineEdit()
        le_desc.setText(desc)
        le_desc.setPlaceholderText("Playlist Description (defaluts to query)")

        le_query = qtw.QLineEdit()
        le_query.setText(query)
        le_query.setPlaceholderText("Playlist Tag Query")

        accept = []

        pb_ok = qtw.QPushButton("Accept")
        pb_ok.clicked.connect(lambda:accept.append(1))
        pb_ok.clicked.connect(dialog.close)
        pb_cancel = qtw.QPushButton("Cancel")
        pb_cancel.clicked.connect(dialog.close)

        d_l.addWidget(le_name)
        d_l.addWidget(le_desc)
        d_l.addWidget(le_query)
        d_l.addWidget(pb_ok)
        d_l.addWidget(pb_cancel)

        dialog.exec()
        if accept:
            self.lib.add_playlist(le_name.text().strip(), le_desc.text().strip(), le_query.text().strip())
        self.update_playlists()

    def update_playlists(self):
        self.playlist_table.clear()
        for vals in self.lib.playlists:
            self.playlist_table.addTopLevelItem(TWI(vals))
    def update_song_info(self):
        if self.song_table.selectedItems():
            item = self.song_table.selectedItems()[0]
            uri = item.text(0)
            if uri in self._image_cache:
                self.song_im.setPixmap(self._image_cache[uri])
            else:
                self.song_im_px = qtg.QPixmap(256, 256)
                self.song_im_px.fill(qtg.QColor("#1010D0"))
                self.song_im.setPixmap(self.song_im_px)
                if self._image_fetch_uri == "":
                    self._image_fetch_uri = uri
                    self.im_fetch_thread = qtc.QThread()
                    self.im_fetch_worker = RequestWorker(self.lib.get_track_info(uri)['artwork'])
                    self.im_fetch_worker.signalReady.connect(self.update_song_image)
                    self.im_fetch_worker.moveToThread(self.im_fetch_thread)
                    self.im_fetch_thread.started.connect(self.im_fetch_worker.run)
                    self.im_fetch_thread.start()

            name = item.text(1)
            artist = item.text(2)
            album = item.text(3)
            tags = self.lib.get_track_tags(uri)
            self.song_label.setText("\n".join([t if len(t) < 30 else t[:28]+"..." for t in [name, artist, album]]))
            self.song_tags.setPlainText(', '.join(tags))
            self.song_tags.setEnabled(True)
            self.pb_apply_tags.setEnabled(True)
        else:
            self.song_label.setText("Select a song.")
            self.song_tags.setPlainText('')
            self.song_tags.setEnabled(False)
            self.pb_apply_tags.setEnabled(False)

    def update_song_image(self, im_bytes):
        self.im_fetch_thread.quit()
        self.im_fetch_thread.wait()
        self._im = qtg.QImage()
        self._im.loadFromData(im_bytes)
        self._image_cache[self._image_fetch_uri] = qtg.QPixmap.fromImage(self._im.scaled(256, 256))
        if self.song_table.selectedItems():
            item = self.song_table.selectedItems()[0]
            uri = item.text(0)
            if uri == self._image_fetch_uri:
                self.song_im.setPixmap(self._image_cache[uri])
        self._image_fetch_uri = ""

    def apply_tags(self):
        item = self.song_table.selectedItems()[0]
        uri = item.text(0)
        tags = self.song_tags.toPlainText().split(",")
        tags = [''.join([c if c.isalnum() else '_' for c in tag.strip().lower()]) for tag in tags]
        self.lib.set_tags(uri, tags)
        self.update_tag_table()
        self.update_page()


    def update_tag_table(self):
        self.tag_table.clear()
        for tag in self.lib.tags:
            twi = TWI([tag, self.lib.tag_use_count(tag)])
            self.tag_table.addTopLevelItem(twi)


    def update_page(self):
        self.song_table.clear()
        for track in self.lib.search_tracks(self.like_query.text(), self.tag_query.text()):
            tag_count = sum(track[7:])
            twi = TWI([track[0], track[2], track[3], track[4], str(tag_count)])
            self.song_table.addTopLevelItem(twi)

    def auto_all(self):
        dialog = qtw.QDialog()
        _l = qtw.QVBoxLayout(dialog)
        text = qtw.QLabel()
        _l.addWidget(text)
        pbar = qtw.QProgressBar()
        _l.addWidget(pbar)
        pb_stop= qtw.QPushButton("stop")
        pb_stop.clicked.connect(dialog.close)
        _l.addWidget(pb_stop)
        running = True
        def dialog_work():
            nonlocal running
            tracks = self.lib.search_tracks()
            print(len(tracks))
            pbar.setMaximum(len(tracks))
            for i, track in enumerate(tracks):
                tag_count = sum(track[7:])
                if not tag_count:
                    text.setText(f"Track {i+1} out of {len(tracks)}:\n {track[3]} - {track[2]}")
                    pbar.setValue(i)
                    qtw.QApplication.processEvents()
                    self.lib.ai_tag(track[0])
                if not dialog.isVisible():
                    break
            dialog.close()

        qtc.QTimer.singleShot(10, dialog_work)
        dialog.exec()
        self.update_page()


if __name__ == "__main__":
    # library = Library()
    # library.apply_playlists()
    # for tag in library.tags:
    #     library.delete_tag(tag)
    # library.match_tags_for_songs([
    #     "spotify:track:5Fu8xKQQ1tPbisztwwW7P5",
    #     "spotify:track:3KpHWzyAKyVlg6LJsEemDT",
    #     "spotify:track:7e5Bewjrz0NJ2znVAR8GBi",
    #     "spotify:track:0HLnHABT8i0ofNlMEMaTLb",
    #     "spotify:track:5VwILdK8UyRMtQtsPKxP3X",
    #     "spotify:track:0OCHK5deaKzLGPORrT4br1",
    #     "spotify:track:3nhH6dc8okYmPb1RAxZoCJ",
    #     "spotify:track:2Kh2C5PbekvEilbCOTzTt1",
    #     "spotify:track:7rTMCY2QFWN8iHD1JjCWye",
    #     "spotify:track:2A32JdgX32o5yUloJMq4Q3"
    # ])
    # library.fetch_track_library()
    # print(library.num_tracks)
    # # library.automatic_genre_sort()
    app = qtw.QApplication(sys.argv)
    mw = Spotibrarian()
    app.exec()

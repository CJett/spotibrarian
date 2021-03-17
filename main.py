import urllib.request

import json
import os
import pandas as pd
import spotipy
import sys
from PyQt5 import QtWidgets as qtw, QtGui as qtg, QtCore as qtc, uic
from spotipy.oauth2 import SpotifyOAuth


def get_artist_names(artists):
    return [a['name'] for a in artists]


def update_track(library, track):
    if track['uri'] not in library:
        new_data = {
            'name': track['name'],
            'tags': [],
            'artists': get_artist_names(track['artists']),
            'album_name': track['album']['name'],
            'album_art': track['album']['images'][0]['url'],
            'preview_url': track['preview_url']
        }
        library.update({track['uri']: new_data})


class Spotibrarian:
    def __init__(self):
        self._ui = uic.loadUi('ui/main.ui')
        scope = 'user-library-read playlist-modify-public'
        cid = "72e180d9f7a54590a1214f158cb264b5"
        cs = "20f168e6f0b94f098c495f6bca4df90d"
        self._sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope, client_id=cid, client_secret=cs,
                                                             redirect_uri="http://localhost:8888/callback"))
        self._init_library()
        self._ui.pbUpdate.clicked.connect(self.update_library)
        self._title = f"{self._sp.current_user()['display_name']}'s Spotify Library: "
        self._ui.twSongs.itemSelectionChanged.connect(self._update_song_info)
        self._ui.lwTags.itemDoubleClicked.connect(self._dclick_add_tag)
        self._current_song = None
        self._ui.show()
        self._ui.pbExport.clicked.connect(self._export_library)
        self._library_update_flag = False
        self.update_library()

    def _dclick_add_tag(self, item):
        self._ui.ptTags.appendPlainText(f"{item.text()},")

    def _export_library(self):
        try:
            if len(self._library):

                fname = qtw.QFileDialog.getSaveFileName(None, 'Save CSV', )[0]
                print(fname)
                if len(fname):
                    try:
                        df = pd.DataFrame(self._library).transpose()
                        print(df)
                        df.to_csv(fname)
                    except Exception as E:
                        msg = qtw.QMessageBox()
                        msg.setWindowTitle('Failed to Export to CSV')
                        msg.setText(str(E))
                        msg.exec_()
        except Exception as E:
            print(E)

    def _init_library(self):
        self._library = {}
        self._playlists = {}
        self._tags = []
        if os.path.exists('library.json'):
            with open('library.json', 'r') as f:
                read_dict = json.load(f)
            self._library = read_dict['library']
            self._playlists = read_dict['playlists']
            self._tags = read_dict['tags']

    def update_library(self):
        song_list = []
        results = self._sp.current_user_saved_tracks()
        for item in results['items']:
            update_track(self._library, item['track'])
            song_list.append(item['track']['uri'])
        while results['next']:
            results = self._sp.next(results)
            for item in results['items']:
                update_track(self._library, item['track'])
                song_list.append(item['track']['uri'])
        poplist = []
        for k in self._library.keys():
            if k not in song_list:
                poplist.append(k)
        for k in poplist:
            self._library.pop(k)
        self._update_library_view()
        self._update_tags()
        self._ui.setWindowTitle(self._title + f" {len(self._library)} songs")

    def _update_tags(self):
        self._tags = []
        for v in self._library.values():
            for t in v['tags']:
                if t not in self._tags and t != '':
                    self._tags.append(t)
        self._ui.lwTags.clear()
        self._ui.lwTags.addItems(self._tags)

    def _update_library_view(self):
        self._library_update_flag = True
        row = -1
        if self._ui.twSongs.currentItem() is not None:
            row = self._ui.twSongs.indexOfTopLevelItem(self._ui.twSongs.currentItem())
        songs = self._ui.twSongs
        while songs.topLevelItemCount():
            songs.takeTopLevelItem(0)
        for uri, data in self._library.items():
            songs.addTopLevelItem(qtw.QTreeWidgetItem([data['name'],
                                                       ', '.join(data['artists']),
                                                       data['album_name'],
                                                       uri,
                                                       ', '.join(data['tags'])]))
            # self._ui.update()
        self._save_library()
        if row > -1:
            if row < self._ui.twSongs.topLevelItemCount():
                self._ui.twSongs.topLevelItem(row).setSelected(True)
                self._ui.twSongs.setCurrentItem(self._ui.twSongs.topLevelItem(row))
                self._ui.twSongs.scrollToItem(self._ui.twSongs.topLevelItem(row))
        self._library_update_flag = False

    def _save_library(self):
        dump_dict = {
            'library': self._library,
            'playlists': self._playlists,
            'tags': self._tags
        }
        with open('library.json', 'w') as f:
            json.dump(dump_dict, f)

    def _update_song_info(self):
        if not self._library_update_flag:
            try:
                if self._current_song is not None:
                    if self._current_song in self._library:
                        self._library[self._current_song]['tags'] = sorted(list(set([tag.strip() for tag in str(
                            self._ui.ptTags.toPlainText()).replace('\n', '').replace('\t', '').split(',') if
                                                                                     tag.strip() != ''])))
                        self._update_library_view()
                        self._update_tags()
                if self._ui.twSongs.currentItem() is not None:
                    uri = self._ui.twSongs.currentItem().text(3)
                    self._current_song = uri
                    song = self._library[uri]
                    self._ui.lbSong.setText(song['name'])
                    self._ui.lbArtist.setText(', '.join(song['artists']))
                    self._ui.lbAlbum.setText(song['album_name'])
                    self._ui.lbSample.setText(f"<a href=\"{song['preview_url']}\">Play Sample</a>")
                    self._ui.ptTags.clear()
                    self._ui.ptTags.insertPlainText(', '.join(song['tags']))
                    image = qtg.QImage()
                    image.loadFromData(urllib.request.urlopen(song['album_art']).read())
                    self._pixmap = qtg.QPixmap(image).scaled(128, 128, qtc.Qt.KeepAspectRatio)
                    self._ui.albumArt.setPixmap(self._pixmap)
                else:
                    self._current_song = None
                    self._ui.lbSong.setText('Song Title')
                    self._ui.lbArtist.setText('Artists')
                    self._ui.lbAlbum.setText('Album')
                    self._ui.lbSample.setText(f"Play Sample")
                    self._ui.ptTags.clear()
                    image = qtg.QImage()
                    image.loadFromData(urllib.request.urlopen(
                        "https://www.solidbackgrounds.com/images/950x350/950x350-arsenic-solid-color-background.jpg").read())
                    self._pixmap = qtg.QPixmap(image).scaled(128, 128, qtc.Qt.KeepAspectRatio)
                    self._ui.albumArt.setPixmap(self._pixmap)

            except Exception as E:
                print(E)
            pass
            # self._ui.lbArtist.


if __name__ == "__main__":
    app = qtw.QApplication(sys.argv)  # Create an instance of QtWidgets.QApplication
    window = Spotibrarian()  # Create an instance of our class
    app.exec_()  # Start the application

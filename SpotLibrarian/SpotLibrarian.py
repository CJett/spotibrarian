import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pandas as pd
import urllib.request
import json
from PyQt5 import QtWidgets as qtw, QtGui as qtg, QtCore as qtc, uic


class SpotLibrarian:
    def __init__(self, client_secret, library_path='library.json'):
        self._library_path = library_path
        self._ui = uic.loadUi('ui/main.ui')
        auth_manager=SpotifyOAuth(scope='user-library-read playlist-modify-public',
                                  client_id='72e180d9f7a54590a1214f158cb264b5',
                                  client_secret=client_secret,
                                  redirect_uri='http://localhost:8888/callback')
        self._sp = spotipy.Spotify(auth_manager=auth_manager)
        self._title = f"{self._sp.current_user()['display_name']}'s Spotify Library: "
        self._init_library()
        self._ui.pbUpdate.clicked.connect(self.update_library)
        self._ui.twSongs.itemSelectionChanged.connect(self._update_song_info)
        self._ui.lwTags.itemDoubleClicked.connect(self._dclick_add_tag)
        self._current_song = None
        self._ui.show()
        self._ui.pbExport.clicked.connect(self._export_library)
        self._library_update_flag = False
        self._ui.leFilter.textChanged.connect(self._update_library_view)


    def _dclick_add_tag(self, item):
        t = item.text()
        t = t[0:t.rfind('(')-1]
        self._ui.ptTags.appendPlainText(f",{t}")


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
        except Exception as e:
            print(e)


    def _init_library(self):
        self._library = {}
        self._playlists = {}
        self._tags = []

        with open(self._library_path, 'r') as f:
            library_json = json.load(f)
        self._library = library_json['library']
        self._playlists = library_json['playlists']
        self._tags = library_json['tags']

        self._update_library_view()
        self._update_tags()
        self._ui.setWindowTitle(self._title + f" {len(self._library)} songs")


    def update_track(library, track):
        if track['uri'] not in library:
            new_data = {
                'name': track['name'],
                'tags': [],
                'artists': [ a['name'] for a in track['artists'] ],
                'album_name': track['album']['name'],
                'album_art': track['album']['images'][0]['url'],
                'preview_url': track['preview_url']
            }
            library.update({track['uri']: new_data})


    def update_library(self):
        song_list = []
        results = self._sp.current_user_saved_tracks()
        for item in results['items']:
            self.update_track(self._library, item['track'])
            song_list.append(item['track']['uri'])

        while results['next']:
            results = self._sp.next(results)
            for item in results['items']:
                self.update_track(self._library, item['track'])
                song_list.append(item['track']['uri'])

        pop_list = []
        for k in self._library.keys():
            if k not in song_list:
                pop_list.append(k)

        for k in pop_list:
            self._library.pop(k)

        self._update_library_view()
        self._update_tags()
        self._ui.setWindowTitle(self._title + f" {len(self._library)} songs")


    def _update_tags(self):
        self._tags = []
        all_tags = []
        for v in self._library.values():
            for t in v['tags']:
                if t != '':
                    all_tags.append(t)

        all_tags = sorted(all_tags)
        for t in all_tags:
            if t not in self._tags:
                self._tags.append(t)

        tag_count = [all_tags.count(t) for t in self._tags]

        self._ui.lwTags.clear()
        self._ui.lwTags.addItems([f"{t} ({c})" for t, c in zip(self._tags, tag_count)])


    def _update_library_view(self):
        self._library_update_flag = True
        row = -1
        if self._ui.twSongs.currentItem() is not None:
            row = self._ui.twSongs.indexOfTopLevelItem(self._ui.twSongs.currentItem())

        songs = self._ui.twSongs
        while songs.topLevelItemCount():
            songs.takeTopLevelItem(0)

        ft = self._ui.leFilter.text().strip().lower()
        if len(ft) < 2:
            ft = ''

        ft = [f.strip() for f in ft.split(' ') if f.strip() != '']
        for uri, data in self._library.items():
            can_add = True
            if not len(ft) == 0:
                for ftp in ft:
                    if ftp != '':
                        part_can_add = False
                        if ftp in uri.lower() or \
                           ftp in data['name'].lower() or \
                           ftp in data['album_name'].lower():
                            part_can_add = True

                        if not part_can_add:
                            for artist in data['artists']:
                                if ftp in artist.lower():
                                    part_can_add = True
                                    break
                        if not part_can_add:
                            for tag in data['tags']:
                                if ftp in tag.lower():
                                    part_can_add = True
                                    break
                        if not part_can_add:
                            can_add = False
                            break
            if can_add:
                songs.addTopLevelItem(qtw.QTreeWidgetItem([data['name'],
                                                           ', '.join(data['artists']),
                                                           data['album_name'],
                                                           uri,
                                                           ', '.join(data['tags'])]))
            # self._ui.update()
        self._save_library()
        if row > -1:
            if row < self._ui.twSongs.topLevelItemCount():
                if self._ui.twSongs.topLevelItem(row).text(3) == self._current_song:
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


class SongData:
    def __init__(self, uri, raw_data):
        self._dict = raw_data
        self.name = raw_data['name']
        self.artists = raw_data['artists']
        self.artists_string = ', '.join(self.artists)
        self.album_name = raw_data['album_name']
        self._uri = uri
        self.tags = raw_data['tags']
        self.tags_string = ', '.join(self.tags)

    def to_songlist(self):
        return [self.name, self.artists_string, self.album_name, self.uri, self.tags_string]


    def filter_string(self, check_string):
        check_list = [self.name, self.album_name, self.uri].append(self.artists).append(self.tags)
        return any(map(lambda x: check_string in x.lower(), check_list))

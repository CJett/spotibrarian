import json
import os
import sys
import traceback
from collections import defaultdict

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
SCOPE = 'user-library-read playlist-modify-public playlist-modify-private user-read-playback-state user-modify-playback-state'
URL = "http://localhost:8888/callback"
PROMPT = {
    'role': 'system',
    'content': f"""Describe the vibe of the song as "<weather (one simple word)> <month> <time of day>" (like "rainy august morning")."""
}
LOCAL = "local.json"
# MERGE_PCT = 0.8
DECIMATE_PLAYLIST_LENGTH = 20
LEGAL_WEATHER = [
    "foggy",
    "stormy",
    "humid",
    "windy",
    "frosty",
    "rainy",
    "snowy",
    "cold",
    "warm",
    "breezy",
    "hot",
    "crisp",
    "clear",
    "cool",
    "misty",
    "dusty",
    "cloudy",
    "sunny",
    "electric",
]
WEATHER_ALIAS = {
    "hazy":"foggy",
    "thunderous":"stormy",
    "thunderstorm":"stormy",
    "balmy":"warm",
    "blustery":"windy",
    "chilly":"cold",
    "arid":"hot",
    "sultry":"humid",
    "sweltering":"humid",
    "tropical":"humid",
    "fiery":"hot",
    "smoky":"foggy",
    "dreary":"rainy",
    "calm":"clear",
    "gloomy":"cloudy",
    "overcast":"cloudy",
    "sunlit":"sunny",
    "frosty":"crisp",
    "muggy":"humid",
    "drizzly":"rainy",
    "blizzard":"snowy",
    "muddy":"rainy",
    "peaceful":"clear",
    "tranquil":"clear",
    "electrifying":"electric",
    "starry":"clear",
    "celestial":"clear",
    "cozy":"cool",
    "neon":"warm",
    "brisk":"frosty",
    "mild":"clear",
    "intense":"stormy"
}
WEATHER_DECIMATOR = {
    "foggy":"rainy",
    "humid":"hot",
    "windy":"warm",
    "frosty":"cold",
    "warm":"hot",
    "breezy":"warm",
    "crisp":"cold",
    "misty":"rainy",
    "cool":"cold",
    "dusty":"hot",
    "sunny":"hot",
    "electric":"hot"
}
LEGAL_TOD = [
    "dawn",
    "morning",
    "afternoon",
    "evening",
    "dusk",
    "night"
]
TOD_ALIAS = {
    "midnight":"night",
    "twilight":"dawn",
    "sunset":"dusk",
    "midday":"afternoon",
    "sunrise":"dawn",
    "nighttime":"night",
    "noon":"afternoon"
}
TOD_DECIMATOR = {
    "dawn":"morning",
    "dusk":"evening",
}
LEGAL_MONTH = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december"
]
MONTH_DECIMATOR = {
    "january":"december",
    "february":"december",
    "march":"april",
    "may":"june",
    "july":"august",
    "september":"october",
    "november":"october"
}
PROMPT_SPECIFIC_WEATHER = PROMPT.copy()
PROMPT_SPECIFIC_TOD = PROMPT.copy()
PROMPT_SPECIFIC_MONTH = PROMPT.copy()
PROMPT_SPECIFIC_WEATHER["content"] += f"Please choose weather from this list: [{', '.join(LEGAL_WEATHER)}]"
PROMPT_SPECIFIC_TOD["content"] += f"Please choose time of day from this list: [{', '.join(LEGAL_TOD)}]"
PROMPT_SPECIFIC_MONTH["content"] += f"Please choose time of day from this list: [{', '.join(LEGAL_MONTH)}]"
assert all([k in LEGAL_WEATHER for k in WEATHER_ALIAS.values()]), str([k for k in WEATHER_ALIAS.values() if not k  in LEGAL_WEATHER ])
assert all([k in LEGAL_TOD for k in TOD_ALIAS.values()]), str([k for k in TOD_ALIAS.values() if not k  in LEGAL_TOD ])

log = logging.getLogger("Spotibrarian")
hdlr = logging.StreamHandler()
log.addHandler(hdlr)
log.setLevel(logging.DEBUG)

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE, client_id=CID, client_secret=CS, redirect_uri=URL))
ai = OpenAI(api_key=AI)
try:
    with open(LOCAL) as f:
        loaded_db = json.loads(f.read())
except:
    loaded_db = {"playlists":{},"tracks":{}}

for k in loaded_db["playlists"].keys():
    print(f"unfollow {k}")
    try:
        sp.current_user_unfollow_playlist(k)
    except:
        print(traceback.format_exc())
exit()

db = {"playlists":{},"tracks":{}}
if input("refresh tracks? [y/N]").lower().strip() == "y":
    # update tracks in db
    def add_tracks(tracks):
        for track in tracks:
            track = track['track']
            artist = ', '.join([t['name'] for t in track['artists']])
            print("add",artist, "-", track['name'])
            db["tracks"][track['uri']] = {
                "song_url":track['external_urls']['spotify'],
                "name":track['name'],
                "artist":artist,
                "album":track['album']['name'],
                "duration_ms":track['duration_ms'],
                "image_url":track['album']['images'][0]['url'],
                "desc":loaded_db["tracks"][track["uri"]]["desc"] if track["uri"] in loaded_db["tracks"] else ""
            }

    results = sp.current_user_saved_tracks()
    add_tracks(results['items'])
    while results['next']:
        results = sp.next(results)
        add_tracks(results['items'])
else:
    db["tracks"] = loaded_db["tracks"].copy()

# update descriptions in db

refresh_all = input("refresh ALL descriptions? [y/N]").lower().strip() == "y"

for uri, info in db["tracks"].items():
    song = f"{info['artist']} - {info['name']}"
    if refresh_all or not info["desc"].strip():
        try:
            resp = ai.chat.completions.create(
                model="gpt-4o",
                messages=[PROMPT, {'role': 'user', 'content': song}]
                # max_tokens=150,  # Adjust the token limit as per your needs
                # temperature=0.7  # Adjust the creativity level
            ).dict()['choices'][0]['message']['content'].strip().lower()
            db["tracks"][uri]["desc"] = resp
            print(song,"=", resp)
        except:
            print(song, traceback.format_exc())
    weather = info["desc"].split(" ")[0]
    while weather not in LEGAL_WEATHER and weather not in WEATHER_ALIAS:
        print("illegal weather", weather, "for song", song)
        try:
            resp = ai.chat.completions.create(
                model="gpt-4o",
                messages=[PROMPT_SPECIFIC_WEATHER, {'role': 'user', 'content': song}]
                # max_tokens=150,  # Adjust the token limit as per your needs
                # temperature=0.7  # Adjust the creativity level
            ).dict()['choices'][0]['message']['content'].strip().lower()
            weather = resp.split(" ")[0]
            db["tracks"][uri]["desc"] = resp
            print(song,"=", resp)
        except:
            print(song, traceback.format_exc())
    month = info["desc"].split(" ")[1]
    while month not in LEGAL_MONTH:
        print("illegal month", month, "for song", song)
        try:
            resp = ai.chat.completions.create(
                model="gpt-4o",
                messages=[PROMPT_SPECIFIC_MONTH, {'role': 'user', 'content': song}]
                # max_tokens=150,  # Adjust the token limit as per your needs
                # temperature=0.7  # Adjust the creativity level
            ).dict()['choices'][0]['message']['content'].strip().lower()
            month = resp.split(" ")[1]
            db["tracks"][uri]["desc"] = resp
            print(song, "=", resp)
        except:
            print(song, traceback.format_exc())
    tod = info["desc"].split(" ")[-1]
    while tod not in LEGAL_TOD and tod not in TOD_ALIAS:
        print("illegal tod", tod, "for song", song)
        try:
            resp = ai.chat.completions.create(
                model="gpt-4o",
                messages=[PROMPT_SPECIFIC_TOD, {'role': 'user', 'content': song}]
                # max_tokens=150,  # Adjust the token limit as per your needs
                # temperature=0.7  # Adjust the creativity level
            ).dict()['choices'][0]['message']['content'].strip().lower()
            tod = resp.split(" ")[-1]
            db["tracks"][uri]["desc"] = resp
            print(song, "=", resp)
        except:
            print(song, traceback.format_exc())
    if weather in WEATHER_ALIAS:
        db["tracks"][uri]["desc"] = " ".join([WEATHER_ALIAS[weather]]+info["desc"].split(" ")[1:])
    if tod in TOD_ALIAS:
        db["tracks"][uri]["desc"] = " ".join(info["desc"].split(" ")[:-1]+[TOD_ALIAS[tod]])

# formulate playlists
weathers = defaultdict(lambda:0)
tods = defaultdict(lambda:0)
months = defaultdict(lambda:0)
playlists = defaultdict(lambda:[])
for uri, info in db["tracks"].items():
    playlists[info["desc"]].append(uri)
    weathers[info["desc"].split(" ")[0]] += 1
    tods[info["desc"].split(" ")[-1]] += 1
    months[info["desc"].split(" ")[1]] += 1

print(len(playlists), "unique playlists")

if not input("Reduce playlist count? [Y/n]").lower().strip() == "n":
    try:
        decimate_limit = int(input("max playlist length for decimating (blank for no limit):"))
    except:
        decimate_limit = 99999999
    print("Decimate by weather")
    for name in list(playlists.keys()):
        songs = playlists[name]
        if len(songs) < decimate_limit:
            weather, month, tod = name.split(" ")
            if weather in WEATHER_DECIMATOR and weather != WEATHER_DECIMATOR[weather]:
                weather = WEATHER_DECIMATOR[weather]
                new_name = f"{weather} {month} {tod}"
                print("decimate", name, "into", new_name)
                playlists[new_name].extend(songs)
                playlists.pop(name)
    print(len(playlists), "unique playlists")
    print("Decimate by month")
    for name in list(playlists.keys()):
        songs = playlists[name]
        if len(songs) < decimate_limit:
            weather, month, tod = name.split(" ")
            if month in MONTH_DECIMATOR and month != MONTH_DECIMATOR[month]:
                month = MONTH_DECIMATOR[month]
                new_name = f"{weather} {month} {tod}"
                print("decimate", name, "into", new_name)
                playlists[new_name].extend(songs)
                playlists.pop(name)
    print(len(playlists), "unique playlists")
    print("Decimate by tod")
    for name in list(playlists.keys()):
        songs = playlists[name]
        if len(songs) < decimate_limit:
            weather, month, tod = name.split(" ")
            if tod in TOD_DECIMATOR and tod != TOD_DECIMATOR[tod]:
                tod = TOD_DECIMATOR[tod]
                new_name = f"{weather} {month} {tod}"
                print("decimate", name, "into", new_name)
                playlists[new_name].extend(songs)
                playlists.pop(name)

playlists = {k: v for k, v in sorted(playlists.items(), key=lambda item: len(item[1]))}
for name, songs in playlists.items():
    print(name, len(songs))
    for song in songs:
        print("\t",db["tracks"][song])
print(len(playlists), "unique playlists")
# db["playlists"] = playlists.copy()

if not input("Create playlists now? [Y/n]").lower().strip() == "n":
    for k in db["playlists"].keys():
        print(f"unfollow {k}")
        sp.current_user_unfollow_playlist(k)
    for name, songs in playlists.items():
        while True:
            try:
                print(f"Create playlist {name}")
                pl = sp.user_playlist_create(sp.current_user()['id'], name, public=False, description=str(name).title())['uri']
                break
            except Exception as e:
                print("Retry:", e)
        songs = songs.copy()
        random.shuffle(songs)
        while len(songs) > 50:
            print(f"{len(songs)} songs left...")
            try:
                sp.playlist_add_items(pl, songs[:50])
                songs = songs[50:]
            except Exception as e:
                print("Retry:", e)
        while songs:
            print(f"Adding {len(songs)}")
            try:
                sp.playlist_add_items(pl, songs[:50])
                songs = []
            except Exception as e:
                print("Retry:", e)

db["playlists"] = playlists
with open(LOCAL, 'w') as f:
    f.write(json.dumps(db, indent = 1))

print("done")
# print(json.dumps(weathers, indent=2))
# print(json.dumps(tods, indent=2))
# print(json.dumps(months, indent=2))
# squash playlists
# do_resquash = True
# squash_ct = 0
# while do_resquash:
#     squash_ct += 1
#     print(f"Squash loop {squash_ct}")



# do_resquash = True
# squash_ct = 0
# while do_resquash:
#     squash_ct += 1
#     print(f"Squash loop {squash_ct}")
#     do_resquash = False
#     squashed_playlists = {}
#     for name, songs in playlists.items():
#         closest_name = ""
#         closest_pct = 0
#         for s_name, s_songs in squashed_playlists.items():
#             pct = len([song for song in songs if song in s_songs])/len(songs)
#             if pct > closest_pct:
#                 closest_pct = pct
#                 closest_name = s_name
#         if closest_pct > MERGE_PCT:
#             do_resquash = True
#             print("squash", name, "into", closest_name, f"({closest_pct})")
#             squashed_playlists[closest_name].extend([song for song in songs if song not in squashed_playlists[closest_name]])
#         else:
#             print("closest", name, "into", closest_name, f"({closest_pct})")
#             squashed_playlists[name] = songs
#     playlists = squashed_playlists.copy()

# print(len(playlists), "squashed playlists")
# db["playlists"] = playlists.copy()
#
#
# #
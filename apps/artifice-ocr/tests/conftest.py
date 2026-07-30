# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

import sqlite3

import pytest


TROPY_SCHEMA = """
CREATE TABLE project (project_id TEXT, name TEXT, created TEXT, base TEXT, store TEXT);
CREATE TABLE items (id INTEGER PRIMARY KEY);
CREATE TABLE subjects (id INTEGER PRIMARY KEY, template TEXT);
CREATE TABLE images (id INTEGER PRIMARY KEY);
CREATE TABLE lists (list_id INTEGER PRIMARY KEY, name TEXT, parent_list_id INTEGER, position INTEGER);
CREATE TABLE list_items (list_id INTEGER, id INTEGER);
CREATE TABLE tags (tag_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE taggings (tag_id INTEGER, id INTEGER);
CREATE TABLE photos (
    id INTEGER PRIMARY KEY, item_id INTEGER, path TEXT, mimetype TEXT,
    page INTEGER DEFAULT 0, filename TEXT,
    orientation INTEGER DEFAULT 1
);
CREATE TABLE notes (
    note_id INTEGER PRIMARY KEY, id INTEGER NOT NULL, text TEXT NOT NULL,
    state TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'en',
    created NUMERIC DEFAULT CURRENT_TIMESTAMP,
    modified NUMERIC DEFAULT CURRENT_TIMESTAMP, deleted NUMERIC,
    CHECK (language != '' AND language = trim(lower(language))),
    CHECK (text != '')
);
CREATE TABLE transcriptions (
    transcription_id INTEGER PRIMARY KEY, id INTEGER NOT NULL, text TEXT,
    config TEXT, data TEXT, status NUMERIC NOT NULL DEFAULT 0,
    deleted NUMERIC, created NUMERIC DEFAULT CURRENT_TIMESTAMP,
    modified NUMERIC DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE metadata (
    id INTEGER, property TEXT, value_id INTEGER,
    PRIMARY KEY (id, property)
);
CREATE TABLE metadata_values (
    value_id INTEGER PRIMARY KEY, text TEXT
);
CREATE TABLE trash (id INTEGER PRIMARY KEY);
CREATE VIRTUAL TABLE fts_notes USING fts5(id UNINDEXED, text, language UNINDEXED);
CREATE VIRTUAL TABLE fts_transcriptions USING fts5(id UNINDEXED, text);
CREATE TRIGGER notes_ai_fts AFTER INSERT ON notes BEGIN
  INSERT INTO fts_notes (rowid, id, text, language)
    VALUES (NEW.note_id, NEW.id, NEW.text, NEW.language);
END;
CREATE TRIGGER transcriptions_ai_fts AFTER INSERT ON transcriptions BEGIN
  INSERT INTO fts_transcriptions (rowid, id, text)
    VALUES (NEW.transcription_id, NEW.id, NEW.text);
END;
"""


@pytest.fixture
def tropy_project(tmp_path):
    root = tmp_path / "Archive.tropy"
    (root / "assets").mkdir(parents=True)
    con = sqlite3.connect(root / "project.tpy")
    con.executescript(TROPY_SCHEMA)
    con.execute("INSERT INTO project VALUES ('u','Archive','2026','project','assets')")
    con.execute("INSERT INTO items (id) VALUES (1)")
    con.execute("INSERT INTO subjects (id, template) VALUES (10, 'photo')")
    con.execute("INSERT INTO images (id) VALUES (10)")
    con.execute(
        "INSERT INTO photos (id,item_id,path,mimetype,page,filename) "
        "VALUES (10,1,'assets/a.pdf','application/pdf',0,'doc.pdf')"
    )
    con.execute(
        "INSERT INTO metadata_values (value_id, text) VALUES (100, 'Doc1')"
    )
    con.execute(
        "INSERT INTO metadata (id, property, value_id) "
        "VALUES (1, 'http://purl.org/dc/elements/1.1/title', 100)"
    )
    con.commit()
    con.close()
    return root

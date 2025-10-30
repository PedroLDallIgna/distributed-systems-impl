import sqlite3
import os
from flask import Flask, request, g
from datetime import datetime
import json
from enum import Enum

DB_PATH = 'server.db'
HOST_ADDRESS = os.getenv('HOST_ADDRESS', '127.0.0.1')
SELECT_ALL_QUERY = "SELECT * FROM registers"
SELECT_VC_BY_ID_QUERY = "SELECT vector_clock FROM registers WHERE id = ?"
INSERT_REGISTER_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)"
UPDATE_VC_BY_ID_QUERY = "UPDATE registers SET vector_clock = ? WHERE id = ?"
SELECT_TIMESTAMP_BY_ID_QUERY = "SELECT timestamp FROM registers WHERE id = ?"

sqlite3.register_converter(
    "timestamp",
    lambda v: datetime.fromisoformat(v.decode()),
)

sqlite3.register_adapter(
    datetime,
    lambda dt: dt.isoformat(),
)

sqlite3.register_converter(
    "json",
    lambda v: json.loads(v.decode()),
)

sqlite3.register_adapter(
    dict,
    lambda d: json.dumps(d),
)

app = Flask(__name__)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            DB_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

class VectorClockComparison(Enum):
    IGUAIS = 1
    SENDER_POSTERIOR = 2
    RECEIVER_POSTERIOR = 3
    CONCORRENTE = 4

def compare_vcs(vc_sender, vc_receiver):
    pass

def merge_vcs(vc_sender, vc_receiver):
    pass

@app.post('/registro')
def post_registro():
    pass

@app.get('/registro')
def get_registro():
    pass


if __name__ == "__main__":
    with sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as init_con:
        with app.open_resource('schema.sql') as f:
            init_con.executescript(f.read().decode('utf8'))

    app.run(host=HOST_ADDRESS, port=5000)

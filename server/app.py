import sqlite3
import sys
from flask import Flask, request, g
from datetime import datetime
import json

DB_PATH = 'server.db'

sqlite3.register_converter(
    "timestamp", lambda v: datetime.fromisoformat(v.decode()),
)
sqlite3.register_converter(
    "json", lambda v: json.loads(v.decode()),
)
sqlite3.register_adapter(
    dict, lambda d: json.dumps(d),
)

app = Flask(__name__)
app.config['DEBUG'] = True

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def compare_vcs():
    pass

def merge_vcs():
    pass

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        data = request.get_json()
        print("recebendo: " + str(data))
        registers = data.get('registers', [])
        db = get_db()
        cur = db.cursor()
        for item in registers:
            cur.execute("INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)", item)
        db.commit()
        return {'status': 'success'}, 201
    elif request.method == 'GET':
        cur = get_db().cursor()
        cur.execute("SELECT * FROM registers")
        rows = cur.fetchall()
        print("enviando: " + str(rows))
        results = [{'id': row[0], 'value': row[1], 'vector_clock': row[2], 'timestamp': row[3].isoformat()} for row in rows]
        return {'registers': results}, 200

if __name__ == "__main__":
    with sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as init_con:
        with app.open_resource('schema.sql') as f:
            init_con.executescript(f.read().decode('utf8'))

    app.run()

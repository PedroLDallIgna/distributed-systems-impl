import sqlite3
import os
from flask import Flask, request, g
from datetime import datetime
import json
from enum import Enum

DB_PATH = 'server.db'
HOST_ADDRESS = os.getenv('HOST_ADDRESS', '127.0.0.1')
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

class VectorClockComparison(Enum):
    IGUAIS = 1
    SENDER_POSTERIOR = 2
    RECEIVER_POSTERIOR = 3
    CONCORRENTE = 4

def compare_vcs(vc_sender, vc_receiver):
    if vc_sender == vc_receiver:
        return VectorClockComparison.IGUAIS

    sender_is_causal = True
    receiver_is_causal = True

    all_nodes = set(vc_sender.keys()) | set(vc_receiver.keys())

    for node in all_nodes:
        sender_count = vc_sender.get(node, 0)
        receiver_count = vc_receiver.get(node, 0)

        if sender_count > receiver_count:
            # sender viu algo que o receiver não viu, então o receiver não é causal
            receiver_is_causal = False
        if receiver_count > sender_count:
            # receiver viu algo que o sender não viu, então o sender não é causal
            sender_is_causal = False

    if sender_is_causal and not receiver_is_causal:
        return VectorClockComparison.SENDER_POSTERIOR
    elif receiver_is_causal and not sender_is_causal:
        return VectorClockComparison.RECEIVER_POSTERIOR
    else:
        return VectorClockComparison.CONCORRENTE


def merge_vcs(vc_sender, vc_receiver):
    merged = {}
    all_nodes = set(vc_sender.keys()) | set(vc_receiver.keys())
    for node in all_nodes:
        merged[node] = max(vc_sender.get(node, 0), vc_receiver.get(node, 0))
    return merged


@app.post('/registro')
def post_registro():
    data = request.get_json()
    app.logger.info("Recebendo: " + str(data))
    
    registers = data.get('registers', [])
    db = get_db()
    cur = db.cursor()

    for item in registers:
        vc_sender = item['vector_clock']
        vc_receiver = cur.execute(SELECT_VC_BY_ID_QUERY, (item['id'],)).fetchone()
        # mescla os vector clocks
        merged_vc = merge_vcs(vc_sender, vc_receiver[0] if vc_receiver != None else {})
        # compara os vector clocks
        vc_comparison = compare_vcs(vc_sender, vc_receiver[0] if vc_receiver != None else {})
        if vc_comparison == VectorClockComparison.SENDER_POSTERIOR:
            app.logger.info("Sender é posterior. Aceitando dados.")
            # aceita o dado do sender pois é posterior (atualiza o vector clock)
            item['vector_clock'] = merged_vc
            cur.execute(INSERT_REGISTER_QUERY, item)
        elif vc_comparison == VectorClockComparison.RECEIVER_POSTERIOR:
            app.logger.info("Sender é anterior. Rejeitando dados.")
            # rejeita o dado do sender pois é anterior (atualiza o vector clock)
            cur.execute(UPDATE_VC_BY_ID_QUERY, (merged_vc, item['id']))
        elif vc_comparison == VectorClockComparison.CONCORRENTE:
            app.logger.info("Conflito detectado entre dados. Verificando timestamps.")
            # vector clocks são concorrentes
            # verifica o timestamp para resolver o conflito
            timestamp_sender = item['timestamp']
            timestamp_receiver = cur.execute(SELECT_TIMESTAMP_BY_ID_QUERY, (item['id'],)).fetchone()[0]
            if timestamp_sender > timestamp_receiver:
                app.logger.info("Sender é mais recente. Aceitando dados.")
                # se o sender for mais recente, aceita o dado do sender (atualiza o vector clock)
                item['vector_clock'] = merged_vc
                cur.execute(INSERT_REGISTER_QUERY, item)
            else:
                app.logger.info("Receiver é mais recente. Rejeitando dados.")
                # se o receiver for mais recente, rejeita o dado do sender (atualiza o vector clock)
                cur.execute(UPDATE_VC_BY_ID_QUERY, (merged_vc, item['id']))

    db.commit()
    
    return {'status': 'pushed'}, 201


@app.get('/registro')
def get_registro():
    cur = get_db().cursor()
    cur.execute("SELECT * FROM registers")
    rows = cur.fetchall()
    results = [
        {
            'id': row[0],
            'value': row[1],
            'vector_clock': row[2],
            'timestamp': row[3].isoformat()
        } for row in rows
    ]
    
    app.logger.info("Enviando: " + str(results))
    return {'registers': results}, 200


if __name__ == "__main__":
    with sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as init_con:
        with app.open_resource('schema.sql') as f:
            init_con.executescript(f.read().decode('utf8'))

    app.run(host=HOST_ADDRESS, port=5000)

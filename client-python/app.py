import sqlite3
import sys
from datetime import datetime
import requests
import json
from uuid import uuid4
import os

SERVER_HOST = os.getenv('SERVER_HOST', '127.0.0.1')
SERVER_PORT = os.getenv('SERVER_PORT', 5000)
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
SYNC_DATABASE_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)"
INSERT_VALUE_QUERY = "INSERT INTO registers (id, value, vector_clock) VALUES (?, ?, ?)"

sqlite3.register_converter(
    "timestamp", lambda v: datetime.fromisoformat(v.decode()),
)
sqlite3.register_adapter(
    datetime, lambda dt: dt.isoformat(),
)
sqlite3.register_converter(
    "json", lambda v: json.loads(v.decode()),
)
sqlite3.register_adapter(
    dict, lambda d: json.dumps(d),
)

con = sqlite3.connect('client_a.db', detect_types=sqlite3.PARSE_DECLTYPES)

with open('schema.sql') as f:
    con.executescript(f.read())

cur = con.cursor()

# sincronizar o banco de dados
def push():
    cur.execute("SELECT * FROM registers")
    rows = cur.fetchall()
    data = [{'id': row[0], 'value': row[1], 'vector_clock': row[2], 'timestamp': row[3].isoformat()} for row in rows]
    if len(data) == 0:
        print('Nada para sincronizar.')
        return
    print("enviando: " + str(data))
    response = requests.post(f'{SERVER_URL}/registro', json={'registers': data})
    if response.status_code == 201:
        print("Dados enviados ao servidor com sucesso.")

def pull():
    response = requests.get(f'{SERVER_URL}/registro')
    if response.status_code == 200:
        data = response.json()
        if 'registers' in data and len(data['registers']) > 0:
            cur.executemany(SYNC_DATABASE_QUERY, data['registers'])
            con.commit()
        else:
            print('Nenhum dado recebido do servidor.')


def show_database(rows):
    if len(rows) == 0:
        print('Nenhum registro para editar.')
        return
    print(f"{'Registros locais':=^120}")
    print(f"{'#':>3} | {'ID':<38} | {'Valor':<20} | {'VC':<20} | {'Timestamp':<27}")
    print('=' * 120)
    for i, row in enumerate(rows):
        print(f"{i:>3} | {row[0]:<38} | {row[1]:<20} | {str(row[2]):<20} | {row[3].isoformat():<27}")
        print('-' * 120)

# inserir dado localmente
def insert():
    value: str = str(input('Digite um valor: '))
    cur.execute(INSERT_VALUE_QUERY, (str(uuid4()), value, {'CA': 1}))
    con.commit()
    print("Valor inserido localmente.")

# editar dado localmente
def edit():
    cur.execute("SELECT * FROM registers")
    rows = cur.fetchall()
    show_database(rows)
    index: int = int(input('Selecione o índice do registro a ser editado: '))
    if index < 0 or index >= len(rows):
        print('Índice inválido.')
        return
    new_value: str = str(input('Digite o novo valor: '))
    selected_row = rows[index]
    vc = selected_row[2]
    vc['CA'] = vc.get('CA', 0) + 1
    cur.execute("UPDATE registers SET value = ?, vector_clock = ?, timestamp = ? WHERE id = ?",
                (new_value, vc, datetime.now(), selected_row[0]))
    con.commit()
    print("Valor editado localmente.")


print("Bem-vindo ao cliente A")
print("Sincronizando com o servidor...")
push()
pull()
print("Sincronização concluída.")
print("Tudo pronto!")

option: str = str(input("""
    [S]ync
    [I]nsert
    [E]dit
    [H]elp
    [Q]uit
Selecione uma opção: """))

while (True):
    if option.upper() == 'S':
        push()
        pull()
        print("Sincronização concluída.")
    elif option.upper() == 'I':
        insert()
    elif option.upper() == 'E':
        edit()
    elif option.upper() == 'Q':
        break
    
    option: str = str(input("""
    [S]ync
    [I]nsert
    [E]dit
    [H]elp
    [Q]uit
Selecione uma opção: """))
        
con.close()
sys.exit()

import sqlite3
import sys
from datetime import datetime, timezone
import requests
import json
from uuid import uuid4
import os
import re

SERVER_HOST = os.getenv('SERVER_HOST', '127.0.0.1')
SERVER_PORT = os.getenv('SERVER_PORT', 5000)
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
SYNC_DATABASE_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)"
INSERT_VALUE_QUERY = "INSERT INTO registers (id, value, vector_clock, timestamp) VALUES (?, ?, ?, ?)"
SELECT_ALL_QUERY = "SELECT * FROM registers"
UPDATE_BY_ID_QUERY = "UPDATE registers SET value = ?, vector_clock = ?, timestamp = ? WHERE id = ?"

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

client_name_entry = str(input('Digite o nome do cliente: '))
client_name = re.sub(r'\W+', '', client_name_entry).lower()

con = sqlite3.connect(f'client_{client_name}.db', detect_types=sqlite3.PARSE_DECLTYPES)

with open('schema.sql') as f:
    con.executescript(f.read())

cur = con.cursor()

def push():
    cur.execute(SELECT_ALL_QUERY)
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
    cur.execute(INSERT_VALUE_QUERY, (str(uuid4()), value, {client_name: 1}, datetime.now(timezone.utc)))
    con.commit()
    print("Valor inserido localmente.")

# editar dado localmente
def edit():
    cur.execute(SELECT_ALL_QUERY)
    rows = cur.fetchall()
    show_database(rows)
    index: int = int(input('Selecione o índice do registro a ser editado: '))
    if index < 0 or index >= len(rows):
        print('Índice inválido.')
        return
    new_value: str = str(input('Digite o novo valor: '))
    selected_row = rows[index]
    vc = selected_row[2]
    vc[client_name] = vc.get(client_name, 0) + 1
    cur.execute(
        UPDATE_BY_ID_QUERY,
        (new_value, vc, datetime.now(timezone.utc), selected_row[0])
    )
    con.commit()
    print("Valor editado localmente.")

# visualizar os dados locais
def view():
    cur.execute(SELECT_ALL_QUERY)
    rows = cur.fetchall()
    show_database(rows)


print("Bem-vindo ao cliente")
print("Sincronizando com o servidor...")
push()
pull()
print("Sincronização concluída.")
print("Tudo pronto!")

call_to_action_message = """    [S]ync
    [I]nsert
    [E]dit
    [V]iew
    [Q]uit
Selecione uma opção: """

option = str(input(call_to_action_message))

while (True):
    if option.upper() == 'S':
        push()
        pull()
        print("Sincronização concluída.")
    elif option.upper() == 'I':
        insert()
    elif option.upper() == 'E':
        edit()
    elif option.upper() == 'V':
        view()
    elif option.upper() == 'Q':
        break

    option = str(input(call_to_action_message))

con.close()
sys.exit()

import sqlite3
import sys
from datetime import datetime
import requests
import json
from uuid import uuid4

SYNC_DATABASE_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)"
INSERT_VALUE_QUERY = "INSERT INTO registers (id, value, vector_clock) VALUES (?, ?, ?)"

sqlite3.register_converter(
    "timestamp", lambda v: datetime.fromisoformat(v.decode()),
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
    response = requests.post('http://localhost:5000/registro', json={'registers': data})
    if response.status_code == 201:
        print("Dados enviados ao servidor com sucesso.")

def pull():
    response = requests.get('http://localhost:5000/registro')
    if response.status_code == 200:
        data = response.json()
        if 'registers' in data and len(data['registers']) > 0:
            cur.executemany(SYNC_DATABASE_QUERY, data['registers'])
            con.commit()
        else:
            print('Nenhum dado recebido do servidor.')

# inserir dado localmente
def insert():
    value: str = str(input('Digite um valor: '))
    cur.execute(INSERT_VALUE_QUERY, (str(uuid4()), value, {'CA': 1}))
    con.commit()
    print("Valor inserido localmente.")

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
        # editar dado localmente
        pass
    elif option.upper() == 'H':
        # mostrar ajuda
        pass
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

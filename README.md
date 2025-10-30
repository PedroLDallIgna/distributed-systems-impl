# Vector Clock

## Grupo

- Adrian Bonhexultes
- Enzo Molossi
- João Zanardo
- Pedro Dall' Igna
- Rafaela Bortoloso
- Tales Aguiar

## Implementação

### Banco de Dados

Schema do banco de dados deve ser único tanto para o servidor como para os clientes.

```sql
DROP TABLE IF EXISTS registers;

CREATE TABLE IF NOT EXISTS registers(
  id TEXT PRIMARY KEY,
  value TEXT,
  vector_clock JSON,
  timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Servidor

No servidor acontece a lógica principal de resolução do Vector Clock. Um Vector Clock é adicionado a cada registro, bem como enviado em cada requisição.

O servidor será desenvolvido utilizando o framework Flask, que facilita a construção de APIs em Python.

O banco de dados utilizado será o SQLite para manter tudo localmente em um arquivo.

Estrutura de arquivos:

```
server/
├─── app.py
├─── schema.sql
├─── requirements.txt
└─── Dockerfile
```

#### Imports

Para a implementação do servidor, serão utilizados alguns pacotes da biblioteca do Python.

```python
import sqlite3  # biblioteca SQLite para o python
import os  # funções do sistema operacional
from flask import Flask, request, g  # importação do Flask
from datetime import datetime  # utilitários de data e hora
import json  # utilitários para manipulação de JSON
from enum import Enum  # classe para criação de enums
```

#### Constantes

Variáveis constantes, como nome do banco de dados e queries SQL.

```python
DB_PATH = 'server.db'
HOST_ADDRESS = os.getenv('HOST_ADDRESS', '127.0.0.1')
HOST_PORT = int(os.getenv('HOST_PORT', '5000'))
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
SELECT_ALL_QUERY = "SELECT * FROM registers"
SELECT_VC_BY_ID_QUERY = "SELECT vector_clock FROM registers WHERE id = ?"
INSERT_REGISTER_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)"
UPDATE_VC_BY_ID_QUERY = "UPDATE registers SET vector_clock = ? WHERE id = ?"
SELECT_TIMESTAMP_BY_ID_QUERY = "SELECT timestamp FROM registers WHERE id = ?"
```

#### Definições de `converters` e `adapters` do SQLite

O SQLite é um banco de dados salvo em um arquivo. Portanto, ele possui restrições em relação a outros bancos de dados com processos dedicados.

Entre as restrições, estão os tipos que ele suporta. Em vista disso, são necessárias conversões e adaptações dos tipos que ele possui com os tipos que a linguagem Python possui, para simplificar a interação entre ambos.

```python
# tipo `timestamp` no banco será transformado em objeto `datetime` do Python
sqlite3.register_converter(
    "timestamp",
    lambda v: datetime.fromisoformat(v.decode()),
)

# tipo `datetime` do Python será transformado para `string` (timestamp) no banco
sqlite3.register_adapter(
    datetime,
    lambda dt: dt.isoformat(),
)

# tipo `json` no banco será transformado em objeto `dict` do Python
sqlite3.register_converter(
    "json",
    lambda v: json.loads(v.decode()),
)

# tipo `dict` do Python será transformado em `json` (text) no banco
sqlite3.register_adapter(
    dict,
    lambda d: json.dumps(d),
)
```

#### Instanciação da aplicação

```python
app = Flask(__name__)
```

#### Conexão e instanciação do banco de dados SQLite

Para utilizar o SQLite juntamente com o Flask, é recomendado manter uma única instância do banco de dados atribuída para toda a aplicação. Portanto, a instância é mantida como global e recuperada por meio da função `get_db`. Para conectar ao banco de dados os parâmetros passados são: o nome do arquivo do banco (obrigatório), e, no nosso caso, são passados parâmetros adicionais para considerar os novos tipos (_converters_ e _adapters_) definidos anteriormente e uma _flag_ de checagem como falsa.

```python
# função para buscar a instância única do banco de dados
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            DB_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        g.db.row_factory = sqlite3.Row
    return g.db
```

Quando a aplicação é finalizada (`@app.teardown_appcontext`), será executada a função `close_db` para fechar a conexão com o banco de dados e excluir a instância global.

```python
# fechar o banco de dados quando finaliza a aplicação Flask
@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()
```

#### Funções para tratar os Vector Clocks

A função `compare_vcs` recebe dois Vector Clocks (`vc_sender` e `vc_receiver`) como parâmetros e faz a comparação entre eles para estabelecer a ordem de alteração: qual foi posterior, se são iguais ou se há conflito.

```python
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
```

A função `merge_vcs` também recebe dois Vector Clocks (`vc_sender` e `vc_receiver`) como parâmetros, mas esta mescla (_merge_) ambos, que consiste basicamente em pegar o valor máximo de cada nó presente nos Vector Clocks.

```python
def merge_vcs(vc_sender, vc_receiver):
    merged = {}
    all_nodes = set(vc_sender.keys()) | set(vc_receiver.keys())
    for node in all_nodes:
        merged[node] = max(vc_sender.get(node, 0), vc_receiver.get(node, 0))
    return merged
```

#### Função de tratamento do método POST

A função `post_registro` manipula requisições para o endpoint `/registro` com o método `POST`. Ela receberá um registro em formato JSON e cadastrará no banco do servidor (central) fazendo os devidos tratamentos, como resolução de conflitos.

  - _body_ da requisição:

    ```json
    {
      "registers": [
        {
          "id": "uuidv4",
          "value": "valor",
          "vector_clock": {
            "server": 0,
            "client_x": 0
          },
          "timestamp": 0.0
        }
      ]
    }
    ```

```python
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
            timestamp_sender = datetime.fromisoformat(item['timestamp']).timestamp()
            receiver = cur.execute(SELECT_TIMESTAMP_BY_ID_QUERY, (item['id'],)).fetchone()[0]
            timestamp_receiver = receiver.timestamp()
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
```

#### Função de tratamento do método GET

A função `get_registro` manipula requisições para o endpoint `/registro` com o método `GET`. Ela retornará todos os registros cadastrados no banco do servidor (central).

```python
@app.get('/registro')
def get_registro():
    cur = get_db().cursor()
    cur.execute(SELECT_ALL_QUERY)
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
```

#### Execução do servidor

```python
if __name__ == "__main__":
    # conexão temporária com o banco local para criar tabelas a partir de schema
    with sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES) as init_con:
        with app.open_resource('schema.sql') as f:
            init_con.executescript(f.read().decode('utf8'))

    # execução da API Flask
    app.run(host=HOST_ADDRESS, port=HOST_PORT, debug=DEBUG)
```

### Clientes

O cliente possuirá um banco de dados SQLite local onde serão salvos os registros criados e editados.

O usuário poderá interagir com o cliente por meio de comandos.

- `[S]ync`: sincronizar o estado local do banco com o do servidor. Basicamente é feito um push (envio para o servidor) e um pull (busca do servidor) dos registros.
- `[I]nsert`: inserir um dado no banco local do cliente.
- `[E]dit`: editar um dado no banco local do cliente.
- `[V]iew`: visualizar estado do banco local.
- `[Q]uit`: terminar a execução da aplicação cliente.

Estrutura de arquivos:

```
client/
├─── app.py
├─── schema.sql
├─── requirements.txt
└─── Dockerfile
```

#### Imports

Para a implementação do servidor, serão utilizados alguns pacotes da biblioteca do Python.

```python
import sqlite3  # biblioteca SQLite para o python
import sys  # funções do sistema
from datetime import datetime, timezone  # utilitários de data e hora
import requests  # funções para realizar requisições HTTP, como GET e POST
import json  # utilitários para manipulação de JSON
from uuid import uuid4  # utilitários para geração de UUIDs
import os  # utilitários do sistema operacional
import re  # utilitários de regex
```

#### Constantes

Variáveis constantes, como nome do banco de dados e queries SQL.

```python
SERVER_HOST = os.getenv('SERVER_HOST', '127.0.0.1')
SERVER_PORT = os.getenv('SERVER_PORT', 5000)
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
SYNC_DATABASE_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES (:id, :value, :vector_clock, :timestamp)"
INSERT_VALUE_QUERY = "INSERT INTO registers (id, value, vector_clock, timestamp) VALUES (?, ?, ?, ?)"
SELECT_ALL_QUERY = "SELECT * FROM registers"
UPDATE_BY_ID_QUERY = "UPDATE registers SET value = ?, vector_clock = ?, timestamp = ? WHERE id = ?"
```

#### Definições de `converters` e `adapters` do SQLite

O SQLite é um banco de dados salvo em um arquivo. Portanto, ele possui restrições em relação a outros bancos de dados com processos dedicados.

Entre as restrições, estão os tipos que ele suporta. Em vista disso, são necessárias conversões e adaptações dos tipos que ele possui com os tipos que a linguagem Python possui, para simplificar a interação entre ambos.

```python
# tipo `timestamp` no banco será transformado em objeto `datetime` do Python
sqlite3.register_converter(
    "timestamp",
    lambda v: datetime.fromisoformat(v.decode()),
)

# tipo `datetime` do Python será transformado para `string` (timestamp) no banco
sqlite3.register_adapter(
    datetime,
    lambda dt: dt.isoformat(),
)

# tipo `json` no banco será transformado em objeto `dict` do Python
sqlite3.register_converter(
    "json",
    lambda v: json.loads(v.decode()),
)

# tipo `dict` do Python será transformado em `json` (text) no banco
sqlite3.register_adapter(
    dict,
    lambda d: json.dumps(d),
)
```

#### Conexão, instanciação e inicialização do banco de dados SQLite

Cria um conexão com o banco de dados SQLite, passando como parâmetros o nome do arquivo de banco de dados e uma configuração para usar os tipos (_converters_ e _adapters_) anteriormente definidos.

```python
# pega dado de entrada para definir nome do cliente
client_name_entry = str(input('Digite o nome do cliente: '))
client_name = re.sub(r'\W+', '', client_name_entry).lower()

con = sqlite3.connect(f'client_{client_name}.db', detect_types=sqlite3.PARSE_DECLTYPES)

# monta tabelas conforme arquivo de schema
with open('schema.sql') as f:
    con.executescript(f.read())

cur = con.cursor()
```

#### Função de envio dos dados para o banco central (push)

Esta função pega os registros criados localmente e os envia para o servidor por meio de uma request POST.

```python
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
```

#### Função de busca das informações para sincronização local (pull)

Esta função realizar uma request GET no servidor para atualizar o banco de dados local com os dados centrais.

```python
def pull():
    response = requests.get(f'{SERVER_URL}/registro')
    if response.status_code == 200:
        data = response.json()
        if 'registers' in data and len(data['registers']) > 0:
            cur.executemany(SYNC_DATABASE_QUERY, data['registers'])
            con.commit()
        else:
            print('Nenhum dado recebido do servidor.')
```

#### Função para inserção de dado localmente

Esta função insere um dado no banco de dados SQLite local.

```python
def insert():
    value: str = str(input('Digite um valor: '))
    cur.execute(INSERT_VALUE_QUERY, (str(uuid4()), value, {client_name: 1}, datetime.now(timezone.utc)))
    con.commit()
    print("Valor inserido localmente.")
```

#### Função para edição de dado localmente

A função `show_database` é uma função utilitária para desenhar em uma tabela os registros que estão contidos no banco de dados SQLite local.

A função `edit` realiza a alteração de um dado do banco de dados SQLite local, incrementando o Vector Clock.

```python
# função para desenhar uma tabela com os registros cadastrados
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
```

#### Função para visualizar os dados localmente

Utiliza a função `show_database()` definida anteriormente para mostrar o estado do banco de dados SQLite.

```python
def view():
    cur.execute(SELECT_ALL_QUERY)
    rows = cur.fetchall()
    show_database(rows)
```

#### Execução base da aplicação e interação com usuário

Este é o trecho de código que realiza a interação do usuário com o cliente, lendo os comandos e valores de entrada e realizando as operações de acordo.

```python
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
```

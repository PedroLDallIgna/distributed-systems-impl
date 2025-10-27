const sqlite3 = require('sqlite3').verbose();
const fs = require('fs');
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');
const readline = require('readline');

const SYNC_DATABASE_QUERY = "INSERT OR REPLACE INTO registers (id, value, vector_clock, timestamp) VALUES ($id, $value, $vector_clock, $timestamp)";
const INSERT_VALUE_QUERY = "INSERT INTO registers (id, value, vector_clock) VALUES (?, ?, ?)";

const db = new sqlite3.Database('client_b.db');

try {
    const schema = fs.readFileSync('schema.sql', 'utf8');
    db.exec(schema, (err) => {
        if (err) {
            console.error('Error creating database schema:', err);
            process.exit(1);
        }
        console.log('Database initialized successfully');
    });
} catch (error) {
    console.error('Error reading schema file:', error);
    process.exit(1);
}

const dbGet = (query, params) => new Promise((resolve, reject) => {
    db.all(query, params, (err, rows) => {
        if (err) reject(err);
        else resolve(rows);
    });
});

const dbRun = (query, params) => new Promise((resolve, reject) => {
    db.run(query, params, function(err) {
        if (err) reject(err);
        else resolve(this);
    });
});

async function push() {
    try {
        const rows = await dbGet("SELECT * FROM registers", []);
        const data = rows.map(row => ({
            id: row.id,
            value: row.value,
            vector_clock: JSON.parse(row.vector_clock),
            timestamp: row.timestamp
        }));

        if (data.length === 0) {
            console.log('Nada para sincronizar.');
            return;
        }

        console.log("enviando:", JSON.stringify(data));
        const response = await axios.post('http://localhost:5000/registro', { registers: data });
        if (response.status === 201) {
            console.log("Dados enviados ao servidor com sucesso.");
        }
    } catch (error) {
        console.error('Erro ao sincronizar:', error.message);
    }
}

async function pull() {
    try {
        const response = await axios.get('http://localhost:5000/registro');
        if (response.data.registers && response.data.registers.length > 0) {
            for (const register of response.data.registers) {
                await dbRun(SYNC_DATABASE_QUERY, {
                    $id: register.id,
                    $value: register.value,
                    $vector_clock: JSON.stringify(register.vector_clock),
                    $timestamp: register.timestamp
                });
            }
        } else {
            console.log('Nenhum dado recebido do servidor.');
        }
    } catch (error) {
        console.error('Erro ao puxar dados:', error.message);
    }
}

function showDatabase(rows) {
    if (rows.length === 0) {
        console.log('Nenhum registro para editar.');
        return;
    }
    console.log('='.repeat(120));
    console.log(`${'#'.padStart(3)} | ${'ID'.padEnd(38)} | ${'Valor'.padEnd(20)} | ${'VC'.padEnd(20)} | ${'Timestamp'.padEnd(27)}`);
    console.log('='.repeat(120));
    rows.forEach((row, i) => {
        console.log(`${String(i).padStart(3)} | ${row.id.padEnd(38)} | ${String(row.value).padEnd(20)} | ${row.vector_clock.padEnd(20)} | ${row.timestamp.padEnd(27)}`);
        console.log('-'.repeat(120));
    });
}

async function insert(rl) {
    const value = await new Promise(resolve => {
        rl.question('Digite um valor: ', resolve);
    });
    
    await dbRun(INSERT_VALUE_QUERY, [uuidv4(), value, JSON.stringify({CA: 1})]);
    console.log("Valor inserido localmente.");
}

async function edit(rl) {
    const rows = await dbGet("SELECT * FROM registers", []);
    showDatabase(rows);

    const index = await new Promise(resolve => {
        rl.question('Selecione o índice do registro a ser editado: ', resolve);
    });

    if (index < 0 || index >= rows.length) {
        console.log('Índice inválido.');
        return;
    }

    const newValue = await new Promise(resolve => {
        rl.question('Digite o novo valor: ', resolve);
    });

    const selectedRow = rows[index];
    const vc = JSON.parse(selectedRow.vector_clock);
    vc.CA = (vc.CA || 0) + 1;

    await dbRun(
        "UPDATE registers SET value = ?, vector_clock = ?, timestamp = ? WHERE id = ?",
        [newValue, JSON.stringify(vc), new Date().toISOString(), selectedRow.id]
    );

    console.log("Valor editado localmente.");
}

async function main() {
    console.log("Bem-vindo ao cliente B");
    console.log("Sincronizando com o servidor...");
    await push();
    await pull();
    console.log("Sincronização concluída.");
    console.log("Tudo pronto!");

    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    const showMenu = () => {
        console.log(`
    [S]ync
    [I]nsert
    [E]dit
    [H]elp
    [Q]uit`);
        return new Promise(resolve => {
            rl.question('Selecione uma opção: ', resolve);
        });
    };

    while (true) {
        const option = await showMenu();
        
        switch (option.toUpperCase()) {
            case 'S':
                await push();
                await pull();
                console.log("Sincronização concluída.");
                break;
            case 'I':
                await insert(rl);
                break;
            case 'E':
                await edit(rl);
                break;
            case 'Q':
                rl.close();
                db.close();
                process.exit(0);
        }
    }
}

main().catch(console.error);
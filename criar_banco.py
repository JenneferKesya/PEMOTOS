import sqlite3

# Criar um novo banco de dados SQLite
conn = sqlite3.connect('PEMOTO.BD.sql')  # Cria o banco de dados no mesmo diretório
cursor = conn.cursor()

# Criar as tabelas
cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS historico_perguntas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        pergunta TEXT NOT NULL,
        resposta TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS acessos_chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS motos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        link_simulacao TEXT NOT NULL
    );
''')

# Inserir dados de exemplo
cursor.execute('''
    INSERT INTO motos (nome, link_simulacao) VALUES
    ('POP 110i', 'https://consorcio.pernambucomotos.com.br/products/pop-110i'),
    ('CG 160 START', 'https://consorcio.pernambucomotos.com.br/products/cg-160-start'),
    ('BIZ 125 ES', 'https://consorcio.pernambucomotos.com.br/products/biz-125-es'),
    ('PCX', 'https://consorcio.pernambucomotos.com.br/products/pcx');
''')

# Confirmar as mudanças e fechar a conexão
conn.commit()
conn.close()

print("Banco de dados criado com sucesso.")

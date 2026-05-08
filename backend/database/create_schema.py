"""
Script para criação do banco de dados a partir do schema.sql.

Lê as credenciais do .env, cria o banco se não existir, e executa o schema.sql,
criando todas as tabelas e índices necessários.

Uso:
    python create_db.py
"""

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Carrega .env da pasta /backend/ (um nível acima de /backend/database/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_backend_dir / '.env')

# Caminho do schema.sql (mesma pasta deste script: /backend/database/)
SCHEMA_PATH = Path(__file__).resolve().parent / 'schema.sql'


def get_credentials():
    db_name = os.getenv('DB_NAME')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_host = os.getenv('DB_HOST')
    db_port = int(os.getenv('DB_PORT', 5432))

    missing = [k for k, v in {
        'DB_NAME': db_name, 'DB_USER': db_user,
        'DB_PASSWORD': db_password, 'DB_HOST': db_host
    }.items() if not v]

    if missing:
        print(f"[ERRO] Variáveis de ambiente faltando: {', '.join(missing)}")
        sys.exit(1)

    return db_name, db_user, db_password, db_host, db_port


def ensure_database_exists(db_name, db_user, db_password, db_host, db_port):
    """Conecta ao banco 'postgres' e cria o banco alvo se não existir."""
    admin_url = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/postgres"

    # isolation_level AUTOCOMMIT é necessário para CREATE DATABASE,
    # que não pode ser executado dentro de uma transação no PostgreSQL
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name}
        ).fetchone()

        if exists:
            print(f"[INFO] Banco '{db_name}' já existe, pulando criação.")
        else:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print(f"[OK] Banco '{db_name}' criado.")

    engine.dispose()


def run_schema(db_name, db_user, db_password, db_host, db_port):
    if not SCHEMA_PATH.exists():
        print(f"[ERRO] schema.sql não encontrado em: {SCHEMA_PATH}")
        sys.exit(1)

    schema_sql = SCHEMA_PATH.read_text(encoding='utf-8')
    url = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(url)

    print("[INFO] Executando schema.sql...")
    with engine.connect() as conn:
        conn.execute(text(schema_sql))
        conn.commit()

    print("[OK] Schema aplicado com sucesso!")
    print("     Tabelas: cameras, vagas, registros_historicos, logs_processamento")
    print("     Índices: idx_vagas_status, idx_historico_vaga")


if __name__ == '__main__':
    credentials = get_credentials()
    ensure_database_exists(*credentials)
    run_schema(*credentials)
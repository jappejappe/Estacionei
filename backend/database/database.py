"""
Módulo de abstração e conexão com o banco de dados.

Este script é responsável por toda a interação com o banco de dados PostgreSQL.
Ele utiliza a biblioteca python-dotenv para carregar as credenciais de um arquivo .env,
oferece uma classe `Database` que gerencia as conexões e simplifica a execução
de queries, e exporta uma instância única `db` para ser usada em toda a aplicação.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

# Carrega .env da pasta /backend/ (um nível acima de /backend/database/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_backend_dir / '.env')


class Database:
    """
    Classe handler para gerenciar a conexão e as operações com o banco de dados.

    Esta classe encapsula a lógica de conexão com o PostgreSQL, lendo as
    credenciais das variáveis de ambiente. Seu principal objetivo é fornecer um
    método `query` simplificado para executar comandos SQL de forma segura,
    gerenciando o ciclo de vida da conexão e do cursor automaticamente.
    """

    def __init__(self):
        """
        Inicializa a instância da classe Database.

        O construtor lê as variáveis de ambiente necessárias para a conexão
        com o banco de dados e cria um engine SQLAlchemy que será usado para
        estabelecer futuras conexões.

        NullPool é usado para evitar conexões persistentes entre requests,
        replicando o comportamento original de abrir/fechar a cada query.
        """
        db_name = os.getenv('DB_NAME')
        db_user = os.getenv('DB_USER')
        db_password = os.getenv('DB_PASSWORD')
        db_host = os.getenv('DB_HOST')
        db_port = int(os.getenv('DB_PORT', 5432))

        connection_url = (
            f"postgresql+psycopg://{db_user}:{db_password}"
            f"@{db_host}:{db_port}/{db_name}"
        )

        self.engine = create_engine(
            connection_url,
            poolclass=NullPool,
            connect_args={"options": "-c timezone=America/Sao_Paulo"}
        )

    def query(self, query: str, args: tuple = None):
        """
        Executa uma query SQL no banco de dados de forma segura.

        Este método abre uma conexão, executa a query fornecida e fecha a
        conexão. Ele usa parâmetros posicionais para prevenir ataques de SQL
        Injection. O comportamento do retorno varia de acordo com o tipo de
        query executada.

        Args:
            query (str): A string da query SQL a ser executada.
                         Use '%s' como placeholder para os parâmetros
                         (convertido internamente para o formato do SQLAlchemy).
            args (tuple, optional): Uma tupla contendo os valores para substituir
                                    os placeholders na query. Defaults to None.

        Raises:
            sqlalchemy.exc.SQLAlchemyError: Captura qualquer exceção relacionada
                ao banco de dados (ex: erro de sintaxe SQL, falha de conexão).

        Returns:
            list[dict]: Para queries `SELECT`, retorna uma lista de dicionários,
                        onde cada dicionário representa uma linha do resultado.
            int: Para queries `INSERT`, `UPDATE` ou `DELETE`, retorna o número
                 de linhas afetadas pela operação.
        """
        # Converte placeholders '%s' (psycopg) para ':p0, :p1...' (SQLAlchemy)
        params = {}
        if args:
            for i, value in enumerate(args):
                placeholder = f":p{i}"
                query = query.replace('%s', placeholder, 1)
                params[f"p{i}"] = value

        with self.engine.connect() as connection:
            result = connection.execute(text(query), params)
            connection.commit()

            query_stripped = query.strip().lower()
            if query_stripped.startswith('select') or 'returning' in query_stripped:
                rows = result.mappings().all()
                return [dict(row) for row in rows]

            return result.rowcount


# Instância única (singleton-like) da classe Database.
# Outros módulos da aplicação devem importar esta variável `db` para interagir
# com o banco de dados, garantindo que a configuração seja carregada uma única vez.
db = Database()
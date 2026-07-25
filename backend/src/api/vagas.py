from flask import Blueprint, jsonify, request
from database.database import db

# Criação do Blueprint com o prefixo /api definido no projeto
vagas_bp = Blueprint('vagas', __name__, url_prefix='/api')

@vagas_bp.route('/statusVagas/', methods=['GET'])
def get_status_vagas():
    """Retorna a lista completa de vagas e seus estados atuais."""
    try:
        query = "SELECT id, codigo_vaga, latitude, longitude, status, ultima_atualizacao FROM vagas"
        vagas = db.query(query)
        return jsonify(vagas), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@vagas_bp.route('/statusVagas/<int:id>', methods=['GET'])
def get_vaga_detalhes(id):
    """Retorna os detalhes e o status de uma vaga específica."""
    try:
        query = "SELECT * FROM vagas WHERE id = %s"
        vagas = db.query(query, (id,))
        if not vagas:
            return jsonify({"erro": "Vaga não encontrada"}), 404
        return jsonify(vagas[0]), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@vagas_bp.route('/vagas/proximas', methods=['GET'])
def get_vagas_proximas():
    """
    Filtra vagas disponíveis com base em coordenadas.
    Espera parâmetros de query: lat e lon.
    """
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    raio_km = request.args.get('raio', default=1.0, type=float)

    if lat is None or lon is None:
        return jsonify({"erro": "Parâmetros 'lat' e 'lon' são obrigatórios"}), 400

    try:
        # Usa subquery para calcular distância via Haversine e filtrar pelo raio
        query = """
            SELECT * FROM (
                SELECT id, codigo_vaga, latitude, longitude, status, ultima_atualizacao,
                (6371 * acos(
                    LEAST(1.0, cos(radians(%s)) * cos(radians(latitude)) * cos(radians(longitude) - radians(%s)) + 
                    sin(radians(%s)) * sin(radians(latitude)))
                )) AS distancia_km
                FROM vagas
            ) AS sub
            WHERE distancia_km <= %s
            ORDER BY distancia_km
        """
        args = (lat, lon, lat, raio_km)
        vagas = db.query(query, args)
        
        return jsonify(vagas), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@vagas_bp.route('/vagas/<int:id>/status', methods=['PUT'])
def update_status_vaga(id):
    """Atualiza manualmente o estado de uma vaga (uso administrativo)."""
    dados = request.get_json()
    if not dados or 'status' not in dados:
        return jsonify({"erro": "Campo 'status' é obrigatório (0 para livre, 1 para ocupada)"}), 400

    status = int(dados['status'])
    if status not in [0, 1]:
         return jsonify({"erro": "Status inválido"}), 400

    try:
        # Atualiza a vaga
        query_update = "UPDATE vagas SET status = %s, ultima_atualizacao = CURRENT_TIMESTAMP WHERE id = %s RETURNING *"
        resultado = db.query(query_update, (status, id))
        
        if not resultado:
             return jsonify({"erro": "Vaga não encontrada"}), 404
             
        # Insere no histórico manual
        db.query("INSERT INTO registros_historicos (vaga_id, status) VALUES (%s, %s)", (id, status))
        
        return jsonify({"mensagem": "Status atualizado com sucesso", "vaga": resultado[0]}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@vagas_bp.route('/historico/<int:vaga_id>', methods=['GET'])
def get_historico(vaga_id):
    """Retorna dados históricos de ocupação para análise urbana."""
    try:
        query = "SELECT * FROM registros_historicos WHERE vaga_id = %s ORDER BY data_hora DESC LIMIT 100"
        historico = db.query(query, (vaga_id,))
        return jsonify(historico), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
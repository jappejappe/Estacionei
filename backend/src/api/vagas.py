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
        
        return jsonify({"mensagem": "Status atualizado com sucesso", "vaga": resultado[0]}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
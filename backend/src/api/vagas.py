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
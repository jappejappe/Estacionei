import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request

dispositivos_bp = Blueprint('dispositivos', __name__, url_prefix='/api')

# Pasta temporária para salvar as imagens recebidas via POST
UPLOAD_FOLDER = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

@dispositivos_bp.route('/analisarFoto/', methods=['POST'])
def analisar_foto():
    """Recebe a imagem do hardware de borda."""
    if 'foto' not in request.files:
        return jsonify({"erro": "Nenhum arquivo de imagem 'foto' foi enviado"}), 400
        
    foto = request.files['foto']
    camera_id = request.form.get('camera_id')

    if foto.filename == '' or not camera_id:
        return jsonify({"erro": "Arquivo ou camera_id não informados"}), 400

    try:
        camera_id = int(camera_id)
        
        # Salva a imagem temporariamente
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cam{camera_id}_{timestamp}.jpg"
        filepath = UPLOAD_FOLDER / filename
        foto.save(filepath)

        return jsonify({
            "mensagem": "Imagem recebida com sucesso, aguardando integração com IA.",
            "filepath": str(filepath)
        }), 200

    except Exception as e:
        return jsonify({"erro": f"Falha no processamento: {str(e)}"}), 500
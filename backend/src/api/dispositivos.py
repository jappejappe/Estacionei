import os
from datetime import datetime
from pathlib import Path
from flask import Blueprint, jsonify, request
from database.database import db

# Importa o detector para processar a imagem recebida
# Ajuste de path já garantido no app.py
try:
    from computer_vision.detector import ParkingDetector
except ImportError:
    ParkingDetector = None  # Permite que a API rode sem o YOLOv8 instalado no ambiente local

dispositivos_bp = Blueprint('dispositivos', __name__, url_prefix='/api')

# Pasta temporária para salvar as imagens recebidas via POST
UPLOAD_FOLDER = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

@dispositivos_bp.route('/analisarFoto/', methods=['POST'])
def analisar_foto():
    """Recebe a imagem do hardware de borda e dispara o processamento da IA."""
    if 'foto' not in request.files:
        return jsonify({"erro": "Nenhum arquivo de imagem 'foto' foi enviado"}), 400
        
    foto = request.files['foto']
    camera_id = request.form.get('camera_id')

    if foto.filename == '' or not camera_id:
        return jsonify({"erro": "Arquivo ou camera_id não informados"}), 400

    try:
        camera_id = int(camera_id)
        
        # Salva a imagem temporariamente para o OpenCV/YOLO processar
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cam{camera_id}_{timestamp}.jpg"
        filepath = UPLOAD_FOLDER / filename
        foto.save(filepath)

        # Se o detector não estiver disponível (ex: rodando a API num ambiente sem GPU/Yolo), retorna sucesso falso
        if ParkingDetector is None:
             return jsonify({
                 "mensagem": "Imagem recebida, mas o módulo YOLO não está carregado neste servidor.",
                 "filepath": str(filepath)
             }), 200

        # Instancia e roda o pipeline do YOLOv8
        detector = ParkingDetector()
        
        # O process_frame já faz a persistência no banco (update em vagas, insert no historico e logs)
        resultados = detector.process_frame(image_path=str(filepath), camera_id=camera_id, save_annotated=True)

        return jsonify({
            "mensagem": "Processamento concluído com sucesso",
            "vagas_processadas": len(resultados),
            "resultados": resultados
        }), 200

    except Exception as e:
        return jsonify({"erro": f"Falha no processamento: {str(e)}"}), 500


@dispositivos_bp.route('/dispositivos/log', methods=['POST'])
def registrar_log():
    """Registra logs de operação e telemetria das câmeras de borda."""
    dados = request.get_json()
    camera_id = dados.get('camera_id')
    mensagem = dados.get('mensagem') # Usando o campo resultado_ia do banco temporariamente para texto de telemetria
    
    if not camera_id or not mensagem:
         return jsonify({"erro": "Campos 'camera_id' e 'mensagem' são obrigatórios"}), 400

    try:
        # Reutilizando a tabela logs_processamento para telemetria básica da câmera
        query = """
            INSERT INTO logs_processamento (camera_id, resultado_ia) 
            VALUES (%s, %s) RETURNING id
        """
        resultado = db.query(query, (camera_id, f"TELEMETRIA: {mensagem}"))
        return jsonify({"mensagem": "Log registrado com sucesso", "log_id": resultado}), 201
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
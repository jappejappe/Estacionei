import sys
from pathlib import Path
from flask import Flask

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from api.vagas import vagas_bp
from api.dispositivos import dispositivos_bp

def create_app():
    app = Flask(__name__)
    
    app.config['JSON_AS_ASCII'] = False
    
    # Registro dos Blueprints
    app.register_blueprint(vagas_bp)
    app.register_blueprint(dispositivos_bp)

    @app.route('/')
    def index():
        return {"status": "API Estacionei operando normalmente", "versao": "1.0"}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
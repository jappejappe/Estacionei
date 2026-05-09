# Estacionei
Sistema inteligente para acompanhar em tempo quase real o estado das vagas de estacionamento ao longo das cidades.

# Como Usar

## Ambiente virtual
> Criar e ativar venv

Windows
```sh
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements.txt
```

Linux
```sh
python -m venv venv
source ./venv/Scripts/Activate
pip install -r requirements.txt
```
## Método automático (painel de controle)

Windows
```sh
.\venv\Scripts\Activate
python backend/control_panel.py
```
Linux
```sh
source ./venv/Scripts/Activate
python backend/control_panel.py
```

## Método manual

### Selecionar ROIs
> Selecionar regiões de interesse (vagas de estacionamento)

Windows
```sh
.\venv\Scripts\Activate
python -m /backend/roi_selector.py
```

Linux
```sh
source ./venv/Scripts/Activate
python -m /backend/roi_selector.py
```


### Executar detecção
> Detecção de veículos e análise de vagas com uma imagem

Windows
```sh
.\venv\Scripts\Activate
cd backend
python -m computer_vision.detector imagem_teste.jpg --camera-id 1
```
Linux
```sh
source ./venv/Scripts/Activate
cd backend
python -m computer_vision.detector imagem_teste.jpg --camera-id 1
```

# IMPORTANTE

Antes de usar em produção:

Coloque o modelo yolov8n.pt em computer_vision/models/
Configure as coordenadas reais das vagas em computer_vision/config/rois.json
Certifique-se de que o banco de dados está rodando e as tabelas existem
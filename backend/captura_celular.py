"""
captura_celular.py — Agente de captura automática via USB (ADB).

Conecta ao celular Android via USB usando ADB, captura uma foto com a câmera
a cada 30 segundos e envia para o endpoint Flask /api/analisarFoto/ para
análise pelo modelo YOLOv8.

Pré-requisitos:
    - ADB instalado e no PATH (https://developer.android.com/tools/adb)
    - Celular com Depuração USB ativada e autorizado no PC
    - Flask rodando em http://localhost:1421
    - Camera_id configurado em rois.json

Uso:
    python captura_celular.py
    python captura_celular.py --camera-id 2 --intervalo 60
    python captura_celular.py --api-url http://192.168.1.10:1421
"""

import argparse
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).resolve().parent / "captura_celular.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("captura_celular")


# ---------------------------------------------------------------------------
# Constantes padrão
# ---------------------------------------------------------------------------
DEFAULT_CAMERA_ID = 1
DEFAULT_INTERVALO_SEGUNDOS = 30
DEFAULT_API_URL = "http://localhost:1421"

# Pasta local temporária onde as fotos capturadas serão salvas antes do envio
CAPTURE_DIR = Path(__file__).resolve().parent / "captures"
CAPTURE_DIR.mkdir(exist_ok=True)

# Caminho no dispositivo Android onde a câmera salva as fotos
ANDROID_PHOTO_PATH = "/sdcard/estacionei_capture.jpg"


# ---------------------------------------------------------------------------
# Funções ADB
# ---------------------------------------------------------------------------

def verificar_adb() -> bool:
    """Verifica se o ADB está instalado e acessível no PATH."""
    if shutil.which("adb") is None:
        logger.error(
            "ADB não encontrado no PATH.\n"
            "Instale o Android SDK Platform Tools: "
            "https://developer.android.com/tools/releases/platform-tools"
        )
        return False
    return True


def verificar_dispositivo() -> str | None:
    """
    Verifica se há um dispositivo Android conectado via USB.

    Returns:
        ID do dispositivo se conectado, None caso contrário.
    """
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().splitlines()

        # A primeira linha é o cabeçalho "List of devices attached"
        devices = [
            line.split("\t")[0]
            for line in lines[1:]
            if "\tdevice" in line
        ]

        if not devices:
            logger.warning(
                "Nenhum dispositivo Android conectado. "
                "Verifique: Depuração USB ativada + cabo conectado + PC autorizado no celular."
            )
            return None

        device_id = devices[0]
        if len(devices) > 1:
            logger.warning(
                "%d dispositivos encontrados. Usando o primeiro: %s",
                len(devices),
                device_id,
            )

        logger.info("Dispositivo conectado: %s", device_id)
        return device_id

    except subprocess.TimeoutExpired:
        logger.error("ADB demorou muito para responder. Verifique a conexão USB.")
        return None
    except Exception as e:
        logger.error("Erro ao verificar dispositivo ADB: %s", e)
        return None


def capturar_foto_adb(device_id: str, destino_local: Path) -> bool:
    """
    Captura uma foto do celular Android via ADB.

    Estratégia:
        1. Usa intent Android para abrir a câmera e tirar foto.
        2. Aguarda 3s para câmera processar.
        3. Copia a foto para o PC com adb pull.
        Fallback: busca a última foto da galeria DCIM/Camera.

    Args:
        device_id: ID do dispositivo ADB.
        destino_local: Caminho local onde a imagem será salva.

    Returns:
        True se a captura foi bem-sucedida, False caso contrário.
    """
    adb = ["adb", "-s", device_id]

    try:
        # Abre o app de câmera nativo (sem tela de confirmação)
        logger.info("Abrindo o app de câmera no dispositivo %s...", device_id)
        subprocess.run(
            adb + [
                "shell", "am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA"
            ],
            capture_output=True,
            timeout=10,
        )

        # Aguarda o app de câmera abrir e realizar o foco automático
        time.sleep(3)

        # Simula o botão de tirar foto. 
        # Enviamos KEYCODE_CAMERA (27) e KEYCODE_VOLUME_DOWN (25) porque diferentes 
        # fabricantes mapeiam o botão do obturador de formas diferentes.
        logger.info("Pressionando botão de captura...")
        subprocess.run(
            adb + ["shell", "input", "keyevent", "27"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(0.5)
        subprocess.run(
            adb + ["shell", "input", "keyevent", "25"],
            capture_output=True,
            timeout=5,
        )

        # Aguarda a câmera processar e salvar a foto na galeria
        time.sleep(2)

        # Volta para a tela anterior (fecha o app de câmera)
        subprocess.run(
            adb + ["shell", "input", "keyevent", "KEYCODE_BACK"],
            capture_output=True,
            timeout=5,
        )

        # A foto foi salva na galeria padrão do celular.
        # Vamos buscar a última foto da galeria e copiar para o PC.
        logger.info("Buscando a foto recém-capturada na galeria...")
        return _fallback_ultima_foto(adb, destino_local)

    except subprocess.TimeoutExpired as e:
        logger.error("Timeout ao capturar foto via ADB: %s", e)
        return False
    except Exception as e:
        logger.error("Erro ao capturar foto: %s", e)
        return False


def _fallback_ultima_foto(adb: list[str], destino_local: Path) -> bool:
    """
    Fallback: busca a foto mais recente na galeria do Android (DCIM/Camera).
    """
    try:
        result = subprocess.run(
            adb + ["shell", "ls", "-t", "/sdcard/DCIM/Camera/"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            logger.error("Nenhuma foto encontrada em /sdcard/DCIM/Camera/")
            return False

        fotos = [
            f for f in result.stdout.strip().splitlines()
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

        if not fotos:
            logger.error("Nenhuma imagem encontrada na galeria do dispositivo.")
            return False

        foto_mais_recente = f"/sdcard/DCIM/Camera/{fotos[0]}"
        logger.info("Usando foto mais recente: %s", foto_mais_recente)

        pull_result = subprocess.run(
            adb + ["pull", foto_mais_recente, str(destino_local)],
            capture_output=True,
            timeout=20,
        )

        return pull_result.returncode == 0

    except Exception as e:
        logger.error("Erro no fallback de galeria: %s", e)
        return False


# ---------------------------------------------------------------------------
# Envio para a API Flask
# ---------------------------------------------------------------------------

def enviar_para_api(
    imagem_path: Path,
    camera_id: int,
    api_url: str,
) -> bool:
    """
    Envia a foto capturada para o endpoint Flask /api/analisarFoto/.
    """
    endpoint = f"{api_url}/api/analisarFoto/"

    try:
        with open(imagem_path, "rb") as f:
            files = {"foto": (imagem_path.name, f, "image/jpeg")}
            data = {"camera_id": str(camera_id)}

            logger.info(
                "Enviando foto para %s (camera_id=%d)...", endpoint, camera_id
            )

            response = requests.post(
                endpoint,
                files=files,
                data=data,
                timeout=120,  # YOLOv8 pode demorar alguns segundos
            )

        if response.status_code == 200:
            resultado = response.json()
            vagas = resultado.get("vagas_processadas", 0)
            logger.info(
                "Processamento concluido | %d vagas analisadas | %s",
                vagas,
                resultado.get("mensagem", ""),
            )
            return True
        else:
            logger.error(
                "Erro na API: HTTP %d | %s",
                response.status_code,
                response.text[:200],
            )
            return False

    except requests.ConnectionError:
        logger.error(
            "Nao foi possivel conectar ao Flask em %s. "
            "Certifique-se de que o servidor esta rodando.",
            api_url,
        )
        return False
    except requests.Timeout:
        logger.error("Timeout ao aguardar resposta da API (>120s).")
        return False
    except Exception as e:
        logger.error("Erro inesperado ao enviar para API: %s", e)
        return False


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def loop_captura(camera_id: int, intervalo: int, api_url: str) -> None:
    """
    Loop infinito que captura uma foto e envia para análise a cada `intervalo` segundos.
    """
    logger.info("=" * 60)
    logger.info("  Estacionei — Agente de Captura USB")
    logger.info("  Camera ID  : %d", camera_id)
    logger.info("  Intervalo  : %ds", intervalo)
    logger.info("  API URL    : %s", api_url)
    logger.info("=" * 60)

    ciclo = 0

    while True:
        ciclo += 1
        logger.info("--- Ciclo #%d | %s ---", ciclo, datetime.now().strftime("%H:%M:%S"))

        # 1. Verifica dispositivo conectado
        device_id = verificar_dispositivo()
        if device_id is None:
            logger.warning(
                "Aguardando conexao do dispositivo... (proxima tentativa em %ds)", intervalo
            )
            time.sleep(intervalo)
            continue

        # 2. Define o caminho local desta captura
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        foto_local = CAPTURE_DIR / f"cam{camera_id}_{timestamp}.jpg"

        # 3. Captura a foto via ADB
        if not capturar_foto_adb(device_id, foto_local):
            logger.warning("Falha na captura. Pulando ciclo #%d.", ciclo)
            time.sleep(intervalo)
            continue

        # 4. Envia para análise no Flask
        enviar_para_api(foto_local, camera_id, api_url)

        # 5. Aguarda o próximo ciclo
        logger.info("Proxima captura em %d segundos...\n", intervalo)
        time.sleep(intervalo)


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Estacionei — Agente de captura de fotos via USB (ADB)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python captura_celular.py
  python captura_celular.py --camera-id 1 --intervalo 30
  python captura_celular.py --camera-id 2 --api-url http://192.168.1.10:1421
        """,
    )
    parser.add_argument(
        "--camera-id",
        type=int,
        default=DEFAULT_CAMERA_ID,
        help=f"ID da câmera configurada no rois.json (padrão: {DEFAULT_CAMERA_ID})",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=DEFAULT_INTERVALO_SEGUNDOS,
        help=f"Intervalo em segundos entre capturas (padrão: {DEFAULT_INTERVALO_SEGUNDOS})",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"URL base do servidor Flask (padrão: {DEFAULT_API_URL})",
    )

    args = parser.parse_args()

    if not verificar_adb():
        sys.exit(1)

    try:
        loop_captura(
            camera_id=args.camera_id,
            intervalo=args.intervalo,
            api_url=args.api_url,
        )
    except KeyboardInterrupt:
        logger.info("\nCaptura encerrada pelo usuário.")
        sys.exit(0)

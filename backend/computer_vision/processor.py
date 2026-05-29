"""
Módulo de pré-processamento de imagem para o sistema Estacionei.

Responsável por carregar, converter e redimensionar os frames capturados
pelo hardware (1280x720 BGR) para o formato exigido pelo YOLOv8 (640x640 RGB),
além de fornecer funções de visualização para monitoramento.
"""

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes de pré-processamento
# ---------------------------------------------------------------------------
TARGET_SIZE: tuple[int, int] = (640, 640)
"""Dimensão alvo (largura, altura) para a entrada do YOLOv8."""

ORIGINAL_SIZE: tuple[int, int] = (1280, 720)
"""Dimensão original esperada das fotos do hardware."""


# ---------------------------------------------------------------------------
# Funções de carregamento
# ---------------------------------------------------------------------------
def load_image(image_path: str) -> np.ndarray | None:
    """
    Carrega uma imagem do disco usando OpenCV.

    Args:
        image_path: Caminho absoluto ou relativo para o arquivo de imagem.

    Returns:
        Frame BGR como np.ndarray, ou None se o carregamento falhar.
    """
    path = Path(image_path)

    if not path.exists():
        logger.error("Arquivo de imagem não encontrado: %s", image_path)
        return None

    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)

    if frame is None:
        logger.error("OpenCV não conseguiu decodificar a imagem: %s", image_path)
        return None

    logger.info(
        "Imagem carregada: %s | Dimensões: %dx%d",
        path.name, frame.shape[1], frame.shape[0],
    )
    return frame


# ---------------------------------------------------------------------------
# Funções de conversão e redimensionamento
# ---------------------------------------------------------------------------
def bgr_to_rgb(frame: np.ndarray) -> np.ndarray:
    """
    Converte um frame de BGR (padrão OpenCV) para RGB (exigência do YOLOv8).

    Args:
        frame: Imagem em formato BGR (H, W, 3).

    Returns:
        Imagem convertida para RGB (H, W, 3).
    """
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def resize_frame(
    frame: np.ndarray,
    target_size: tuple[int, int] = TARGET_SIZE,
) -> np.ndarray:
    """
    Redimensiona o frame para as dimensões alvo.

    Utiliza interpolação INTER_LINEAR para redução (padrão para downscale com
    boa relação qualidade/velocidade).

    Args:
        frame: Imagem de entrada (H, W, 3).
        target_size: Tupla (largura, altura) do tamanho alvo.

    Returns:
        Imagem redimensionada (target_h, target_w, 3).
    """
    return cv2.resize(frame, target_size, interpolation=cv2.INTER_LINEAR)


def preprocess(
    image_path: str,
    target_size: tuple[int, int] = TARGET_SIZE,
) -> np.ndarray | None:
    """
    Pipeline completo de pré-processamento: carrega → BGR→RGB → redimensiona.

    Este é o ponto de entrada principal para preparar um frame para inferência.

    Args:
        image_path: Caminho para o arquivo de imagem.
        target_size: Dimensões alvo (largura, altura).

    Returns:
        Imagem pronta para inferência (RGB, target_size), ou None em caso de erro.
    """
    frame = load_image(image_path)
    if frame is None:
        return None

    frame_rgb = bgr_to_rgb(frame)
    frame_resized = resize_frame(frame_rgb, target_size)

    logger.info(
        "Pré-processamento concluído: %dx%d → %dx%d (RGB)",
        ORIGINAL_SIZE[0], ORIGINAL_SIZE[1],
        target_size[0], target_size[1],
    )
    return frame_resized


# ---------------------------------------------------------------------------
# Pré-processamento de ROI via OpenCV (preparação para o YOLO)
# ---------------------------------------------------------------------------
def crop_roi(
    frame_bgr: np.ndarray,
    roi_coords: list[list[int]],
    output_size: int = 640,
) -> np.ndarray:
    """
    Recorta uma ROI do frame original e redimensiona com letterbox (sem filtros).

    Usado para o YOLO analisar a imagem crua da vaga, ampliada de perto.

    Args:
        frame_bgr: Frame original em BGR.
        roi_coords: Lista de 4 pontos [[x,y], ...] do polígono da vaga.
        output_size: Tamanho quadrado de saída (padrão: 640).

    Returns:
        Imagem BGR recortada e redimensionada (output_size x output_size).
    """
    poly = np.array(roi_coords, dtype=np.int32)

    x, y, w, h = cv2.boundingRect(poly)

    img_h, img_w = frame_bgr.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = min(w, img_w - x)
    h = min(h, img_h - y)

    crop = frame_bgr[y:y+h, x:x+w].copy()

    if crop.size == 0:
        return np.zeros((output_size, output_size, 3), dtype=np.uint8)

    # Redimensiona mantendo proporção (letterbox)
    scale = output_size / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Padding para ficar quadrado (cinza 114 = padrão YOLO)
    canvas = np.full((output_size, output_size, 3), 114, dtype=np.uint8)
    pad_x = (output_size - new_w) // 2
    pad_y = (output_size - new_h) // 2
    canvas[pad_y:pad_y+new_h, pad_x:pad_x+new_w] = resized

    return canvas


def enhance_roi_crop(
    frame_bgr: np.ndarray,
    roi_coords: list[list[int]],
    output_size: int = 640,
) -> np.ndarray:
    """
    Recorta uma ROI, aplica melhorias de imagem via OpenCV e redimensiona.

    Diferente de crop_roi(), esta versão aplica:
    - CLAHE (equalização adaptativa de contraste)
    - Sharpening (filtro de nitidez)

    Usado como segundo passe para ajudar o YOLO a enxergar veículos em
    condições difíceis (baixo contraste, vista aérea, sombras).

    Args:
        frame_bgr: Frame original em BGR.
        roi_coords: Lista de 4 pontos [[x,y], ...] do polígono da vaga.
        output_size: Tamanho quadrado de saída (padrão: 640).

    Returns:
        Imagem BGR recortada, melhorada e redimensionada (output_size x output_size).
    """
    poly = np.array(roi_coords, dtype=np.int32)

    x, y, w, h = cv2.boundingRect(poly)

    img_h, img_w = frame_bgr.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = min(w, img_w - x)
    h = min(h, img_h - y)

    crop = frame_bgr[y:y+h, x:x+w].copy()

    if crop.size == 0:
        return np.zeros((output_size, output_size, 3), dtype=np.uint8)

    # CLAHE — Equalização adaptativa de contraste
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    l_enhanced = clahe.apply(l_channel)
    lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
    crop = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # Sharpening — Aumenta a nitidez para realçar contornos do veículo
    sharpen_kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0],
    ], dtype=np.float32)
    crop = cv2.filter2D(crop, -1, sharpen_kernel)

    # Redimensiona mantendo proporção (letterbox)
    scale = output_size / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((output_size, output_size, 3), 114, dtype=np.uint8)
    pad_x = (output_size - new_w) // 2
    pad_y = (output_size - new_h) // 2
    canvas[pad_y:pad_y+new_h, pad_x:pad_x+new_w] = resized

    return canvas


# ---------------------------------------------------------------------------
# Funções de visualização (monitoramento)
# ---------------------------------------------------------------------------
_COLOR_LIVRE: tuple[int, int, int] = (0, 200, 0)      # Verde
_COLOR_OCUPADA: tuple[int, int, int] = (0, 0, 220)     # Vermelho
_COLOR_BBOX: tuple[int, int, int] = (255, 200, 0)      # Ciano/Amarelo
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_rois(
    frame: np.ndarray,
    rois: list[dict],
    statuses: dict[int, int],
) -> np.ndarray:
    """
    Desenha os polígonos das ROIs (vagas) sobre o frame com cores de status.

    Cada ROI recebe:
    - Verde (Livre) se status == 0
    - Vermelho (Ocupada) se status == 1
    - Rótulo com código da vaga e status

    Args:
        frame: Imagem base (BGR) onde as ROIs serão desenhadas.
               Uma cópia é criada internamente para não alterar o original.
        rois: Lista de dicts com as ROIs. Cada dict deve conter:
              - "vaga_id" (int)
              - "codigo_vaga" (str)
              - "coords" (list[list[int]]): 4 pontos [[x,y], ...] do polígono.
        statuses: Dicionário {vaga_id: status} onde status é 0 (livre) ou 1 (ocupada).

    Returns:
        Cópia do frame com as ROIs desenhadas.
    """
    annotated = frame.copy()

    for roi in rois:
        vaga_id = roi["vaga_id"]
        codigo = roi.get("codigo_vaga", f"V{vaga_id}")
        coords = np.array(roi["coords"], dtype=np.int32)

        status = statuses.get(vaga_id, 0)
        color = _COLOR_OCUPADA if status == 1 else _COLOR_LIVRE
        label = f"{codigo}: {'Ocupada' if status == 1 else 'Livre'}"

        # Desenha o polígono da vaga
        cv2.polylines(annotated, [coords], isClosed=True, color=color, thickness=2)

        # Preenche com transparência
        overlay = annotated.copy()
        cv2.fillPoly(overlay, [coords], color)
        cv2.addWeighted(overlay, 0.25, annotated, 0.75, 0, annotated)

        # Rótulo acima do ponto superior esquerdo
        top_left = coords.min(axis=0)
        label_pos = (int(top_left[0]), int(top_left[1]) - 8)
        cv2.putText(
            annotated, label, label_pos,
            _FONT, 0.45, color, 1, cv2.LINE_AA,
        )

    return annotated


def draw_detections(
    frame: np.ndarray,
    detections: list[dict],
) -> np.ndarray:
    """
    Desenha as bounding boxes das detecções YOLO sobre o frame.

    Args:
        frame: Imagem base (BGR).
        detections: Lista de dicts, cada um contendo:
                    - "bbox" (tuple): (x1, y1, x2, y2)
                    - "confidence" (float): Confiança da detecção
                    - "class_name" (str, opcional): Nome da classe detectada

    Returns:
        Cópia do frame com as detecções desenhadas.
    """
    annotated = frame.copy()

    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        conf = det.get("confidence", 0.0)
        class_name = det.get("class_name", "carro")

        cv2.rectangle(annotated, (x1, y1), (x2, y2), _COLOR_BBOX, 2)

        label = f"{class_name} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(label, _FONT, 0.45, 1)
        cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), _COLOR_BBOX, -1)
        cv2.putText(
            annotated, label, (x1 + 2, y1 - 4),
            _FONT, 0.45, (0, 0, 0), 1, cv2.LINE_AA,
        )

    return annotated


def save_annotated_frame(
    frame: np.ndarray,
    output_path: str,
) -> bool:
    """
    Salva um frame anotado no disco para fins de monitoramento.

    Args:
        frame: Imagem anotada (BGR).
        output_path: Caminho de saída para o arquivo.

    Returns:
        True se salvo com sucesso, False caso contrário.
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        success = cv2.imwrite(output_path, frame)
        if success:
            logger.info("Frame anotado salvo em: %s", output_path)
        else:
            logger.error("Falha ao salvar frame anotado: %s", output_path)
        return success
    except Exception as e:
        logger.error("Erro ao salvar frame anotado: %s", e)
        return False

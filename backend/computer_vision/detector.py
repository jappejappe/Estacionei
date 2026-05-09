"""
Módulo de detecção de veículos e análise de ocupação de vagas — Estacionei.

Carrega o modelo YOLOv8, executa inferência sobre frames pré-processados,
calcula a interseção (IoA) entre bounding boxes e ROIs das vagas, e persiste
os resultados no banco de dados PostgreSQL via database.py.

Fluxo principal:
    ParkingDetector.process_frame(image_path, camera_id)
        → preprocess → detect → evaluate → persist → annotate
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Ajuste de sys.path para importar database.py de backend/database/
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from database.database import db  # noqa: E402
from computer_vision.processor import (  # noqa: E402
    bgr_to_rgb,
    draw_detections,
    draw_rois,
    load_image,
    resize_frame,
    save_annotated_frame,
)

# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------
_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "detection.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_VEHICLE_CLASSES: set[int] = {2, 3, 5, 7, 67}
"""IDs de classes no COCO: 2=car, 3=motorcycle, 5=bus, 7=truck, 67=cell phone (Workaround para o YOLOv8n)."""

_DEFAULT_MODEL_PATH: str = str(
    Path(__file__).resolve().parent / "models" / "yolov8n.pt"
)

_DEFAULT_CONFIG_PATH: str = str(
    Path(__file__).resolve().parent / "config" / "rois.json"
)

_ANNOTATED_DIR: str = str(
    Path(__file__).resolve().parent / "output"
)


class ParkingDetector:
    """
    Detector de ocupação de vagas de estacionamento usando YOLOv8.

    Encapsula o modelo YOLO, a configuração de ROIs e a lógica de avaliação
    de ocupação via IoA (Intersection over Area).

    Attributes:
        model: Instância do modelo YOLO carregado.
        ioa_threshold: Limiar mínimo de IoA para considerar uma vaga ocupada.
        config_path: Caminho para o arquivo rois.json.
        confidence_threshold: Confiança mínima para aceitar uma detecção YOLO.
    """

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL_PATH,
        config_path: str = _DEFAULT_CONFIG_PATH,
        ioa_threshold: float = 0.3,
        confidence_threshold: float = 0.5,
    ) -> None:
        """
        Inicializa o detector carregando o modelo YOLOv8.

        Args:
            model_path: Caminho para o arquivo .pt do modelo YOLOv8.
            config_path: Caminho para o rois.json com coordenadas das vagas.
            ioa_threshold: Limiar de IoA (0.0–1.0) para marcar vaga como ocupada.
            confidence_threshold: Confiança mínima do YOLO (0.0–1.0).

        Raises:
            FileNotFoundError: Se o arquivo do modelo não existir.
            RuntimeError: Se o modelo não puder ser carregado.
        """
        # Importação tardia para evitar erro se ultralytics não estiver instalado
        # em contextos de teste do processor.py
        from ultralytics import YOLO

        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(
                f"Modelo YOLOv8 não encontrado em: {model_path}\n"
                f"Baixe o modelo em: https://github.com/ultralytics/assets/releases"
            )

        logger.info("Carregando modelo YOLOv8 de: %s", model_path)
        try:
            self.model: Any = YOLO(str(model_file))
            logger.info("Modelo YOLOv8 carregado com sucesso.")
        except Exception as e:
            raise RuntimeError(f"Falha ao carregar modelo YOLOv8: {e}") from e

        self.ioa_threshold = ioa_threshold
        self.confidence_threshold = confidence_threshold
        self.config_path = config_path

    # ------------------------------------------------------------------
    # Carregamento de ROIs
    # ------------------------------------------------------------------
    def load_rois(self, camera_id: int) -> list[dict]:
        """
        Carrega as ROIs de um camera_id específico a partir do rois.json.

        Args:
            camera_id: ID da câmera no banco de dados.

        Returns:
            Lista de dicts, cada um com:
            - "vaga_id" (int)
            - "codigo_vaga" (str)
            - "coords" (list[list[int]])

        Raises:
            FileNotFoundError: Se o arquivo de configuração não existir.
            KeyError: Se o camera_id não existir na configuração.
        """
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração de ROIs não encontrado: {self.config_path}"
            )

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        camera_key = str(camera_id)
        if camera_key not in config.get("cameras", {}):
            raise KeyError(
                f"Camera ID {camera_id} não encontrada no arquivo de configuração. "
                f"Câmeras disponíveis: {list(config.get('cameras', {}).keys())}"
            )

        rois = config["cameras"][camera_key]["rois"]
        logger.info(
            "ROIs carregadas: câmera %d → %d vagas", camera_id, len(rois)
        )
        return rois

    # ------------------------------------------------------------------
    # Detecção de veículos
    # ------------------------------------------------------------------
    def detect_vehicles(self, frame_bgr: np.ndarray, target_size: tuple[int, int] = (640, 640)) -> list[dict]:
        """
        Executa inferência YOLOv8 na imagem original (para melhor precisão)
        e mapeia as bounding boxes para a escala do ROI (640x640). O YOLOv8
        espera BGR nativamente quando passado um array do OpenCV.

        Args:
            frame_bgr: Imagem original BGR (sem redimensionamento).
            target_size: Tamanho para o qual as bounding boxes serão escalonadas.

        Returns:
            Lista de detecções.
        """
        orig_h, orig_w = frame_bgr.shape[:2]
        
        results = self.model(
            frame_bgr,
            conf=self.confidence_threshold,
            verbose=False,
        )
        result = results[0]

        scale_x = target_size[0] / orig_w
        scale_y = target_size[1] / orig_h

        detections: list[dict] = []
        for box in result.boxes:
            class_id = int(box.cls[0])

            # Filtra apenas veículos (carro, moto, ônibus, caminhão)
            if class_id not in _VEHICLE_CLASSES:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            
            # Escalonando as coordenadas para 640x640 para bater com o ROI
            x1_scaled = int(x1 * scale_x)
            y1_scaled = int(y1 * scale_y)
            x2_scaled = int(x2 * scale_x)
            y2_scaled = int(y2 * scale_y)

            confidence = float(box.conf[0])

            detections.append({
                "bbox": (x1_scaled, y1_scaled, x2_scaled, y2_scaled),
                "confidence": confidence,
                "class_id": class_id,
                "class_name": result.names[class_id],
            })

        logger.info("Detecções YOLO: %d veículos encontrados.", len(detections))
        return detections

    # ------------------------------------------------------------------
    # Cálculo de IoA (Intersection over Area)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_ioa(
        bbox: tuple[int, int, int, int],
        roi_coords: list[list[int]],
    ) -> float:
        """
        Calcula a razão Intersection over Area (IoA) entre uma bounding box
        retangular e um polígono ROI.

        IoA = Área(Interseção) / Área(ROI)

        Utiliza IoA em vez de IoU porque uma vaga pequena pode ser totalmente
        coberta por um carro grande — o IoA captura isso corretamente.

        Args:
            bbox: Bounding box do carro (x1, y1, x2, y2).
            roi_coords: Lista de 4 pontos [[x,y], ...] do polígono da vaga.

        Returns:
            Valor de IoA entre 0.0 e 1.0.
        """
        # Converte a bounding box em polígono retangular
        x1, y1, x2, y2 = bbox
        bbox_poly = np.array([
            [x1, y1], [x2, y1], [x2, y2], [x1, y2],
        ], dtype=np.float32)

        roi_poly = np.array(roi_coords, dtype=np.float32)

        # Calcula a interseção entre os dois polígonos convexos
        intersection_result = cv2.intersectConvexConvex(bbox_poly, roi_poly)

        # cv2.intersectConvexConvex retorna (area, pontos_interseção)
        intersection_area = intersection_result[0]

        if intersection_area <= 0:
            return 0.0

        # Área do polígono ROI
        roi_area = cv2.contourArea(roi_poly)

        if roi_area <= 0:
            return 0.0

        ioa = intersection_area / roi_area
        return min(ioa, 1.0)

    # ------------------------------------------------------------------
    # Avaliação de ocupação
    # ------------------------------------------------------------------
    def evaluate_occupancy(
        self,
        detections: list[dict],
        rois: list[dict],
    ) -> dict[int, int]:
        """
        Para cada ROI/vaga, verifica se alguma detecção a intercepta
        acima do limiar de IoA.

        Args:
            detections: Lista de detecções retornada por detect_vehicles().
            rois: Lista de ROIs retornada por load_rois().

        Returns:
            Dicionário {vaga_id: status} onde:
            - 0 = Livre (nenhuma detecção intercepta a ROI significativamente)
            - 1 = Ocupada (pelo menos uma detecção supera o limiar de IoA)
        """
        statuses: dict[int, int] = {}

        for roi in rois:
            vaga_id = roi["vaga_id"]
            roi_coords = roi["coords"]
            status = 0  # Livre por padrão

            for det in detections:
                ioa = self.compute_ioa(det["bbox"], roi_coords)

                if ioa >= self.ioa_threshold:
                    status = 1  # Ocupada
                    logger.debug(
                        "Vaga %d: IoA=%.2f (>= %.2f) → OCUPADA",
                        vaga_id, ioa, self.ioa_threshold,
                    )
                    break

            statuses[vaga_id] = status

        livres = sum(1 for s in statuses.values() if s == 0)
        ocupadas = sum(1 for s in statuses.values() if s == 1)
        logger.info(
            "Avaliação de ocupação: %d livres, %d ocupadas (de %d vagas)",
            livres, ocupadas, len(rois),
        )

        return statuses

    # ------------------------------------------------------------------
    # Persistência no banco de dados
    # ------------------------------------------------------------------
    def persist_results(
        self,
        camera_id: int,
        image_path: str,
        results: dict[int, int],
        detections: list[dict],
        elapsed_time: float,
    ) -> None:
        """
        Persiste os resultados da detecção no banco de dados PostgreSQL.

        Operações executadas:
        1. UPDATE vagas SET status, ultima_atualizacao para cada vaga processada.
        2. INSERT INTO registros_historicos para cada vaga.
        3. INSERT INTO logs_processamento com metadados da inferência.

        Args:
            camera_id: ID da câmera que capturou a imagem.
            image_path: Caminho da imagem processada.
            results: Dicionário {vaga_id: status} retornado por evaluate_occupancy().
            detections: Lista de detecções retornada por detect_vehicles().
            elapsed_time: Tempo total de processamento em segundos.
        """
        agora = datetime.now()

        # --- 1. Atualiza o status de cada vaga ---
        for vaga_id, status in results.items():
            try:
                db.query(
                    "UPDATE vagas SET status = %s, ultima_atualizacao = %s WHERE id = %s",
                    (status, agora, vaga_id),
                )
            except Exception as e:
                logger.error("Erro ao atualizar vaga %d: %s", vaga_id, e)

        # --- 2. Insere registros históricos ---
        for vaga_id, status in results.items():
            try:
                db.query(
                    "INSERT INTO registros_historicos (vaga_id, status, data_hora) "
                    "VALUES (%s, %s, %s)",
                    (vaga_id, status, agora),
                )
            except Exception as e:
                logger.error(
                    "Erro ao inserir registro histórico para vaga %d: %s",
                    vaga_id, e,
                )

        # --- 3. Insere log de processamento ---
        resultado_ia = json.dumps({
            "total_deteccoes": len(detections),
            "confianca_media": (
                round(
                    sum(d["confidence"] for d in detections) / len(detections), 4
                )
                if detections
                else 0.0
            ),
            "vagas_processadas": len(results),
            "vagas_ocupadas": sum(1 for s in results.values() if s == 1),
            "vagas_livres": sum(1 for s in results.values() if s == 0),
            "tempo_processamento_s": round(elapsed_time, 3),
            "ioa_threshold": self.ioa_threshold,
            "confidence_threshold": self.confidence_threshold,
        }, ensure_ascii=False)

        try:
            db.query(
                "INSERT INTO logs_processamento "
                "(camera_id, data_hora, caminho_imagem, resultado_ia) "
                "VALUES (%s, %s, %s, %s)",
                (camera_id, agora, image_path, resultado_ia),
            )
        except Exception as e:
            logger.error("Erro ao inserir log de processamento: %s", e)

        logger.info(
            "Resultados persistidos: %d vagas atualizadas, 1 log inserido.",
            len(results),
        )

    # ------------------------------------------------------------------
    # Pipeline principal
    # ------------------------------------------------------------------
    def process_frame(
        self,
        image_path: str,
        camera_id: int,
        save_annotated: bool = True,
    ) -> dict[int, int]:
        """
        Pipeline completo de processamento de um frame capturado pelo hardware.

        Etapas:
        1. Carrega a imagem do disco.
        2. Converte BGR → RGB e redimensiona para 640×640.
        3. Executa inferência YOLOv8 (filtrando apenas carros).
        4. Avalia ocupação de cada vaga via IoA.
        5. Persiste resultados no banco de dados.
        6. (Opcional) Salva frame anotado para monitoramento.

        Args:
            image_path: Caminho para a imagem capturada pelo hardware.
            camera_id: ID da câmera no banco de dados.
            save_annotated: Se True, salva um frame anotado com ROIs e detecções.

        Returns:
            Dicionário {vaga_id: status} (0=livre, 1=ocupada).

        Raises:
            ValueError: Se a imagem não puder ser carregada.
            KeyError: Se o camera_id não estiver configurado em rois.json.
        """
        t_start = time.perf_counter()

        # --- 1. Carrega imagem ---
        frame_bgr = load_image(image_path)
        if frame_bgr is None:
            raise ValueError(f"Não foi possível carregar a imagem: {image_path}")

        # --- 2. Pré-processamento ---
        frame_rgb = bgr_to_rgb(frame_bgr)
        frame_resized = resize_frame(frame_rgb)

        # --- 3. Detecção (Usa a original BGR para evitar distorção e cores trocadas, mas pega coords em 640x640) ---
        detections = self.detect_vehicles(frame_bgr)

        # --- 4. Avaliação de ocupação ---
        rois = self.load_rois(camera_id)
        results = self.evaluate_occupancy(detections, rois)

        # --- 5. Persistência ---
        t_elapsed = time.perf_counter() - t_start
        self.persist_results(camera_id, image_path, results, detections, t_elapsed)

        # --- 6. Frame anotado (opcional) ---
        if save_annotated:
            # Usa o frame redimensionado (BGR) para anotação
            frame_annotated_bgr = cv2.cvtColor(frame_resized, cv2.COLOR_RGB2BGR)
            frame_annotated_bgr = draw_rois(frame_annotated_bgr, rois, results)
            frame_annotated_bgr = draw_detections(frame_annotated_bgr, detections)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(
                Path(_ANNOTATED_DIR) / f"cam{camera_id}_{timestamp}.jpg"
            )
            save_annotated_frame(frame_annotated_bgr, output_file)

        t_total = time.perf_counter() - t_start
        logger.info(
            "Pipeline concluído em %.2fs (limite: 60s) | Câmera: %d | "
            "Vagas: %d livres, %d ocupadas",
            t_total,
            camera_id,
            sum(1 for s in results.values() if s == 0),
            sum(1 for s in results.values() if s == 1),
        )

        if t_total > 60.0:
            logger.warning(
                "ATENÇÃO: Latência total (%.2fs) excedeu o limite de 60s!",
                t_total,
            )

        return results


# ---------------------------------------------------------------------------
# Execução direta (para testes manuais)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Estacionei — Detector de ocupação de vagas",
    )
    parser.add_argument(
        "image",
        help="Caminho para a imagem HD (1280x720) do estacionamento.",
    )
    parser.add_argument(
        "--camera-id",
        type=int,
        default=1,
        help="ID da câmera (deve existir em rois.json). Padrão: 1",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL_PATH,
        help=f"Caminho para o modelo YOLOv8. Padrão: {_DEFAULT_MODEL_PATH}",
    )
    parser.add_argument(
        "--config",
        default=_DEFAULT_CONFIG_PATH,
        help=f"Caminho para rois.json. Padrão: {_DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "--ioa-threshold",
        type=float,
        default=0.3,
        help="Limiar de IoA para ocupação. Padrão: 0.3",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.25,
        help="Confiança mínima do YOLO. Padrão: 0.25",
    )
    parser.add_argument(
        "--no-annotate",
        action="store_true",
        help="Desativa a geração de frame anotado.",
    )

    args = parser.parse_args()

    detector = ParkingDetector(
        model_path=args.model,
        config_path=args.config,
        ioa_threshold=args.ioa_threshold,
        confidence_threshold=args.confidence,
    )

    resultado = detector.process_frame(
        image_path=args.image,
        camera_id=args.camera_id,
        save_annotated=not args.no_annotate,
    )

    print("\n" + "=" * 50)
    print("  RESULTADO DA DETECÇÃO")
    print("=" * 50)
    for vaga_id, status in sorted(resultado.items()):
        emoji = "🔴 Ocupada" if status == 1 else "🟢 Livre"
        print(f"  Vaga {vaga_id}: {emoji}")
    print("=" * 50)

import sys
import json
import requests
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from computer_vision.detector import ParkingDetector

def transmit_results(api_url: str, camera_id: int, results: dict, total_detections: int) -> bool:
    payload = {
        "camera_id": camera_id,
        "vagas": [{"vaga_id": v_id, "status": stat} for v_id, stat in results.items()],
        "total_detecoes": total_detections
    }
    
    try:
        response = requests.post(f"{api_url}/api/dispositivos/vagas", json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"[OK] Dados transmitidos com sucesso para a API.")
            return True
        print(f"[ERRO] API retornou status {response.status_code}: {response.text}")
        return False
    except Exception as e:
        print(f"[ERRO] Falha ao conectar na API: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Uso: python send_detection.py <caminho_da_imagem> [--camera-id ID] [--api-url URL]")
        sys.exit(1)
        
    image_path = sys.argv[1]
    camera_id = 1
    api_url = "http://localhost:1421"
    
    if "--camera-id" in sys.argv:
        idx = sys.argv.index("--camera-id")
        camera_id = int(sys.argv[idx + 1])
        
    if "--api-url" in sys.argv:
        idx = sys.argv.index("--api-url")
        api_url = sys.argv[idx + 1]

    try:
        detector = ParkingDetector()
        rois = detector.load_rois(camera_id)
        
        import cv2
        frame_bgr = cv2.imread(image_path)
        if frame_bgr is None:
            sys.exit(1)
            
        detections = detector.detect_vehicles(frame_bgr)
        results = detector.evaluate_occupancy(frame_bgr, detections, rois)
        
        transmit_results(api_url, camera_id, results, len(detections))
        
    except Exception as e:
        print(f"[ERRO] Falha no pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
"""
Painel de Controle — Estacionei.

Interface gráfica (Tkinter) que centraliza o acesso às ferramentas do sistema:
  • Seletor de ROIs  — abre o roi_selector.py para demarcar vagas na imagem.
  • Detector          — executa o pipeline de detecção de ocupação (detector.py).
"""

import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path

# Diretório base do backend e scripts
_BACKEND_DIR = Path(__file__).resolve().parent
_ROI_SELECTOR = _BACKEND_DIR / "computer_vision" / "roi_selector.py"
_DETECTOR = _BACKEND_DIR / "computer_vision" / "detector.py"

# Cores do tema — paleta Estacionei
_BG = "#181C2A"            # Fundo principal (azul escuro)
_BG_CARD = "#1f2337"       # Fundo dos cards (derivada mais clara)
_ACCENT = "#F2B807"        # Amarelo dourado — destaque principal
_ACCENT_HOVER = "#D9A406"  # Amarelo escurecido para hover
_ACCENT_SOFT = "#F5C842"   # Amarelo suavizado para hover secundário
_TEXT = "#FAFCFC"           # Texto principal (branco)
_TEXT_DIM = "#8b90a5"       # Texto secundário (cinza azulado)
_BORDER = "#2a2f45"        # Bordas dos cards (derivada do BG)


class ControlPanel:
    # Painel de controle principal do Estacionei

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Estacionei — Painel de Controle")
        self.root.configure(bg=_BG)
        self.root.resizable(True, True)

        self._setup_ui()

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        # Título
        title = tk.Label(
            self.root,
            text="Estacionei",
            font=("Segoe UI", 22, "bold"),
            fg=_ACCENT,
            bg=_BG,
        )
        title.pack(pady=(28, 4))

        subtitle = tk.Label(
            self.root,
            text="Painel de Controle",
            font=("Segoe UI", 12),
            fg=_TEXT_DIM,
            bg=_BG,
        )
        subtitle.pack(pady=(0, 24))

        # Card Seletor de ROIs
        roi_frame = tk.Frame(self.root, bg=_BG_CARD, highlightbackground=_BORDER, highlightthickness=1)
        roi_frame.pack(padx=32, pady=8, fill=tk.X)

        tk.Label(
            roi_frame,
            text="📐  Seletor de ROIs",
            font=("Segoe UI", 14, "bold"),
            fg=_TEXT,
            bg=_BG_CARD,
            anchor=tk.W,
        ).pack(padx=16, pady=(14, 2), anchor=tk.W)

        tk.Label(
            roi_frame,
            text="Abra o editor visual para demarcar as vagas de estacionamento sobre uma imagem.",
            font=("Segoe UI", 10),
            fg=_TEXT_DIM,
            bg=_BG_CARD,
            justify=tk.LEFT,
            anchor=tk.W,
        ).pack(padx=16, pady=(0, 10), anchor=tk.W)

        self.btn_roi = tk.Button(
            roi_frame,
            text="Abrir Seletor de ROIs",
            font=("Segoe UI", 11, "bold"),
            bg=_ACCENT,
            fg=_BG,
            activebackground=_ACCENT_HOVER,
            activeforeground=_BG,
            relief=tk.FLAT,
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._open_roi_selector,
        )
        self.btn_roi.pack(padx=16, pady=(0, 16), anchor=tk.W)

        # Card detector
        det_frame = tk.Frame(self.root, bg=_BG_CARD, highlightbackground=_BORDER, highlightthickness=1)
        det_frame.pack(padx=32, pady=8, fill=tk.X)

        tk.Label(
            det_frame,
            text="🚗  Detector de Vagas",
            font=("Segoe UI", 14, "bold"),
            fg=_TEXT,
            bg=_BG_CARD,
            anchor=tk.W,
        ).pack(padx=16, pady=(14, 2), anchor=tk.W)

        tk.Label(
            det_frame,
            text="Execute o pipeline de detecção YOLOv8 para avaliar a ocupação das vagas configuradas.",
            font=("Segoe UI", 10),
            fg=_TEXT_DIM,
            bg=_BG_CARD,
            justify=tk.LEFT,
            anchor=tk.W,
        ).pack(padx=16, pady=(0, 10), anchor=tk.W)

        self.btn_detector = tk.Button(
            det_frame,
            text="Executar Detector",
            font=("Segoe UI", 11, "bold"),
            bg=_ACCENT,
            fg=_BG,
            activebackground=_ACCENT_HOVER,
            activeforeground=_BG,
            relief=tk.FLAT,
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._open_detector,
        )
        self.btn_detector.pack(padx=16, pady=(0, 16), anchor=tk.W)

        # Status bar
        self.status_var = tk.StringVar(value="Pronto.")
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            fg=_TEXT_DIM,
            bg=_BG,
            anchor=tk.W,
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=32, pady=(12, 16))

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _open_roi_selector(self) -> None:
        """Abre o Seletor de ROIs (roi_selector.py) em um subprocesso"""
        if not _ROI_SELECTOR.exists():
            messagebox.showerror(
                "Erro",
                f"Arquivo não encontrado:\n{_ROI_SELECTOR}",
            )
            return

        self.status_var.set("Abrindo Seletor de ROIs...")
        self.root.update()

        try:
            subprocess.Popen(
                [sys.executable, str(_ROI_SELECTOR)],
                cwd=str(_BACKEND_DIR),
            )
            self.status_var.set("Seletor de ROIs aberto em nova janela.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao abrir o Seletor de ROIs:\n{e}")
            self.status_var.set("Erro ao abrir o Seletor de ROIs.")

    def _open_detector(self) -> None:
        """
        Solicita uma imagem e o ID da câmera e executa o detector.py
        em um subprocesso.
        """
        # Seleciona imagem
        image_path = filedialog.askopenfilename(
            title="Selecione a imagem do estacionamento",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png"), ("Todos os arquivos", "*.*")],
        )
        if not image_path:
            return

        # Solicita o ID da câmera
        camera_id = simpledialog.askinteger(
            "Detector",
            "Digite o ID da câmera (deve existir em rois.json):",
            initialvalue=1,
            minvalue=1,
            parent=self.root,
        )
        if camera_id is None:
            return

        if not _DETECTOR.exists():
            messagebox.showerror(
                "Erro",
                f"Arquivo não encontrado:\n{_DETECTOR}",
            )
            return

        self.status_var.set(f"Executando detector (Câmera {camera_id})...")
        self.root.update()

        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(_DETECTOR),
                    image_path,
                    "--camera-id", str(camera_id),
                ],
                cwd=str(_BACKEND_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Aguarda o término e pega a saída
            stdout, _ = process.communicate(timeout=120)

            if process.returncode == 0:
                messagebox.showinfo("Detector - Resultado", stdout or "Detecção concluída com sucesso.")
                self.status_var.set("Detecção concluída com sucesso.")
            else:
                messagebox.showerror("Detector - Erro", stdout or "Erro desconhecido durante a detecção.")
                self.status_var.set("Erro na detecção.")

        except subprocess.TimeoutExpired:
            process.kill()
            messagebox.showerror("Timeout", "A detecção excedeu o tempo limite de 120 segundos.")
            self.status_var.set("Timeout na detecção.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao executar o detector:\n{e}")
            self.status_var.set("Erro ao executar o detector.")


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    ControlPanel(root)

    # Centraliza a janela na tela
    root.update_idletasks()
    w, h = 600, 600
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()

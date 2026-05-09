import json
import logging
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import numpy as np
from PIL import Image, ImageTk

# Importa as funções do processor
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from computer_vision.processor import preprocess

# Configuração de caminhos
_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "rois.json"


class ROISelectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Estacionei - Seletor de ROIs")
        
        self.image_array = None
        self.photo_image = None
        
        # Estado
        self.polygons = []  # Lista de dicts: {"vaga_id": int, "codigo_vaga": str, "coords": list[list[int]]}
        self.current_points = []  # Pontos do polígono atual em construção
        
        self._setup_ui()
        
    def _setup_ui(self):
        # Painel superior (Botões)
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        tk.Button(top_frame, text="Carregar Imagem", command=self.load_image).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Desfazer Último Clique", command=self.undo).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Limpar Tudo", command=self.clear_all).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Salvar ROIs", command=self.save_rois).pack(side=tk.RIGHT, padx=5)
        
        # Área da imagem
        # 640x640 é o padrão de preprocess do YOLO
        self.canvas = tk.Canvas(self.root, width=640, height=640, bg="gray")
        self.canvas.pack(side=tk.TOP, padx=5, pady=5)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Pronto. Carregue uma imagem para começar.")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def load_image(self):
        file_path = filedialog.askopenfilename(
            title="Selecione uma imagem de estacionamento",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png"), ("Todos os arquivos", "*.*")]
        )
        if not file_path:
            return
            
        try:
            self.status_var.set(f"Processando imagem: {Path(file_path).name}...")
            self.root.update()
            
            # Utiliza o preprocess do processor para garantir exatamente 640x640 (RGB)
            frame_resized = preprocess(file_path)
            
            if frame_resized is None:
                messagebox.showerror("Erro", "Falha ao carregar a imagem com o OpenCV. O arquivo pode estar corrompido.")
                self.status_var.set("Erro ao carregar imagem.")
                return
                
            self.image_array = frame_resized
            
            # Converte para Pillow Image e depois PhotoImage para o Tkinter
            image_pil = Image.fromarray(self.image_array)
            self.photo_image = ImageTk.PhotoImage(image_pil)
            
            # Limpa estado
            self.current_points = []
            self.polygons = []
            
            self.redraw()
            self.status_var.set("Imagem carregada. Clique 4 vezes no Canvas para marcar os cantos de uma vaga.")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Ocorreu um erro ao processar a imagem:\n{e}")
            self.status_var.set("Erro na imagem.")

    def redraw(self):
        self.canvas.delete("all")
        
        # Desenha imagem de fundo
        if self.photo_image:
            self.canvas.create_image(0, 0, image=self.photo_image, anchor=tk.NW)
            
        # Desenha polígonos finalizados
        for poly in self.polygons:
            pts = poly["coords"]
            flat_pts = [coord for pt in pts for coord in pt]
            
            # Linha ao redor
            self.canvas.create_polygon(flat_pts, outline="#00FF00", fill="", width=2)
            
            # Rótulo no centro do polígono
            cx = sum(p[0] for p in pts) / 4
            cy = sum(p[1] for p in pts) / 4
            label = f"{poly['codigo_vaga']} (ID:{poly['vaga_id']})"
            
            # Texto com sombra preta para contraste
            self.canvas.create_text(cx+1, cy+1, text=label, fill="black", font=("Arial", 10, "bold"))
            self.canvas.create_text(cx, cy, text=label, fill="white", font=("Arial", 10, "bold"))
            
        # Desenha polígono em construção (pontos e linhas vermelhas)
        if self.current_points:
            for x, y in self.current_points:
                self.canvas.create_oval(x-3, y-3, x+3, y+3, fill="red", outline="red")
                
            if len(self.current_points) > 1:
                flat_pts = [coord for pt in self.current_points for coord in pt]
                self.canvas.create_line(flat_pts, fill="red", width=2)

    def on_canvas_click(self, event):
        if self.image_array is None:
            messagebox.showinfo("Aviso", "Por favor, carregue uma imagem primeiro.")
            return
            
        x, y = event.x, event.y
        self.current_points.append([x, y])
        self.redraw()
        
        # Se formou os 4 pontos, finaliza o polígono da vaga
        if len(self.current_points) == 4:
            self.prompt_for_polygon()

    def prompt_for_polygon(self):
        vaga_id = simpledialog.askinteger(
            "Nova Vaga", "Digite o ID numérico da vaga (ex: 4):", parent=self.root
        )
        if vaga_id is None:
            # Cancelou
            self.current_points.pop()
            self.redraw()
            return
            
        codigo_vaga = simpledialog.askstring(
            "Nova Vaga", "Digite o Código da vaga (ex: A04):", parent=self.root
        )
        if codigo_vaga is None:
            # Cancelou
            self.current_points.pop()
            self.redraw()
            return
            
        # Adiciona aos finalizados
        self.polygons.append({
            "vaga_id": vaga_id,
            "codigo_vaga": codigo_vaga,
            "coords": self.current_points.copy()
        })
        self.current_points = []
        self.redraw()
        self.status_var.set(f"Vaga {codigo_vaga} adicionada. Marque a próxima vaga (4 cantos).")

    def undo(self):
        if self.current_points:
            self.current_points.pop()
            self.status_var.set("Ponto desfeito.")
        elif self.polygons:
            poly = self.polygons.pop()
            self.status_var.set(f"Vaga {poly['codigo_vaga']} desfeita.")
        else:
            self.status_var.set("Nenhuma ação para desfazer.")
        self.redraw()

    def clear_all(self):
        if not self.polygons and not self.current_points:
            return
            
        if messagebox.askyesno("Confirmar", "Deseja remover TODAS as vagas marcadas na tela?"):
            self.current_points = []
            self.polygons = []
            self.redraw()
            self.status_var.set("Todas as marcações foram limpas.")

    def save_rois(self):
        if not self.polygons:
            messagebox.showwarning("Aviso", "Você precisa marcar pelo menos uma vaga antes de salvar.")
            return
            
        camera_id = simpledialog.askinteger(
            "Salvar ROIs", "Para qual ID de Câmera você quer salvar? (ex: 1)", parent=self.root
        )
        if camera_id is None:
            return
            
        camera_id_str = str(camera_id)
        
        # Tenta carregar as configurações existentes
        config = {"cameras": {}}
        if _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                if not messagebox.askyesno("Erro", f"O arquivo rois.json atual parece estar corrompido:\n{e}\n\nDeseja sobrescrever tudo (criando um novo arquivo limpo)?"):
                    return
        
        # Prepara a entrada da câmera se não existir
        if "cameras" not in config:
            config["cameras"] = {}
            
        if camera_id_str not in config["cameras"]:
            config["cameras"][camera_id_str] = {
                "descricao": f"Câmera {camera_id}",
                "rois": []
            }
            
        # Substitui os ROIs daquela câmera pela lista desenhada
        config["cameras"][camera_id_str]["rois"] = self.polygons
        
        # Salva o arquivo atualizado
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                
            messagebox.showinfo("Sucesso", f"{len(self.polygons)} vaga(s) salvas para a Câmera {camera_id}!")
            self.status_var.set(f"Salvo com sucesso em rois.json para Câmera {camera_id}.")
        except Exception as e:
            messagebox.showerror("Erro de Escrita", f"Falha ao escrever arquivo rois.json:\n{e}")


def main():
    root = tk.Tk()
    app = ROISelectorApp(root)
    
    # Centraliza a janela
    root.update_idletasks()
    w = 660
    h = 740
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    
    root.resizable(True, True)
    
    root.mainloop()


if __name__ == "__main__":
    main()

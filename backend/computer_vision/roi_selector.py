import json
import logging
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
from PIL import Image, ImageTk

# Importa as funções do processor
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from computer_vision.processor import preprocess
from database.database import db

# Configuração de caminhos
_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "rois.json"

# Cores do tema — paleta Estacionei (consistente com o control_panel)
_BG = "#181C2A"
_BG_CARD = "#1f2337"
_ACCENT = "#F2B807"
_ACCENT_HOVER = "#D9A406"
_TEXT = "#FAFCFC"
_TEXT_DIM = "#8b90a5"
_BORDER = "#2a2f45"
_GREEN = "#4CAF50"
_RED = "#EF5350"


class ROISelectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Estacionei - Seletor de ROIs & Coordenadas")
        self.root.configure(bg=_BG)

        self.image_array = None
        self.photo_image = None

        # Estado ROI
        self.polygons = []  # Lista de dicts: {"vaga_id": int, "codigo_vaga": str, "coords": list[list[int]]}
        self.current_points = []  # Pontos do polígono atual em construção

        # Estado Coordenadas
        self.vagas_db = []  # Lista de vagas carregadas do banco
        self.coord_entries = {}  # {vaga_id: {"lat": Entry, "lng": Entry}}

        self._setup_ui()

    # ==================================================================
    # UI Principal — Notebook com abas
    # ==================================================================

    def _setup_ui(self):
        # Cria o Notebook (abas) estilizado
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=_BG_CARD, foreground=_TEXT,
                         padding=[14, 6], font=("Segoe UI", 11, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", _ACCENT)],
                  foreground=[("selected", _BG)])

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Aba 1 — Seletor de ROIs (funcionalidade original)
        self.tab_roi = tk.Frame(self.notebook, bg=_BG)
        self.notebook.add(self.tab_roi, text="  📐  ROIs  ")

        # Aba 2 — Coordenadas GPS
        self.tab_coords = tk.Frame(self.notebook, bg=_BG)
        self.notebook.add(self.tab_coords, text="  📍  Coordenadas  ")

        self._build_tab_roi()
        self._build_tab_coords()

        # Status bar global (fora do notebook)
        self.status_var = tk.StringVar()
        self.status_var.set("Pronto. Selecione uma aba para começar.")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1,
                              relief=tk.SUNKEN, anchor=tk.W,
                              bg=_BG_CARD, fg=_TEXT_DIM,
                              font=("Segoe UI", 9), padx=8)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ==================================================================
    # ABA 1 — Seletor de ROIs (funcionalidade original mantida)
    # ==================================================================

    def _build_tab_roi(self):
        # Painel superior (Botões)
        top_frame = tk.Frame(self.tab_roi, bg=_BG)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        self._make_button(top_frame, "Carregar Imagem", self.load_image).pack(side=tk.LEFT, padx=4)
        self._make_button(top_frame, "Desfazer Último Clique", self.undo).pack(side=tk.LEFT, padx=4)
        self._make_button(top_frame, "Limpar Tudo", self.clear_all).pack(side=tk.LEFT, padx=4)
        self._make_button(top_frame, "Salvar ROIs", self.save_rois, accent=True).pack(side=tk.RIGHT, padx=4)

        # Área da imagem
        # 640x640 é o padrão de preprocess do YOLO
        self.canvas = tk.Canvas(self.tab_roi, width=640, height=640, bg="#111", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, padx=8, pady=4)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

    # ==================================================================
    # ABA 2 — Coordenadas GPS
    # ==================================================================

    def _build_tab_coords(self):
        # Título e descrição
        header = tk.Frame(self.tab_coords, bg=_BG)
        header.pack(fill=tk.X, padx=16, pady=(16, 4))

        tk.Label(header, text="Coordenadas GPS das Vagas",
                 font=("Segoe UI", 16, "bold"), fg=_TEXT, bg=_BG).pack(anchor=tk.W)
        tk.Label(header, text="Carregue as vagas do banco, edite latitude/longitude e salve.",
                 font=("Segoe UI", 10), fg=_TEXT_DIM, bg=_BG).pack(anchor=tk.W, pady=(2, 0))

        # Botões de ação
        btn_frame = tk.Frame(self.tab_coords, bg=_BG)
        btn_frame.pack(fill=tk.X, padx=16, pady=8)

        self._make_button(btn_frame, "🔄  Carregar do Banco", self._carregar_vagas_db).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_frame, "💾  Salvar Coordenadas", self._salvar_coordenadas, accent=True).pack(side=tk.RIGHT, padx=4)

        # Cabeçalhos da tabela
        cols_frame = tk.Frame(self.tab_coords, bg=_BG_CARD)
        cols_frame.pack(fill=tk.X, padx=16, pady=(4, 0))

        headers = [("ID", 6), ("Código", 10), ("Latitude", 20), ("Longitude", 20), ("Status", 8)]
        for titulo, w in headers:
            tk.Label(cols_frame, text=titulo, width=w,
                     font=("Segoe UI", 10, "bold"), fg=_ACCENT, bg=_BG_CARD,
                     anchor=tk.W, padx=6).pack(side=tk.LEFT, pady=4)

        # Área scrollável para as vagas
        container = tk.Frame(self.tab_coords, bg=_BG)
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        self.coords_canvas = tk.Canvas(container, bg=_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient=tk.VERTICAL, command=self.coords_canvas.yview)
        self.coords_scroll_frame = tk.Frame(self.coords_canvas, bg=_BG)

        self.coords_scroll_frame.bind(
            "<Configure>",
            lambda e: self.coords_canvas.configure(scrollregion=self.coords_canvas.bbox("all"))
        )
        self.coords_canvas.create_window((0, 0), window=self.coords_scroll_frame, anchor=tk.NW)
        self.coords_canvas.configure(yscrollcommand=scrollbar.set)

        self.coords_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mousewheel para scroll
        self.coords_canvas.bind_all("<MouseWheel>",
            lambda e: self.coords_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Placeholder inicial
        self._placeholder_label = tk.Label(
            self.coords_scroll_frame,
            text="Clique em \"Carregar do Banco\" para listar as vagas.",
            font=("Segoe UI", 11), fg=_TEXT_DIM, bg=_BG, pady=40
        )
        self._placeholder_label.pack()

    def _carregar_vagas_db(self):
        """Busca todas as vagas do banco de dados e popula a aba de coordenadas."""
        self.status_var.set("Conectando ao banco de dados...")
        self.root.update()

        try:
            result = db.query("SELECT id, codigo_vaga, latitude, longitude, status FROM vagas ORDER BY id")
            self.vagas_db = result if result else []
        except Exception as e:
            messagebox.showerror("Erro de Banco", f"Falha ao conectar ao banco de dados:\n{e}")
            self.status_var.set("Erro ao carregar vagas do banco.")
            return

        # Limpa o frame anterior
        for widget in self.coords_scroll_frame.winfo_children():
            widget.destroy()
        self.coord_entries.clear()

        if not self.vagas_db:
            tk.Label(self.coords_scroll_frame, text="Nenhuma vaga encontrada no banco.",
                     font=("Segoe UI", 11), fg=_TEXT_DIM, bg=_BG, pady=40).pack()
            self.status_var.set("Nenhuma vaga encontrada.")
            return

        # Popula a lista de vagas com campos editáveis de lat/lng
        for i, vaga in enumerate(self.vagas_db):
            row_bg = _BG_CARD if i % 2 == 0 else _BG
            row = tk.Frame(self.coords_scroll_frame, bg=row_bg)
            row.pack(fill=tk.X, pady=1)

            # ID
            tk.Label(row, text=str(vaga["id"]), width=6,
                     font=("Segoe UI", 10), fg=_TEXT, bg=row_bg,
                     anchor=tk.W, padx=6).pack(side=tk.LEFT, pady=6)

            # Código da Vaga
            tk.Label(row, text=str(vaga["codigo_vaga"]), width=10,
                     font=("Segoe UI", 10, "bold"), fg=_TEXT, bg=row_bg,
                     anchor=tk.W, padx=6).pack(side=tk.LEFT, pady=6)

            # Latitude (editável)
            lat_entry = tk.Entry(row, width=20, font=("Consolas", 10),
                                 bg="#252940", fg=_TEXT, insertbackground=_TEXT,
                                 relief=tk.FLAT, highlightthickness=1,
                                 highlightbackground=_BORDER, highlightcolor=_ACCENT)
            lat_entry.insert(0, str(vaga["latitude"]))
            lat_entry.pack(side=tk.LEFT, padx=4, pady=6)

            # Longitude (editável)
            lng_entry = tk.Entry(row, width=20, font=("Consolas", 10),
                                 bg="#252940", fg=_TEXT, insertbackground=_TEXT,
                                 relief=tk.FLAT, highlightthickness=1,
                                 highlightbackground=_BORDER, highlightcolor=_ACCENT)
            lng_entry.insert(0, str(vaga["longitude"]))
            lng_entry.pack(side=tk.LEFT, padx=4, pady=6)

            # Status (indicador visual)
            status_val = vaga.get("status", 0)
            status_text = "Livre" if status_val == 0 else "Ocupada"
            status_color = _GREEN if status_val == 0 else _RED
            tk.Label(row, text=status_text, width=8,
                     font=("Segoe UI", 10, "bold"), fg=status_color, bg=row_bg,
                     anchor=tk.W, padx=6).pack(side=tk.LEFT, pady=6)

            self.coord_entries[vaga["id"]] = {"lat": lat_entry, "lng": lng_entry}

        total = len(self.vagas_db)
        self.status_var.set(f"{total} vaga(s) carregada(s) do banco. Edite as coordenadas e clique em Salvar.")

    def _salvar_coordenadas(self):
        """Salva as coordenadas editadas de volta no banco de dados."""
        if not self.coord_entries:
            messagebox.showwarning("Aviso", "Carregue as vagas do banco antes de salvar.")
            return

        erros = []
        atualizadas = 0

        for vaga_id, entries in self.coord_entries.items():
            lat_str = entries["lat"].get().strip()
            lng_str = entries["lng"].get().strip()

            try:
                lat = float(lat_str)
                lng = float(lng_str)
            except ValueError:
                erros.append(f"Vaga {vaga_id}: latitude ou longitude inválida ('{lat_str}', '{lng_str}')")
                continue

            try:
                db.query(
                    "UPDATE vagas SET latitude = %s, longitude = %s, ultima_atualizacao = CURRENT_TIMESTAMP WHERE id = %s",
                    (lat, lng, vaga_id)
                )
                atualizadas += 1
            except Exception as e:
                erros.append(f"Vaga {vaga_id}: erro no banco — {e}")

        # Feedback
        msg_parts = []
        if atualizadas > 0:
            msg_parts.append(f"✅ {atualizadas} vaga(s) atualizada(s) com sucesso.")
        if erros:
            msg_parts.append(f"⚠️ {len(erros)} erro(s):\n" + "\n".join(erros))

        resultado = "\n\n".join(msg_parts)

        if erros:
            messagebox.showwarning("Resultado", resultado)
        else:
            messagebox.showinfo("Sucesso", resultado)

        self.status_var.set(f"{atualizadas} coordenada(s) salva(s) no banco.")

        # Recarrega a lista para refletir o estado atual
        self._carregar_vagas_db()

    # ==================================================================
    # Métodos da Aba ROI (funcionalidade original preservada)
    # ==================================================================

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
        except Exception as e:
            messagebox.showerror("Erro de Escrita", f"Falha ao escrever arquivo rois.json:\n{e}")
            return

        # -----------------------------------------------------------------
        # Sincroniza com o banco de dados (INSERT ou UPDATE)
        # Garante que a API /api/statusVagas/ retorne as vagas recém-criadas
        # -----------------------------------------------------------------
        db_ok = 0
        db_erros = []
        for poly in self.polygons:
            vaga_id = poly["vaga_id"]
            codigo = poly["codigo_vaga"]
            try:
                # Tenta inserir; se o codigo_vaga já existir, atualiza o id
                # (usa ON CONFLICT no codigo_vaga que é UNIQUE)
                db.query(
                    """INSERT INTO vagas (id, codigo_vaga, latitude, longitude, status, ultima_atualizacao)
                       VALUES (%s, %s, 0.0, 0.0, 0, CURRENT_TIMESTAMP)
                       ON CONFLICT (codigo_vaga) DO UPDATE
                       SET ultima_atualizacao = CURRENT_TIMESTAMP""",
                    (vaga_id, codigo)
                )
                db_ok += 1
            except Exception as e:
                db_erros.append(f"Vaga {codigo} (ID {vaga_id}): {e}")

        # Feedback final
        msg = f"{len(self.polygons)} ROI(s) salvas em rois.json para Câmera {camera_id}.\n"
        if db_ok > 0:
            msg += f"\n✅ {db_ok} vaga(s) sincronizada(s) no banco de dados."
        if db_erros:
            msg += f"\n\n⚠️ {len(db_erros)} erro(s) no banco:\n" + "\n".join(db_erros)

        if db_erros:
            messagebox.showwarning("Resultado", msg)
        else:
            messagebox.showinfo("Sucesso", msg)

        self.status_var.set(f"ROIs salvas + {db_ok} vaga(s) no banco para Câmera {camera_id}.")

    # ==================================================================
    # Helpers
    # ==================================================================

    def _make_button(self, parent, text, command, accent=False):
        """Cria um botão estilizado no tema Estacionei."""
        bg = _ACCENT if accent else _BG_CARD
        fg = _BG if accent else _TEXT
        active_bg = _ACCENT_HOVER if accent else _BORDER

        btn = tk.Button(
            parent, text=text, command=command,
            font=("Segoe UI", 10, "bold"),
            bg=bg, fg=fg,
            activebackground=active_bg, activeforeground=fg,
            relief=tk.FLAT, cursor="hand2",
            padx=12, pady=4
        )
        return btn


def main():
    root = tk.Tk()
    app = ROISelectorApp(root)

    # Centraliza a janela (um pouco mais larga para acomodar a aba de coordenadas)
    root.update_idletasks()
    w = 760
    h = 800
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.resizable(True, True)

    root.mainloop()


if __name__ == "__main__":
    main()

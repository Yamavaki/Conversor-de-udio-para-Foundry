# -*- coding: utf-8 -*-
"""
Conversor de Áudio para Foundry (Forge)
Baixa áudio do YouTube (ou converte arquivos do PC) direto para .ogg pequeno.
Dependências (o Iniciar.bat instala sozinho): yt-dlp[default], imageio-ffmpeg, deno
"""
import os
import re
import sys
import shutil
import sysconfig
import tempfile
import threading
import queue
import subprocess
import unicodedata
import traceback

LOG_ERRO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erro.log")


def _registrar_erro(tipo, valor, tb):
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    try:
        with open(LOG_ERRO, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    except Exception:
        pass
    sys.__stderr__ and sys.__stderr__.write(texto)


sys.excepthook = _registrar_erro

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("\n[ERRO] O Python instalado veio sem o Tkinter (a parte que desenha janelas).")
    print("Reinstale o Python pelo site python.org e deixe marcada a opcao")
    print('"tcl/tk and IDLE" na instalacao personalizada.\n')
    sys.exit(1)

# ---------------------------------------------------------------- dependências
try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = shutil.which("ffmpeg")

try:
    import yt_dlp
except Exception:
    yt_dlp = None

# O YouTube hoje exige um runtime de JavaScript (Deno) para o yt-dlp.
# O pacote "deno" do pip instala o executável na pasta Scripts do Python:
for pasta in {sysconfig.get_path("scripts"), sysconfig.get_path("scripts", f"{os.name}_user")}:
    if pasta and os.path.isdir(pasta) and pasta not in os.environ.get("PATH", ""):
        os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")

NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # não abrir janela preta do ffmpeg

# ---------------------------------------------------------------- presets
# (nome do botão, explicação, bitrate kbps, mono?, alvo de volume LUFS)
PRESETS = [
    ("Música", "Música de fundo · 64 kbps estéreo · cerca de 0,5 MB por minuto", 64, False, -18),
    ("Ambiente", "Ambiente / loop · 48 kbps estéreo · cerca de 0,35 MB por minuto", 48, False, -20),
    ("Efeito", "Efeito sonoro · 48 kbps mono · bem leve", 48, True, -16),
    ("Voz", "Voz / narração · 32 kbps mono · cerca de 0,25 MB por minuto", 32, True, -16),
    ("Alta qualidade", "Alta qualidade · 96 kbps estéreo · cerca de 0,7 MB por minuto", 96, False, -16),
]
FORMATOS = [
    ("Opus (.ogg)", "Recomendado: o menor arquivo com o melhor som.", "opus"),
    ("Vorbis (.ogg)", "Para aparelhos antigos (iPhone/Mac desatualizados). Um pouco maior.", "vorbis"),
]

# Paleta Nauren
ROXO, ROXO_ESC, OURO, TEXTO, CAMPO = "#2a1740", "#160b24", "#d9b44a", "#efe6ff", "#3a2457"
SUAVE, BORDA, HOVER = "#a993c9", "#5a3d80", "#4b2f70"
FONTE = "Segoe UI"


def detectar_encoders():
    try:
        out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True,
                             text=True, creationflags=NO_WINDOW).stdout
    except Exception:
        return "opus", "vorbis"
    opus = "libopus" if "libopus" in out else "opus"
    vorbis = "libvorbis" if "libvorbis" in out else "vorbis"
    return opus, vorbis


def nome_seguro(nome, simples=True):
    """Nomes que não quebram URL na Forge (Linux diferencia maiúsculas)."""
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", nome).strip() or "audio"
    if simples:
        nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
        nome = re.sub(r"[^A-Za-z0-9]+", "-", nome).strip("-").lower() or "audio"
    return nome[:90]


def cfg_tempo(seg):
    seg = int(seg)
    h, m, s = seg // 3600, seg % 3600 // 60, seg % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def tamanho(caminho):
    b = os.path.getsize(caminho)
    return f"{b / 1048576:.2f} MB" if b >= 1048576 else f"{b / 1024:.0f} KB"


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        self.fila = queue.Queue()
        self.ocupado = False
        self.arquivos_locais = []
        self.enc_opus, self.enc_vorbis = detectar_encoders()

        raiz.title("Conversor de Áudio para Foundry — Nauren")
        raiz.geometry("840x880")
        raiz.minsize(720, 700)
        raiz.configure(bg=ROXO_ESC)
        self._estilo()
        self._montar()
        raiz.after(100, self._ler_fila)

        if not FFMPEG:
            self.log("⚠ ffmpeg não encontrado. Rode pelo Iniciar.bat para instalar tudo.")
        if yt_dlp is None:
            self.log("⚠ yt-dlp não encontrado — só a conversão de arquivos do PC vai funcionar.")

    # ------------------------------------------------------------ interface
    def _estilo(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Horizontal.TProgressbar", background=OURO, troughcolor=CAMPO,
                    bordercolor=ROXO_ESC, lightcolor=OURO, darkcolor=OURO, thickness=8)

    # helpers visuais --------------------------------------------------
    def _cartao(self, titulo, dica=None):
        caixa = tk.Frame(self.raiz, bg=ROXO, highlightthickness=1, highlightbackground=BORDA)
        caixa.pack(fill="x", padx=16, pady=(0, 10))
        topo = tk.Frame(caixa, bg=ROXO)
        topo.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(topo, text=titulo, bg=ROXO, fg=OURO, font=(FONTE, 11, "bold")).pack(side="left")
        if dica:
            tk.Label(topo, text=dica, bg=ROXO, fg=SUAVE, font=(FONTE, 9)).pack(side="left", padx=8)
        corpo = tk.Frame(caixa, bg=ROXO)
        corpo.pack(fill="x", padx=14, pady=(0, 12))
        return corpo

    def _botao(self, pai, texto, comando, destaque=False):
        b = tk.Button(pai, text=texto, command=comando, cursor="hand2", relief="flat", bd=0,
                      font=(FONTE, 13 if destaque else 10, "bold" if destaque else "normal"),
                      bg=OURO if destaque else CAMPO, fg=ROXO_ESC if destaque else TEXTO,
                      activebackground="#f0cc63" if destaque else HOVER,
                      activeforeground=ROXO_ESC if destaque else TEXTO,
                      disabledforeground="#6b5a2e" if destaque else SUAVE,
                      padx=14, pady=10 if destaque else 6)
        return b

    def _entrada(self, pai, var, largura=None):
        e = tk.Entry(pai, textvariable=var, bg=CAMPO, fg=TEXTO, insertbackground=OURO,
                     relief="flat", font=(FONTE, 10), highlightthickness=1,
                     highlightbackground=BORDA, highlightcolor=OURO)
        if largura:
            e.config(width=largura)
        return e

    def _grupo_pilulas(self, pai, opcoes, var, ao_mudar=None, multipla=False):
        """Botões em forma de pílula; o selecionado fica dourado com texto escuro."""
        botoes = []

        def pintar(*_):
            for b, chave in botoes:
                ligado = chave.get() if multipla else var.get() == chave
                b.config(bg=OURO if ligado else CAMPO, fg=ROXO_ESC if ligado else TEXTO,
                         activebackground="#f0cc63" if ligado else HOVER,
                         activeforeground=ROXO_ESC if ligado else TEXTO,
                         text=(("✓  " if ligado else "    ") + b._rotulo) if multipla else b._rotulo)
            if ao_mudar:
                ao_mudar()

        linha = tk.Frame(pai, bg=ROXO)
        for rotulo, chave in opcoes:
            if multipla:
                b = tk.Checkbutton(linha, variable=chave, indicatoron=0, command=pintar)
            else:
                b = tk.Radiobutton(linha, variable=var, value=chave, indicatoron=0, command=pintar)
            b._rotulo = rotulo
            b.config(text=rotulo, relief="flat", bd=0, padx=14, pady=7, cursor="hand2",
                     font=(FONTE, 10), selectcolor=OURO, highlightthickness=0,
                     offrelief="flat", overrelief="flat")
            b.pack(side="left", padx=(0, 6), pady=2)
            botoes.append((b, chave))
        pintar()
        linha.pintar = pintar
        return linha

    def _montar(self):
        # cabeçalho
        cab = tk.Frame(self.raiz, bg=ROXO_ESC)
        cab.pack(fill="x", padx=16, pady=(14, 10))
        tk.Label(cab, text="Conversor de Áudio", bg=ROXO_ESC, fg=OURO,
                 font=(FONTE, 18, "bold")).pack(anchor="w")
        tk.Label(cab, text="Arquivos .ogg leves, prontos para subir na Forge", bg=ROXO_ESC,
                 fg=SUAVE, font=(FONTE, 10)).pack(anchor="w")

        # links
        c1 = self._cartao("Links do YouTube", "um por linha · aceita playlist")
        self.txt_links = tk.Text(c1, height=4, bg=CAMPO, fg=TEXTO, insertbackground=OURO,
                                 relief="flat", font=("Consolas", 10), padx=8, pady=6,
                                 highlightthickness=1, highlightbackground=BORDA,
                                 highlightcolor=OURO)
        self.txt_links.pack(fill="x")

        # arquivos locais
        c2 = self._cartao("Arquivos do PC", "mp3, wav, flac, m4a, vídeos…")
        lin = tk.Frame(c2, bg=ROXO)
        lin.pack(fill="x")
        self._botao(lin, "Adicionar arquivos…", self.add_arquivos).pack(side="left")
        self._botao(lin, "Limpar", self.limpar_arquivos).pack(side="left", padx=8)
        self.lbl_arqs = tk.Label(lin, text="Nenhum arquivo", bg=ROXO, fg=SUAVE, font=(FONTE, 10))
        self.lbl_arqs.pack(side="left", padx=6)

        # uso
        c3 = self._cartao("Para que é o áudio?")
        self.var_preset = tk.IntVar(value=0)
        self.lbl_preset = tk.Label(c3, bg=ROXO, fg=SUAVE, font=(FONTE, 9), anchor="w")
        self._grupo_pilulas(c3, [(p[0], i) for i, p in enumerate(PRESETS)], self.var_preset,
                            lambda: self.lbl_preset.config(text=PRESETS[self.var_preset.get()][1])
                            ).pack(fill="x")
        self.lbl_preset.pack(fill="x", pady=(6, 0))

        # formato + opções
        c4 = self._cartao("Formato e ajustes")
        self.var_formato = tk.IntVar(value=0)
        self.lbl_formato = tk.Label(c4, bg=ROXO, fg=SUAVE, font=(FONTE, 9), anchor="w")
        self._grupo_pilulas(c4, [(f[0], i) for i, f in enumerate(FORMATOS)], self.var_formato,
                            lambda: self.lbl_formato.config(text=FORMATOS[self.var_formato.get()][1])
                            ).pack(fill="x")
        self.lbl_formato.pack(fill="x", pady=(6, 10))

        self.var_norm = tk.BooleanVar(value=True)
        self.var_sil = tk.BooleanVar(value=True)
        self.var_fade = tk.BooleanVar(value=False)
        self.var_nome = tk.BooleanVar(value=True)
        self.var_playlist = tk.BooleanVar(value=False)
        self._grupo_pilulas(c4, [("Igualar volume", self.var_norm),
                                 ("Cortar silêncio das pontas", self.var_sil),
                                 ("Fade de 2 s no fim", self.var_fade),
                                 ("Nome seguro para a Forge", self.var_nome)],
                            None, multipla=True).pack(fill="x")
        pl = tk.Frame(c4, bg=ROXO)
        pl.pack(fill="x", pady=(6, 0))
        self._grupo_pilulas(pl, [("Baixar a playlist inteira", self.var_playlist)],
                            None, multipla=True).pack(side="left")
        tk.Label(pl, text="desligado: link de vídeo com playlist/Mix baixa só aquele vídeo",
                 bg=ROXO, fg=SUAVE, font=(FONTE, 9)).pack(side="left", padx=4)

        self.var_ini = tk.StringVar()
        self.var_fim = tk.StringVar()
        atalhos = [("Inteiro", ""), ("15 s", "0:15"), ("30 s", "0:30"),
                   ("1 min", "1:00"), ("2 min", "2:00")]
        self.var_atalho = tk.IntVar(value=0)
        self._mudando_atalho = False

        def aplicar_atalho():
            i = self.var_atalho.get()
            if i < 0:
                return
            self._mudando_atalho = True
            self.var_ini.set("")
            self.var_fim.set(atalhos[i][1])
            self._mudando_atalho = False

        at = tk.Frame(c4, bg=ROXO)
        at.pack(fill="x", pady=(12, 0))
        tk.Label(at, text="Duração:", bg=ROXO, fg=TEXTO, font=(FONTE, 10)).pack(side="left", padx=(0, 10))
        grupo_at = self._grupo_pilulas(at, [(t, i) for i, (t, _) in enumerate(atalhos)],
                                       self.var_atalho, aplicar_atalho)
        grupo_at.pack(side="left")
        tk.Label(at, text="a partir do início do vídeo", bg=ROXO, fg=SUAVE,
                 font=(FONTE, 9)).pack(side="left", padx=4)

        def digitou(*_):
            if self._mudando_atalho:
                return
            self.var_atalho.set(-1)   # personalizado: nenhum atalho aceso
            grupo_at.pintar()

        self.var_ini.trace_add("write", digitou)
        self.var_fim.trace_add("write", digitou)

        tr = tk.Frame(c4, bg=ROXO)
        tr.pack(fill="x", pady=(8, 0))
        tk.Label(tr, text="Ou trecho exato:", bg=ROXO, fg=TEXTO, font=(FONTE, 10)).pack(side="left")
        tk.Label(tr, text="início", bg=ROXO, fg=SUAVE, font=(FONTE, 10)).pack(side="left", padx=(10, 4))
        self._entrada(tr, self.var_ini, 8).pack(side="left", ipady=3)
        tk.Label(tr, text="fim", bg=ROXO, fg=SUAVE, font=(FONTE, 10)).pack(side="left", padx=(10, 4))
        self._entrada(tr, self.var_fim, 8).pack(side="left", ipady=3)
        tk.Label(tr, text="opcional · ex.: 0:15 e 3:40", bg=ROXO, fg=SUAVE,
                 font=(FONTE, 9)).pack(side="left", padx=10)

        pa = tk.Frame(c4, bg=ROXO)
        pa.pack(fill="x", pady=(10, 0))
        self.var_pasta = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Music", "Foundry"))
        tk.Label(pa, text="Salvar em:", bg=ROXO, fg=TEXTO, font=(FONTE, 10)).pack(side="left")
        self._entrada(pa, self.var_pasta).pack(side="left", fill="x", expand=True, padx=10, ipady=4)
        self._botao(pa, "Escolher…", self.escolher_pasta).pack(side="left")

        # ação
        self.btn = self._botao(self.raiz, "Baixar e converter", self.iniciar, destaque=True)
        self.btn.pack(fill="x", padx=16, pady=(4, 8))
        self.prog = ttk.Progressbar(self.raiz, mode="determinate", maximum=100)
        self.prog.pack(fill="x", padx=16)

        self.txt_log = tk.Text(self.raiz, height=7, bg=ROXO, fg=TEXTO, relief="flat",
                               font=("Consolas", 9), padx=10, pady=8, state="disabled",
                               highlightthickness=1, highlightbackground=BORDA)
        self.txt_log.pack(fill="both", expand=True, padx=16, pady=(10, 16))

    # ------------------------------------------------------------ ações da UI
    def add_arquivos(self):
        arqs = filedialog.askopenfilenames(title="Escolha os arquivos")
        self.arquivos_locais.extend(a for a in arqs if a not in self.arquivos_locais)
        self.lbl_arqs.config(text=f"{len(self.arquivos_locais)} arquivo(s) na fila" if self.arquivos_locais else "Nenhum arquivo",
                             fg=OURO if self.arquivos_locais else SUAVE)

    def limpar_arquivos(self):
        self.arquivos_locais = []
        self.lbl_arqs.config(text="Nenhum arquivo", fg=SUAVE)

    def escolher_pasta(self):
        p = filedialog.askdirectory(initialdir=self.var_pasta.get())
        if p:
            self.var_pasta.set(p)

    def log(self, msg):
        self.fila.put(("log", msg))

    def _ler_fila(self):
        try:
            while True:
                tipo, val = self.fila.get_nowait()
                if tipo == "log":
                    self.txt_log.config(state="normal")
                    self.txt_log.insert("end", val + "\n")
                    self.txt_log.see("end")
                    self.txt_log.config(state="disabled")
                elif tipo == "prog":
                    self.prog["value"] = val
                elif tipo == "fim":
                    self.ocupado = False
                    self.btn.config(state="normal")
        except queue.Empty:
            pass
        self.raiz.after(100, self._ler_fila)

    def iniciar(self):
        if self.ocupado:
            return
        links = [l.strip() for l in self.txt_links.get("1.0", "end").splitlines() if l.strip()]
        if not links and not self.arquivos_locais:
            messagebox.showinfo("Nada para fazer", "Cole um link do YouTube ou adicione arquivos.")
            return
        if not FFMPEG:
            messagebox.showerror("ffmpeg ausente", "Abra o programa pelo Iniciar.bat.")
            return
        _, _, bitrate, mono, lufs = PRESETS[self.var_preset.get()]
        cfg = dict(
            links=links, locais=list(self.arquivos_locais), pasta=self.var_pasta.get(),
            bitrate=bitrate, mono=mono, lufs=lufs, codec=FORMATOS[self.var_formato.get()][2],
            normalizar=self.var_norm.get(), silencio=self.var_sil.get(),
            fade=self.var_fade.get(), nome_simples=self.var_nome.get(),
            playlist=self.var_playlist.get(),
            ini=self.var_ini.get().strip(), fim=self.var_fim.get().strip(),
        )
        self.ocupado = True
        self.btn.config(state="disabled")
        self.prog["value"] = 0
        threading.Thread(target=self._trabalho, args=(cfg,), daemon=True).start()

    # ------------------------------------------------------------ trabalho
    def _trabalho(self, cfg):
        os.makedirs(cfg["pasta"], exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="nauren_audio_")
        # cada tarefa: ("local", caminho, titulo) ou ("yt", url, titulo)
        tarefas = [("local", p, os.path.splitext(os.path.basename(p))[0]) for p in cfg["locais"]]
        antes = depois = feitos = 0
        try:
            if cfg["links"]:
                if yt_dlp is None:
                    self.log("✗ yt-dlp não está instalado; pulando os links.")
                else:
                    for link in cfg["links"]:
                        tarefas += self._expandir(link, cfg["playlist"])
            total = len(tarefas)
            if total:
                self.log(f"{total} áudio(s) na fila.\n")
            for i, (tipo, alvo, titulo) in enumerate(tarefas):
                base = i / total * 100
                passo = 100 / total
                if tipo == "yt":
                    self.log(f"↓ Baixando {i + 1} de {total}: {titulo or alvo}")
                    origem, titulo2 = self._baixar_um(alvo, tmp, base, passo * 0.7,
                                                      self._segundos(cfg["ini"]),
                                                      self._segundos(cfg["fim"]))
                    if not origem:
                        continue
                    titulo = titulo2 or titulo or "audio"
                else:
                    origem = alvo
                    self.log(f"→ Convertendo {i + 1} de {total}: {titulo}")
                destino = self._destino(cfg, titulo)
                # trecho de link do YouTube já vem cortado no download
                ok, erro = self._converter(origem, destino, cfg, cortar=(tipo == "local"))
                if ok:
                    antes += os.path.getsize(origem)
                    depois += os.path.getsize(destino)
                    feitos += 1
                    self.log(f"  ✓ {os.path.basename(destino)}  ({tamanho(origem)} → {tamanho(destino)})")
                else:
                    self.log(f"  ✗ Falhou: {erro}")
                if tipo == "yt":
                    try:
                        os.remove(origem)
                    except OSError:
                        pass
                self.fila.put(("prog", base + passo))
            if feitos:
                self.log(f"\nPronto! {feitos} arquivo(s): {antes/1048576:.1f} MB → {depois/1048576:.1f} MB"
                         f"\nPasta: {cfg['pasta']}")
                if os.name == "nt":
                    os.startfile(cfg["pasta"])
            elif total:
                self.log("\nNenhum arquivo foi gerado. Veja os erros acima.")
        except Exception as e:
            self.log(f"✗ Erro: {e}")
            _registrar_erro(type(e), e, e.__traceback__)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.fila.put(("prog", 100))
            self.fila.put(("fim", None))

    def _expandir(self, link, playlist_inteira):
        """Transforma um link em uma lista de vídeos (sem baixar nada ainda)."""
        opcoes = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
                  "noplaylist": not playlist_inteira, "playlistend": 300}
        self.log(f"🔎 Lendo link: {link}")
        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                info = ydl.extract_info(link, download=False)
        except Exception as e:
            self.log(f"  ✗ Não consegui ler o link: {e}")
            return []
        if not info:
            return []
        if info.get("entries") is not None:
            lista = []
            for e in info["entries"]:
                if not e:
                    continue
                url = e.get("url") or e.get("webpage_url") or e.get("id")
                if url:
                    lista.append(("yt", url, e.get("title")))
            self.log(f"  Playlist “{info.get('title') or ''}”: {len(lista)} vídeo(s)")
            return lista
        return [("yt", info.get("webpage_url") or link, info.get("title"))]

    def _baixar_um(self, url, tmp, base, faixa, ini=None, fim=None):
        resultado = {}

        def gancho(d):
            if d["status"] == "downloading":
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if tot:
                    self.fila.put(("prog", base + faixa * d.get("downloaded_bytes", 0) / tot))
            elif d["status"] == "finished":
                resultado["arquivo"] = d["filename"]
                resultado["titulo"] = d.get("info_dict", {}).get("title")

        opcoes = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
            "quiet": True, "no_warnings": True, "noprogress": True,
            "noplaylist": True,
            "progress_hooks": [gancho],
        }
        if FFMPEG:
            opcoes["ffmpeg_location"] = FFMPEG
        if ini or fim:
            from yt_dlp.utils import download_range_func
            opcoes["download_ranges"] = download_range_func(
                None, [(ini or 0, fim if fim else float("inf"))])
            self.log(f"  (baixando só o trecho {cfg_tempo(ini or 0)} → "
                     f"{cfg_tempo(fim) if fim else 'fim'})")
        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                ydl.download([url])
        except Exception as e:
            self.log(f"  ✗ Não consegui baixar: {e}")
            return None, None
        if not resultado.get("arquivo") or not os.path.exists(resultado["arquivo"]):
            self.log("  ✗ O download não gerou arquivo.")
            return None, None
        return resultado["arquivo"], resultado.get("titulo")

    def _destino(self, cfg, titulo):
        base = nome_seguro(titulo, cfg["nome_simples"])
        destino = os.path.join(cfg["pasta"], base + ".ogg")
        n = 2
        while os.path.exists(destino):
            destino = os.path.join(cfg["pasta"], f"{base}-{n}.ogg")
            n += 1
        return destino

    def _duracao(self, arquivo):
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", arquivo], capture_output=True,
                           text=True, errors="ignore", creationflags=NO_WINDOW)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
        return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None

    @staticmethod
    def _segundos(txt):
        if not txt:
            return None
        partes = [float(p.replace(",", ".")) for p in txt.split(":")]
        s = 0.0
        for p in partes:
            s = s * 60 + p
        return s

    def _converter(self, origem, destino, cfg, cortar=True):
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
        ini, fim = (self._segundos(cfg["ini"]), self._segundos(cfg["fim"])) if cortar else (None, None)
        if ini:
            cmd += ["-ss", str(ini)]
        if fim:
            cmd += ["-to", str(fim)]
        cmd += ["-i", origem, "-vn", "-sn", "-dn", "-map_metadata", "-1"]

        filtros = []
        if cfg["silencio"]:
            sr = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.1"
            filtros += [sr, "areverse", sr, "areverse"]
        if cfg["normalizar"]:
            filtros.append(f"loudnorm=I={cfg['lufs']}:TP=-1.5:LRA=11")
        if cfg["fade"]:
            dur = self._duracao(origem)
            if dur:
                if fim:
                    dur = min(dur, fim)
                if ini:
                    dur -= ini
                if dur > 4:
                    filtros.append(f"afade=t=out:st={dur - 2:.2f}:d=2")
        if filtros:
            cmd += ["-af", ",".join(filtros)]

        if cfg["mono"]:
            cmd += ["-ac", "1"]
        else:
            cmd += ["-ac", "2"]

        br = cfg["bitrate"]
        if cfg["codec"] == "opus":
            cmd += ["-c:a", self.enc_opus, "-b:a", f"{br}k", "-ar", "48000"]
            if self.enc_opus == "libopus":
                cmd += ["-vbr", "on", "-compression_level", "10", "-application", "audio"]
            else:
                cmd += ["-strict", "-2"]
        else:
            # Vorbis precisa de um pouco mais de bitrate para soar igual
            br_v = max(br + 16, 48) if not cfg["mono"] else max(br, 40)
            cmd += ["-c:a", self.enc_vorbis, "-b:a", f"{br_v}k", "-ar", "44100"]
            if self.enc_vorbis != "libvorbis":
                cmd += ["-strict", "-2"]
        cmd.append(destino)

        r = subprocess.run(cmd, capture_output=True, text=True, errors="ignore",
                           creationflags=NO_WINDOW)
        if r.returncode != 0 or not os.path.exists(destino):
            return False, (r.stderr.strip().splitlines() or ["erro desconhecido"])[-1]
        return True, None


if __name__ == "__main__":
    raiz = tk.Tk()
    raiz.report_callback_exception = lambda t, v, tb: (
        _registrar_erro(t, v, tb),
        messagebox.showerror("Erro", f"{v}\n\nDetalhes salvos em erro.log"))
    App(raiz)
    raiz.mainloop()

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                          login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
from datetime import date, datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-troque-em-producao")
DB = os.path.join(os.path.dirname(__file__), "treinamentos.db")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta área."

# ── DB ──────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            nome TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'gestor',
            ativo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS setores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sigla TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS colaboradores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            setor_id INTEGER NOT NULL,
            ativo INTEGER DEFAULT 1,
            FOREIGN KEY (setor_id) REFERENCES setores(id)
        );
        CREATE TABLE IF NOT EXISTS treinamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            departamentos TEXT NOT NULL,
            sigla_doc TEXT,
            data_aprovacao TEXT,
            obs TEXT
        );
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            colaborador_id INTEGER NOT NULL,
            treinamento_id INTEGER NOT NULL,
            data_realizacao TEXT,
            na INTEGER DEFAULT 0,
            UNIQUE(colaborador_id, treinamento_id),
            FOREIGN KEY (colaborador_id) REFERENCES colaboradores(id),
            FOREIGN KEY (treinamento_id) REFERENCES treinamentos(id)
        );
    """)
    db.commit()

    # cria admin padrão na primeira execução, se não existir nenhum usuário
    existe = db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if existe == 0:
        senha_inicial = os.environ.get("ADMIN_SENHA_INICIAL", "admin123")
        db.execute(
            "INSERT INTO usuarios (login, senha_hash, nome, role) VALUES (?,?,?,?)",
            ("admin", generate_password_hash(senha_inicial), "Administrador", "admin")
        )
        db.commit()
        print(f"\n⚠️  Usuário admin criado. Login: admin / Senha: {senha_inicial}")
        print("   Troque essa senha assim que possível em /usuarios\n")

    db.close()

init_db()

def status_treinamento(data_aprovacao, data_realizacao, na):
    if na:
        return "NA"
    if not data_realizacao:
        return "não realizado"
    try:
        dt_aprov = datetime.strptime(data_aprovacao, "%Y-%m-%d").date() if data_aprovacao else None
        dt_real  = datetime.strptime(data_realizacao, "%Y-%m-%d").date()
        if dt_aprov is None:
            return "válido"
        return "válido" if dt_real >= dt_aprov else "não realizado"
    except:
        return "não realizado"

# ── LOGIN (Flask-Login) ───────────────────────────────────────────────────────

class Usuario(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.login = row["login"]
        self.nome = row["nome"]
        self.role = row["role"]

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM usuarios WHERE id=? AND ativo=1", (user_id,)).fetchone()
    db.close()
    return Usuario(row) if row else None

@app.context_processor
def inject_globals():
    db = get_db()
    all_setores = db.execute("SELECT * FROM setores ORDER BY sigla").fetchall()
    db.close()
    return dict(all_setores=all_setores, current_user=current_user)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        db = get_db()
        row = db.execute(
            "SELECT * FROM usuarios WHERE login=? AND ativo=1", (request.form["login"].strip(),)
        ).fetchone()
        db.close()
        if row and check_password_hash(row["senha_hash"], request.form["senha"]):
            login_user(Usuario(row))
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Login ou senha incorretos.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# ── GESTÃO DE USUÁRIOS (somente admin) ────────────────────────────────────────

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Apenas administradores podem acessar essa área.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/usuarios")
@admin_required
def usuarios():
    db = get_db()
    rows = db.execute("SELECT * FROM usuarios WHERE ativo=1 ORDER BY nome").fetchall()
    db.close()
    return render_template("usuarios.html", usuarios=rows)

@app.route("/usuarios/novo", methods=["POST"])
@admin_required
def novo_usuario():
    db = get_db()
    try:
        db.execute(
            "INSERT INTO usuarios (login, senha_hash, nome, role) VALUES (?,?,?,?)",
            (request.form["login"].strip(), generate_password_hash(request.form["senha"]),
             request.form["nome"].strip(), request.form["role"])
        )
        db.commit()
        flash("Usuário criado com sucesso.", "ok")
    except sqlite3.IntegrityError:
        flash("Esse login já existe.", "error")
    db.close()
    return redirect(url_for("usuarios"))

@app.route("/usuarios/<int:uid>/desativar", methods=["POST"])
@admin_required
def desativar_usuario(uid):
    if uid == current_user.id:
        flash("Você não pode desativar seu próprio usuário.", "error")
        return redirect(url_for("usuarios"))
    db = get_db()
    db.execute("UPDATE usuarios SET ativo=0 WHERE id=?", (uid,))
    db.commit(); db.close()
    flash("Usuário desativado.", "ok")
    return redirect(url_for("usuarios"))

# ── ROUTES PRINCIPAIS (público) ────────────────────────────────────────────────

@app.route("/")
def index():
    db = get_db()
    setores = db.execute("SELECT * FROM setores ORDER BY sigla").fetchall()
    total_treinos = db.execute("SELECT COUNT(*) FROM treinamentos").fetchone()[0]
    total_colab   = db.execute("SELECT COUNT(*) FROM colaboradores WHERE ativo=1").fetchone()[0]
    registros = db.execute("""
        SELECT r.na, r.data_realizacao, t.data_aprovacao
        FROM registros r JOIN treinamentos t ON t.id=r.treinamento_id
    """).fetchall()
    contagem = {"válido":0,"não realizado":0,"NA":0}
    for r in registros:
        s = status_treinamento(r["data_aprovacao"], r["data_realizacao"], r["na"])
        contagem[s] = contagem.get(s,0)+1
    db.close()
    return render_template("index.html", setores=setores,
                           total_treinos=total_treinos, total_colab=total_colab,
                           contagem=contagem)

# ── BUSCA DE COLABORADOR (nav) ──────────────────────────────────────────────

@app.route("/api/buscar-colaborador")
def buscar_colaborador():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    db = get_db()
    rows = db.execute("""
        SELECT c.id, c.nome, s.sigla, s.nome as setor_nome
        FROM colaboradores c JOIN setores s ON s.id=c.setor_id
        WHERE c.ativo=1 AND c.nome LIKE ?
        ORDER BY c.nome LIMIT 12
    """, (f"%{q}%",)).fetchall()
    db.close()
    return jsonify([
        {"id": r["id"], "nome": r["nome"], "sigla": r["sigla"], "setor_nome": r["setor_nome"]}
        for r in rows
    ])

# ── TREINAMENTOS (Lista Doc) ──────────────────────────────────────────────────

@app.route("/treinamentos")
def treinamentos():
    db = get_db()
    rows = db.execute("SELECT * FROM treinamentos ORDER BY codigo").fetchall()
    setores = db.execute("SELECT * FROM setores ORDER BY sigla").fetchall()
    db.close()
    return render_template("treinamentos.html", treinamentos=rows, setores=setores)

@app.route("/treinamentos/novo", methods=["GET","POST"])
@login_required
def novo_treinamento():
    if request.method == "POST":
        db = get_db()
        db.execute("INSERT INTO treinamentos (codigo,departamentos,sigla_doc,data_aprovacao,obs) VALUES (?,?,?,?,?)",
            (request.form["codigo"], request.form["departamentos"],
             request.form["sigla_doc"], request.form["data_aprovacao"] or None,
             request.form["obs"]))
        db.commit(); db.close()
        flash("Treinamento cadastrado.", "ok")
        return redirect(url_for("treinamentos"))
    return render_template("form_treinamento.html", t=None)

@app.route("/treinamentos/<int:tid>/editar", methods=["GET","POST"])
@login_required
def editar_treinamento(tid):
    db = get_db()
    if request.method == "POST":
        db.execute("UPDATE treinamentos SET codigo=?,departamentos=?,sigla_doc=?,data_aprovacao=?,obs=? WHERE id=?",
            (request.form["codigo"], request.form["departamentos"],
             request.form["sigla_doc"], request.form["data_aprovacao"] or None,
             request.form["obs"], tid))
        db.commit(); db.close()
        flash("Treinamento atualizado.", "ok")
        return redirect(url_for("treinamentos"))
    t = db.execute("SELECT * FROM treinamentos WHERE id=?", (tid,)).fetchone()
    db.close()
    return render_template("form_treinamento.html", t=t)

@app.route("/treinamentos/<int:tid>/excluir", methods=["POST"])
@login_required
def excluir_treinamento(tid):
    db = get_db()
    db.execute("DELETE FROM registros WHERE treinamento_id=?", (tid,))
    db.execute("DELETE FROM treinamentos WHERE id=?", (tid,))
    db.commit(); db.close()
    flash("Treinamento excluído.", "ok")
    return redirect(url_for("treinamentos"))

# ── COLABORADORES ─────────────────────────────────────────────────────────────

@app.route("/colaboradores")
def colaboradores():
    db = get_db()
    rows = db.execute("""
        SELECT c.*, s.sigla, s.nome as setor_nome
        FROM colaboradores c JOIN setores s ON s.id=c.setor_id
        WHERE c.ativo=1 ORDER BY s.sigla, c.nome
    """).fetchall()
    setores = db.execute("SELECT * FROM setores ORDER BY sigla").fetchall()
    db.close()
    return render_template("colaboradores.html", colaboradores=rows, setores=setores)

@app.route("/colaboradores/novo", methods=["POST"])
@login_required
def novo_colaborador():
    db = get_db()
    db.execute("INSERT INTO colaboradores (nome, setor_id) VALUES (?,?)",
               (request.form["nome"], request.form["setor_id"]))
    db.commit(); db.close()
    flash("Colaborador cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

@app.route("/colaboradores/<int:cid>/excluir", methods=["POST"])
@login_required
def excluir_colaborador(cid):
    db = get_db()
    db.execute("UPDATE colaboradores SET ativo=0 WHERE id=?", (cid,))
    db.commit(); db.close()
    flash("Colaborador desativado.", "ok")
    return redirect(url_for("colaboradores"))

# ── SETORES ───────────────────────────────────────────────────────────────────

@app.route("/setores/novo", methods=["POST"])
@login_required
def novo_setor():
    db = get_db()
    db.execute("INSERT OR IGNORE INTO setores (sigla, nome) VALUES (?,?)",
               (request.form["sigla"].upper(), request.form["nome"]))
    db.commit(); db.close()
    flash("Setor cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

# ── SETOR DASHBOARD ───────────────────────────────────────────────────────────

@app.route("/setor/<sigla>")
def setor(sigla):
    db = get_db()
    s = db.execute("SELECT * FROM setores WHERE sigla=?", (sigla,)).fetchone()
    if not s:
        db.close()
        return "Setor não encontrado", 404

    colabs = db.execute(
        "SELECT * FROM colaboradores WHERE setor_id=? AND ativo=1 ORDER BY nome", (s["id"],)
    ).fetchall()

    treinos = db.execute("SELECT * FROM treinamentos ORDER BY codigo").fetchall()
    treinos_setor = [t for t in treinos if sigla in [x.strip() for x in t["departamentos"].split(",")]]

    matriz = []
    for t in treinos_setor:
        linha = {"treinamento": t, "cells": []}
        for c in colabs:
            reg = db.execute(
                "SELECT * FROM registros WHERE colaborador_id=? AND treinamento_id=?",
                (c["id"], t["id"])
            ).fetchone()
            if reg:
                st = status_treinamento(t["data_aprovacao"], reg["data_realizacao"], reg["na"])
                linha["cells"].append({"colab_id": c["id"], "data": reg["data_realizacao"], "na": reg["na"], "status": st, "reg_id": reg["id"]})
            else:
                linha["cells"].append({"colab_id": c["id"], "data": None, "na": False, "status": "—", "reg_id": None})
        matriz.append(linha)

    db.close()
    destaque_colab = request.args.get("colab", type=int)
    return render_template("setor.html", setor=s, colabs=colabs, matriz=matriz,
                           hoje=date.today().isoformat(), destaque_colab=destaque_colab)

@app.route("/registro/salvar", methods=["POST"])
@login_required
def salvar_registro():
    db = get_db()
    colab_id    = request.form["colab_id"]
    treino_id   = request.form["treino_id"]
    data_real   = request.form.get("data_realizacao") or None
    na          = 1 if request.form.get("na") else 0
    db.execute("""
        INSERT INTO registros (colaborador_id, treinamento_id, data_realizacao, na)
        VALUES (?,?,?,?)
        ON CONFLICT(colaborador_id, treinamento_id)
        DO UPDATE SET data_realizacao=excluded.data_realizacao, na=excluded.na
    """, (colab_id, treino_id, data_real, na))
    db.commit(); db.close()
    return jsonify({"ok": True})

# ── EXPORTAR EXCEL (público) ───────────────────────────────────────────────────

@app.route("/exportar/<sigla>")
def exportar_excel(sigla):
    db = get_db()
    s = db.execute("SELECT * FROM setores WHERE sigla=?", (sigla,)).fetchone()
    if not s:
        db.close()
        return "Setor não encontrado", 404
    colabs = db.execute(
        "SELECT * FROM colaboradores WHERE setor_id=? AND ativo=1 ORDER BY nome", (s["id"],)
    ).fetchall()
    treinos = db.execute("SELECT * FROM treinamentos ORDER BY codigo").fetchall()
    treinos_setor = [t for t in treinos if sigla in [x.strip() for x in t["departamentos"].split(",")]]

    wb = Workbook()
    ws = wb.active
    ws.title = sigla

    verde    = PatternFill("solid", fgColor="92D050")
    vermelho = PatternFill("solid", fgColor="FFC7CE")
    cinza    = PatternFill("solid", fgColor="D9D9D9")
    azul_h   = PatternFill("solid", fgColor="1F4E79")

    bold_w = Font(bold=True, color="FFFFFF")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:E1")
    ws["A1"] = "Lista de Treinamentos"
    ws["A1"].font = Font(bold=True, size=12, color="FFFFFF")
    ws["A1"].fill = azul_h
    ws["A1"].alignment = center

    col = 6
    for c in colabs:
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col+1)
        cell = ws.cell(row=1, column=col, value=c["nome"])
        cell.font = bold_w; cell.fill = azul_h; cell.alignment = center
        col += 2

    headers = ["Item","Treinamento","Departamentos Aplicáveis","Sigla do Doc","Data de Aprovação"]
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=2, column=i, value=h)
        c.font = bold_w; c.fill = azul_h; c.alignment = center; c.border = border

    col = 6
    for _ in colabs:
        for lbl in ["Data do Treinamento","Status do Treinamento"]:
            c = ws.cell(row=2, column=col, value=lbl)
            c.font = bold_w; c.fill = azul_h; c.alignment = center; c.border = border
            col += 1

    for idx, t in enumerate(treinos_setor, 1):
        row = idx + 2
        vals = [idx, t["codigo"], t["departamentos"], t["sigla_doc"], t["data_aprovacao"] or ""]
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=ci, value=v)
            cell.alignment = center; cell.border = border

        col = 6
        for c in colabs:
            reg = db.execute(
                "SELECT * FROM registros WHERE colaborador_id=? AND treinamento_id=?",
                (c["id"], t["id"])
            ).fetchone()
            if reg:
                st = status_treinamento(t["data_aprovacao"], reg["data_realizacao"], reg["na"])
                data_val = reg["data_realizacao"] if not reg["na"] else "NA"
                st_val = st
            else:
                data_val = ""; st_val = "—"; st = "—"

            dc = ws.cell(row=row, column=col, value=data_val)
            dc.alignment = center; dc.border = border
            sc = ws.cell(row=row, column=col+1, value=st_val)
            sc.alignment = center; sc.border = border
            if st == "válido": sc.fill = verde
            elif st == "não realizado": sc.fill = vermelho
            elif st == "NA": sc.fill = cinza
            col += 2

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 16
    col = 6
    for _ in colabs:
        ws.column_dimensions[get_column_letter(col)].width = 16
        ws.column_dimensions[get_column_letter(col+1)].width = 16
        col += 2

    db.close()
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    fname = f"Treinamentos_{sigla}_{date.today()}.xlsx"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    print("\n✅  Acesse: http://localhost:5000\n")
    app.run(debug=True, host="0.0.0.0", port=5000)

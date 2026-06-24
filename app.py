from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import date, datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-troque-em-producao")

# Configuração do banco de dados SQLite via SQLAlchemy
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'treinamentos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta área."

# ── MODELOS ORM (SQLAlchemy) ──────────────────────────────────────────────────

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False) # Mudado de 'login' para 'email' conforme novo HTML
    senha_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='gestor')
    ativo = db.Column(db.Integer, default=1)

class Setor(db.Model):
    __tablename__ = 'setores'
    id = db.Column(db.Integer, primary_key=True)
    sigla = db.Column(db.String(10), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    colaboradores = db.relationship('Colaborador', backref='setor', lazy=True)

class Colaborador(db.Model):
    __tablename__ = 'colaboradores'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setores.id'), nullable=False)
    ativo = db.Column(db.Integer, default=1)
    registros = db.relationship('Registro', backref='colaborador', cascade="all, delete-orphan", lazy=True)

class Treinamento(db.Model):
    __tablename__ = 'treinamentos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(100), nullable=False) # Contém o código e nome ("IT-LAB-001...")
    departamentos = db.Column(db.String(200), nullable=False)
    sigla_doc = db.Column(db.String(50))
    data_aprovacao = db.Column(db.String(20))
    obs = db.Column(db.Text)
    registros = db.relationship('Registro', backref='treinamento', cascade="all, delete-orphan", lazy=True)

    # Propriedade dinâmica para compatibilidade com os templates que buscam .nome e .observacoes
    @property
    def nome(self):
        return self.codigo
    
    @property
    def observacoes(self):
        return self.obs

class Registro(db.Model):
    __tablename__ = 'registros'
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)
    treinamento_id = db.Column(db.Integer, db.ForeignKey('treinamentos.id'), nullable=False)
    data_realizacao = db.Column(db.String(20))
    na = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint('colaborador_id', 'treinamento_id', name='_colab_treino_uc'),)

# Helper de status
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

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.filter_by(id=int(user_id), ativo=1).first()

@app.context_processor
def inject_globals():
    all_setores = Setor.query.order_by(Setor.sigla).all()
    return dict(all_setores=all_setores, current_user=current_user)

# ── AUTENTICAÇÃO (API JSON & VIEWS) ───────────────────────────────────────────

@app.route("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")

    user = Usuario.query.filter_by(email=email, ativo=1).first()
    if user and check_password_hash(user.senha_hash, password):
        login_user(user)
        return jsonify({"ok": True, "redirect_url": url_for("index")})
    
    return jsonify({"error": "E-mail ou senha incorretos."}), 400

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    nome = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not nome or not email or not password:
        return jsonify({"error": "Preencha todos os campos."}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "Este e-mail já está cadastrado."}), 400

    novo_usuario = Usuario(
        nome=nome,
        email=email,
        senha_hash=generate_password_hash(password),
        role='gestor'
    )
    db.session.add(novo_usuario)
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# Decorator Administrativo
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Apenas administradores podem acessar essa área.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

# ── ROTAS OPERACIONAIS ────────────────────────────────────────────────────────

@app.route("/")
def index():
    setores = Setor.query.order_by(Setor.sigla).all()
    total_treinos = Treinamento.query.count()
    total_colab = Colaborador.query.filter_by(ativo=1).count()
    
    registros = db.session.query(Registro.na, Registro.data_realizacao, Treinamento.data_aprovacao)\
        .join(Treinamento, Treinamento.id == Registro.treinamento_id).all()
        
    contagem = {"válido": 0, "não realizado": 0, "NA": 0}
    for r in registros:
        s = status_treinamento(r.data_aprovacao, r.data_realizacao, r.na)
        if s in contagem:
            contagem[s] += 1
            
    return render_template("index.html", setores=setores, total_treinamentos=total_treinos, 
                           total_validos=contagem["válido"], total_nao_realizados=contagem["não realizado"])

@app.route("/api/buscar-colaborador")
def buscar_colaborador():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    
    results = Colaborador.query.join(Setor).filter(
        Colaborador.ativo == 1,
        Colaborador.nome.like(f"%{q}%")
    ).order_by(Colaborador.nome).limit(12).all()
    
    return jsonify([
        {"id": r.id, "nome": r.nome, "sigla": r.setor.sigla, "setor_nome": r.setor.nome}
        for r in results
    ])

@app.route("/treinamentos")
def treinamentos():
    rows = Treinamento.query.order_by(Treinamento.codigo).all()
    setores = Setor.query.order_by(Setor.sigla).all()
    return render_template("treinamentos.html", treinamentos=rows, setores=setores)

@app.route("/treinamentos/novo", methods=["GET","POST"])
@login_required
def novo_treinamento():
    if request.method == "POST":
        t = Treinamento(
            codigo=request.form["codigo"],
            departamentos=request.form["departamentos"],
            sigla_doc=request.form["sigla_doc"],
            data_aprovacao=request.form["data_aprovacao"] or None,
            obs=request.form["obs"]
        )
        db.session.add(t)
        db.session.commit()
        flash("Treinamento cadastrado.", "ok")
        return redirect(url_for("treinamentos"))
    return render_template("form_treinamento.html", t=None)

@app.route("/treinamentos/<int:tid>/editar", methods=["GET","POST"])
@login_required
def editar_treinamento(tid):
    t = Treinamento.query.get_or_404(tid)
    if request.method == "POST":
        t.codigo = request.form["codigo"]
        t.departamentos = request.form["departamentos"]
        t.sigla_doc = request.form["sigla_doc"]
        t.data_aprovacao = request.form["data_aprovacao"] or None
        t.obs = request.form["obs"]
        db.session.commit()
        flash("Treinamento atualizado.", "ok")
        return redirect(url_for("treinamentos"))
    return render_template("form_treinamento.html", t=t)

@app.route("/colaboradores")
def colaboradores():
    setores = Setor.query.order_by(Setor.sigla).all()
    pesquisa = request.args.get("busca_nome", "").strip()
    
    if pesquisa:
        colabs = Colaborador.query.join(Setor).filter(
            Colaborador.ativo == 1, Colaborador.nome.like(f"%{pesquisa}%")
        ).order_by(Setor.sigla, Colaborador.nome).all()
    else:
        colabs = Colaborador.query.join(Setor).filter(Colaborador.ativo == 1).order_by(Setor.sigla, Colaborador.nome).all()
        
    # Adaptação para passar os objetos corretos esperados pelo template
    colaboradores_adaptados = []
    for c in colabs:
        colaboradores_adaptados.append({
            "id": c.id, "nome": c.nome, "sigla": c.setor.sigla, "setor_nome": c.setor.nome
        })
    return render_template("colaboradores.html", colaboradores=colaboradores_adaptados, setores=setores, pesquisa=pesquisa)

@app.route("/colaboradores/novo", methods=["POST"])
@login_required
def novo_colaborador():
    c = Colaborador(nome=request.form["nome"], setor_id=int(request.form["setor_id"]))
    db.session.add(c)
    db.session.commit()
    flash("Colaborador cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

@app.route("/colaboradores/<int:cid>/excluir", methods=["POST"])
@login_required
def excluir_colaborador(cid):
    c = Colaborador.query.get_or_404(cid)
    c.ativo = 0
    db.session.commit()
    flash("Colaborador desativado.", "ok")
    return redirect(url_for("colaboradores"))

@app.route("/setores/novo", methods=["POST"])
@login_required
def novo_setor():
    sigla_up = request.form["sigla"].upper().strip()
    if not Setor.query.filter_by(sigla=sigla_up).first():
        s = Setor(sigla=sigla_up, nome=request.form["nome"].strip())
        db.session.add(s)
        db.session.commit()
        flash("Setor cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

# ── DASHBOARD DO SETOR (RAIO-X CORRIGIDO) ─────────────────────────────────────

@app.route("/setor/<sigla>")
def setor(sigla):
    s = Setor.query.filter_by(sigla=sigla).first_or_404()
    colabs = Colaborador.query.filter_by(setor_id=s.id, ativo=1).order_by(Colaborador.nome).all()
    
    todos_treinos = Treinamento.query.order_by(Treinamento.codigo).all()
    treinos_setor = [t for t in todos_treinos if sigla in [x.strip() for x in t.departamentos.split(",")]]
    
    filtro = request.args.get("filtro", "").strip().lower()
    if filtro:
        treinos_setor = [t for t in treinos_setor if filtro in t.codigo.lower() or filtro in (t.obs or "").lower()]
        
    # Coleta todos os registros deste setor para a matriz de dados
    colab_ids = [c.id for c in colabs]
    registros_query = Registro.query.filter(Registro.colaborador_id.in_(colab_ids)).all() if colab_ids else []

    return render_template(
        "setor.html", 
        setor=s, 
        colaboradores_setor=colabs,       # Corrigido conforme nome usado no setor.html
        treinamentos_setor=treinos_setor,   # Corrigido conforme nome usado no setor.html
        matriz_dados=registros_query,       # Corrigido conforme nome usado no setor.html
        hoje=date.today().isoformat()
    )

@app.route("/registro/salvar", methods=["POST"])
@login_required
def salvar_registro():
    colab_id = int(request.form["colab_id"])
    treino_id = int(request.form["treino_id"])
    data_real = request.form.get("data_realizacao") or None
    na = 1 if request.form.get("na") else 0
    
    reg = Registro.query.filter_by(colaborador_id=colab_id, treinamento_id=treino_id).first()
    if reg:
        reg.data_realizacao = data_real
        reg.na = na
    else:
        reg = Registro(colaborador_id=colab_id, treinamento_id=treino_id, data_realizacao=data_real, na=na)
        db.session.add(reg)
        
    db.session.commit()
    return jsonify({"ok": True})

# ── EXPORTAR EXCEL CONFORME MODELO ───────────────────────────────────────────

@app.route("/setor/<int:sid>/exportar")
def exportar_excel(sid):
    s = Setor.query.get_or_404(sid)
    colabs = Colaborador.query.filter_by(setor_id=s.id, ativo=1).order_by(Colaborador.nome).all()
    todos_treinos = Treinamento.query.order_by(Treinamento.codigo).all()
    treinos_setor = [t for t in todos_treinos if s.sigla in [x.strip() for x in t.departamentos.split(",")]]

    wb = Workbook()
    ws = wb.active
    ws.title = s.sigla

    verde = PatternFill("solid", fgColor="92D050")
    vermelho = PatternFill("solid", fgColor="FFC7CE")
    cinza = PatternFill("solid", fgColor="D9D9D9")
    azul_h = PatternFill("solid", fgColor="1F4E79")

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
        cell = ws.cell(row=1, column=col, value=c.nome)
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
        vals = [idx, t.codigo, t.departamentos, t.sigla_doc, t.data_aprovacao or ""]
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=ci, value=v)
            cell.alignment = center; cell.border = border

        col = 6
        for c in colabs:
            reg = Registro.query.filter_by(colaborador_id=c.id, treinamento_id=t.id).first()
            if reg:
                st = status_treinamento(t.data_aprovacao, reg.data_realizacao, reg.na)
                data_val = reg.data_realizacao if not reg.na else "NA"
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

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    fname = f"Treinamentos_{s.sigla}_{date.today()}.xlsx"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Inicialização do Banco com Admin Padrão
with app.app_context():
    db.create_all()
    if Usuario.query.count() == 0:
        senha_inicial = os.environ.get("ADMIN_SENHA_INICIAL", "admin123")
        admin = Usuario(
            nome="Administrador",
            email="admin@empresa.com", # Usando e-mail padrão do sistema
            senha_hash=generate_password_hash(senha_inicial),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print(f"\n⚠️ Usuário admin criado. E-mail: admin@empresa.com / Senha: {senha_inicial}\n")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

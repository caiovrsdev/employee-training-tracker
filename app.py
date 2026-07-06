import os, io
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-troque-em-producao")
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), 'treinamentos.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ── MODELOS ───────────────────────────────────────────────────────────────────
class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
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
    cargo = db.Column(db.String(50), nullable=False, default='analista') # NOVO CAMPO
    setor_id = db.Column(db.Integer, db.ForeignKey('setores.id'), nullable=False)
    ativo = db.Column(db.Integer, default=1)
    registros = db.relationship('Registro', backref='colaborador', cascade="all, delete-orphan", lazy=True)

class Treinamento(db.Model):
    __tablename__ = 'treinamentos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(100), nullable=False)
    departamentos = db.Column(db.String(200), nullable=False)
    sigla_doc = db.Column(db.String(50))
    data_aprovacao = db.Column(db.String(20))
    obs = db.Column(db.Text)
    registros = db.relationship('Registro', backref='treinamento', cascade="all, delete-orphan", lazy=True)
    @property
    def nome(self): return self.codigo

class Registro(db.Model):
    __tablename__ = 'registros'
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)
    treinamento_id = db.Column(db.Integer, db.ForeignKey('treinamentos.id'), nullable=False)
    data_realizacao = db.Column(db.String(20))
    na = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint('colaborador_id', 'treinamento_id', name='_colab_treino_uc'),)

# ── FUNÇÕES GLOBAIS ───────────────────────────────────────────────────────────
def status_treinamento(data_aprovacao, data_realizacao, na):
    if na: return "NA"
    if not data_realizacao: return "não realizado"
    if not data_aprovacao: return "válido"
    try:
        dt_aprov = datetime.strptime(data_aprovacao, "%Y-%m-%d").date()
        dt_real  = datetime.strptime(data_realizacao, "%Y-%m-%d").date()
        return "pendente" if dt_aprov > dt_real else "válido"
    except: return "não realizado"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

@app.context_processor
def inject_globals():
    return dict(all_setores=Setor.query.order_by(Setor.sigla).all(), current_user=current_user, status_treinamento=status_treinamento)

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Acesso negado.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

# ── AUTENTICAÇÃO ──────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("index"))
    if request.method == "POST":
        login_input = (request.form.get("login") or request.form.get("email") or "").strip()
        senha_input = request.form.get("senha") or request.form.get("password")
        user = Usuario.query.filter_by(email="admin@empresa.com" if login_input=="admin" else login_input, ativo=1).first()
        if user and check_password_hash(user.senha_hash, senha_input):
            login_user(user)
            return redirect(url_for("index"))
        flash("Credenciais incorretas.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ── ROTAS PRINCIPAIS ──────────────────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    registros = db.session.query(Registro.na, Registro.data_realizacao, Treinamento.data_aprovacao).join(Treinamento).all()
    c = {"válido": 0, "não realizado": 0, "pendente": 0, "NA": 0}
    for r in registros:
        s = status_treinamento(r.data_aprovacao, r.data_realizacao, r.na)
        if s in c: c[s] += 1
    return render_template("index.html", t_validos=c["válido"], t_pendentes=c["não realizado"] + c["pendente"], total=Treinamento.query.count())

@app.route("/colaboradores")
@login_required
def colaboradores():
    pesquisa = request.args.get("busca_nome", "").strip()
    query = Colaborador.query.filter_by(ativo=1)
    if pesquisa: query = query.filter(Colaborador.nome.like(f"%{pesquisa}%"))
    return render_template("colaboradores.html", colaboradores=query.join(Setor).order_by(Colaborador.nome).all())

@app.route("/colaboradores/novo", methods=["POST"])
@login_required
def novo_colaborador():
    db.session.add(Colaborador(nome=request.form["nome"].strip(), setor_id=int(request.form["setor_id"]), cargo=request.form["cargo"]))
    db.session.commit()
    flash("Colaborador cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

# ABA INDIVIDUAL DO COLABORADOR
@app.route("/colaborador/<int:cid>")
@login_required
def aba_colaborador(cid):
    c = Colaborador.query.get_or_404(cid)
    treinos = [t for t in Treinamento.query.order_by(Treinamento.codigo).all() if c.setor.sigla in [x.strip() for x in t.departamentos.split(",")]]
    registros = Registro.query.filter_by(colaborador_id=c.id).all()
    return render_template("colaborador.html", colab=c, treinamentos_setor=treinos, matriz_dados=registros)

@app.route("/setor/<sigla>")
@login_required
def setor(sigla):
    s = Setor.query.filter_by(sigla=sigla).first_or_404()
    colabs = Colaborador.query.filter_by(setor_id=s.id, ativo=1).order_by(Colaborador.nome).all()
    treinos = [t for t in Treinamento.query.order_by(Treinamento.codigo).all() if sigla in [x.strip() for x in t.departamentos.split(",")]]
    registros = Registro.query.filter(Registro.colaborador_id.in_([c.id for c in colabs])).all() if colabs else []
    return render_template("setor.html", setor=s, colaboradores_setor=colabs, treinamentos_setor=treinos, matriz_dados=registros)

# ROTA DO FUNIL (AJAX)
@app.route("/api/funil_colaboradores")
@login_required
def funil_colabs():
    setor_id = request.args.get("setor_id")
    cargo = request.args.get("cargo")
    query = Colaborador.query.filter_by(ativo=1)
    if setor_id: query = query.filter_by(setor_id=int(setor_id))
    if cargo: query = query.filter_by(cargo=cargo)
    
    resultados = [{"id": c.id, "nome": c.nome, "cargo": c.cargo.title()} for c in query.order_by(Colaborador.nome).all()]
    return jsonify(resultados)

# ROTA DE REGISTRO UNIFICADA (COM FORÇAR ATUALIZAÇÃO)
@app.route("/registro/salvar", methods=["POST"])
@login_required
def salvar_registro():
    try:
        cid, tid = int(request.form.get("colab_id")), int(request.form.get("treino_id"))
        data_real = request.form.get("data_realizacao") or None
        na = 1 if request.form.get("na") else 0
        forcar_atualizacao = request.form.get("atualizar") # Checagem do Switch

        if forcar_atualizacao: # Se marcou, invalida o treinamento imediatamente
            data_real = None
            na = 0

        reg = Registro.query.filter_by(colaborador_id=cid, treinamento_id=tid).first()
        if reg:
            reg.data_realizacao, reg.na = data_real, na
        else:
            db.session.add(Registro(colaborador_id=cid, treinamento_id=tid, data_realizacao=data_real, na=na))
            
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

with app.app_context():
    db.create_all()
    if not Usuario.query.first():
        db.session.add(Usuario(nome="Admin", email="admin@empresa.com", senha_hash=generate_password_hash("admin123"), role="admin"))
        db.session.commit()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

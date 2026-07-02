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

# ── CONFIGURAÇÕES GERAIS ──────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-troque-em-producao")
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), 'treinamentos.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta área."

# ── MODELOS ORM (SQLAlchemy) ──────────────────────────────────────────────────
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
    
    @property
    def observacoes(self): return self.obs

class Registro(db.Model):
    __tablename__ = 'registros'
    id = db.Column(db.Integer, primary_key=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)
    treinamento_id = db.Column(db.Integer, db.ForeignKey('treinamentos.id'), nullable=False)
    data_realizacao = db.Column(db.String(20))
    na = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint('colaborador_id', 'treinamento_id', name='_colab_treino_uc'),)

# ── HELPERS & DECORATORS ──────────────────────────────────────────────────────
def status_treinamento(data_aprovacao, data_realizacao, na):
    if na: return "NA"
    if not data_realizacao: return "não realizado"
    try:
        dt_aprov = datetime.strptime(data_aprovacao, "%Y-%m-%d").date() if data_aprovacao else None
        dt_real  = datetime.strptime(data_realizacao, "%Y-%m-%d").date()
        return "válido" if not dt_aprov or dt_real >= dt_aprov else "não realizado"
    except ValueError:
        return "não realizado"

def _find_user(identifier):
    """Resolve login como 'admin' para e-mail ou busca direto por e-mail."""
    email = "admin@empresa.com" if identifier == "admin" else identifier
    return Usuario.query.filter_by(email=email, ativo=1).first()

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Apenas administradores podem acessar essa área.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.filter_by(id=int(user_id), ativo=1).first()

@app.context_processor
def inject_globals():
    return dict(all_setores=Setor.query.order_by(Setor.sigla).all(), current_user=current_user)

# ── AUTENTICAÇÃO E USUÁRIOS ───────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        login_input = (request.form.get("login") or request.form.get("email") or "").strip()
        senha_input = request.form.get("senha") or request.form.get("password")
        
        user = _find_user(login_input)
        if user and check_password_hash(user.senha_hash, senha_input):
            login_user(user)
            return redirect(request.args.get("next") or url_for("index"))
            
        flash("Login ou senha incorretos.", "error")
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    user = _find_user((data.get("email") or "").strip())
    if user and check_password_hash(user.senha_hash, data.get("password", "")):
        login_user(user)
        return jsonify({"ok": True, "redirect_url": url_for("index")})
    return jsonify({"error": "E-mail ou senha incorretos."}), 400

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    nome, email, password = data.get("name", "").strip(), data.get("email", "").strip(), data.get("password", "")

    if not all([nome, email, password]):
        return jsonify({"error": "Preencha todos os campos."}), 400
    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "Este e-mail já está cadastrado."}), 400

    db.session.add(Usuario(nome=nome, email=email, senha_hash=generate_password_hash(password)))
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/usuarios")
@admin_required
def usuarios():
    return render_template("usuarios.html", usuarios=Usuario.query.filter_by(ativo=1).order_by(Usuario.nome).all())

@app.route("/usuarios/novo", methods=["POST"])
@admin_required
def novo_usuario():
    email = (request.form.get("email") or request.form.get("login") or "").strip()
    if Usuario.query.filter_by(email=email).first():
        flash("Esse e-mail já existe.", "error")
    else:
        db.session.add(Usuario(
            nome=request.form.get("nome", "").strip(),
            email=email,
            senha_hash=generate_password_hash(request.form.get("senha", "")),
            role=request.form.get("role", "gestor")
        ))
        db.session.commit()
        flash("Usuário criado com sucesso.", "ok")
    return redirect(url_for("usuarios"))

@app.route("/usuarios/<int:uid>/desativar", methods=["POST"])
@admin_required
def desativar_usuario(uid):
    if uid == current_user.id:
        flash("Você não pode desativar seu próprio usuário.", "error")
    else:
        Usuario.query.get_or_404(uid).ativo = 0
        db.session.commit()
        flash("Usuário desativado.", "ok")
    return redirect(url_for("usuarios"))

# ── ROTAS OPERACIONAIS GERAIS ─────────────────────────────────────────────────
@app.route("/")
def index():
    registros = db.session.query(Registro.na, Registro.data_realizacao, Treinamento.data_aprovacao).join(Treinamento).all()
    contagem = {"válido": 0, "não realizado": 0, "NA": 0}
    
    for r in registros:
        s = status_treinamento(r.data_aprovacao, r.data_realizacao, r.na)
        if s in contagem: contagem[s] += 1
            
    return render_template("index.html", 
                           setores=Setor.query.order_by(Setor.sigla).all(), 
                           total_treinamentos=Treinamento.query.count(), 
                           total_validos=contagem["válido"], 
                           total_nao_realizados=contagem["não realizado"])

@app.route("/api/buscar-colaborador")
def buscar_colaborador():
    q = request.args.get("q", "").strip()
    if len(q) < 2: return jsonify([])
    
    colabs = Colaborador.query.join(Setor).filter(Colaborador.ativo == 1, Colaborador.nome.like(f"%{q}%")).order_by(Colaborador.nome).limit(12).all()
    return jsonify([{"id": c.id, "nome": c.nome, "sigla": c.setor.sigla, "setor_nome": c.setor.nome} for c in colabs])

# ── CADASTROS BASE (Setores, Colaboradores, Treinamentos) ─────────────────────
@app.route("/setores/novo", methods=["POST"])
@login_required
def novo_setor():
    sigla = request.form["sigla"].upper().strip()
    if not Setor.query.filter_by(sigla=sigla).first():
        db.session.add(Setor(sigla=sigla, nome=request.form["nome"].strip()))
        db.session.commit()
        flash("Setor cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

@app.route("/colaboradores")
def colaboradores():
    pesquisa = request.args.get("busca_nome", "").strip()
    query = Colaborador.query.join(Setor).filter(Colaborador.ativo == 1)
    if pesquisa: query = query.filter(Colaborador.nome.like(f"%{pesquisa}%"))
    
    colabs_formatados = [{"id": c.id, "nome": c.nome, "sigla": c.setor.sigla, "setor_nome": c.setor.nome} 
                         for c in query.order_by(Setor.sigla, Colaborador.nome).all()]
                         
    return render_template("colaboradores.html", colaboradores=colabs_formatados, 
                           setores=Setor.query.order_by(Setor.sigla).all(), pesquisa=pesquisa)

@app.route("/colaboradores/novo", methods=["POST"])
@login_required
def novo_colaborador():
    db.session.add(Colaborador(nome=request.form["nome"], setor_id=int(request.form["setor_id"])))
    db.session.commit()
    flash("Colaborador cadastrado.", "ok")
    return redirect(url_for("colaboradores"))

@app.route("/colaboradores/<int:cid>/excluir", methods=["POST"])
@login_required
def excluir_colaborador(cid):
    Colaborador.query.get_or_404(cid).ativo = 0
    db.session.commit()
    flash("Colaborador desativado.", "ok")
    return redirect(url_for("colaboradores"))

@app.route("/treinamentos")
def treinamentos():
    return render_template("treinamentos.html", 
                           treinamentos=Treinamento.query.order_by(Treinamento.codigo).all(), 
                           setores=Setor.query.order_by(Setor.sigla).all())

@app.route("/treinamentos/novo", methods=["GET","POST"])
@login_required
def novo_treinamento():
    if request.method == "POST":
        db.session.add(Treinamento(
            codigo=request.form["codigo"], departamentos=request.form["departamentos"],
            sigla_doc=request.form["sigla_doc"], data_aprovacao=request.form["data_aprovacao"] or None, obs=request.form["obs"]
        ))
        db.session.commit()
        flash("Treinamento cadastrado.", "ok")
        return redirect(url_for("treinamentos"))
    return render_template("form_treinamento.html", t=None)

@app.route("/treinamentos/<int:tid>/editar", methods=["GET","POST"])
@login_required
def editar_treinamento(tid):
    t = Treinamento.query.get_or_404(tid)
    if request.method == "POST":
        t.codigo, t.departamentos = request.form["codigo"], request.form["departamentos"]
        t.sigla_doc, t.data_aprovacao = request.form["sigla_doc"], request.form["data_aprovacao"] or None
        t.obs = request.form["obs"]
        db.session.commit()
        flash("Treinamento atualizado.", "ok")
        return redirect(url_for("treinamentos"))
    return render_template("form_treinamento.html", t=t)

# ── DASHBOARD MATRIZ E EXPORTAÇÃO ─────────────────────────────────────────────
@app.route("/setor/<sigla>")
def setor(sigla):
    s = Setor.query.filter_by(sigla=sigla).first_or_404()
    colabs = Colaborador.query.filter_by(setor_id=s.id, ativo=1).order_by(Colaborador.nome).all()
    
    filtro = request.args.get("filtro", "").strip().lower()
    treinos_setor = [t for t in Treinamento.query.order_by(Treinamento.codigo).all() 
                     if sigla in [x.strip() for x in t.departamentos.split(",")] and 
                     (not filtro or filtro in t.codigo.lower() or filtro in (t.obs or "").lower())]
        
    colab_ids = [c.id for c in colabs]
    registros = Registro.query.filter(Registro.colaborador_id.in_(colab_ids)).all() if colab_ids else []

    return render_template("setor.html", setor=s, colaboradores_setor=colabs, 
                           treinamentos_setor=treinos_setor, matriz_dados=registros, hoje=date.today().isoformat())

@app.route("/registro/salvar", methods=["POST"])
@login_required
def salvar_registro():
    cid, tid = int(request.form["colab_id"]), int(request.form["treino_id"])
    data_real, na = request.form.get("data_realizacao") or None, 1 if request.form.get("na") else 0
    
    reg = Registro.query.filter_by(colaborador_id=cid, treinamento_id=tid).first()
    if reg:
        reg.data_realizacao, reg.na = data_real, na
    else:
        db.session.add(Registro(colaborador_id=cid, treinamento_id=tid, data_realizacao=data_real, na=na))
        
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/setor/<int:sid>/exportar")
def exportar_excel(sid):
    s = Setor.query.get_or_404(sid)
    colabs = Colaborador.query.filter_by(setor_id=s.id, ativo=1).order_by(Colaborador.nome).all()
    treinos = [t for t in Treinamento.query.order_by(Treinamento.codigo).all() if s.sigla in [x.strip() for x in t.departamentos.split(",")]]

    wb = Workbook()
    ws = wb.active
    ws.title = s.sigla

    # Estilos Otimizados
    styles = {
        "verde": PatternFill("solid", fgColor="92D050"), "vermelho": PatternFill("solid", fgColor="FFC7CE"),
        "cinza": PatternFill("solid", fgColor="D9D9D9"), "azul_h": PatternFill("solid", fgColor="1F4E79"),
        "bold_w": Font(bold=True, color="FFFFFF"), "center": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "border": Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
    }

    ws.merge_cells("A1:E1")
    ws["A1"].value, ws["A1"].font, ws["A1"].fill, ws["A1"].alignment = "Lista de Treinamentos", Font(bold=True, size=12, color="FFFFFF"), styles["azul_h"], styles["center"]

    # Header de Colaboradores e Configuração de Colunas
    for i, c in enumerate(colabs):
        col = 6 + (i * 2)
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col+1)
        cell = ws.cell(row=1, column=col, value=c.nome)
        cell.font, cell.fill, cell.alignment = styles["bold_w"], styles["azul_h"], styles["center"]
        ws.column_dimensions[get_column_letter(col)].width = ws.column_dimensions[get_column_letter(col+1)].width = 16

    # Headers Secundários
    headers = ["Item", "Treinamento", "Departamentos Aplicáveis", "Sigla do Doc", "Data de Aprovação"] + ["Data do Treinamento", "Status do Treinamento"] * len(colabs)
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=i, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = styles["bold_w"], styles["azul_h"], styles["center"], styles["border"]

    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width, ws.column_dimensions["D"].width, ws.column_dimensions["E"].width = 6, 30, 40, 12, 16

    # Preenchimento da Matriz
    for idx, t in enumerate(treinos, 1):
        row = idx + 2
        for ci, val in enumerate([idx, t.codigo, t.departamentos, t.sigla_doc, t.data_aprovacao or ""], 1):
            cell = ws.cell(row=row, column=ci, value=val)
            cell.alignment, cell.border = styles["center"], styles["border"]

        for i, c in enumerate(colabs):
            col = 6 + (i * 2)
            reg = Registro.query.filter_by(colaborador_id=c.id, treinamento_id=t.id).first()
            
            st = status_treinamento(t.data_aprovacao, reg.data_realizacao if reg else None, reg.na if reg else 0)
            data_val = (reg.data_realizacao if not reg.na else "NA") if reg else ""
            
            dc, sc = ws.cell(row=row, column=col, value=data_val), ws.cell(row=row, column=col+1, value=st if reg else "—")
            dc.alignment, dc.border, sc.alignment, sc.border = styles["center"], styles["border"], styles["center"], styles["border"]
            
            if st == "válido" and reg: sc.fill = styles["verde"]
            elif st == "não realizado" and reg: sc.fill = styles["vermelho"]
            elif st == "NA" and reg: sc.fill = styles["cinza"]

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"Treinamentos_{s.sigla}_{date.today()}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── INICIALIZAÇÃO ─────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    if not Usuario.query.first():
        senha_inicial = os.environ.get("ADMIN_SENHA_INICIAL", "admin123")
        db.session.add(Usuario(nome="Administrador", email="admin@empresa.com", senha_hash=generate_password_hash(senha_inicial), role="admin"))
        db.session.commit()
        print(f"\n⚠️ Usuário admin criado. E-mail: admin@empresa.com / Senha: {senha_inicial}\n")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)  

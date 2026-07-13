import os
import sys
import traceback
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# 1. INFRAESTRUTURA E CONFIGURAÇÃO ABSOLUTA
# ==========================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_dev_super_secreta')

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'ecolyzer_v3_clean.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

# ==========================================
# 2. CAMADA DE COMPATIBILIDADE ULTRA-BLINDADA
# ==========================================
class LegacyTemplateMixin:
    def __getitem__(self, key):
        columns = [c.key for c in self.__table__.columns]
        if isinstance(key, int):
            try:
                return getattr(self, columns[key], "")
            except Exception:
                return ""
        if isinstance(key, str):
            if key in ['id_colaborador', 'colaborador_id']:
                return getattr(self, 'colaborador_id', "")
            if key in ['id_setor', 'setor_id']:
                return getattr(self, 'setor_id', "")
            return getattr(self, key, "")
        return ""

    def get(self, key, default=None):
        val = self.__getitem__(key)
        return val if val != "" else default

# ==========================================
# 3. MODELOS DE PERSISTÊNCIA
# ==========================================
class Usuario(db.Model, UserMixin, LegacyTemplateMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Setor(db.Model, LegacyTemplateMixin):
    __tablename__ = 'setores'
    id = db.Column(db.Integer, primary_key=True)
    sigla = db.Column(db.String(10), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    colaboradores = db.relationship('Colaborador', backref='setor', lazy=True)

class Colaborador(db.Model, LegacyTemplateMixin):
    __tablename__ = 'colaboradores'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(50), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setores.id'), nullable=False)
    treinamentos = db.relationship('Treinamento', backref='colaborador', lazy=True)

class Treinamento(db.Model, LegacyTemplateMixin):
    __tablename__ = 'treinamentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    data_realizacao = db.Column(db.String(20), nullable=True)
    validade = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(50), nullable=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ==========================================
# 4. INTERFACES WEB (ROTAS GET)
# ==========================================
@app.route('/login', methods=['GET'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    return render_template('index.html', setores=Setor.query.all())

@app.route('/colaboradores')
@login_required
def colaboradores_page():
    return render_template('colaboradores.html', setores=Setor.query.all(), colaboradores=Colaborador.query.all())

@app.route('/treinamentos')
@login_required
def treinamentos_page():
    return render_template(
        'treinamentos.html', 
        setores=Setor.query.all(), 
        treinamentos=Treinamento.query.all(), 
        colaboradores=Colaborador.query.all()
    )

# CORREÇÃO DEFINITIVA DO TEMPLATE NOT FOUND:
# Em vez de tentar abrir uma página que não existe, renderiza a própria listagem 
# onde o formulário antigo/modal de novos treinamentos reside!
@app.route('/treinamentos/novo')
@login_required
def novo_treinamento():
    return render_template(
        'treinamentos.html',
        setores=Setor.query.all(),
        treinamentos=Treinamento.query.all(),
        colaboradores=Colaborador.query.all()
    )

# ==========================================
# 5. ENDPOINTS DE AUTENTICAÇÃO
# ==========================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    user = Usuario.query.filter_by(email=email).first()
    if user and check_password_hash(user.password, password):
        login_user(user)
        return jsonify({"success": True}), 200
        
    return jsonify({"error": "Credenciais invalidas."}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or request.form or {}
    nome = (data.get('nome') or data.get('name', '')).strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not nome or not email or not password:
        return jsonify({"error": "Dados incompletos."}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "E-mail ja cadastrado."}), 409

    try:
        novo_usuario = Usuario(nome=nome, email=email, password=generate_password_hash(password))
        db.session.add(novo_usuario)
        db.session.commit()
        login_user(novo_usuario)
        return jsonify({"success": True}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Falha no banco de dados."}), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))

# ==========================================
# 6. APIs DE CADASTRO
# ==========================================
@app.route('/api/setor/cadastrar', methods=['POST'])
@app.route('/api/setor', methods=['POST'])
@login_required
def api_setor():
    data = request.get_json(silent=True) or request.form or {}
    sigla = (data.get('sigla') or data.get('txt_sigla') or data.get('txtSigla') or data.get('sigla_setor') or '').strip().upper()
    nome = (data.get('nome') or data.get('txt_nome') or data.get('txtNome') or data.get('nome_setor') or data.get('name') or '').strip()
    
    if not sigla or not nome:
        return jsonify({"error": "Campos obrigatorios nao identificados."}), 400
    if Setor.query.filter_by(sigla=sigla).first():
        return jsonify({"error": "O setor ja existe."}), 409

    try:
        db.session.add(Setor(sigla=sigla, nome=nome))
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro de gravacao."}), 500

@app.route('/api/colaborador/cadastrar', methods=['POST'])
@app.route('/api/colaborador', methods=['POST'])
@login_required
def api_colaborador():
    data = request.get_json(silent=True) or request.form or {}
    nome = (data.get('nome') or data.get('txt_nome') or data.get('txtColaborador') or data.get('name') or '').strip()
    cargo = (data.get('cargo') or data.get('txt_cargo') or data.get('txtCargo') or data.get('funcao') or '').strip()
    setor_id = data.get('setor_id') or data.get('txt_setor_id') or data.get('setor') or data.get('sel_setor')

    if not all([nome, cargo, setor_id]):
        return jsonify({"error": "Dados de colaborador incompletos."}), 400

    try:
        db.session.add(Colaborador(nome=nome, cargo=cargo, setor_id=int(setor_id)))
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro de gravacao."}), 500

@app.route('/api/treinamento/cadastrar', methods=['POST'])
@app.route('/api/treinamento', methods=['POST'])
@login_required
def api_treinamento():
    data = request.get_json(silent=True) or request.form or {}
    
    nome = (data.get('nome') or data.get('txt_nome') or data.get('txtTreinamento') or data.get('nome_treinamento') or '').strip()
    data_realizacao = data.get('data_realizacao') or data.get('txt_data') or data.get('data') or data.get('txtDataRealizacao')
    validade = data.get('validade') or data.get('txt_validade') or data.get('validade_treinamento') or data.get('txtValidade')
    status = data.get('status') or data.get('txt_status') or data.get('status_treinamento') or 'Pendente'
    colaborador_id = data.get('colaborador_id') or data.get('txt_colaborador_id') or data.get('colaborador') or data.get('sel_colaborador')

    if not nome or not colaborador_id:
        return jsonify({"error": "Nome do treinamento e colaborador sao obrigatorios."}), 400

    try:
        novo_treinamento = Treinamento(
            nome=nome,
            data_realizacao=str(data_realizacao) if data_realizacao else "",
            validade=str(validade) if validade else "",
            status=str(status),
            colaborador_id=int(colaborador_id)
        )
        db.session.add(novo_treinamento)
        db.session.commit()
        
        if request.form:
            return redirect(url_for('treinamentos_page'))
        return jsonify({"success": True}), 201
    except Exception as err:
        db.session.rollback()
        print(f"--- ERRO CADASTRO TREINAMENTO --- Detalhes: {str(err)}", file=sys.stderr)
        return jsonify({"error": "Erro ao salvar treinamento no banco."}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

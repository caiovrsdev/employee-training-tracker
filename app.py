import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# 1. INFRAESTRUTURA E CONFIGURAÇÃO
# ==========================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_dev_super_secreta')

# Mantida a compatibilidade com a base original de treinamentos
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///treinamentos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

# ==========================================
# 2. MODELOS DE PERSISTÊNCIA (DATA SCHEMA)
# ==========================================
class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Setor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sigla = db.Column(db.String(10), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    colaboradores = db.relationship('Colaborador', backref='setor', lazy=True)

class Colaborador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(50), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ==========================================
# 3. INTERFACES WEB (PROTEÇÃO CONTRA ERRO 500)
# ==========================================
@app.route('/login', methods=['GET'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    setores_lista = Setor.query.all() or []
    return render_template('index.html', setores=setores_lista)

@app.route('/colaboradores')
@login_required
def colaboradores_page():
    # Injeção preemptiva de coleções limpas para mitigar quebras no Jinja2
    setores_lista = Setor.query.all() or []
    colaboradores_lista = Colaborador.query.all() or []
    return render_template('colaboradores.html', setores=setores_lista, colaboradores=colaboradores_lista)

@app.route('/treinamentos')
@login_required
def treinamentos_page():
    # Injeção de arrays vazios como contratos de interface com o frontend
    setores_lista = Setor.query.all() or []
    return render_template('treinamentos.html', setores=setores_lista, treinamentos=[], colaboradores=[])

# ==========================================
# 4. APIs DE AUTENTICAÇÃO
# ==========================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or request.form or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    user = Usuario.query.filter_by(email=email).first()
    if user and check_password_hash(user.password, password):
        login_user(user)
        return jsonify({"success": True}), 200
        
    return jsonify({"error": "Credenciais invalidas."}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or request.form or {}
    nome = (data.get('nome') or data.get('name', '')).strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not nome or not email or not password:
        return jsonify({"error": "Nome, e-mail e senha sao obrigatorios."}), 400

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
        return jsonify({"error": "Erro interno ao salvar no banco."}), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))

# ==========================================
# 5. APIs DE DOMÍNIO (NORMALIZAÇÃO DE DTO)
# ==========================================
@app.route('/api/setor', methods=['POST'])
@login_required
def api_setor():
    # Estrutura agnostica: processa requisicoes nativas de form ou payloads JSON via Fetch API
    data = request.get_json() or request.form or {}
    sigla = data.get('sigla', '').strip().upper()
    nome = data.get('nome', '').strip()
    
    if not sigla or not nome:
        return jsonify({"error": "Sigla e nome sao obrigatorios."}), 400
        
    if Setor.query.filter_by(sigla=sigla).first():
        return jsonify({"error": "O setor ja existe."}), 409

    try:
        db.session.add(Setor(sigla=sigla, nome=nome))
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro ao criar setor."}), 500

@app.route('/api/colaborador', methods=['POST'])
@login_required
def api_colaborador():
    data = request.get_json() or request.form or {}
    nome = data.get('nome', '').strip()
    cargo = data.get('cargo', '').strip()
    setor_id = data.get('setor_id')

    if not all([nome, cargo, setor_id]):
        return jsonify({"error": "Dados incompletos para colaborador."}), 400

    try:
        db.session.add(Colaborador(nome=nome, cargo=cargo, setor_id=int(setor_id)))
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Erro ao adicionar colaborador."}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

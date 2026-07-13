import os
import sys
import traceback
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# 1. INFRAESTRUTURA E CONFIGURAÇÃO
# ==========================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_dev_super_secreta')

# Engenharia de Caminho Absoluto com nomenclatura rotacionada (v2)
basedir = os.path.abspath(os.path.dirname(__file__))
default_db_url = f"sqlite:///{os.path.join(basedir, 'ecolyzer_v2.db')}"

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', default_db_url)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'
# ==========================================
# 2. INTERCEPTOR DE ERROS (LOGS NO TERMINAL)
# ==========================================
@app.errorhandler(Exception)
def handle_backend_exception(e):
    print("\n" + "="*50, file=sys.stderr)
    print("EXCEÇÃO DETECTADA NO BACKEND DA APLICAÇÃO", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    print("="*50 + "\n", file=sys.stderr)
    return jsonify({
        "error": "Erro interno de processamento no servidor.",
        "details": str(e)
    }), 500

# ==========================================
# 3. MODELOS DE PERSISTÊNCIA (DATA SCHEMA PLURALIZADO)
# ==========================================
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

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
    cargo = db.Column(db.String(50), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setores.id'), nullable=False)
    treinamentos = db.relationship('Treinamento', backref='colaborador', lazy=True)

class Treinamento(db.Model):
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
# 4. INTERFACES WEB (VIEWS)
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

# ==========================================
# 5. APIs DE AUTENTICAÇÃO
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
        return jsonify({"error": "Dados incompletos para registro."}), 400

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
        raise

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))

# ==========================================
# 6. APIs DE CADASTRO DE RECURSOS
# ==========================================
@app.route('/api/setor', methods=['POST'])
@login_required
def api_setor():
    data = request.get_json() or request.form or {}
    sigla = data.get('sigla', '').strip().upper()
    nome = data.get('nome', '').strip()
    
    if not sigla or not nome:
        return jsonify({"error": "Campos obrigatorios ausentes."}), 400
        
    if Setor.query.filter_by(sigla=sigla).first():
        return jsonify({"error": "O setor ja existe."}), 409

    try:
        db.session.add(Setor(sigla=sigla, nome=nome))
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception:
        db.session.rollback()
        raise

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
        raise

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

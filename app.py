import os
import sys
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_dev_super_secreta')

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'ecolyzer_v3_clean.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

# ==========================================
# MODELOS DE BANCO DE DADOS
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
    colaboradores = db.relationship('Colaborador', backref='setor_ref', lazy=True)

class Colaborador(db.Model):
    __tablename__ = 'colaboradores'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(50), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setores.id'), nullable=False)
    treinamentos = db.relationship('Treinamento', backref='colaborador_ref', lazy=True)

class Treinamento(db.Model):
    __tablename__ = 'treinamentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    departamentos = db.Column(db.String(200), nullable=True)
    sigla_doc = db.Column(db.String(20), nullable=True)
    data_aprovacao = db.Column(db.String(20), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ==========================================
# ROTAS DE PÁGINAS VISUAIS
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
    return render_template('treinamentos.html', treinamentos=Treinamento.query.all())

@app.route('/treinamentos/editar/<int:tid>')
@login_required
def editar_treinamento(tid):
    return redirect(url_for('treinamentos_page'))

# ==========================================
# ENDPOINTS DE AUTENTICAÇÃO E CADASTROS
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
    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "E-mail ja cadastrado."}), 409
    
    novo_usuario = Usuario(nome=nome, email=email, password=generate_password_hash(password))
    db.session.add(novo_usuario)
    db.session.commit()
    return jsonify({"success": True}), 201

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))

@app.route('/api/setor/cadastrar', methods=['POST'])
@login_required
def api_setor():
    data = request.get_json(silent=True) or request.form or {}
    db.session.add(Setor(sigla=(data.get('sigla') or '').strip().upper(), nome=(data.get('nome') or '').strip()))
    db.session.commit()
    return jsonify({"success": True}), 201

@app.route('/api/colaborador/cadastrar', methods=['POST'])
@login_required
def api_colaborador():
    data = request.get_json(silent=True) or request.form or {}
    db.session.add(Colaborador(nome=data.get('nome'), cargo=data.get('cargo'), setor_id=int(data.get('setor_id'))))
    db.session.commit()
    return jsonify({"success": True}), 201

# ---> A ROTA QUE VAI SALVAR O SEU NOVO TREINAMENTO <---
@app.route('/api/treinamento/cadastrar', methods=['POST'])
@login_required
def api_treinamento():
    nome = request.form.get('nome')
    if not nome:
        return redirect(url_for('treinamentos_page'))
    
    novo_treinamento = Treinamento(
        nome=nome,
        departamentos=request.form.get('departamentos', ''),
        sigla_doc=request.form.get('sigla_doc', ''),
        data_aprovacao=request.form.get('data_aprovacao', ''),
        observacoes=request.form.get('observacoes', '')
    )
    db.session.add(novo_treinamento)
    db.session.commit()
    return redirect(url_for('treinamentos_page'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

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

# --- MODELOS ---
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Treinamento(db.Model):
    __tablename__ = 'treinamentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    departamentos = db.Column(db.String(200), nullable=True) # Campo novo
    sigla_doc = db.Column(db.String(20), nullable=True)      # Campo novo
    data_aprovacao = db.Column(db.String(20), nullable=True) # Campo novo
    observacoes = db.Column(db.Text, nullable=True)          # Campo novo
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=True)

# (Mantenha os outros modelos Setor e Colaborador aqui)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    db.create_all()

# --- ROTAS CORRIGIDAS ---
@app.route('/treinamentos')
@login_required
def treinamentos_page():
    return render_template('treinamentos.html', treinamentos=Treinamento.query.all())

@app.route('/treinamentos/novo')
@login_required
def novo_treinamento():
    return redirect(url_for('treinamentos_page')) # Redireciona para o modal abrir

@app.route('/treinamentos/editar/<int:tid>')
@login_required
def editar_treinamento(tid):
    # Lógica de edição aqui
    return f"Editando treinamento {tid}"

# ... (Mantenha o restante das rotas de API que já funcionam)

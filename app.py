import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS DO FLASK E BANCO
# ==========================================
app = Flask(__name__)
# Chave secreta obrigatória para o Flask-Login (Pode mudar depois)
app.secret_key = 'chave_secreta_ecolyzer_super_segura'

# Configuração do Banco de Dados (SQLAlchemy)
basedir = os.path.abspath(os.path.dirname(__name__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'treinamentos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configuração do Flask-Login para proteger as páginas
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page' # Redireciona pra cá se não estiver logado

# ==========================================
# 2. MODELOS DE DADOS (Tabelas do Banco)
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
    # Relação: Um setor pode ter vários colaboradores vinculados
    colaboradores = db.relationship('Colaborador', backref='setor', lazy=True)

class Colaborador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cargo = db.Column(db.String(50), nullable=False)
    setor_id = db.Column(db.Integer, db.ForeignKey('setor.id'), nullable=False)

# (Se houver modelos de Treinamento e Matriz, pode adicionar abaixo futuramente)

# Carregador de usuário para o Flask-Login saber quem está logado na sessão
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Cria as tabelas do SQLite magicamente se elas ainda não existirem
with app.app_context():
    db.create_all()


# ==========================================
# 3. ROTAS DE AUTENTICAÇÃO E LOGIN
# ==========================================

@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        password = data.get('password')

        user = Usuario.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "E-mail ou senha incorretos."}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json() if request.is_json else request.form
        nome = data.get('nome')
        email = data.get('email')
        password = data.get('password')

        # Proteção contra e-mails duplicados
        if Usuario.query.filter_by(email=email).first():
            return jsonify({"error": "E-mail já cadastrado"}), 400

        novo_usuario = Usuario(
            nome=nome,
            email=email,
            password=generate_password_hash(password) # Senha criptografada!
        )
        db.session.add(novo_usuario)
        db.session.commit()
        
        login_user(novo_usuario) # Faz o login automático após registrar
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))


# ==========================================
# 4. ROTAS DA APLICAÇÃO (Protegidas)
# ==========================================

@app.route('/')
@login_required
def index():
    # Passando setores para a dashboard caso seja necessário renderizar os blocos
    setores = Setor.query.all()
    return render_template('index.html', setores=setores)

@app.route('/colaboradores')
@login_required
def colaboradores_page():
    # Pega todos os setores do banco e passa para o formulário
    setores = Setor.query.all()
    return render_template('colaboradores.html', setores=setores)

@app.route('/treinamentos')
@login_required
def treinamentos_page():
    return render_template('treinamentos.html')


# ==========================================
# 5. ROTAS DE CADASTRO DE DADOS (APIs)
# ==========================================

@app.route('/api/setor/cadastrar', methods=['POST'])
@login_required
def api_cadastrar_setor():
    try:
        sigla = request.form.get('sigla').upper()
        nome = request.form.get('nome')
        
        if Setor.query.filter_by(sigla=sigla).first():
            return "Setor já existe", 400

        novo_setor = Setor(sigla=sigla, nome=nome)
        db.session.add(novo_setor)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return str(e), 500

@app.route('/api/colaborador/cadastrar', methods=['POST'])
@login_required
def api_cadastrar_colaborador():
    try:
        nome = request.form.get('nome')
        cargo = request.form.get('cargo')
        setor_id = request.form.get('setor_id')

        novo_colaborador = Colaborador(nome=nome, cargo=cargo, setor_id=int(setor_id))
        db.session.add(novo_colaborador)
        db.session.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.session.rollback()
        return str(e), 500


# ==========================================
# 6. INICIAR A APLICAÇÃO
# ==========================================
if __name__ == '__main__':
    # Rodar em modo Debug na porta 5000
    app.run(debug=True, host='0.0.0.0', port=5000)

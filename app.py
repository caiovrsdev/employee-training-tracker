import os
import openpyxl
import traceback
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_dev_super_secreta_ecolyzer')

basedir = os.path.abspath(os.path.dirname(__file__))

db_nome_limpo = 'ecolyzer_v2_clean.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, db_nome_limpo)}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'timeout': 15}}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'

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
    treinamentos = db.relationship('Treinamento', backref='colaborador_ref', lazy=True, cascade="all, delete-orphan")

class Treinamento(db.Model):
    __tablename__ = 'treinamentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    departamentos = db.Column(db.String(200), nullable=True)
    sigla_doc = db.Column(db.String(20), nullable=True)
    data_aprovacao = db.Column(db.String(20), nullable=True)
    data_realizacao = db.Column(db.String(20), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    colaborador_id = db.Column(db.Integer, db.ForeignKey('colaboradores.id'), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

with app.app_context():
    db.create_all()

def calcular_status_treinamento(data_realizacao, data_aprovacao):
    if not data_realizacao or not data_aprovacao:
        return "Pendente"
    if data_realizacao > data_aprovacao:
        return "Valido"
    return "Pendente"

@app.context_processor
def utility_processor():
    return dict(get_status=calcular_status_treinamento)

@app.route('/login', methods=['GET'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('register.html')

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
    filtro_pendente = request.args.get('filtro') == 'pendente'
    all_treinamentos = Treinamento.query.all()
    if filtro_pendente:
        treinamentos_filtrados = [t for t in all_treinamentos if calcular_status_treinamento(t.data_realizacao, t.data_aprovacao) == "Pendente"]
    else:
        treinamentos_filtrados = all_treinamentos
    return render_template('treinamentos.html', treinamentos=treinamentos_filtrados)

@app.route('/importar_excel', methods=['POST'])
@login.required
def importar_excel():
if 'file' not in request.files:
    flash('Nenhum arquivo enviado', 'danger')
    return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado','danger')
        retur redirect(url_for('index'))

if file and (file.filename.endswith('xlsx') or file.filename.endswith ('xls')):
    try:
        wb = openpyxl.load_workbook(file)
        sheet = wb.active

for row in sheet.iter_rows(min_row=2, values_only=True):
    if not row[0]:
        continue

    nome_colaborador = row[0]
                nome_setor = row[1] if len(row) > 1 and row[1] else "Geral"
                nome_treinamento = row[2] if len(row) > 2 and row[2] else "Treinamento Padrão"
                
                setor_obj = Setor.query.filter_by(nome=nome_setor).first()
                if not setor_obj:
                    setor_obj = Setor(nome=nome_setor)
                    db.session.add(setor_obj)
                    db.session.commit()
                
                colab_obj = Colaborador.query.filter_by(nome=nome_colaborador).first()
                if not colab_obj:
                    colab_obj = Colaborador(nome=nome_colaborador, setor_id=setor_obj.id)
                    db.session.add(colab_obj)
                    db.session.commit()
                
                treinamento_obj = Treinamento.query.filter_by(nome=nome_treinamento, colaborador_id=colab_obj.id).first()
                if not treinamento_obj:
                    treinamento_obj = Treinamento(
                        nome=nome_treinamento, 
                        colaborador_id=colab_obj.id
                    )
                    db.session.add(treinamento_obj)
                    db.session.commit()

            db.session.commit()
            flash('Planilha importada com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao processar planilha: {str(e)}', 'danger')
            
    return redirect(url_for('index'))


@app.route('/setor/<int:sid>')
@login_required
def view_setor(sid):
    try:
        setor = Setor.query.get_or_404(sid)
        colaboradores = Colaborador.query.filter_by(setor_id=sid).all()

        treinamentos_unicos = db.session.query(Treinamento.nome).distinct().all()
        nomes_treinamentos = [t[0] for t in treinamentos_unicos]
        
        treinamentos = Treinamento.query.all() 
        
        records = []
        for colab in colaboradores:
            for t in colab.treinamentos:
                status = calcular_status_treinamento(t.data_realizacao, t.data_aprovacao)
                records.append({
                    "colaborador": colab,
                    "treinamento": t,
                    "status": status
                })
                
        return render_template('setor.html', 
                               setor=setor, 
                               colaboradores=colaboradores, 
                               treinamentos=treinamentos,
                               nomes_treinamentos=nomes_treinamentos,
                               records=records)
                               
    except Exception as e:
        # Se o Jinja ou o Python quebrarem, essa linha vai cuspir a resposta na tela!
        erro_completo = traceback.format_exc()
        return f"<h1>RAIO-X DO ERRO 500:</h1><p>O seu HTML quebrou pelo seguinte motivo:</p><pre style='background:#f4f4f4; padding:20px; border-radius:8px; font-size:14px;'>{erro_completo}</pre>", 500

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')
    user = Usuario.query.filter_by(email=email).first()
    if user and check_password_hash(user.password, password):
        login_user(user)
        return jsonify({"success": True}), 200
    return jsonify({"error": "Credenciais invalidas"}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or request.form or {}
    nome = (data.get('nome') or data.get('name', '')).strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "E-mail ja cadastrado"}), 409
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
@app.route('/setor/cadastrar', methods=['POST'])
@login_required
def api_cadastrar_setor():
    sigla = request.form.get('sigla')
    nome = request.form.get('nome')
    if not sigla or not nome:
        return redirect(url_for('index'))
    try:
        novo_setor = Setor(sigla=sigla.upper(), nome=nome)
        db.session.add(novo_setor)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for('index'))

@app.route('/api/colaborador/cadastrar', methods=['POST'])
@app.route('/colaborador/cadastrar', methods=['POST'])
@login_required
def api_cadastrar_colaborador():
    nome = request.form.get('nome')
    cargo = request.form.get('cargo')
    setor_id = request.form.get('setor_id')
    if not nome or not cargo or not setor_id:
        return redirect(url_for('colaboradores_page'))
    try:
        novo_colab = Colaborador(nome=nome, cargo=cargo, setor_id=int(setor_id))
        db.session.add(novo_colab)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for('colaboradores_page'))

@app.route('/api/treinamento/cadastrar', methods=['POST'])
@login_required
def api_treinamento():
    nome = request.form.get('nome')
    if not nome:
        return redirect(request.referrer or url_for('treinamentos_page'))
        
    colab_id = request.form.get('colaborador_id')
    if colab_id and str(colab_id).isdigit():
        colab_id = int(colab_id)
    else:
        colab_id = None

    novo_treinamento = Treinamento(
        nome=nome,
        departamentos=request.form.get('departamentos', ''),
        sigla_doc=request.form.get('sigla_doc', ''),
        data_aprovacao=request.form.get('data_aprovacao', ''),
        data_realizacao=request.form.get('data_realizacao', ''),
        observacoes=request.form.get('observacoes', ''),
        colaborador_id=colab_id
    )
    db.session.add(novo_treinamento)
    db.session.commit()
    return redirect(request.referrer or url_for('treinamentos_page'))

@app.route('/api/treinamento/atualizar/<int:tid>', methods=['POST'])
@login_required
def api_atualizar_treinamento(tid):
    t = Treinamento.query.get_or_404(tid)
    data_real = request.form.get('data_realizacao')
    if data_real:
        t.data_realizacao = data_real
        db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/api/cargos', methods=['GET'])
@login_required
def api_cargos():
    setor_id = request.args.get('setor_id')
    if setor_id:
        cargos = db.session.query(Colaborador.cargo).filter_by(setor_id=int(setor_id)).distinct().all()
    else:
        cargos = db.session.query(Colaborador.cargo).distinct().all()
    return jsonify([c[0] for c in cargos if c[0]])

# CORREÇÃO 2: Lógica do Funil arrumada
@app.route('/api/funil', methods=['POST'])
@login_required
def api_funil():
    data = request.get_json() or {}
    setor_id = data.get('setor_id')
    cargo = data.get('cargo')
    
    query = Colaborador.query
    
    # Proteção caso o frontend envie "all" ou string vazia
    if setor_id and str(setor_id).isdigit():
        query = query.filter_by(setor_id=int(setor_id))
    if cargo and str(cargo).strip() != '' and str(cargo).lower() != 'all':
        query = query.filter_by(cargo=cargo)
        
    colaboradores = query.all()
    resultados = []
    
    for colab in colaboradores:
        # Mostra o colaborador no funil MESMO que ele não tenha treinamentos
        if not colab.treinamentos:
            resultados.append({
                "colaborador_nome": colab.nome,
                "cargo": colab.cargo,
                "setor_sigla": colab.setor_ref.sigla if colab.setor_ref else "",
                "treinamento_nome": "Nenhum treinamento vinculado",
                "data_realizacao": "-",
                "status": "Pendente"
            })
        else:
            for t in colab.treinamentos:
                status = calcular_status_treinamento(t.data_realizacao, t.data_aprovacao)
                resultados.append({
                    "colaborador_nome": colab.nome,
                    "cargo": colab.cargo,
                    "setor_sigla": colab.setor_ref.sigla if colab.setor_ref else "",
                    "treinamento_nome": t.nome,
                    "data_realizacao": t.data_realizacao or "Não realizada",
                    "status": "Valido" if status == "Valido" else "Pendente"
                })
                
    return jsonify({"success": True, "resultados": resultados})

@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def api_dashboard_stats():
    total_treinamentos = Treinamento.query.count()
    total_setores = Setor.query.count()
    treinamentos_all = Treinamento.query.all()
    treinamentos_pendentes = 0
    for t in treinamentos_all:
        status = calcular_status_treinamento(t.data_realizacao, t.data_aprovacao)
        if status == "Pendente":
            treinamentos_pendentes += 1
    return jsonify({
        "success": True,
        "total_treinamentos": total_treinamentos,
        "treinamentos_pendentes": treinamentos_pendentes,
        "total_setores": total_setores
    }), 200

@app.route('/api/busca', methods=['GET'])
@login_required
def api_busca():
    termo = request.args.get('q', '').lower()
    if len(termo) < 2:
        return jsonify([])
    colaboradores = Colaborador.query.filter(Colaborador.nome.ilike(f'%{termo}%')).limit(10).all()
    resultados = [
        {
            "nome": c.nome, 
            "setor_sigla": c.setor_ref.sigla if c.setor_ref else "Sem Setor", 
            "setor_id": c.setor_id
        } 
        for c in colaboradores
    ]
    return jsonify(resultados)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

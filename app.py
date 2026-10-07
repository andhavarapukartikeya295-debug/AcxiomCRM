from datetime import datetime, date, timedelta
from functools import wraps
import os

import torch
import torch.nn as nn
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, has_request_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'acxiomcrm-dev-secret-change-me'),
    SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(BASE_DIR, 'acxiomcrm.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    WTF_CSRF_ENABLED=False,  # API/demo friendly; enable CSRF in production forms.
)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

ROLES = ['Admin', 'Manager', 'SalesExecutive']
LEAD_STATUSES = ['New', 'Contacted', 'Qualified', 'Unqualified', 'Converted', 'Lost']
LEAD_SOURCES = ['Website', 'Referral', 'Email', 'Social Media', 'Cold Call', 'Event']
OPP_STAGES = ['Qualification', 'Proposal', 'Negotiation', 'Won', 'Lost']
FOLLOWUP_STATUSES = ['Planned', 'Completed', 'Missed', 'Cancelled']
FOLLOWUP_TYPES = ['Call', 'Meeting', 'Email', 'Task']


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='SalesExecutive')
    is_active = db.Column(db.Boolean, default=True)
    failed_login_count = db.Column(db.Integer, default=0)
    lockout_end = db.Column(db.DateTime, nullable=True)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(30), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    company_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(250), default='')
    city = db.Column(db.String(80), default='')
    state = db.Column(db.String(80), default='')
    status = db.Column(db.String(30), default='Active')
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_code = db.Column(db.String(30), unique=True, nullable=False)
    lead_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    company_name = db.Column(db.String(150), default='')
    source = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='New')
    priority = db.Column(db.String(20), default='Medium')
    expected_value = db.Column(db.Float, default=0)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Opportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    opportunity_name = db.Column(db.String(150), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    stage = db.Column(db.String(40), nullable=False, default='Qualification')
    probability = db.Column(db.Integer, nullable=False, default=20)
    expected_close_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Open')
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text, default='')

    @property
    def weighted_value(self):
        return self.amount * self.probability / 100


class FollowUp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=True)
    follow_up_date = db.Column(db.Date, nullable=False)
    follow_up_type = db.Column(db.String(30), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    remarks = db.Column(db.Text, default='')
    status = db.Column(db.String(30), nullable=False, default='Planned')
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(30), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default='')
    activity_date = db.Column(db.DateTime, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, nullable=True)
    lead_id = db.Column(db.Integer, nullable=True)
    assigned_to = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(30), default='Completed')


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(50), nullable=False)
    entity_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.String(50), nullable=True)
    old_value = db.Column(db.Text, default='')
    new_value = db.Column(db.Text, default='')
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(60), default='')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def audit(action, entity, record_id='', old='', new=''):
    entry = AuditLog(
        user_id=current_user.id if current_user and current_user.is_authenticated else None,
        action=action, entity_name=entity, record_id=str(record_id),
        old_value=str(old)[:2000], new_value=str(new)[:2000],
        ip_address=(request.remote_addr or '') if has_request_context() else ''
    )
    db.session.add(entry)
    db.session.commit()


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def scoped_query(model, owner_field):
    q = model.query
    if current_user.role == 'SalesExecutive':
        return q.filter(owner_field == current_user.id)
    return q


def valid_email(value):
    return bool(value and '@' in value and '.' in value.rsplit('@', 1)[-1])


def valid_phone(value):
    digits = ''.join(c for c in (value or '') if c.isdigit())
    return len(digits) == 10

@app.context_processor
def inject_globals():
    return {'today': date.today()}


# -------------------- Authentication --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Invalid email or password.', 'danger')
            return render_template('login.html')
        if user.lockout_end and user.lockout_end > datetime.utcnow():
            flash('Account is temporarily locked. Try again later.', 'danger')
            return render_template('login.html')
        if not user.is_active:
            flash('Account is inactive.', 'danger')
            return render_template('login.html')
        if user.check_password(password):
            user.failed_login_count = 0
            user.lockout_end = None
            db.session.commit()
            login_user(user)
            audit('LOGIN_SUCCESS', 'Authentication', user.id, new='Login successful')
            return redirect(url_for('dashboard'))
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.lockout_end = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()
        audit('LOGIN_FAILED', 'Authentication', user.id, new='Invalid credentials')
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not name or len(name) > 100:
            flash('Name is required.', 'danger')
        elif not valid_email(email):
            flash('Enter a valid email address.', 'danger')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
        else:
            user = User(name=name, email=email, role='SalesExecutive')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            audit('REGISTER', 'User', user.id, new='Self registration')
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    audit('LOGOUT', 'Authentication', current_user.id)
    logout_user()
    return redirect(url_for('login'))


# -------------------- Dashboard --------------------
@app.route('/')
def home():
    return redirect(url_for('dashboard')) if current_user.is_authenticated else redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    customers = scoped_query(Customer, Customer.created_by).count() if current_user.role == 'SalesExecutive' else Customer.query.count()
    leads = scoped_query(Lead, Lead.assigned_to).all()
    opps = scoped_query(Opportunity, Opportunity.assigned_to).all()
    followups = scoped_query(FollowUp, FollowUp.assigned_to).all()
    open_leads = sum(1 for x in leads if x.status not in ['Lost', 'Converted', 'Unqualified'])
    open_opps = sum(1 for x in opps if x.status == 'Open' and x.stage not in ['Won', 'Lost'])
    won = sum(1 for x in opps if x.stage == 'Won')
    lost = sum(1 for x in opps if x.stage == 'Lost')
    pipeline = sum(x.amount for x in opps if x.status == 'Open' and x.stage not in ['Lost', 'Won'])
    pending = sum(1 for x in followups if x.status == 'Planned')
    lead_chart = {s: sum(1 for x in leads if x.status == s) for s in LEAD_STATUSES}
    opp_chart = {s: sum(1 for x in opps if x.stage == s) for s in OPP_STAGES}
    recent_audit = AuditLog.query.order_by(AuditLog.created_date.desc()).limit(8).all()
    return render_template('dashboard.html', customers=customers, leads=len(leads), open_leads=open_leads,
                           opportunities=len(opps), open_opps=open_opps, won=won, lost=lost,
                           pipeline=pipeline, pending=pending, lead_chart=lead_chart, opp_chart=opp_chart,
                           recent_audit=recent_audit)


# -------------------- Customers --------------------
@app.route('/customers')
@login_required
def customers():
    q = request.args.get('q', '').strip()
    query = scoped_query(Customer, Customer.created_by)
    if q:
        query = query.filter(db.or_(Customer.customer_name.ilike(f'%{q}%'), Customer.email.ilike(f'%{q}%'), Customer.phone.ilike(f'%{q}%'), Customer.company_name.ilike(f'%{q}%')))
    return render_template('customers.html', customers=query.order_by(Customer.created_date.desc()).all(), q=q)


@app.route('/customers/new', methods=['GET', 'POST'])
@login_required
def customer_new():
    if request.method == 'POST':
        name, email, phone, company = [request.form.get(x, '').strip() for x in ['customer_name', 'email', 'phone', 'company_name']]
        if not name or len(name) > 120: flash('Customer name is required.', 'danger')
        elif not valid_email(email): flash('Enter a valid email address.', 'danger')
        elif not valid_phone(phone): flash('Enter a valid 10-digit phone number.', 'danger')
        elif Customer.query.filter((Customer.email == email) | (Customer.phone == phone)).first(): flash('Duplicate customer email or phone.', 'danger')
        else:
            c = Customer(customer_code=f'CUST-{datetime.utcnow().strftime("%y%m%d%H%M%S")}', customer_name=name, email=email, phone=phone,
                         company_name=company, address=request.form.get('address','').strip(), city=request.form.get('city','').strip(),
                         state=request.form.get('state','').strip(), status=request.form.get('status','Active'), created_by=current_user.id)
            db.session.add(c); db.session.commit(); audit('CREATE','Customer',c.id,new=name)
            flash('Customer created successfully.', 'success'); return redirect(url_for('customers'))
    return render_template('customer_form.html', customer=None)


@app.route('/customers/<int:id>/delete', methods=['POST'])
@role_required('Admin', 'Manager')
def customer_delete(id):
    c = db.session.get(Customer, id)
    if not c: abort(404)
    old = c.customer_name
    db.session.delete(c); db.session.commit(); audit('DELETE','Customer',id,old=old)
    flash('Customer deleted.', 'success'); return redirect(url_for('customers'))


# -------------------- Leads --------------------
@app.route('/leads')
@login_required
def leads():
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '')
    query = scoped_query(Lead, Lead.assigned_to)
    if q: query = query.filter(db.or_(Lead.lead_name.ilike(f'%{q}%'), Lead.company_name.ilike(f'%{q}%'), Lead.email.ilike(f'%{q}%')))
    if status: query = query.filter_by(status=status)
    return render_template('leads.html', leads=query.order_by(Lead.created_date.desc()).all(), q=q, status=status, statuses=LEAD_STATUSES)


@app.route('/leads/new', methods=['GET', 'POST'])
@login_required
def lead_new():
    if request.method == 'POST':
        name = request.form.get('lead_name','').strip(); email=request.form.get('email','').strip(); phone=request.form.get('phone','').strip()
        status=request.form.get('status','New'); source=request.form.get('source','Website'); expected=request.form.get('expected_value','0')
        if not name: flash('Lead name is required.', 'danger')
        elif not valid_email(email): flash('Enter a valid email address.', 'danger')
        elif not valid_phone(phone): flash('Enter a valid phone number.', 'danger')
        elif status not in LEAD_STATUSES: flash('Invalid lead status.', 'danger')
        else:
            try: expected=float(expected)
            except ValueError: expected=-1
            if expected < 0: flash('Expected value must be numeric and non-negative.', 'danger')
            else:
                assigned = current_user.id if current_user.role == 'SalesExecutive' else int(request.form.get('assigned_to') or current_user.id)
                lead=Lead(lead_code=f'LEAD-{datetime.utcnow().strftime("%y%m%d%H%M%S")}',lead_name=name,email=email,phone=phone,
                          company_name=request.form.get('company_name','').strip(),source=source,status=status,priority=request.form.get('priority','Medium'),
                          expected_value=expected,assigned_to=assigned)
                db.session.add(lead); db.session.commit(); audit('CREATE','Lead',lead.id,new=name)
                flash('Lead created.', 'success'); return redirect(url_for('leads'))
    users=User.query.filter_by(is_active=True).all()
    return render_template('lead_form.html', lead=None, users=users, statuses=LEAD_STATUSES, sources=LEAD_SOURCES)


# -------------------- Opportunities --------------------
@app.route('/opportunities')
@login_required
def opportunities():
    query = scoped_query(Opportunity, Opportunity.assigned_to)
    return render_template('opportunities.html', opportunities=query.order_by(Opportunity.created_date.desc()).all())


@app.route('/opportunities/new', methods=['GET','POST'])
@login_required
def opportunity_new():
    if request.method == 'POST':
        name=request.form.get('opportunity_name','').strip(); stage=request.form.get('stage','Qualification')
        try: amount=float(request.form.get('amount','0')); probability=int(request.form.get('probability','0'))
        except ValueError: amount=-1; probability=-1
        try: close_date=datetime.strptime(request.form.get('expected_close_date',''), '%Y-%m-%d').date()
        except ValueError: close_date=None
        if not name: flash('Opportunity name is required.','danger')
        elif amount <= 0: flash('Opportunity Amount must be greater than 0.','danger')
        elif not 0 <= probability <= 100: flash('Probability must be between 0 and 100.','danger')
        elif not close_date or close_date < date.today(): flash('Expected Close Date cannot be in the past.','danger')
        elif stage not in OPP_STAGES: flash('Invalid opportunity stage.','danger')
        else:
            assigned=current_user.id if current_user.role=='SalesExecutive' else int(request.form.get('assigned_to') or current_user.id)
            status='Won' if stage=='Won' else ('Lost' if stage=='Lost' else 'Open')
            o=Opportunity(opportunity_name=name,customer_id=request.form.get('customer_id') or None,lead_id=request.form.get('lead_id') or None,
                          amount=amount,stage=stage,probability=probability,expected_close_date=close_date,status=status,assigned_to=assigned,
                          notes=request.form.get('notes','').strip())
            db.session.add(o); db.session.commit(); audit('CREATE','Opportunity',o.id,new=name)
            flash('Opportunity created.','success'); return redirect(url_for('opportunities'))
    customers=Customer.query.order_by(Customer.customer_name).all(); leads=Lead.query.order_by(Lead.lead_name).all(); users=User.query.filter_by(is_active=True).all()
    return render_template('opportunity_form.html', opportunity=None, customers=customers, leads=leads, users=users, stages=OPP_STAGES)


# -------------------- Follow-ups --------------------
@app.route('/followups')
@login_required
def followups():
    query=scoped_query(FollowUp, FollowUp.assigned_to)
    return render_template('followups.html', followups=query.order_by(FollowUp.follow_up_date.asc()).all())


@app.route('/followups/new', methods=['GET','POST'])
@login_required
def followup_new():
    if request.method=='POST':
        try: d=datetime.strptime(request.form.get('follow_up_date',''), '%Y-%m-%d').date()
        except ValueError: d=None
        if not d or d < date.today(): flash('Follow-up date cannot be earlier than today.','danger')
        elif not request.form.get('subject','').strip(): flash('Subject is required.','danger')
        else:
            assigned=current_user.id if current_user.role=='SalesExecutive' else int(request.form.get('assigned_to') or current_user.id)
            f=FollowUp(customer_id=request.form.get('customer_id') or None,lead_id=request.form.get('lead_id') or None,follow_up_date=d,
                       follow_up_type=request.form.get('follow_up_type','Call'),subject=request.form.get('subject','').strip(),
                       remarks=request.form.get('remarks','').strip(),status='Planned',assigned_to=assigned)
            db.session.add(f); db.session.commit(); audit('CREATE','FollowUp',f.id,new=f.subject)
            flash('Follow-up scheduled.','success'); return redirect(url_for('followups'))
    customers=Customer.query.order_by(Customer.customer_name).all(); leads=Lead.query.order_by(Lead.lead_name).all(); users=User.query.filter_by(is_active=True).all()
    return render_template('followup_form.html', customers=customers, leads=leads, users=users, types=FOLLOWUP_TYPES)


@app.route('/followups/<int:id>/complete', methods=['POST'])
@login_required
def followup_complete(id):
    f=db.session.get(FollowUp,id)
    if not f: abort(404)
    if current_user.role=='SalesExecutive' and f.assigned_to != current_user.id: abort(403)
    f.status='Completed'; db.session.commit(); audit('UPDATE','FollowUp',id,new='Completed')
    flash('Follow-up completed.','success'); return redirect(url_for('followups'))


# -------------------- Users / Audit --------------------
@app.route('/users')
@role_required('Admin')
def users():
    return render_template('users.html', users=User.query.order_by(User.created_date.desc()).all())


@app.route('/users/<int:id>/toggle', methods=['POST'])
@role_required('Admin')
def user_toggle(id):
    u=db.session.get(User,id)
    if not u: abort(404)
    if u.id == current_user.id: flash('You cannot deactivate yourself.','warning')
    else:
        u.is_active=not u.is_active; db.session.commit(); audit('USER_STATUS','User',id,new=str(u.is_active)); flash('User status updated.','success')
    return redirect(url_for('users'))


@app.route('/audit')
@role_required('Admin','Manager')
def audit_page():
    return render_template('audit.html', logs=AuditLog.query.order_by(AuditLog.created_date.desc()).limit(200).all())


# -------------------- REST APIs --------------------
def customer_json(c):
    return {'id':c.id,'customerCode':c.customer_code,'customerName':c.customer_name,'email':c.email,'phone':c.phone,'companyName':c.company_name,'status':c.status}

def lead_json(x):
    return {'id':x.id,'leadCode':x.lead_code,'leadName':x.lead_name,'email':x.email,'phone':x.phone,'companyName':x.company_name,'source':x.source,'status':x.status,'expectedValue':x.expected_value,'assignedTo':x.assigned_to}

def opp_json(x):
    return {'id':x.id,'opportunityName':x.opportunity_name,'customerId':x.customer_id,'leadId':x.lead_id,'amount':x.amount,'stage':x.stage,'probability':x.probability,'expectedCloseDate':x.expected_close_date.isoformat(),'status':x.status,'weightedValue':x.weighted_value}


@app.route('/api/customers', methods=['GET','POST'])
@login_required
def api_customers():
    if request.method=='GET':
        q=scoped_query(Customer, Customer.created_by).all(); return jsonify([customer_json(x) for x in q])
    data=request.get_json(silent=True) or {}
    if not data.get('customerName') or not valid_email(data.get('email')) or not valid_phone(data.get('phone')):
        return jsonify({'error':'Valid customerName, email and 10-digit phone are required.'}),400
    if Customer.query.filter((Customer.email==data['email']) | (Customer.phone==data['phone'])).first(): return jsonify({'error':'Duplicate email or phone'}),409
    c=Customer(customer_code=f'CUST-{datetime.utcnow().strftime("%y%m%d%H%M%S")}',customer_name=data['customerName'],email=data['email'],phone=data['phone'],company_name=data.get('companyName',''),created_by=current_user.id)
    db.session.add(c); db.session.commit(); audit('CREATE','Customer',c.id,new=c.customer_name); return jsonify(customer_json(c)),201


@app.route('/api/customers/<int:id>', methods=['GET','PUT','DELETE'])
@login_required
def api_customer(id):
    c=db.session.get(Customer,id)
    if not c: return jsonify({'error':'Not found'}),404
    if current_user.role=='SalesExecutive' and c.created_by != current_user.id: return jsonify({'error':'Forbidden'}),403
    if request.method=='GET': return jsonify(customer_json(c))
    if request.method=='DELETE':
        if current_user.role not in ['Admin','Manager']: return jsonify({'error':'Forbidden'}),403
        db.session.delete(c); db.session.commit(); audit('DELETE','Customer',id); return jsonify({'message':'Deleted'})
    data=request.get_json(silent=True) or {}
    if data.get('email') and not valid_email(data['email']): return jsonify({'error':'Invalid email'}),400
    if data.get('phone') and not valid_phone(data['phone']): return jsonify({'error':'Invalid phone'}),400
    for key,attr in [('customerName','customer_name'),('email','email'),('phone','phone'),('companyName','company_name'),('status','status')]:
        if key in data: setattr(c,attr,data[key])
    db.session.commit(); audit('UPDATE','Customer',id); return jsonify(customer_json(c))


@app.route('/api/leads', methods=['GET','POST'])
@login_required
def api_leads():
    if request.method=='GET': return jsonify([lead_json(x) for x in scoped_query(Lead, Lead.assigned_to).all()])
    data=request.get_json(silent=True) or {}
    if not data.get('leadName') or not valid_email(data.get('email')) or not valid_phone(data.get('phone')): return jsonify({'error':'Invalid lead fields'}),400
    status=data.get('status','New')
    if status not in LEAD_STATUSES: return jsonify({'error':'Invalid status'}),400
    x=Lead(lead_code=f'LEAD-{datetime.utcnow().strftime("%y%m%d%H%M%S")}',lead_name=data['leadName'],email=data['email'],phone=data['phone'],company_name=data.get('companyName',''),source=data.get('source','Website'),status=status,expected_value=float(data.get('expectedValue',0)),assigned_to=current_user.id)
    db.session.add(x); db.session.commit(); audit('CREATE','Lead',x.id,new=x.lead_name); return jsonify(lead_json(x)),201


@app.route('/api/opportunities', methods=['GET','POST'])
@login_required
def api_opportunities():
    if request.method=='GET': return jsonify([opp_json(x) for x in scoped_query(Opportunity, Opportunity.assigned_to).all()])
    data=request.get_json(silent=True) or {}
    try: amount=float(data['amount']); probability=int(data['probability']); close=datetime.strptime(data['expectedCloseDate'],'%Y-%m-%d').date()
    except Exception: return jsonify({'error':'amount, probability and expectedCloseDate are required'}),400
    if amount<=0: return jsonify({'error':'Opportunity Amount must be greater than 0.'}),400
    if not 0<=probability<=100: return jsonify({'error':'Probability must be between 0 and 100.'}),400
    if close<date.today(): return jsonify({'error':'Expected Close Date cannot be in the past.'}),400
    x=Opportunity(opportunity_name=data.get('opportunityName','Untitled'),customer_id=data.get('customerId'),lead_id=data.get('leadId'),amount=amount,stage=data.get('stage','Qualification'),probability=probability,expected_close_date=close,assigned_to=current_user.id,status='Open')
    db.session.add(x); db.session.commit(); audit('CREATE','Opportunity',x.id,new=x.opportunity_name); return jsonify(opp_json(x)),201


@app.route('/api/reports/pipeline')
@login_required
def api_pipeline():
    opps=scoped_query(Opportunity, Opportunity.assigned_to).all()
    result={s:{'amount':sum(x.amount for x in opps if x.stage==s),'count':sum(1 for x in opps if x.stage==s)} for s in OPP_STAGES}
    return jsonify(result)


# -------------------- PyTorch Lead Scoring --------------------
class LeadScorer(nn.Module):
    def __init__(self):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(4,8),nn.ReLU(),nn.Linear(8,1),nn.Sigmoid())
    def forward(self,x): return self.net(x)

scorer=LeadScorer()
# Deterministic demo weights. In a production system train on historical CRM outcomes.
with torch.no_grad():
    scorer.net[0].weight.fill_(0.08); scorer.net[0].bias.fill_(-0.12)
    scorer.net[2].weight.fill_(0.18); scorer.net[2].bias.fill_(-0.15)
scorer.eval()

@app.route('/api/lead-score', methods=['POST'])
@login_required
def api_lead_score():
    data=request.get_json(silent=True) or {}
    try:
        features=torch.tensor([[float(data.get('expectedValue',0))/100000, float(data.get('priorityScore',0))/10, float(data.get('contacted',0)), float(data.get('engagement',0))/10]],dtype=torch.float32)
        score=float(scorer(features).item())
    except Exception: return jsonify({'error':'Invalid numeric input'}),400
    return jsonify({'leadScore':round(score*100,2),'model':'PyTorch LeadScorer','note':'Demo scoring model; retrain with historical outcomes for production.'})


@app.errorhandler(403)
def forbidden(e): return render_template('error.html', code=403, message='You are not authorized to access this resource.'),403

@app.errorhandler(404)
def not_found(e): return render_template('error.html', code=404, message='The requested resource was not found.'),404


def seed_data():
    if User.query.count(): return
    accounts=[('System Admin','admin@acxiom.local','Admin','Admin@123'),('Sales Manager','manager@acxiom.local','Manager','Manager@123'),('Sales Executive','sales@acxiom.local','SalesExecutive','Sales@123')]
    users=[]
    for name,email,role,pw in accounts:
        u=User(name=name,email=email,role=role);u.set_password(pw);db.session.add(u);users.append(u)
    db.session.commit()
    c1=Customer(customer_code='CUST-001',customer_name='Acme Industries',email='contact@acme.example',phone='9876543210',company_name='Acme Industries',city='Visakhapatnam',state='Andhra Pradesh',created_by=users[1].id)
    c2=Customer(customer_code='CUST-002',customer_name='Nova Retail',email='hello@nova.example',phone='9123456780',company_name='Nova Retail',city='Hyderabad',state='Telangana',created_by=users[2].id)
    db.session.add_all([c1,c2]);db.session.commit()
    leads=[Lead(lead_code='LEAD-001',lead_name='Ravi Kumar',email='ravi@example.com',phone='9000011111',company_name='TechNova',source='Website',status='Qualified',priority='High',expected_value=50000,assigned_to=users[2].id),Lead(lead_code='LEAD-002',lead_name='Priya Shah',email='priya@example.com',phone='9000022222',company_name='MarketHub',source='Referral',status='Contacted',priority='Medium',expected_value=30000,assigned_to=users[1].id)]
    db.session.add_all(leads);db.session.commit()
    opps=[Opportunity(opportunity_name='Acme CRM License',customer_id=c1.id,amount=120000,stage='Proposal',probability=65,expected_close_date=date.today()+timedelta(days=30),assigned_to=users[1].id,status='Open'),Opportunity(opportunity_name='Nova Analytics',customer_id=c2.id,amount=85000,stage='Negotiation',probability=75,expected_close_date=date.today()+timedelta(days=20),assigned_to=users[2].id,status='Open')]
    db.session.add_all(opps);db.session.commit()
    f=FollowUp(customer_id=c2.id,follow_up_date=date.today()+timedelta(days=2),follow_up_type='Call',subject='Product demo follow-up',remarks='Confirm demo attendees',status='Planned',assigned_to=users[2].id)
    db.session.add(f);db.session.commit()
    audit('SEED','System',new='Demo data initialized')


with app.app_context():
    db.create_all()
    seed_data()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)

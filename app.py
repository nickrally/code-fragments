import os
import datetime
import re
from flask import Flask, request, render_template, flash, session, redirect, url_for
from wtforms import Form, StringField, TextAreaField, Field, PasswordField, validators, widgets
from flask_wtf import FlaskForm
from passlib.hash import sha256_crypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_ , and_
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.secret_key = b'ZsbK\x9fdD|`\x07\x05\x01\x95\x93u\xae'

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['CODE'] = os.environ['CODE']
db = SQLAlchemy(app)

today = datetime.date.today().strftime("%Y-%m-%d")

class User(db.Model):
    __tablename__ = 'users'

    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.Text)
    email    = db.Column(db.Text)
    username = db.Column(db.Text)
    password = db.Column(db.Text)
    register_date = db.Column(db.Date)

    def __init__(self, name=name, email=email, username=username, password=password):
        self.name      = name
        self.username  = username
        self.password  = password
        self.email = email
        self.register_date = datetime.date.today().strftime("%Y-%m-%d")



class RegisterForm(Form):

    code  = StringField('code',       [validators.DataRequired(), validators.Regexp('^%s\d+$' % app.config['CODE'])])
    name  = StringField('name',       [validators.Length(min=1,max=10)])
    email = StringField('email',      [validators.Length(min=3, max=24), validators.Email()])
    username = StringField('username',[validators.Length(min=4,max=10)])
    password = PasswordField('password',
                             [validators.DataRequired(),
                              validators.EqualTo('confirm', message="Passwords don't match")])
    confirm = PasswordField('confirm password')


@app.route('/register', methods=['GET','POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name     = form.name.data
        email    = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))
        user = User(name, email, username, password)
        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            return render_template('error.html', error="Username already exists")
        return redirect(url_for('index'))
    return render_template('register.html', form = form)

def is_logged_in(f):
    def wrapper(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, please login', 'danger')
            return redirect(url_for('login'))

    return wrapper

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            hash = user.password
            if sha256_crypt.verify(password_candidate, hash):
                session['logged_in'] = True
                session['username']  = username
                flash('You are logged in', 'success')
                return redirect('/dashboard')

            else:
                error = 'Invalid login'
                return render_template('login.html', error=error)
        else:
            error = 'Username not found'
            return render_template('login.html', error=error)

    return render_template('login.html')

class Fragment(db.Model):
    __tablename__ = 'fragment'
    __searchable__ = ['text','tags', 'date']

    id     = db.Column(db.Integer, primary_key=True)
    title  = db.Column(db.Text,    unique=False, nullable=False)
    text   = db.Column(db.Text,    unique=False, nullable=False)
    tags   = db.Column(db.ARRAY(db.String), unique=False, nullable=True)
    date   = db.Column(db.Date, unique=True, nullable=False)

    def __init__(self, title=title, text=text, tags=tags, date=date):
        self.title = title
        self.text  = text
        self.tags  = tags.split(",")
        self.date = date

def stripSpaceAndLowerTags(tags):
    tags = tags.lower()
    tags = re.sub(r'\s*,\s*', ',', tags).strip()
    tags = re.sub('\s+', ' ', tags)
    return tags

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/fragments')
def viewFirstPage():
    return redirect(url_for('view', page=1))

@app.route('/pages/<int:page>',methods=['GET'])
def view(page=1):
    per_page = 5
    fragments = Fragment.query.order_by(Fragment.id.desc()).paginate(page,per_page, error_out=True)
    return render_template('view.html',fragments=fragments, page=page)

@app.route('/<int:id>')
def show(id):
    fragment = Fragment.query.get(id)
    return render_template('show.html', fragment=fragment, id=id)

@app.route('/fragment/<string:id>/')
def fragment(id):
    return render_template('show.html', id=id)

@app.route('/pages/search')
def search():
    fragments = None

    def searchText():
        txt = "%{}%".format(request.args.get('textQuery'))
        return Fragment.text.ilike(txt)

    def searchTags():
        tags_arr = (request.args.get('tagsQuery')).split(",")
        tags_str = stripSpaceAndLowerTags(','.join(tags_arr))
        tags_arr = tags_str.split(',')
        clauses = [Fragment.tags.any(tag) for tag in tags_arr]
        if request.args.get('operator'):
            return and_(*clauses)
        else:
            return or_(*clauses)


    def searchByDate():
        date = request.args.get('dateQuery').replace(" ", "")
        option = request.args.get('date-radio')
        if option == 'on':
            return Fragment.date == date
        elif option == 'before':
            return Fragment.date <= date
        elif option == 'after':
            return Fragment.date >= date
        elif option == 'between':
            dates = date.split(',')
            return and_(Fragment.date >= dates[0], Fragment.date <= dates[1])

    text_selected = request.args.get('searchText') and request.args.get('textQuery')
    tags_selected = request.args.get('searchTags') and request.args.get('tagsQuery')
    date_selected = request.args.get('searchByDate') and request.args.get('dateQuery')

    if text_selected:
        fragments = Fragment.query.filter(searchText()).all()

    if tags_selected:
        fragments = Fragment.query.filter(searchTags()).all()

    if date_selected:
        if request.args.get('date-radio'):
            fragments = Fragment.query.filter(searchByDate()).all()

    if text_selected and date_selected:
        if request.args.get('date-radio'):
            fragments = Fragment.query.filter(and_(searchText(), searchByDate())).all()

    if text_selected and tags_selected:
        fragments = Fragment.query.filter(and_(searchText(), searchTags())).all()

    if tags_selected and date_selected:
        if request.args.get('date-radio'):
            fragments = Fragment.query.filter(and_(searchTags(), searchByDate())).all()

    if text_selected and tags_selected and date_selected:
        if request.args.get('date-radio'):
            fragments = Fragment.query.filter(and_(searchText(), searchTags(), searchByDate())).all()

    return render_template('results.html', fragments=fragments)


@app.route('/dashboard', endpoint='dashboard')
@is_logged_in
def dashboard():
    fragments = Fragment.query.order_by(Fragment.id.desc())
    return render_template('dashboard.html', fragments=fragments)


@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        fragment = Fragment(request.form['title'],
                            request.form['text'],
                            stripSpaceAndLowerTags(request.form['tags']))

        db.session.add(fragment)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('add.html', today=today)

class TagListField(Field):
    widget = widgets.TextInput()

    def _value(self):
        if self.data:
            return u', '.join(self.data)
        else:
            return u''

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [x.strip() for x in valuelist[0].split(',')]
        else:
            self.data = []

class FragmentForm(FlaskForm):
    title = StringField('title')
    text  = TextAreaField('text')
    tags  = TagListField('tags')

@app.route('/edit/<string:id>', methods=['GET','POST'], endpoint='edit')
@is_logged_in
def edit(id):
    fragment = Fragment.query.get(id)
    form = FragmentForm(obj=fragment)
    if request.method == 'POST':
        form.populate_obj(fragment)
        tags = stripSpaceAndLowerTags(','.join(fragment.tags))
        fragment.tags = tags.split(',')
        db.session.add(fragment)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('edit.html', fragment=fragment, id=id, form=form)

@app.route('/delete/<int:id>', methods=['GET','POST'])
@is_logged_in
def delete(id):
    fragment = Fragment.query.get(id)
    if request.method == 'POST':
        title = fragment.title
        db.session.delete(fragment)
        db.session.commit()
        return redirect(url_for('confirm', title=title))
    return render_template('delete.html', fragment=fragment, id=id)

@app.route('/confirm', endpoint='confirm')
@is_logged_in
def confirm():
    return render_template('confirm.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('you are now logged out', 'success')
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(debug=True)

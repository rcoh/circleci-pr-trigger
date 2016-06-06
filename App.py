from flask_github import GitHub
from flask import Flask, request, g, session, redirect, url_for, render_template
from flask import render_template_string

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from circle import CircleCi

DATABASE_URI = 'sqlite:////tmp/github-flask.db'
SECRET_KEY = 'development key'
DEBUG = True


# setup flask
app = Flask(__name__)
app.config.from_object(__name__)
# Set these values
app.config['GITHUB_CLIENT_ID'] = '905ed692609686609213'
app.config['GITHUB_CLIENT_SECRET'] = '5ecff42c7336252b1c3e702ba19012bcd0576e7b'

# setup github-flask
github = GitHub(app)

# setup sqlalchemy
engine = create_engine(app.config['DATABASE_URI'])
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    Base.metadata.create_all(bind=engine)

# User:
# - Github Token
# - Circle CI Token
# - Repo name

# ManagedRepo:
# - user-id
# - build number
# - branch
# - build status
class Build(Base):
	__tablename__ = 'build'

	id = Column(Integer, primary_key=True)
	user_id = Column(Integer)
	build_num = Column(Integer)
	branch = Column(String(200))
	status = Column(String(200))

	def __init__(self, user_id, build_num, branch, status):
		self.user_id = user_id
		self.build_num = build_num
		self.branch = branch
		self.status = status

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(200))
    github_access_token = Column(String(200))
    circle_ci_token = Column(String(200))
    repo = Column(String(200))
    owner = Column(String(200))

    def __init__(self, github_access_token):
        self.github_access_token = github_access_token


@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])


@app.after_request
def after_request(response):
    db_session.remove()
    return response


@app.route('/')
def index():
    if g.user:
        t = 'Hello! <a href="{{ url_for("user") }}">Get user</a> ' \
            '<a href="{{ url_for("logout") }}">Logout</a>'
    else:
        t = 'Hello! <a href="{{ url_for("login") }}">Login</a>'

    return render_template_string(t)


@github.access_token_getter
def token_getter():
    user = g.user
    if user is not None:
        return user.github_access_token


@app.route('/configure')
def configure():
	if (g.user is None):
		return redirect(url_for('index'))

	return render_template('configure.html', circle_ci_token=g.user.circle_ci_token, owner = g.user.owner, repo = g.user.repo)

@app.route('/do-configure', methods=['POST'])
def do_configure():
	import pdb; pdb.set_trace()
	if (g.user is None):
		return redirect(url_for('index'))
	data = request.form
	user = g.user
	user.circle_ci_token = data['circle_ci_token']
	(owner, repo) = (data['owner'], data['repo'])
	user.repo = repo
	user.owner = owner
	db_session.add(user)
	db_session.commit()
	create_webhook(owner, repo)
	return redirect(url_for('configure'))

@app.route('/github-callback')
@github.authorized_handler
def authorized(access_token):
    next_url = url_for('configure')
    if access_token is None:
        return redirect(next_url)

    user = User.query.filter_by(github_access_token=access_token).first()
    if user is None:
        user = User(access_token)
        db_session.add(user)
    user.github_access_token = access_token
    db_session.commit()

    session['user_id'] = user.id
    return redirect(next_url)


@app.route('/login')
def login():
	print "id: ", bool(session.get('user_id')), session.get('user_id') == "", session.get('user_id') == None, session.get('user_id'), "!!"

	if not session.get('user_id'):
		return github.authorize(scope = 'write:repo_hook')
	else:
		return 'Already logged in: ', session.get('user_id')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))


@app.route('/user')
def user():
    return str(github.get('user'))

@app.route('/hook-event/<owner>/<repo>', methods=['GET', 'POST'])
def hook_fired(owner, repo):
	hook_data = request.json
	
	#import pprint
	#pp = pprint.PrettyPrinter(indent=4)
	#pp.pprint(hook_data)

	branch_rev = extract_info_from_hook(hook_data)
	if branch_rev is None:
		return "OK"
	else:
		(branch, revision) = branch_rev
	
	user = User.query.filter_by(owner = owner, repo = repo).first()
	circle = CircleCi(user.circle_ci_token, owner, repo)
	print "cancelling ongoing builds"
	cancel_ongoing_builds(branch)

	print "Starting the build"
	result = circle.start_build(branch, revision)
	build_num = result.json()['build_num']
	build = Build(user.id, build_num, branch, "building")
	db_session.add(build)
	db_session.commit()

	return owner, repo

def extract_info_from_hook(hook_data):
	if 'pull_request' in hook_data:
		if not hook_data["action"] in ["opened", "reopened"]:
			print "Not handling PR with action %s" % hook_data["action"]
			return None

		branch = hook_data['pull_request']['head']['ref']
		revision = hook_data['pull_request']['head']['sha']
		return (branch, revision)
	elif 'ref' in hook_data and 'pusher' in hook_data:
		refs, head, branch = hook_data['ref'].split('/')
		revision = hook_data['after']
		return (branch, revision)
	else: 
		return None


def cancel_ongoing_builds(branch):
	builds = Build.query.filter_by(branch = branch, status="building").all()
	for build in builds:
		user = User.query.filter_by(id = build.user_id).first()
		circle = CircleCi(user.circle_ci_token, user.owner, user.repo)
		result = circle.cancel_build(build.build_num)
		print "trying to cancel ", build.build_num
		canceled, status = result.json()["canceled"], result.json()["status"]
		if canceled or status == "failed" or status == "succeeded":
			print "Canceled build #", build.build_num
			build.status = "canceled"
			db_session.add(build)
			db_session.commit()
		else:
			print "failure to cancel"
			print result.json()

def create_webhook(owner, repo):
	hook_url = 'repos/%s/%s/hooks' % (owner, repo)
	github.post(
		hook_url,
		{
		  "name": "web",
		  "active": True,
		  "events": [
		  	"push",
		    "pull_request"
		  ],
		  "config": {
		    "url": "http://cibuilder.ngrok.io/hook-event/%s/%s" % (owner, repo),
		    "content_type": "json"
		  }
		}
	)

	


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
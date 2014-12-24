from flask import Flask
from app.admin import admin
from flask.ext.mail import Mail
from ConfigParser import SafeConfigParser
import os


app = Flask(__name__,
        static_folder="static", # match with your static folder
        static_url_path="/static" # you can change this to anything other than static, its your URL
      )

# mail config start

mail = Mail(app)

app.config.update(
                    MAIL_SERVER='smtp.gmail.com',
                    MAIL_PORT=465,
                    MAIL_USE_SSL=True,
                    MAIL_USERNAME = 'email@gmail.com',
                    MAIL_PASSWORD = 'yourcurrentpasswordis'
                  )
# mail config end

from app import views


# global domain name config
# calling from jinja => {{ config["domain_name"] }}
# ambil informasi ini dari settings.ini
parser = SafeConfigParser()
settings_path = os.path.join(os.getcwd(), "app", "settings.ini")
parser.read(settings_path)

url = parser.get("site_config", "url")
name = parser.get("site_config", "name")

if not url or not name:  # jika data lom ada (baru deploy/localhost)
    name = "example"
    url = "http://127.0.0.1:5000"

app.config["SITE_NAME"] = name
app.config["SITE_URL"] = url
app.config["VERSION"] = "1.0"
app.config["APP_TITLE"] = name

# important! needed for login things >> joss
app.secret_key = "vertigo"

# adding admin blueprint
from app.admin.views import admin
app.register_blueprint(admin)

# logging tools
# author: https://gist.github.com/mitsuhiko/5659670
# monitor uwsgi access / error :: output di nohup.out

import sys
from logging import Formatter, StreamHandler
handler = StreamHandler(sys.stderr)
handler.setFormatter(Formatter(
    '%(asctime)s %(levelname)s: %(message)s '
    '[in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(handler)

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db?check_same_thread=false"
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": False}
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True

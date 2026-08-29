"""WSGI entrypoint for production servers (PythonAnywhere, gunicorn, waitress).

PythonAnywhere: in the web app's WSGI configuration file, add the project
directory to sys.path and then:

    from wsgi import application
"""
from app import app as application

if __name__ == '__main__':
    application.run()

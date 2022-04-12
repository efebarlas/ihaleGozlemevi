from flask import Flask
app = Flask(__name__)
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import ihaleGozlemevi.lib.ekap_client as ekap_client

@app.route('/')
def homepage():
    return "Hello world!"

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
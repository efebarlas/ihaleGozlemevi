from .lib import ekap_client


from flask import Flask
app = Flask(__name__)



@app.route('/')
def homepage():
    e = ekap_client.EKAPClient()
    return "Hello world!"

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
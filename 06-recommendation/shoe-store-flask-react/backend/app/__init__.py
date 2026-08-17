from flask import Flask
from flask_cors import CORS
from app.routes.products import products_bp

def create_app():
    app = Flask(__name__)

    # Enable CORS for all routes and origins (during development)
    CORS(app)

    # Or to restrict to specific origin:
    # CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

    app.register_blueprint(products_bp)
    return app

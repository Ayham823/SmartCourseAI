"""Flask REST boundary for the existing three-tier SmartCourse AI application."""
import logging
import sys
from pathlib import Path
from uuid import UUID, uuid4

# Support both python -m server.app and the original cd server; python app.py.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from server.config import ROOT_DIR, get_settings
from server.database import db
from server.errors import AppError
from server.rag.retriever import retrieve_chunks
from server.rag.service import answer_question
from server.services.chat_service import process_message


def create_app(test_config=None):
    application = Flask(__name__, static_folder=str(ROOT_DIR / "client"), static_url_path="/static")
    application.config.update(get_settings())
    if test_config:
        application.config.update(test_config)
    application.json.ensure_ascii = False

    def json_input(field):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise AppError("Request body must be a valid JSON object.", "invalid_json", 400)
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AppError(f"{field.capitalize()} must be a nonempty string.", "invalid_input", 400)
        value = value.strip()
        if len(value) > application.config["MAX_MESSAGE_LENGTH"]:
            raise AppError("Message is too long.", "invalid_input", 400)
        return data, value

    def validate_session(value):
        if not isinstance(value, str) or not db.is_valid_uuid(value):
            raise AppError("Invalid session_id.", "invalid_session", 400)
        session_id = str(UUID(value))
        if not db.session_exists(session_id):
            raise AppError("Session not found. Start a new chat.", "session_not_found", 404)
        return session_id

    @application.get("/")
    def home():
        return application.send_static_file("index.html")

    @application.get("/health")
    def health():
        connected = db.check_database_connection()
        return jsonify(status="ok" if connected else "error", server="running",
                       database="connected" if connected else "disconnected"), 200 if connected else 503

    @application.post("/chat")
    def chat():
        data, message = json_input("message")
        supplied_session = data.get("session_id")
        if supplied_session is not None:
            session_id = validate_session(supplied_session)
        else:
            session_id = str(uuid4())
            db.create_session(session_id)
        history = db.get_messages(session_id, limit=application.config["MEMORY_MESSAGES"])
        try:
            response = process_message(message, session_id, history)
            db.save_exchange(session_id, message, response)
        except AppError as error:
            return jsonify(error=error.message, code=error.code, session_id=session_id), error.status
        return jsonify(response), 200

    @application.post("/sessions")
    def new_session():
        # Reserve the UUID before the slow model call, so browser timeouts can
        # recover the same conversation through /history instead of losing it.
        session_id = str(uuid4())
        db.create_session(session_id)
        return jsonify(session_id=session_id), 201

    @application.get("/history")
    def history():
        session_id = validate_session(request.args.get("session_id"))
        return jsonify(session_id=session_id, messages=db.get_messages(session_id)), 200

    @application.post("/rag/search")
    def rag_search():
        _, query = json_input("query")
        return jsonify(query=query, results=retrieve_chunks(query, limit=5)), 200

    @application.post("/rag/answer")
    def rag_answer():
        _, query = json_input("query")
        return jsonify(answer_question(query)), 200

    @application.errorhandler(AppError)
    def application_error(error):
        return jsonify(error=error.message, code=error.code), error.status

    @application.errorhandler(psycopg.Error)
    def database_error(error):
        application.logger.warning("Database operation failed (%s).", type(error).__name__)
        return jsonify(error="Database is unavailable. Please try again.", code="database_unavailable"), 503

    @application.errorhandler(HTTPException)
    def http_error(error):
        message = "Request is too large." if error.code == 413 else error.description
        return jsonify(error=message, code="http_error"), error.code

    @application.errorhandler(Exception)
    def unexpected_error(error):
        # Provider errors may contain credentials or prompts: log type only.
        application.logger.error("Request failed (%s).", type(error).__name__)
        return jsonify(error="Unable to process the request at this time.", code="internal_error"), 500

    return application


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])


import os, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from .solver import solve_quiz_sequence

load_dotenv()
SECRET = os.getenv('QUIZ_SECRET')
PORT = int(os.getenv('PORT', '8000'))
WORKER_TIMEOUT = int(os.getenv('WORKER_TIMEOUT_SECONDS', '170'))

app = Flask(__name__)

@app.route('/api/quiz', methods=['POST'])
def api_quiz():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'invalid json'}), 400

    if payload.get('secret') != SECRET:
        return jsonify({'error': 'invalid secret'}), 403

    email = payload.get('email')
    url = payload.get('url')
    if not email or not url:
        return jsonify({'error': 'email and url required'}), 400

    start_time = time.time()
    try:
        results = solve_quiz_sequence(url, email, payload.get('secret'), timeout_seconds=WORKER_TIMEOUT)
    except Exception as e:
        return jsonify({'error': 'solver error', 'details': str(e)}), 500

    elapsed = time.time() - start_time
    return jsonify({'ok': True, 'elapsed_seconds': elapsed, 'results': results}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)

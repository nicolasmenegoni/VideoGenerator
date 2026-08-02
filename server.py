from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

# URLs das APIs externas
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
QWEN_API_URL = "https://chat.qwen.ai/"

@app.route('/')
def index():
    return send_from_directory('.', 'app.html')

@app.route('/api/groq', methods=['POST'])
def groq_proxy():
    try:
        data = request.json
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {data.get("api_key", "")}'
        }
        payload = {
            'model': data.get('model', 'llama-3.3-70b-versatile'),
            'messages': data.get('messages', [])
        }
        
        response = requests.post(GROQ_API_URL, json=payload, headers=headers)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/qwen', methods=['POST'])
def qwen_proxy():
    try:
        # Implementação específica para Qwen
        data = request.json
        # Adapte conforme necessário para a API do Qwen
        return jsonify({'status': 'proxy configurado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Servidor rodando em http://localhost:5001")
    app.run(debug=False, port=5001, host='0.0.0.0')

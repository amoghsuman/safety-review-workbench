import requests

resp = requests.post(
    'http://localhost:11434/api/generate',
    json={
        'model': 'llama3.1:8b',
        'prompt': 'Reply with only the word: WORKING',
        'stream': False
    },
    timeout=120
)
print('Status code:', resp.status_code)
print('Response:', resp.json().get('response', '')[:200])
print('OLLAMA OK' if resp.status_code == 200 else 'OLLAMA FAILED')

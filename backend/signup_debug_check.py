import json
import urllib.request

url = 'http://127.0.0.1:8000/signup'
payload = {
    'name': 'Org Test',
    'email': 'student@university.org',
    'password': 'pass1234',
    'role': 'student'
}
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)

try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode('utf-8')
        print('STATUS', resp.status)
        print(body)
except Exception as exc:
    import traceback
    traceback.print_exc()

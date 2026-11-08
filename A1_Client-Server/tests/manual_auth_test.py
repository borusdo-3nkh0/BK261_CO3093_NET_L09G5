
import json

from server.socket_server import SocketServer


server = SocketServer()

request = {
    "action": "REGISTER",
    "username": "alice",
    "password": "demo123"
}

data = json.dumps(request).encode("utf-8")

response = server.process_auth_data(data)

print("Response:", response.decode("utf-8").strip())

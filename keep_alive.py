from http.server import BaseHTTPRequestHandler, HTTPServer

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"I'm alive")

def start_keep_alive():
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, KeepAliveHandler)
    print('Keep alive server running on port 8080...')
    httpd.serve_forever()

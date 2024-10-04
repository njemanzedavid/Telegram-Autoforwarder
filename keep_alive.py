from http.server import BaseHTTPRequestHandler, HTTPServer

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)  # Send HTTP 200 OK response
        self.send_header('Content-type', 'text/plain')  # Set content type
        self.end_headers()
        self.wfile.write(b"I'm alive")  # Write the response body

def run(server_class=HTTPServer, handler_class=KeepAliveHandler, port=8080):
    server_address = ('', port)  # Empty string means all interfaces
    httpd = server_class(server_address, handler_class)
    print(f'Server running on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run()

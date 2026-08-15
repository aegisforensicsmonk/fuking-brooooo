from app import handler, app

if __name__ == "__main__":
    from http.server import HTTPServer
    server = HTTPServer(("0.0.0.0", 3000), handler)
    print("Serving on port 3000...")
    server.serve_forever()

from flask import Flask, send_from_directory, abort, request
import ssl
from settings import WORKING_DIR
app = Flask(__name__)
allowed = []

@app.route('/download_fucking_file')
def download_file():
    filename = request.args.get('filename', default=None, type=str)
    if filename in allowed:
        allowed.remove(filename)
        try:
            return send_from_directory(directory=f"{WORKING_DIR}/files", path=filename, as_attachment=True)
        except FileNotFoundError:
            abort(404)
    else:
        abort(404)

@app.route('/favicon.ico')
def favicon():
    try:
        return send_from_directory(directory=f"{WORKING_DIR}/files", path="web2.ico")
    except FileNotFoundError:
        abort(404)

@app.route('/sec_check')
def sec_check():
    if request.remote_addr in ['127.0.0.1', 'localhost']:
        arg = request.args.get('arg', default=None, type=str)
        if arg:
            allowed.append(arg)
            return "ok"
    else:
        abort(404)

@app.route('/wf_file')
def wf_file():
    filename = request.args.get('filename', default=None, type=str)
    if filename in allowed:
        allowed.remove(filename)
        try:
            return send_from_directory(directory=rf'{WORKING_DIR}/temp', path=filename, as_attachment=True)
        except FileNotFoundError:
            abort(404)
    else:
        abort(404)

@app.route('/upload_file', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        if file:
            fileformat = file.filename.split('.')[-1]
            file.save(f'{WORKING_DIR}/files/tempfile.{fileformat}')
            allowed.append(f'tempfile.{fileformat}')
            return "ok"
    return "error"

@app.route('/ping')
def ping():
    return "pong"

if __name__ == '__main__':
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('C:/Users/Admin/Desktop/nginx-mcsm/files/keys/domain.crt', 'C:/Users/Admin/Desktop/nginx-mcsm/files/keys/domain.key')
    app.run(host="0.0.0.0", port=4856, ssl_context=context)

from flask import Flask, send_from_directory, abort, request
from base_settings import PORT
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
import threading

app = Flask(__name__)
allowed = []
allowed_lock = threading.Lock()  # 线程安全锁

# 请求频率限制
request_times = defaultdict(list)
RATE_LIMIT = 10  # 每分钟最大请求数
RATE_WINDOW = 60  # 时间窗口（秒）

WORKING_DIR = os.getcwd()

def is_safe_filename(filename):
    """检查文件名是否安全，防止目录遍历攻击"""
    if not filename:
        return False
    # 防止目录遍历
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    # 只允许字母、数字、下划线、点、连字符
    if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
        return False
    return True

def check_rate_limit(ip):
    """检查请求频率限制"""
    now = datetime.now()
    window_start = now - timedelta(seconds=RATE_WINDOW)
    
    # 清理旧记录
    request_times[ip] = [t for t in request_times[ip] if t > window_start]
    
    # 检查是否超过限制
    if len(request_times[ip]) >= RATE_LIMIT:
        return False
    
    request_times[ip].append(now)
    return True

def is_local_request():
    """检查是否为本地请求"""
    remote_addr = request.remote_addr
    # 检查IPv4和IPv6的本地地址
    local_ips = ['127.0.0.1', 'localhost', '::1']
    return remote_addr in local_ips or remote_addr.startswith('192.168.') or remote_addr.startswith('10.')

@app.route('/download_fucking_file')
def download_file():
    """下载文件（仅限通过安全检查的文件）"""
    # 频率限制检查
    if not check_rate_limit(request.remote_addr):
        abort(429)  # Too Many Requests
    
    filename = request.args.get('filename', default=None, type=str)
    
    # 安全检查
    if not filename or not is_safe_filename(filename):
        abort(400)  # Bad Request
    
    with allowed_lock:
        if filename in allowed:
            allowed.remove(filename)
            try:
                file_path = os.path.join(WORKING_DIR, "files", filename)
                # 额外路径安全检查
                if not os.path.normpath(file_path).startswith(os.path.normpath(os.path.join(WORKING_DIR, "files"))):
                    abort(403)  # Forbidden
                
                return send_from_directory(directory=os.path.join(WORKING_DIR, "files"),
                                         path=filename, as_attachment=True)
            except FileNotFoundError:
                abort(404)
        else:
            abort(404)

@app.route('/favicon.ico')
def favicon():
    """提供网站图标"""
    try:
        return send_from_directory(directory=os.path.join(WORKING_DIR, "files"),
                                 path="web.ico")
    except FileNotFoundError:
        abort(404)

@app.route('/sec_check')
def sec_check():
    """安全检查端点（仅限本地请求）"""
    if not is_local_request():
        abort(403)  # Forbidden
    
    # 频率限制检查
    if not check_rate_limit(request.remote_addr):
        abort(429)
    
    arg = request.args.get('arg', default=None, type=str)
    if arg and is_safe_filename(arg):
        with allowed_lock:
            allowed.append(arg)
        return "ok"
    else:
        abort(400)

@app.route('/wf_file')
def wf_file():
    """提供临时文件下载"""
    # 频率限制检查
    if not check_rate_limit(request.remote_addr):
        abort(429)
    
    filename = request.args.get('filename', default=None, type=str)
    
    # 安全检查
    if not filename or not is_safe_filename(filename):
        abort(400)
    
    with allowed_lock:
        if filename in allowed:
            allowed.remove(filename)
            try:
                file_path = os.path.join(WORKING_DIR, "temp", filename)
                # 额外路径安全检查
                if not os.path.normpath(file_path).startswith(os.path.normpath(os.path.join(WORKING_DIR, "temp"))):
                    abort(403)
                
                return send_from_directory(directory=os.path.join(WORKING_DIR, "temp"),
                                         path=filename, as_attachment=True)
            except FileNotFoundError:
                abort(404)
        else:
            abort(404)

@app.route('/ping')
def ping():
    """健康检查端点"""
    return "pong"

@app.errorhandler(404)
def not_found(error):
    return "Not Found", 404

@app.errorhandler(403)
def forbidden(error):
    return "Forbidden", 403

@app.errorhandler(429)
def too_many_requests(error):
    return "Too Many Requests", 429

@app.errorhandler(400)
def bad_request(error):
    return "Bad Request", 400

if __name__ == '__main__':
    print(f"文件服务启动在 http://0.0.0.0:{PORT}")
    print("安全特性已启用：")
    print("  - 文件名安全检查")
    print("  - 请求频率限制（10次/分钟）")
    print("  - 本地请求验证")
    print("  - 路径遍历攻击防护")
    app.run(host="0.0.0.0", port=PORT, debug=False)

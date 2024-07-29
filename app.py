from flask import Flask, request, render_template, make_response, send_file, send_from_directory, abort
from flask_cors import CORS
from socketctl import create_video_socket
import logging
from logging.handlers import TimedRotatingFileHandler
# import eventlet
import os
import io
import shutil
import tempfile
import zipfile
import yaml

def create_flask_app():
    current_path = os.path.abspath(os.path.dirname(__file__))
    config_path = os.path.join(current_path, 'configs', 'config.yaml')
    log_directory = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'public', 'logs')
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    log_filename = os.path.join(log_directory, "app.log")

    app = Flask(__name__, static_folder="frontend/static")
    CORS(app)

    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'default': {
                'format': '[%(asctime)s](%(levelname)s) %(message)s',
            }
        },
        'handlers': {
            'file': {
                'class': 'logging.handlers.TimedRotatingFileHandler',
                'formatter': 'default',
                'filename': log_filename,
                'when': 'midnight',  # 每天午夜輪轉
                'interval': 1,
                'backupCount': 7,  # 保留最近7天的log檔案
                'level': 'WARNING',
                'encoding': 'utf-8',
            },
            'wsgi': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://flask.logging.wsgi_errors_stream',
                'formatter': 'default'
            }
        },
        'root': {
            'level': 'INFO',
            'handlers': ['file', 'wsgi']
        },
        'loggers': {
            'flask.app': {
                'level': 'INFO',
                'handlers': ['file', 'wsgi'],
                'propagate': False  # 不將訊息傳遞到父logger
            }
        }
    })

    logging.info('[PROCESS] Starting Flask App. Loading config path: {}'.format(config_path))
    with open(config_path) as f:
        cdata = yaml.safe_load(f.read())
        app.config.update(cdata)

    app.config['SECRET_KEY'] = 'secretkey'
    app.config['Allow-Origin'] = '*'

    @app.route("/")
    def index():
        return send_from_directory(os.path.join(current_path), 'frontend/index.html')

    @app.route("/<path:filename>")
    def main(filename):
        # return render_template('index.html')
        return send_from_directory(os.path.join(current_path, 'frontend'), filename)

    @app.route("/public/addr/<path:filename>")
    def public_path_addr(filename):
        return send_from_directory(os.path.join(current_path, 'public', 'addr'), filename)
    
    @app.route("/public/addr2/<path:filename>")
    def public_path_addr2(filename):
        return send_from_directory(os.path.join(current_path, 'public', 'addr2'), filename)
    
    @app.route('/export-logs', methods=['GET'])
    def export_logs():
        logs_folder = os.path.join(current_path, 'public', 'logs')  # 設置你的 logs 資料夾路徑
        zip_filename = 'logs.zip'

        logging.info('export request received')

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Copy logs to the temporary directory
                shutil.copytree(logs_folder, os.path.join(temp_dir, 'logs'))

                # 創建一個內存中的 ZIP 文件
                memory_file = io.BytesIO()
                with zipfile.ZipFile(memory_file, 'w') as zf:
                    for foldername, subfolders, filenames in os.walk(temp_dir):
                        for filename in filenames:
                            filepath = os.path.join(foldername, filename)
                            zf.write(filepath, os.path.relpath(filepath, temp_dir))
                memory_file.seek(0)

            # 傳送 ZIP 文件給前端
            return send_file(memory_file, download_name=zip_filename, as_attachment=True)
        except Exception as error: 
            logging.error(str(error))
            abort(404)

    
    logging.info('[PROCESS] Created Flask App.')

    return app



def create_merged_app(flask_app):
    sio = create_video_socket(flask_app)
    logging.info('[PROCESS] Created SocketIO Service and than Merge Apps.')
    return sio



def create_gunicorn_service():
    f_app = create_flask_app()
    create_merged_app(f_app)
    return f_app



if __name__ == '__main__':
    logging.info('[Dev] Start By main process.')
    try:
        
        app = create_flask_app()
        s_app = create_merged_app(app)
        s_app.run(app, port=5000, debug=app.config['DEBUG'])
        # wsgi_app = socketio.WSGIApp(sio, app)
        # eventlet.wsgi.server(eventlet.listen(('', 5000)), wsgi_app)

    except KeyboardInterrupt:
        
        logging.error('KeyboardInterrupt.')

    except Exception as error:
        
        logging.error(str(error))

    finally:

        s_app.exit_background_ocrtask()
        # sio.stop()
else:
    
    logging.info('[PROD] Start By wsgi service.')
    app = create_gunicorn_service()

    
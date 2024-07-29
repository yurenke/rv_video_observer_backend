from flask_socketio import SocketIO, send, emit
from classes.ocr import OCRObserver
from classes.data import VideoDataset
from classes.timeformula import minutes_difference
from datetime import datetime, timezone

import bg_celery.tasks as celery_task
import threading
import os
import json
# import multiprocessing
# import concurrent
import tempfile
import tracemalloc
import linecache
import gc





def create_video_socket(app):
    """ create a socketIO mreged flask app 
    """
    _is_debug_mode = app.config['DEBUG']
    remote_video_url = app.config['VIDEO']['URL']
    if _is_debug_mode:
        tracemalloc.start()
    
    video_data = VideoDataset(url_data=remote_video_url, debug_mode=_is_debug_mode, logger=app.logger)
    sio = VideoSocketIO(app, video_data)
    
    
    @sio.event
    def connect():
        app.logger.info('has a user connected.')

    @sio.event
    def disconnect():
        app.logger.info('a user disconnected.')

    @sio.on('message')
    def handle_message(data):
        app.logger.info('received message: {}'.format(data))
        if data == 'getinfo':
            emit('video_info', video_data.get_construct_info())
            emit('history_update', video_data.grab_history_warning())
        if data == 'reload':
            sio.reload_tasks()
            sio.reload_video_data()
            emit('video_info', video_data.get_construct_info())
            emit('history_update', video_data.grab_history_warning())
            

    sio.start_background_ocrtask()

    return sio





class VideoSocketIO(SocketIO):
    """ 
    """
    flask_app = None
    ocr_observer = None
    data_ctl = None
    evt_exit_background = threading.Event()
    evt_video_handling = threading.Event()

    tmp_hourly_refresh = 0
    celery_frame_tasks = []
    dir_public = ''



    def __init__(self, app, data_ctl: VideoDataset = None):
        super().__init__(app, async_mode='threading', cors_allowed_origins="*", allow_unsafe_werkzeug=True)
        self.dir_public = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'public')
        self.flask_app = app
        self.data_ctl = data_ctl
        self.ocr_observer = OCRObserver(app)
        app.logger.info(' [VideoSocketIO] Video Socket is Ready. Debug mode = {}'.format(app.config['DEBUG']))



    def exit_background_ocrtask(self):
        self.evt_exit_background.set()
        self.evt_video_handling.set()
        return self
    


    def start_background_ocrtask(self):
        self.start_background_task(self.background_multiprocess)
        return self
    


    def reload_video_data(self):
        # self.flask_app.logger.info('[PROCESS] Start Load Remote Video Data: {}'.format(self.flask_app.config['VIDEO']['URL']))
        self.data_ctl.fetch_data_from_url()
        return self
    


    def reload_tasks(self):
        self.evt_video_handling.set()
        for cft in self.celery_frame_tasks:
            cft.revoke()
        del self.celery_frame_tasks
        dir_public_addr_tmp = os.path.join(self.dir_public, 'addr', 'tmp')
        dir_public_addr2_tmp = os.path.join(self.dir_public, 'addr2', 'tmp')
        for jpg_file in os.listdir(dir_public_addr_tmp):
            path_jpg = os.path.join(dir_public_addr_tmp, jpg_file)
            os.remove(path_jpg)
        for jpg_file in os.listdir(dir_public_addr2_tmp):
            path_jpg = os.path.join(dir_public_addr2_tmp, jpg_file)
            os.remove(path_jpg)
        celery_task.app.control.purge()
        gc.collect()
        self.celery_frame_tasks = []



    def check_video_status_hourly(self):
        dt_now = datetime.utcnow()
        if dt_now.hour != self.tmp_hourly_refresh:
            self.tmp_hourly_refresh = dt_now.hour
            self.data_ctl.refresh_video_data()



    def background_multiprocess(self):
        TIMEOUT_CYCLE_CAPTURING = self.flask_app.config['HANDLER'].get('VIDEO_PROCESS_TIMEOUT', 60)

        while not self.evt_exit_background.is_set():
            pid_urls = self.data_ctl.get_urls(is_activate=True)
            self.celery_frame_tasks = [celery_task.capture_video.delay(_['id'], _['src'], _['url'], self.dir_public) for _ in pid_urls]
            self.evt_video_handling = threading.Event()
            self.while_working_by_celery_tasks(timeout=TIMEOUT_CYCLE_CAPTURING)
            self.reload_tasks()
            self.check_video_status_hourly()
            # 
            
            if self.flask_app.config['DEBUG']:
                snapshot = tracemalloc.take_snapshot()
                self.debug_display_memo_top(snapshot)

            del pid_urls

        self.flask_app.logger.info('Background Task Stopped.')
        self.debug_logging()



    def while_working_by_celery_tasks(self, timeout:float=60):
        dt_start = datetime.utcnow()
        self.next_round_done_video_src_id_map = {}
        video_data_update_to_fronted = []
        
        while not self.evt_exit_background.is_set():
            tasks = self.celery_frame_tasks
            length_tasks = len(tasks)

            results = [task.get() for task in tasks if task.ready()]
            _len_results = len(results)
            if _len_results > 0:
                new_results = [_ for _ in results if self.next_round_done_video_src_id_map.get(str(_['src']) + '_' + _['pid'], None) is None and _['opened']]
                updated_src_ids = self.handle_video_tasks(new_results) # it will take a long time to execute
                if len(updated_src_ids) == 0:
                    self.evt_exit_background.wait(2)
                else:
                    for src_pid in updated_src_ids:
                        self.next_round_done_video_src_id_map[src_pid] = True
                    video_data_update_to_fronted = self.data_ctl.get_ws_video_data_by_ids(updated_src_ids)
                    self.emit('video_data_update', video_data_update_to_fronted)
            else:
                self.evt_exit_background.wait(5)
            
            is_timeout = (datetime.utcnow() - dt_start).total_seconds() > timeout

            if _len_results >= length_tasks or is_timeout:
                not_open_src_ids = [str(res['src']) + '_' + res['pid'] for res in results if not res['opened']]
                length_not_open = len(not_open_src_ids)

                length_finish = len(self.next_round_done_video_src_id_map)
                self.flask_app.logger.info('Done A Cycle Capturing. Finished Length: {} | Close Length: {} | Task Length: {}'.format(length_finish, length_not_open, length_tasks))

                if length_not_open > 0:
                    self.data_ctl.set_error_with_not_open_videos(not_open_src_ids)
                    video_data_update_to_fronted = self.data_ctl.get_ws_video_data_by_ids(not_open_src_ids)
                    self.emit('video_data_update', video_data_update_to_fronted)
                break
        
        del video_data_update_to_fronted
        del self.next_round_done_video_src_id_map



    def handle_video_tasks(self, task_results:list=[]) -> list[str]:
        # MAX_HANDLE_FRAME = 50
        dt_now = datetime.utcnow()
        num_done_frame = 0
        updated_src_ids = []
        
        try:
            for task_res in task_results:
                if self.evt_video_handling.is_set():
                    break
                pid = task_res['pid']
                src = task_res['src']
                task_minute = task_res['minute']
                task_frames = task_res['frames']
                if minutes_difference(dt_now.minute, int(task_minute)) < 2:

                    parsed_minutes = self.handle_frames(src, pid, task_frames)
                    num_done_frame += len(parsed_minutes)
                    updated_src_ids.append(str(src) + '_' + pid)
                
        except Exception as err:
            self.flask_app.logger.info(str(err))
            # self.reload_tasks()
            # self.exit_background_ocrtask()
        
        spend_seconds = (datetime.utcnow() - dt_now).total_seconds()
        self.flask_app.logger.info('[handle_video_tasks] spend secods: {},  total handle files: {}  updated src ids: {}'.format(spend_seconds, num_done_frame, len(updated_src_ids)))
        return updated_src_ids



    def handle_frames(self, src:int, pid:str, frames:list):
        result_minuts = []
        ocr_obr = self.ocr_observer
        _tmp_xyxy = []
        _depth_yolo = 0

        for path_frame in frames:
            if len(_tmp_xyxy) == 4:
                # minute_parsed, digits = ocr_obr.get_parsed_digits_by_frame_and_position(frame, _tmp_xyxy)
                minute_parsed, digits = ocr_obr.get_parsed_digits_by_path_and_position(path_frame, _tmp_xyxy)
                _depth_yolo = 2
            else:
                # image_frame, minute_parsed, digits, yolo_find_images, xyxy_datetime = ocr_obr.get_parsed_frame(frame)
                image_frame, minute_parsed, digits, yolo_find_images, xyxy_datetime = ocr_obr.get_parsed_frame_by_path(path_frame)
                _depth_yolo = len(yolo_find_images)
                _tmp_xyxy = xyxy_datetime

                self.data_ctl.save_image(src=src, id=pid, img=image_frame)
                
                # self.data_ctl.debug_logging(id=pid, full_frame=image_frame, minute=minute_parsed, yolo_images=yolo_find_images, digits=digits, depth_yolo=_depth_yolo)
            result_minuts.append(minute_parsed)

            is_ontime = self.data_ctl.update_data_by_ocr_result(
                src=src,
                id=pid,
                minute=minute_parsed,
                digits=digits,
                depth_yolo=_depth_yolo,
            )

            if is_ontime:
                break

        pointer = self.data_ctl.get_video_construct_pointer_by_id(pid, src)
        if pointer:
            if pointer['warning']['overtime']:
                self.flask_app.logger.warning(f"[{pointer['id']}][來源{pointer['src']}] 超過一分鐘的延遲時間 推測分鐘數為({pointer['minute_flexible']})")
            if pointer['warning']['datetime']:
                self.flask_app.logger.warning(f"[{pointer['id']}][來源{pointer['src']}] 找不到平板位置")
            if pointer['warning']['format']:
                self.flask_app.logger.warning(f"[{pointer['id']}][來源{pointer['src']}] 連續檢測到錯誤的時間格式")

        return result_minuts



    def debug_logging(self):
        logs = self.data_ctl.get_log_for_developer()
        accuracies = []
        for _k in logs:
            acc = logs[_k].get('accuracy', None)
            if acc is not None:
                print('{} : accuracy: {}'.format(_k, logs[_k]['accuracy']))
                accuracies.append(acc)
            else:
                print('{} : {}'.format(_k, logs[_k]))
        
        if len(accuracies) > 0:
            print('All Mean Accuracy: {}%'.format(round(sum(accuracies) *100 / len(accuracies))) )
        
        if self.flask_app.config['DEBUG']:
            with open(os.path.abspath(os.path.dirname(__file__)) + '/debug/debug_ocr.json', 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=4)



    def debug_display_memo_top(self, snapshot, key_type='lineno', limit=10):
        print(" [ TOP Memory Stats ] ")
        snapshot = snapshot.filter_traces((
            tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
            tracemalloc.Filter(False, "<unknown>"),
        ))
        top_stats = snapshot.statistics(key_type)

        print(" -- Show Top {} lines".format(limit))
        for index, stat in enumerate(top_stats[:limit], 1):
            frame = stat.traceback[0]
            print("#{}: {}:{}:  size: {:.1f} KiB".format(index, frame.filename, frame.lineno, stat.size / 1024))
            line = linecache.getline(frame.filename, frame.lineno).strip()
            if line:
                print('    ', line)

        other = top_stats[limit:]
        if other:
            size = sum(stat.size for stat in other)
            print("other length: {}  |  other size: {:.1f} KiB".format(len(other), size / 1024))
        total = sum(stat.size for stat in top_stats)
        print("Total allocated size: {:.1f} KiB".format(total / 1024))

        





    
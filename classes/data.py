from PIL import Image
from datetime import datetime
from classes.timeformula import check_minute_normally
from classes.internet import get_remote_video_data
from enum import Enum
import os
import cv2
import json
import re
from typing import Dict, List




class VideoFlagENum(Enum):
    CLOSE = 0
    OPEN = 1
    PEDDING = 2
    ERROR = 4




class VideoProcessStatusEnum(Enum):
    PREPARING = 0
    NO_PANEL = 1
    NO_DATETIME = 2
    WRONG_FORMAT = 3
    MINUTE_FOUND = 4




class VideoDataset():
    """ store all datainfo of videos. 

    init parameter must be like 
        url_data: a remote url from video data api,
        debug_mode: whether is debug mode,
        logger: specify logger for showing logs,
    """
    STR_DEBUG_LOG_HISTORY = '_debug_history'
    construct_videos = []
    construct_videos2 = []
    list_history_warning = []
    map_video_index = {}
    map_video_index2 = {}
    current_path = os.path.abspath(os.path.dirname(__file__))
    url_remote_video_data = ''
    debug_mode = False
    show_logs = False
    logger = None

    log_dev = {}



    def __init__(self, url_data:str, debug_mode:bool = False, logger = None) -> None:
        self.debug_mode = debug_mode
        if debug_mode:
            self.log_dev[self.STR_DEBUG_LOG_HISTORY] = {}
        if logger is not None:
            self.show_logs = True
            self.logger = logger
        self.url_remote_video_data = url_data
        self.fetch_data_from_url(url_data)



    def fetch_data_from_url(self, url:str = ''):
        _video_url = self.url_remote_video_data if url == '' else url
        self.logging('[PROCESS] Start Fetching Video Data From Url: {}'.format(_video_url))
        remote_videos_data = get_remote_video_data(_video_url, self.debug_mode)
        self.load_data_from_url_videos(remote_videos_data)
        self.logging('[PROCESS] Loaded Video Data Length: {}'.format(len(remote_videos_data)))



    def load_data_from_url_videos(self, url_videos:list):
        videos = []
        videos_2 = []
        dict_map = {}
        dict_map_2 = {}
        for _vdata in url_videos:
            _vid = _vdata.get('vid', None)
            _addr = _vdata.get('addr', None)
            _addr2 = _vdata.get('addr2', None)
            _flag = _vdata.get('flag', VideoFlagENum.CLOSE)
            # if _vid is None or _addr is None:
            #     print('[VideoDataset] parsing failed. data: ', _vdata)
            #     continue

            if _vid and _addr:
                dict_map[_vid] = len(videos)
                videos.append({
                    'id': _vid,
                    'img': '/public/addr/{}.jpg'.format(_vid),
                    'src': 1,
                    'status': VideoFlagENum(_flag),
                    'flag': VideoFlagENum(_flag),
                    # 'ontime': True,
                    'minute_last': -1,
                    'minute_flexible': -1,
                    'list_past_minutes': [],
                    'last_timestamp': '',
                    'url': _addr,
                    'wrongs': {
                        'datetime': 0,
                        'format': 0,
                        'overtime': 0,
                    },
                    'warning': {
                        'datetime': False,
                        'format': False,
                        'overtime': False,
                    },
                    'parsed_digits': []
                })
            
            if _vid and _addr2:
                _parsed_addr = re.search(r'url=(.*)&(.*)streamname=(.*)', _addr2)
                _addr2 = _parsed_addr.group(1) + '/' + _parsed_addr.group(3)
                _flag = VideoFlagENum.OPEN
                dict_map_2[_vid] = len(videos_2)
                videos_2.append({
                    'id': _vid,
                    'img': '/public/addr2/{}.jpg'.format(_vid),
                    'src': 2,
                    'status': VideoFlagENum(_flag),
                    'flag': VideoFlagENum(_flag),
                    # 'ontime': True,
                    'minute_last': -1,
                    'minute_flexible': -1,
                    'list_past_minutes': [],
                    'last_timestamp': '',
                    'url': _addr2,
                    'wrongs': {
                        'datetime': 0,
                        'format': 0,
                        'overtime': 0,
                    },
                    'warning': {
                        'datetime': False,
                        'format': False,
                        'overtime': False,
                    },
                    'parsed_digits': []
                })

        self.construct_videos = videos
        self.construct_videos2 = videos_2
        self.map_video_index = dict_map
        self.map_video_index2 = dict_map_2
        self.list_history_warning = []



    def refresh_video_data(self):
        self.logging('[PROCESS] Start Refresh Video Data. remote url: {}'.format(self.url_remote_video_data))
        url_videos = get_remote_video_data(self.url_remote_video_data, self.debug_mode)
        videos = self.construct_videos
        videos2 = self.construct_videos2
        map_vidx = self.map_video_index
        map_vidx2 = self.map_video_index2
        self.logging('[PROCESS] Loaded New Video Data Length: {}.'.format(len(url_videos)))
        for _vdata in url_videos:
            _vid = _vdata.get('vid', None)
            _addr = _vdata.get('addr', None)
            _addr2 = _vdata.get('addr2', None)
            _flag = _vdata.get('flag', VideoFlagENum.CLOSE)
            if _vid and _addr:
                idx = map_vidx.get(_vid, -1)
                if idx >= 0 and idx < len(videos):
                    videos[idx]['url'] = _addr
                    videos[idx]['status'] = VideoFlagENum(_flag)
                    videos[idx]['flag'] = VideoFlagENum(_flag)

            if _vid and _addr2:
                _parsed_addr = re.search(r'url=(.*)&(.*)streamname=(.*)', _addr2)
                _addr2 = _parsed_addr.group(1) + '/' + _parsed_addr.group(3)
                _flag = VideoFlagENum.OPEN
                idx = map_vidx2.get(_vid, -1)
                if idx >= 0 and idx < len(videos2):
                    videos2[idx]['url'] = _addr2
                    videos2[idx]['status'] = VideoFlagENum(_flag)
                    videos2[idx]['flag'] = VideoFlagENum(_flag)
        self.logging('[PROCESS] Refresh Video Data Done.')




    def get_construct_info(self) -> Dict[str, List[Dict]]:
        return {'addrVideos': [self.get_dict_by_keys(_, ['id', 'img', 'src', 'flag', 'wrongs', 'warning']) for _ in self.construct_videos],
                'addr2Videos': [self.get_dict_by_keys(_, ['id', 'img', 'src', 'flag', 'wrongs', 'warning']) for _ in self.construct_videos2]}


    def refresh_construct_flags(self):
        for v in self.construct_videos:
            v['flag'] = v['status']
        
        for v in self.construct_videos2:
            v['flag'] = v['status']

    def get_urls(self, is_activate:bool = True) -> list[dict]:
        """ get dict[id, url, flag] all videos, if parameter is_activated is True then filter only opened video
        """
        # videos = self.construct_videos if src == 1 else self.construct_videos2

        if is_activate:
            return [self.get_dict_by_keys(_, ['id', 'url', 'src', 'flag']) for _ in self.construct_videos if _['flag'] == VideoFlagENum.OPEN] + \
                    [self.get_dict_by_keys(_, ['id', 'url', 'src', 'flag']) for _ in self.construct_videos2]
        else:
            return [self.get_dict_by_keys(_, ['id', 'url', 'src', 'flag']) for _ in self.construct_videos] + \
                    [self.get_dict_by_keys(_, ['id', 'url', 'src', 'flag']) for _ in self.construct_videos2]


    def get_dict_by_keys(self, obj:dict, keys:list = []) -> dict:
        result = {}
        for k in keys:
            result[k] = obj.get(k, None)
            if k == 'flag' and isinstance(result[k], VideoFlagENum):
                result[k] = int(result[k].value)
        
        return result    


    def get_video_construct_pointer_by_id(self, id:str, src = 1):
        videos = self.construct_videos if src == 1 else self.construct_videos2
        map_vidx = self.map_video_index if src == 1 else self.map_video_index2
        idx = map_vidx.get(id, -1)
        if idx == -1:
            return {}
        
        return videos[idx]


    def get_ws_video_data_by_ids(self, src_ids:list):
        vdata = []
        cnt1, cnt2 = 0, 0
        for src_id in src_ids:
            _splitted = src_id.split('_')
            src, id = int(_splitted[0]), _splitted[1]
            if src == 1:
                cnt1 += 1
            else:
                cnt2 += 1
            vdata.append(self.get_dict_by_keys(
                self.get_video_construct_pointer_by_id(id, src),
                ['id', 'src', 'flag', 'minute_flexible', 'minute_last', 'last_timestamp','wrongs', 'warning', 'parsed_digits']
            ))  
        
        return {'addrUpdateCount': cnt1, 'addr2UpdateCount': cnt2, 'vdata': vdata}


    # def tape_video_fail_by_id(self, id:str, src = 1):
    #     pointer = self.get_video_construct_pointer_by_id(id, src)
    #     pointer['flag'] = VideoFlagENum.ERROR
    #     return pointer  


    def get_process_status(self, minute:int, depth_yolo:int) -> VideoProcessStatusEnum:
        dt_now = datetime.utcnow()
        if depth_yolo == 0:
            return VideoProcessStatusEnum.NO_PANEL
        elif depth_yolo == 1:
            return VideoProcessStatusEnum.NO_DATETIME
        elif check_minute_normally(minute, dt_now.minute):
            return VideoProcessStatusEnum.MINUTE_FOUND
        else:
            return VideoProcessStatusEnum.WRONG_FORMAT
        


    def update_data_by_ocr_result(self, id:str, minute:int, digits:list[str], depth_yolo:int, src = 1) -> bool:
        """ update processed data into data center
        
        """
        pointer = self.get_video_construct_pointer_by_id(id, src)

        if pointer:
            dt_now = datetime.utcnow()
            ontime = False

            pointer['minute_last'] = minute
            pointer['parsed_digits'] = digits
            pointer['last_timestamp'] = dt_now.strftime("%Y-%m-%d %H:%M:%S")

            process_status = self.get_process_status(minute, depth_yolo)

            if process_status is VideoProcessStatusEnum.NO_PANEL or process_status is VideoProcessStatusEnum.NO_DATETIME:
                pointer['wrongs']['datetime'] += 1

            elif process_status is VideoProcessStatusEnum.WRONG_FORMAT:
                # if pointer['warning']['format']:
                #     pointer['wrongs']['format'] = 0
                pointer['wrongs']['format'] += 1
                # pointer['minute_flexible'] = minute # trans by some algo
            
            elif process_status is VideoProcessStatusEnum.MINUTE_FOUND:
                pointer['wrongs']['format'] = 0
                pointer['wrongs']['datetime'] = 0

                pointer['minute_flexible'] = minute
                ontime = self.check_minute_ontime(pointer['minute_flexible'], dt_now.minute)
                
                if ontime:
                    pointer['wrongs']['overtime'] = 0
                else:
                    pointer['wrongs']['overtime'] += 1


            pointer['warning']['overtime'] = pointer['wrongs']['overtime'] > 2
            pointer['warning']['datetime'] = pointer['wrongs']['datetime'] > 4
            pointer['warning']['format'] = pointer['wrongs']['format'] > 6

            self.refresh_history_by_video_construct(pointer)

            self.stamp_analyzing(id=id, src=src, process_status=process_status, ontime=ontime)
            
            return ontime

        return True


    def logging(self, info:str):
        if self.show_logs:
            self.logger.info(info)



    def debug_logging(self, src: int, id:str, full_frame:any, minute:int, yolo_images:list, digits:list, depth_yolo:int):
        if self.debug_mode:
            self.debug_logging_while_update_video_data(
                src=src,
                id=id,
                process_status=self.get_process_status(minute, depth_yolo), 
                image=full_frame,
                yolo_images=yolo_images,
                digits=digits
            )



    def refresh_history_by_video_construct(self, vc_data:dict) -> bool:
        """ return whether have warning put into history record.
        """
        has_new = False
        if len(self.list_history_warning) > 0:
            last_history_record = self.list_history_warning[-1]
            last_time = last_history_record['time']
            if last_time == vc_data['last_timestamp']:
                return has_new
        
        for _wkey in vc_data['warning']:
            if vc_data['warning'][_wkey]:
                self.list_history_warning.append({
                    'id': vc_data['id'],
                    'src': vc_data['src'],
                    'key': _wkey,
                    'flexible': vc_data['minute_flexible'],
                    'digits': vc_data['parsed_digits'],
                    'time': vc_data['last_timestamp']
                })
                has_new = True
                break
            
        if len(self.list_history_warning) > 50:
            self.list_history_warning = self.list_history_warning[-50:]

        return has_new



    def grab_history_warning(self, get_newest:bool=False) -> list[dict]:
        if get_newest:
            now = datetime.now()
            warning_results = [_ for _ in self.list_history_warning if _['time'] >= now]
            return warning_results

        return self.list_history_warning



    def save_image(self, src: int, id:str, img:any, specify_path:str = ''):
        path = ''
        # _next_img = Image.fromarray(img.astype('uint8'), mode='RGB')
        # if resize != 1 and resize > 0:
        #     _shape = [_ // resize for _ in img.shape[:2]]
        #     _next_img.thumbnail(_shape)
        
        if specify_path:
            if '{}' in specify_path:
                path = os.path.join(self.current_path, '..', specify_path.format(src, id, datetime.now().strftime('%H%M')))
            else:
                path = os.path.join(self.current_path, '..', specify_path)
        else:
            src_path = 'addr' if src == 1 else 'addr2'
            path = os.path.join(self.current_path, '..', 'public', src_path, '{}.jpg'.format(id))

        # _next_img.save(path, 'JPEG')
        cv2.imwrite(path, img)
        
        return path
    


    def check_minute_ontime(self, minute: int, now: int) -> bool:
        if minute == now:
            return True
        if now == 0:
            return minute == 59
        return abs(now - minute) < 2
    


    def find_most_common(self, lst):
        _dict = {}
        _closely = 6
        for _ in lst:
            if _ in _dict:
                _dict[_] += _closely
            else:
                _dict[_] = _closely
            _closely -= 1
        return max(_dict, key=_dict.get)
    


    def get_log_for_developer(self):

        return self.log_dev
    
    
    def stamp_analyzing(self, src:int, id:str, process_status:VideoProcessStatusEnum, ontime:bool):
        _analyzing_key = 'analyzing_{}_{}'.format(src, id)
        if self.log_dev.get(_analyzing_key, None) is None:
            self.log_dev[_analyzing_key] = {'total': 0, 'right': 0, 'no_panel': 0, 'no_datetime': 0, 'wrong_format': 0, 'wrong_time': 0, 'accuracy': 0.0}
        _ana_pointer = self.log_dev[_analyzing_key]
        _ana_pointer['total'] += 1

        if process_status is VideoProcessStatusEnum.MINUTE_FOUND:
            if ontime:
                _ana_pointer['right'] += 1
            else:
                _ana_pointer['wrong_time'] += 1

        elif process_status is VideoProcessStatusEnum.NO_PANEL:
            _ana_pointer['no_panel'] += 1

        elif process_status is VideoProcessStatusEnum.NO_DATETIME:
            _ana_pointer['no_datetime'] += 1

        elif process_status is VideoProcessStatusEnum.WRONG_FORMAT:
            _ana_pointer['wrong_format'] += 1

        _ana_pointer['accuracy'] = _ana_pointer['right'] / _ana_pointer['total']



    def debug_logging_while_update_video_data(self, src: int, id:str, process_status:VideoProcessStatusEnum, image:any, yolo_images:list[any], digits:list):
        """ should be private function!
        """
        if self.log_dev[self.STR_DEBUG_LOG_HISTORY].get(id, None) is None:
            self.log_dev[self.STR_DEBUG_LOG_HISTORY][id] = []

        _dev_pointer = self.log_dev[self.STR_DEBUG_LOG_HISTORY][id]


        if process_status is VideoProcessStatusEnum.NO_PANEL:
            self.save_image(src, id, image, specify_path='debug/no_panel_found_{}_{}_{}.jpg')

        elif process_status is VideoProcessStatusEnum.NO_DATETIME:
            self.save_image(src, id, image, specify_path='debug/no_datetime_found_{}_{}_{}.jpg')

        elif process_status is VideoProcessStatusEnum.WRONG_FORMAT:
            if self.get_video_construct_pointer_by_id(id)['warning']['format']:
                path_img = self.save_image(src, id, yolo_images[-1], specify_path='debug/wrong_format_{}_{}_{}_img_datetime.jpg')
                _dev_pointer.append({
                    'digits': digits,
                    'ans_minute': datetime.now().minute,
                    'img_datetime': path_img,
                })



    def set_error_with_not_open_videos(self, src_ids = []):
        for src_id in src_ids:
            _splitted = src_id.split('_')
            src, id = int(_splitted[0]), _splitted[1]
            self.logger.error(f"[{id}][來源{src}]連線失敗")
            map_vi = self.map_video_index if src == 1 else self.map_video_index2
            videos = self.construct_videos if src == 1 else self.construct_videos2
            _idx = map_vi.get(id, -1)
            if _idx >= 0:
                videos[_idx]['flag'] = VideoFlagENum.ERROR
    

    

        
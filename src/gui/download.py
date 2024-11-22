import io
import wx
import os
import json
import time
import wx.adv
import requests
import subprocess
from typing import List, Dict

from gui.templates import Frame, ScrolledPanel
from gui.dialog.error_info import ErrorInfoDialog
from gui.dialog.cover import CoverViewerDialog

from utils.config import Config, Download, conf
from utils.downloader import Downloader, DownloaderInfo
from utils.tools import get_background_color, msw_open_in_explorer
from utils.thread import Thread
from utils.mapping import video_quality_mapping, audio_quality_mapping, video_codec_mapping, get_mapping_key_by_value
from utils.extra import ExtraParser
from utils.data_type import DownloadTaskInfo

class DownloadManagerInfo:
    download_list: Dict[int, DownloadTaskInfo] = {}
    no_task: bool = True

class DownloadTaskUtils:
    def __init__(self, info: DownloadTaskInfo, onError, onComplete):
        self.info, self.onError, self.audio_type, self.onComplete = info, onError, "mp3", onComplete

    def getVideoDurl(self):
        json_dash = self.getVideoDurlJson()

        # 获取视频最高清晰度
        highest_video_quality_id = self.getHighestVideoQuality(json_dash["video"])

        if self.info.video_quality_id == 200:
            # 当选择自动时，选取最高可用清晰度
            self.info.video_quality_id = highest_video_quality_id
        else:
            if highest_video_quality_id < self.info.video_quality_id:
                # 当视频不存在选取的清晰度时，选取最高可用的清晰度
                self.info.video_quality_id = highest_video_quality_id
            else:
                self.info.video_quality_id = self.info.video_quality_id

        # 获取选定清晰度的视频列表，包含多种清晰度
        temp_video_durl_list = [i for i in json_dash["video"] if i["id"] == self.info.video_quality_id]

        self.info.video_codec_id = Config.Download.video_codec_id

        codec_index = self.getVideoAvailableCodecIndex(temp_video_durl_list)

        # 判断视频支持选定的编码
        if codec_index is not None:
            durl_json = temp_video_durl_list[codec_index]

        else:
            # 不支持选定编码，自动切换到 H264
            durl_json = temp_video_durl_list[0]
            self.info.video_codec_id = 7

        self.video_durl_list = self.getAvailableDurlList(durl_json)

        if json_dash["audio"]:
            # 解析默认音质
            self.getDefaultAudioDurl(json_dash["audio"])

            if self.info.audio_quality_id == 30300:
                try:
                    # 获取无损或杜比链接
                    if "flac" in json_dash:
                        if json_dash["flac"]:
                            if "audio" in json_dash["flac"]:
                                if json_dash["flac"]["audio"]:
                                    # 无损
                                    audio_node = json_dash["flac"]["audio"]

                                    self.audio_durl_list = self.getAvailableDurlList(audio_node)

                                    self.audio_type = "flac"
                                    self.audio_quality = 30251

                    if "dolby" in json_dash:
                        if json_dash["dolby"]:
                            if "audio" in json_dash["dolby"]:
                                if json_dash["dolby"]["audio"]:
                                    # 杜比全景声
                                    audio_node = self.audio_durl_list = json_dash["dolby"]["audio"][0]

                                    self.audio_durl_list = self.getAvailableDurlList(audio_node)

                                    self.audio_type = "ec3"
                                    self.audio_quality = 30250

                except Exception:
                    # 无法获取无损或杜比链接，换回默认音质
                    self.getDefaultAudioDurl(json_dash["audio"])

        else:
            # 视频不存在音频，标记 flag 为仅下载视频
            self.info.video_merge_type = Config.Type.MERGE_TYPE_VIDEO

    def getVideoDurlJson(self) -> Dict:
        try:
            match self.info.download_type:
                case Config.Type.VIDEO:
                    url = f"https://api.bilibili.com/x/player/playurl?bvid={self.info.bvid}&cid={self.info.cid}&qn=0&fnver=0&fnval=4048&fourk=1"

                    req = requests.get(url)
                    resp = json.loads(req.text)

                    json_dash = resp["data"]["dash"]

                case Config.Type.BANGUMI:
                    url = f"https://api.bilibili.com/pgc/player/web/playurl?bvid={self.info.bvid}&cid={self.info.cid}&qn=0&fnver=0&fnval=12240&fourk=1"

                    req = requests.get(url)
                    resp = json.loads(req.text)

                    json_dash = resp["result"]["dash"]

            return json_dash

        except Exception:
            self.onError()

    def getDefaultAudioDurl(self, data):
        highest_audio_quality = self.getHighestAudioQuality(data)

        if highest_audio_quality < self.info.audio_quality_id or self.info.audio_quality_id == 30300:
            # 当视频不存在选取的音质时，选取最高可用的音质
            audio_quality = highest_audio_quality
        else:
            audio_quality = self.info.audio_quality_id

        temp_audio_durl = [i for i in data if i["id"] == audio_quality]

        self.audio_durl_list = self.getAvailableDurlList(temp_audio_durl[0])

        self.audio_type = "mp3"
        self.audio_quality = audio_quality

    def getDownloadInfo(self) -> list:
        # 获取视频下载链接
        self.getVideoDurl()

        temp_info = []
        video_info = audio_info = None

        match self.info.video_merge_type:
            case Config.Type.MERGE_TYPE_ALL:
                video_info = self.getVideoDownloaderInfo()
                audio_info = self.getAudioDownloaderInfo()

            case Config.Type.MERGE_TYPE_VIDEO:
                video_info = self.getVideoDownloaderInfo()

            case Config.Type.MERGE_TYPE_AUDIO:
                audio_info = self.getAudioDownloaderInfo()

        if video_info:
            temp_info.append(video_info)

        if audio_info:
            temp_info.append(audio_info)

        return temp_info

    def getVideoDownloaderInfo(self):
        # 返回视频下载信息，提供给下载器 Downloader
        return {
            "id": self.info.id,
            "type": "video",
            "url": self.video_durl_list, # 包含下载链接的列表，后续将遍历其可用性
            "referer_url": self.info.referer_url,
            "file_name": "video_{}.mp4".format(self.info.id),
            "chunk_list": []
        }

    def getAudioDownloaderInfo(self):
        # 返回音频下载信息，提供给下载器 Downloader
        return {
                "id": self.info.id,
                "type": "audio",
                "url": self.audio_durl_list, # 包含下载链接的列表，后续将遍历其可用性
                "referer_url": self.info.referer_url,
                "file_name": "audio_{}.{}".format(self.info.id, self.audio_type),
                "chunk_list": []
            }

    def getAvailableDurlList(self, entry):
        # 取视频音频的所有下载链接
        temp_list = []

        node_list = ["backupUrl", "backup_url", "baseUrl", "base_url"]

        for node_name in node_list:
            if node_name in entry:
                # 判断是否为列表
                if isinstance(entry[node_name], list):
                    temp_list.extend(entry[node_name])
                
                else:
                    temp_list.append(entry[node_name])

        return temp_list

    def mergeVideo(self):
        video_file_name = f"video_{self.info.id}.mp4"
        audio_file_name = f"audio_{self.info.id}.{self.audio_type}"

        cmd = self.getMergeVideoCmd(video_file_name, audio_file_name, self.getFileNameWithIndex())

        try:
            self.merge_process = self.runSubprocess(cmd)

        except Exception as e:
            # subprocess 运行出错
            self.onMergeError(f"尝试启动 subprocess 时出错：{e}")

            wx.CallAfter(self.onComplete, [video_file_name, audio_file_name])

            return

        if self.merge_process.returncode == 0:
            if self.info.video_merge_type == Config.Type.MERGE_TYPE_ALL:
                if Config.Merge.auto_clean:
                    pass

        else:
            # 合成失败时，获取错误信息
            try:
                output = self.merge_process.stdout.decode()

            except Exception:
                output = "无法获取错误信息"

            finally:
                self.onMergeError(output)

        wx.CallAfter(self.onComplete, [video_file_name, audio_file_name])

    def getMergeVideoCmd(self, video_file_name: str, audio_file_name: str, title: str):
        match Config.Sys.platform:
            case "windows":
                rename_cmd = "rename"

            case "linux" | "darwin":
                rename_cmd = "mv"

        match self.info.video_merge_type:
            case Config.Type.MERGE_TYPE_ALL:
                # 存在音频文件，调用 FFmpeg 合成
                if not Config.Merge.auto_clean:
                    # 不自动清理文件，保留音视频
                    cmd_extra = f'&& {rename_cmd} "{video_file_name}" "{title}_video.mp4" && {rename_cmd} "{audio_file_name}" "{title}_audio.{self.audio_type}"'
                else:
                    cmd_extra = ""

                cmd_piece = f'"{Config.FFmpeg.path}" -y -i "{video_file_name}" -i "{audio_file_name}" -acodec copy -vcodec copy -strict experimental _out.mp4'

                cmd = f'{cmd_piece} && {rename_cmd} _out.mp4 "{title}.mp4"{cmd_extra}'

            case Config.Type.MERGE_TYPE_VIDEO:
                # 无音频文件，仅有视频，直接重命名
                cmd = f'{rename_cmd} "{video_file_name}" "{title}.mp4"'

            case Config.Type.MERGE_TYPE_AUDIO:
                # 无视频文件，仅有音频，直接重命名，若为无损格式，根据设置决定是否转化为标准无损格式
                if self.audio_type == "flac" and Config.Merge.m4a_to_mp3:
                    cmd = f'"{Config.FFmpeg.path}" -y -i "{audio_file_name}" -c:a flac "{title}.flac"'
                else:
                    cmd = f'{rename_cmd} "{audio_file_name}" "{title}.{self.audio_type}"'

        return cmd

    def runSubprocess(self, cmd):
        process = subprocess.run(cmd, cwd = Config.Download.path, stdout = subprocess.PIPE, stderr = subprocess.STDOUT, shell = True)

        # subprocess 执行完成后，返回 process 指针

        return process

    def onMergeError(self, output):
        if hasattr(self, "merge_process"):
            return_code = self.merge_process.returncode
        else:
            return_code = "未知"

        self.merge_error_log = {"log": output, "time": "", "return_code": return_code}

        self.info.status = Config.Type.DOWNLOAD_STATUS_MERGE_FAILED

    def getHighestVideoQuality(self, data):
        # 默认为 360P
        highest_video_quality_id = 16

        for entry in data:
            # 遍历列表，选取其中最高的清晰度
            if entry["id"] > highest_video_quality_id:
                highest_video_quality_id = entry["id"]

        return highest_video_quality_id

    def getHighestAudioQuality(self, data):
        # 默认为 64K
        highest_audio_quality = 30216

        for entry in data:
            if entry["id"] > highest_audio_quality:
                highest_audio_quality = entry["id"]

        return highest_audio_quality

    def getVideoAvailableCodecIndex(self, data):
        for index, entry in enumerate(data):
            if entry["codecid"] == self.info.video_codec_id:
                return index

    def getFileNameWithIndex(self):
        if self.info.index and Config.Download.add_number:
            return f"{self.info.index} - {self.info.title_legal}"
        else:
            return self.info.title_legal
    
class DownloadWindow(Frame):
    def __init__(self, parent):
        Frame.__init__(self, parent, "下载管理", style = wx.DEFAULT_FRAME_STYLE & (~wx.MINIMIZE_BOX) & (~wx.MAXIMIZE_BOX))

        self.init_UI()

        self.setDownloadWindowSize()

        self.Bind_EVT()

        self.init_utils()

    def init_UI(self):
        font: wx.Font = self.GetFont()
        font.SetPointSize(14)

        self.task_lab = wx.StaticText(self, -1, "下载管理")
        self.task_lab.SetFont(font)

        max_download_lab = wx.StaticText(self, -1, "并行下载数：")
        self.max_download_choice = wx.Choice(self, -1, choices = ["1 个", "2 个", "3 个", "4 个"])

        self.start_all_btn = wx.Button(self, -1, "全部开始")
        self.pause_all_btn = wx.Button(self, -1, "全部暂停")
        self.stop_all_btn = wx.Button(self, -1, "全部取消")

        action_hbox = wx.BoxSizer(wx.HORIZONTAL)
        action_hbox.Add(max_download_lab, 0, wx.ALL & (~wx.TOP) | wx.ALIGN_CENTER, 10)
        action_hbox.Add(self.max_download_choice, 0, wx.ALL & (~wx.LEFT) & (~wx.TOP), 10)
        action_hbox.AddStretchSpacer()
        action_hbox.Add(self.start_all_btn, 0, wx.ALL & (~wx.TOP), 10)
        action_hbox.Add(self.pause_all_btn, 0, wx.ALL & (~wx.TOP) & (~wx.LEFT), 10)
        action_hbox.Add(self.stop_all_btn, 0, wx.ALL & (~wx.TOP) & (~wx.LEFT), 10)

        top_border = wx.StaticLine(self, -1, style = wx.LI_HORIZONTAL)

        self.download_list_panel = ScrolledPanel(self, size = self.FromDIP((720, 280)))
        self.download_list_panel.SetBackgroundColour(get_background_color())

        bottom_border = wx.StaticLine(self, -1, style = wx.LI_HORIZONTAL)

        botton_hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.open_btn = wx.Button(self, -1, "打开下载目录", size = self.getButtonSize())
        self.clear_btn = wx.Button(self, -1, "清除下载记录", size = self.getButtonSize())

        botton_hbox.Add(self.open_btn, 0, wx.ALL, 10)
        botton_hbox.AddStretchSpacer()
        botton_hbox.Add(self.clear_btn, 0, wx.ALL, 10)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.task_lab, 0, wx.ALL, 10)
        vbox.Add(action_hbox, 0, wx.EXPAND)
        vbox.Add(top_border, 0, wx.EXPAND)
        vbox.Add(self.download_list_panel, 1, wx.EXPAND)
        vbox.Add(bottom_border, 0, wx.EXPAND)
        vbox.Add(botton_hbox, 0, wx.EXPAND)

        self.SetSizerAndFit(vbox)

        self.SetBackgroundColour(get_background_color())

    def Bind_EVT(self):
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        self.clear_btn.Bind(wx.EVT_BUTTON, self.onClear)
        self.open_btn.Bind(wx.EVT_BUTTON, self.onOpenDir)

        self.max_download_choice.Bind(wx.EVT_CHOICE, self.onMaxDownloadChoice)
        self.stop_all_btn.Bind(wx.EVT_BUTTON, self.onStopAll)
        self.pause_all_btn.Bind(wx.EVT_BUTTON, self.onPauseAll)
        self.start_all_btn.Bind(wx.EVT_BUTTON, self.onStartAll)

    def init_utils(self):
        self.update_max_download_choice()

        self.load_tasks()

    def load_tasks(self):
        self.download_info = DownloaderInfo()

        tasks = self.download_info.read_info()

        for task_id, info in tasks.items():
            download_task_info = DownloadTaskInfo()
            download_task_info.load_from_dict(info["base_info"])

            if download_task_info.status == Config.Type.DOWNLOAD_STATUS_DOWNLOADING:
                download_task_info.status = Config.Type.DOWNLOAD_STATUS_PAUSE

            Download.download_list.append(download_task_info)

        if len(tasks):
            self.add_download_item(start_download = False)

    def OnClose(self, event):
        Config.Temp.download_window_pos = self.GetPosition()

        self.Hide()

    def onClear(self, event):
        # 首先遍历下载列表
        callback_list = [value.onStop_Callback for key, value in DownloadManagerInfo.download_list.items() if value.status == Config.Type.DOWNLOAD_STATUS_FINISHED]
        self.runCallbackList(callback_list)

    def onOpenDir(self, event):
        # 打开下载目录
        match Config.Sys.platform:
            case "windows":
                os.startfile(Config.Download.path)

            case "linux":
                subprocess.Popen(f'xdg-open "{Config.Download.path}"', shell = True)

            case "darwin":
                subprocess.Popen(f'open "{Config.Download.path}"', shell = True)

    def onMaxDownloadChoice(self, event):
        index = self.max_download_choice.GetSelection()

        Config.Download.max_download_count = index + 1

        conf.config.set("download", "max_download", str(Config.Download.max_download_count))
        conf.config_save()

        self.start_download()

    def onStartAll(self, event):
        callback_list = [value.onResume_Callback for key, value in DownloadManagerInfo.download_list.items() if value.status == Config.Type.DOWNLOAD_STATUS_PAUSE]

        self.runCallbackList(callback_list)

    def onPauseAll(self, event):
        callback_list = [value.onPause_Callback for key, value in DownloadManagerInfo.download_list.items() if value.status == Config.Type.DOWNLOAD_STATUS_DOWNLOADING]

        self.runCallbackList(callback_list)

    def onStopAll(self, event):
        callback_list = [value.onStop_Callback for key, value in DownloadManagerInfo.download_list.items() if value.status == Config.Type.DOWNLOAD_STATUS_WAITING or value.status == Config.Type.DOWNLOAD_STATUS_DOWNLOADING or value.status == Config.Type.DOWNLOAD_STATUS_PAUSE]

        self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))

        wx.CallAfter(self.runCallbackList, callback_list, True)

    def runCallbackList(self, callback_list: List, stopAll: bool = False):
        for callback in callback_list:
            if stopAll:
                callback(0, stopAll)
            else:
                callback(0)

        self.layout_sizer()

        self.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def add_download_item(self, download_task_info_list: List[DownloadTaskInfo], start_download: bool = True):
        multiple = True if len(Download.download_list) > 1 else False

        self.add_panel_item_worker(multiple, start_download)

    def add_panel_item_worker(self, download_task_info_list: List[DownloadTaskInfo], multiple: bool, start_download: bool):
        item_list = []

        # 暂时停止 UI 更新
        self.download_list_panel.Freeze()

        for index, entry in enumerate(download_task_info_list):
            if self.is_already_in_list(entry.title, entry.cid):
                continue

            item_list.append(self.add_panel_item_to_panel(index, entry, multiple))

        # 恢复 UI 更新
        self.download_list_panel.Thaw()

        # 添加下载项并更新 UI
        self.download_list_panel.sizer.AddMany(item_list)
        self.layout_sizer()

        # 关闭加载窗口回调
        self.GetParent().hideProcessWindowCallback()

        # 开始下载
        if start_download:
            self.start_download()

    def add_panel_item_to_panel(self, index: int, entry: DownloadTaskInfo, multiple: bool):
        if multiple:
            # 只有在批量下载视频时，才更新 index，否则都为默认值 0
            entry.index = index + 1

        item = DownloadItemPanel(self.download_list_panel, entry)

        entry.startDwonload_Callback = item.start
        entry.onPause_Callback = item.onPauseCallback
        entry.onResume_Callback = item.onResumeCallback
        entry.onStop_Callback = item.onStop

        DownloadManagerInfo.download_list[entry.id] = entry

        return (item, 0, wx.EXPAND)

    def layout_sizer(self):
        self.update_task_lab()

        self.download_list_panel.Layout()
        self.download_list_panel.SetupScrolling(scroll_x = False, scrollToTop = False)

    def update_task_lab(self):
        count = 0

        for key, value in DownloadManagerInfo.download_list.items():
            if value.status == Config.Type.DOWNLOAD_STATUS_WAITING or value.status == Config.Type.DOWNLOAD_STATUS_DOWNLOADING or value.status == Config.Type.DOWNLOAD_STATUS_PAUSE:
                count += 1

        if count:
            self.task_lab.SetLabel(f"{count} 个任务正在下载")

            DownloadManagerInfo.no_task = False
        else:
            self.task_lab.SetLabel("下载管理")

            if not DownloadManagerInfo.no_task:
                self.ShowNotificationToast()

            DownloadManagerInfo.no_task = True

    def start_download(self):
        for key, value in DownloadManagerInfo.download_list.items():
            if value.status == Config.Type.DOWNLOAD_STATUS_WAITING and self.get_downloading_count() < Config.Download.max_download_count:
                value.startDwonload_Callback()

    def get_downloading_count(self):
        count = 0

        for key, value in DownloadManagerInfo.download_list.items():
            if value.status == Config.Type.DOWNLOAD_STATUS_DOWNLOADING:
                count += 1

        return count

    def ShowNotificationToast(self):
        if Config.Download.show_notification:
            # 任务栏闪烁，需主窗口失去焦点的情况下才有效
            self.GetParent().RequestUserAttention(wx.USER_ATTENTION_ERROR)
            
            # 弹出 Toast 通知
            notification = wx.adv.NotificationMessage("下载完成", "所有任务已下载完成", self)

            notification.Show()

    def is_already_in_list(self, title: str, cid: int) -> bool:
        # 检查下载任务是否在下载列表中，防止重复下载
        for key, value in DownloadManagerInfo.download_list.items():
            return value.title == title and value.cid == cid

    def update_max_download_choice(self):
        max_download = Config.Download.max_download_count

        match max_download:
            case max_download if max_download < 1:
                index = 0

            case 1 | 2 | 3 | 4:
                index = max_download - 1

            case max_download if max_download > 4:
                choices = self.max_download_choice.GetItems()
                choices.append(f"{max_download} 个")

                index = len(choices) - 1

                self.max_download_choice.Set(choices)

        self.max_download_choice.SetSelection(index)

    def setDownloadWindowSize(self):
        match Config.Sys.platform:
            case "windows":
                self.SetSize(self.FromDIP((810, 500)))

            case "linux" | "darwin":
                self.SetClientSize(self.FromDIP((950, 550)))

        self.SetMinSize(self.GetSize())

    def getButtonSize(self):
        match Config.Sys.platform:
            case "windows":
                size = self.FromDIP((100, 30))

            case "linux" | "darwin":
                size = self.FromDIP((120, 40))

        return size

class DownloadItemPanel(wx.Panel):
    def __init__(self, parent, info: DownloadTaskInfo):
        self.info = info

        wx.Panel.__init__(self, parent)

        self.init_scale()

        self.init_UI()

        self.Bind_EVT()

        self.init_utils()

        self.CentreOnParent()

    def init_utils(self):
        # 获取视频封面
        Thread(target = self.getCover, daemon = False).start()

        # 下载类
        self.downloader = Downloader(self.info, self.onStartCallback, self.onDownloadCallback, self.onMerge, self.onError)
        # 功能类
        self.utils = DownloadTaskUtils(self.info, self.onError, self.onMergeComplete)

        # 断点续传
        if self.info.completed_size:
            self.loadDownloadInfo()

    def loadDownloadInfo(self):
        # 当存在文件总大小信息时，才显示已下载的文件大小
        if self.info.total_size:

            self.gauge.SetValue(self.info.progress)

        self.video_quality_lab.SetLabel(get_mapping_key_by_value(video_quality_mapping, self.info.video_quality_id))
        self.video_codec_lab.SetLabel(get_mapping_key_by_value(video_codec_mapping, self.info.video_codec_id))

        self.updatePauseBtn(self.info.status)

    def init_scale(self):
        match Config.Sys.platform:
            case "windows" | "darwin":
                self.scale_size = self.FromDIP((16, 16))
                self.is_scaled = True if self.scale_size != (16, 16) else False

            case "linux":
                self.scale_size = self.FromDIP((32, 32))
                self.is_scaled = True

    def init_UI(self):
        self.cover = wx.StaticBitmap(self, -1, size = self.FromDIP((112, 63)))
        self.cover.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        self.title_lab = wx.StaticText(self, -1, self.info.title, size = self.FromDIP((300, 24)), style = wx.ST_ELLIPSIZE_MIDDLE)
        self.title_lab.SetToolTip(self.info.title)

        self.video_quality_lab = wx.StaticText(self, -1, "--", size = self.FromDIP((-1, -1)))
        self.video_quality_lab.SetForegroundColour(wx.Colour(108, 108, 108))

        self.video_codec_lab = wx.StaticText(self, -1, "--", size = self.FromDIP((-1, -1)))
        self.video_codec_lab.SetForegroundColour(wx.Colour(108, 108, 108))

        self.video_size_lab = wx.StaticText(self, -1, "--", size = self.FromDIP((-1, -1)))
        self.video_size_lab.SetForegroundColour(wx.Colour(108, 108, 108))

        video_info_hbox = wx.BoxSizer(wx.HORIZONTAL)
        video_info_hbox.Add(self.video_quality_lab, 1, wx.ALL & (~wx.TOP) | wx.ALIGN_CENTER, 10)
        video_info_hbox.Add(self.video_codec_lab, 1, wx.ALL & (~wx.TOP) | wx.ALIGN_CENTER, 10)
        video_info_hbox.Add(self.video_size_lab, 1, wx.ALL & (~wx.TOP) | wx.ALIGN_CENTER, 10)

        info_vbox = wx.BoxSizer(wx.VERTICAL)
        info_vbox.AddSpacer(5)
        info_vbox.Add(self.title_lab, 0, wx.ALL & (~wx.BOTTOM) | wx.EXPAND, 10)
        info_vbox.AddStretchSpacer()
        info_vbox.Add(video_info_hbox, 0, wx.EXPAND)
        info_vbox.AddSpacer(5)

        self.gauge = wx.Gauge(self, -1, 100, size = self.getGaugeSize(), style = wx.GA_SMOOTH)

        gauge_hbox = wx.BoxSizer(wx.HORIZONTAL)
        gauge_hbox.Add(self.gauge, 0, wx.ALL & (~wx.BOTTOM) | wx.ALIGN_CENTER, 10)

        self.speed_lab = wx.StaticText(self, -1, "等待下载...", size = self.FromDIP((-1, -1)))
        self.speed_lab.SetForegroundColour(wx.Colour(108, 108, 108))

        speed_hbox = wx.BoxSizer(wx.HORIZONTAL)
        speed_hbox.Add(self.speed_lab, 0, wx.ALL & (~wx.TOP) | wx.ALIGN_CENTER, 10)

        gauge_vbox = wx.BoxSizer(wx.VERTICAL)
        gauge_vbox.AddSpacer(5)
        gauge_vbox.Add(gauge_hbox, 0, wx.EXPAND)
        gauge_vbox.AddStretchSpacer()
        gauge_vbox.Add(speed_hbox, 0, wx.EXPAND)
        gauge_vbox.AddSpacer(5)

        self.pause_btn = wx.BitmapButton(self, -1, size = self.getButtonSize())
        self.pause_btn.SetToolTip("开始下载")

        self.stop_btn = wx.BitmapButton(self, -1, size = self.getButtonSize())
        self.stop_btn.SetToolTip("取消下载")

        panel_hbox = wx.BoxSizer(wx.HORIZONTAL)
        panel_hbox.Add(self.cover, 0, wx.ALL, 10)
        panel_hbox.Add(info_vbox, 0, wx.EXPAND)
        panel_hbox.AddStretchSpacer(1)
        panel_hbox.Add(gauge_vbox, 0, wx.EXPAND)
        panel_hbox.Add(self.pause_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        panel_hbox.Add(self.stop_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        panel_hbox.AddSpacer(10)

        border = wx.StaticLine(self, -1, style = wx.LI_HORIZONTAL)

        self.panel_vbox = wx.BoxSizer(wx.VERTICAL)
        self.panel_vbox.Add(panel_hbox, 1, wx.EXPAND)
        self.panel_vbox.Add(border, 0, wx.EXPAND)

        self.SetSizer(self.panel_vbox)

    def Bind_EVT(self):
        self.pause_btn.Bind(wx.EVT_BUTTON, self.onPause_EVT)
        self.stop_btn.Bind(wx.EVT_BUTTON, self.onStop)

        self.speed_lab.Bind(wx.EVT_LEFT_DOWN, self.onShowError)
        self.cover.Bind(wx.EVT_LEFT_DOWN, self.onViewCover)

    def getCover(self):
        req = requests.get(self.info.cover_url)

        scale_size = self.FromDIP((112, 63))

        temp_cover_image = wx.Image(io.BytesIO(req.content))

        # 判断封面是否为 16:9，若不是，进行裁剪
        if not self.isCover16_9(temp_cover_image):
            temp_cover_image = self.resizeCoverTo16_9(temp_cover_image)

        self.cover_image = temp_cover_image

        self.cover_image_raw = req.content

        image = self.cover_image.Scale(scale_size[0], scale_size[1], wx.IMAGE_QUALITY_HIGH)

        self.cover.SetBitmap(image.ConvertToBitmap())

        self.panel_vbox.Layout()

    def start(self):
        # 准备开始下载
        self.setStatus(Config.Type.DOWNLOAD_STATUS_DOWNLOADING)

        # 开启线程，防止 UI 阻塞
        self.start_thread = Thread(target = self.startDownloadThread)
        self.start_thread.start()

    def startDownloadThread(self):
        self.speed_lab.SetLabel("准备下载...")

        # 获取下载信息，开始下载
        info_list = self.utils.getDownloadInfo()

        self.downloader.start_download(info_list)

    def onPause_EVT(self, event):
        match self.info.status:
            case Config.Type.DOWNLOAD_STATUS_WAITING:
                self.start()

            case Config.Type.DOWNLOAD_STATUS_DOWNLOADING:
                self.onPause()

            case Config.Type.DOWNLOAD_STATUS_PAUSE:
                self.onResume()

            case Config.Type.DOWNLOAD_STATUS_FINISHED:
                self.onOpenFolder()
                return

            case Config.Type.DOWNLOAD_STATUS_MERGE_FAILED:
                self.onMerge(retry = True)
                return
        
        if self.info.status in Config.Type.DOWNLOAD_STATUS_ALIVE_LIST:
            self.setStatus(self.info.status)

        self.updatePauseBtn(self.info.status)

    def onStartCallback(self):
        # 开始下载回调函数，更新下载信息
        self.info.total_size = self.downloader.total_size

        self.speed_lab.SetLabel("")
        self.video_size_lab.SetLabel(f"0 MB/{(self.info.total_size)}")

        match self.info.video_merge_type:
            case Config.Type.MERGE_TYPE_VIDEO | Config.Type.MERGE_TYPE_ALL:
                # 视频番组类
                self.video_quality_lab.SetLabel(get_mapping_key_by_value(video_quality_mapping, self.info.video_quality_id))
                self.video_codec_lab.SetLabel(get_mapping_key_by_value(video_codec_mapping, self.info.video_codec_id))

            case Config.Type.MERGE_TYPE_AUDIO:
                # 音频类
                self.video_quality_lab.SetLabel("音频")
                self.video_codec_lab.SetLabel(get_mapping_key_by_value(audio_quality_mapping, self.info.audio_quality_id))

        self.updatePauseBtn(Config.Type.DOWNLOAD_STATUS_DOWNLOADING)

        self.Layout()

        # 写入文件，记录下载信息
        base_info = {
            "total_size": self.info.total_size,
            "video_quality_id": self.info.video_quality_id,
            "audio_quality_id": self.info.audio_quality_id,
            "video_codec_id": self.info.video_codec_id,
            "status": Config.Type.DOWNLOAD_STATUS_DOWNLOADING
        }

        self.downloader.downloader_info.update_base_info_kwargs(**base_info)

    def onDownloadCallback(self, download_progress_info: Dict):
        # 更新下载进度回调函数
        if self.info.status == Config.Type.DOWNLOAD_STATUS_DOWNLOADING:
            self.gauge.SetValue(download_progress_info["progress"])

            self.speed_lab.SetLabel(download_progress_info["speed"])
            self.video_size_lab.SetLabel("{}/{}".format((download_progress_info["completed_size"]), (self.info.total_size)))

            progress_info = {
                "progress": download_progress_info["progress"],
                "completed_size": download_progress_info["completed_size"]
            }

            self.downloader.downloader_info.update_base_info_kwargs(**progress_info)

            # 更新下载进度至 DownloadTaskInfo
            self.info.progress = download_progress_info["progress"]
            self.info.completed_size = download_progress_info["completed_size"]

    def onPause(self):
        self.downloader.onPause()

    def onPauseCallback(self, event):
        self.onPause()

        self.setStatus(Config.Type.DOWNLOAD_STATUS_PAUSE)
        self.updatePauseBtn(Config.Type.DOWNLOAD_STATUS_PAUSE)

    def onResume(self):
        # 判断是否下载完成
        if self.info.completed_size:
            if self.info.completed_size >= self.info.total_size:
                self.info.download_finish_flag = True

        # 判断下载状态
        if self.info.download_finish_flag:
            # 下载完成，直接开始合成
            self.onMerge()
        else:
            # 判断是否已经开始下载
            if self.info.completed_size:
                self.downloader.onResume()

            else:
                # 未开始下载，调用 start
                self.start()

    def onResumeCallback(self, event):
        self.onResume()

        self.setStatus(Config.Type.DOWNLOAD_STATUS_DOWNLOADING)
        self.updatePauseBtn(Config.Type.DOWNLOAD_STATUS_DOWNLOADING)

    def onStop(self, event, stopAll: bool = False):
        self.downloader.downloader_info.clear()

        self.downloader.onStop()

        self.Hide()

        if self.info.id in DownloadManagerInfo.download_list:
            DownloadManagerInfo.download_list.pop(self.info.id)

        Thread(target = self.onStopThread).start()

        if not stopAll:
            self.GetParent().GetParent().layout_sizer()

        self.Destroy()

    def onStopThread(self):
        time.sleep(1)

    def onMerge(self, retry: bool = False):
        self.setStatus(Config.Type.DOWNLOAD_STATUS_MERGING)

        self.speed_lab.SetForegroundColour(wx.Colour(108, 108, 108))

        self.video_size_lab.SetLabel((self.info.total_size))
        self.speed_lab.SetLabel("正在合成视频...")
        self.pause_btn.Enable(False)

        # 保存下载完成标识符
        finish_info = {
            "download_finish_flag": True
        }

        self.downloader.downloader_info.update_base_info_kwargs(**finish_info)

        if not retry:
            parent = self.GetParent().GetParent()

            parent.update_task_lab()
            parent.start_download()

        Thread(target = self.utils.mergeVideo).start()

    def onMergeComplete(self, file_list: List):
        if self.info.status == Config.Type.DOWNLOAD_STATUS_MERGE_FAILED:
            self.onMergeFailed()

            return
        else:
            self.speed_lab.SetLabel("下载完成")

            self.setStatus(Config.Type.DOWNLOAD_STATUS_FINISHED)

            self.pause_btn.Enable(True)

            if Config.Merge.auto_clean:
                # 再次删除文件，防止残留
                pass

        self.downloader.downloader_info.clear()

        self.stop_btn.SetToolTip("清除记录")

        self.updatePauseBtnImage(self.info.status)

        self.pause_btn.SetToolTip("打开所在位置")

        self.gauge.SetValue(100)

        self.getExtraContents()

    def onMergeFailed(self):
        self.speed_lab.SetLabel("合成视频失败，点击查看详情")
        self.speed_lab.SetForegroundColour(wx.Colour("red"))
        self.speed_lab.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        self.setStatus(Config.Type.DOWNLOAD_STATUS_MERGE_FAILED)
        self.updatePauseBtn(Config.Type.DOWNLOAD_STATUS_MERGE_FAILED)
    
    def onError(self):
        self.setStatus(Config.Type.DOWNLOAD_STATUS_DOWNLOAD_FAILED)

        self.speed_lab.SetLabel("下载失败")
        self.speed_lab.SetForegroundColour("red")
        self.stop_btn.SetToolTip("清除记录")

        self.pause_btn.Enable(False)

        self.Layout()

        self.GetParent().GetParent().update_task_lab()

        self.downloader.downloader_info.clear()

    def onOpenFolder(self):
        match self.info.video_merge_type:
            case Config.Type.MERGE_TYPE_ALL | Config.Type.MERGE_TYPE_VIDEO:
                file_type = "mp4"

            case Config.Type.MERGE_TYPE_AUDIO:
                file_type = f"{self.utils.audio_type}"

        self.file_full_name = f"{self.utils.getFileNameWithIndex()}.{file_type}"
        full_path = os.path.join(Config.Download.path, self.file_full_name)

        if not os.path.exists(full_path):
            wx.MessageDialog(self.GetParent().GetParent(), f"文件不存在\n\n无法打开文件：{self.file_full_name}\n\n文件不存在。", "警告", wx.ICON_WARNING).ShowModal()
            return
        
        if Config.Sys.platform == "windows":
            # Windows 下直接使用 SHOpenFolderAndSelectItems API 函数，避免被360拦截
            msw_open_in_explorer(full_path)

        else:
            match Config.Sys.platform:
                case "linux":
                    # Linux 下 xdg-open 并不支持选中文件，故仅打开所在文件夹
                    cmd = f'xdg-open "{Config.Download.path}"'

                case "darwin":
                    cmd = f'open -R "{self.file_full_name}"'

            subprocess.Popen(cmd, cwd = Config.Download.path, shell = True)

    def onViewCover(self, event):
        cover_viewer_dlg = CoverViewerDialog(self.GetParent().GetParent(), self.cover_image, self.cover_image_raw)
        cover_viewer_dlg.ShowModal()

    def onShowError(self, event):
        if not self.pause_btn.Enabled or self.info.status == Config.Type.DOWNLOAD_STATUS_MERGE_FAILED:
            show_error_dlg = ErrorInfoDialog(self.GetParent().GetParent(), self.utils.merge_error_log)
            show_error_dlg.ShowModal()

    def updatePauseBtn(self, status: int):
        match status:
            case Config.Type.DOWNLOAD_STATUS_DOWNLOADING:
                self.pause_btn.SetToolTip("暂停下载")

                self.speed_lab.SetLabel("准备下载...")

            case Config.Type.DOWNLOAD_STATUS_PAUSE:
                self.pause_btn.SetToolTip("继续下载")

                self.speed_lab.SetLabel("暂停中")

            case Config.Type.DOWNLOAD_STATUS_MERGE_FAILED:
                self.pause_btn.SetToolTip("重试")

                self.pause_btn.Enable(True)

        self.updatePauseBtnImage(status)

    def updatePauseBtnImage(self, status: int):
        match status:
            case Config.Type.DOWNLOAD_STATUS_DOWNLOADING:
                image = wx.Image(io.BytesIO(())) if self.is_scaled else wx.Image(io.BytesIO(()))

            case Config.Type.DOWNLOAD_STATUS_PAUSE | Config.Type.DOWNLOAD_STATUS_WAITING:
                image = wx.Image(io.BytesIO(())) if self.is_scaled else wx.Image(io.BytesIO(()))

            case Config.Type.DOWNLOAD_STATUS_MERGE_FAILED:
                image = wx.Image(io.BytesIO(())) if self.is_scaled else wx.Image(io.BytesIO(()))

            case Config.Type.DOWNLOAD_STATUS_FINISHED:
                image = wx.Image(io.BytesIO(())) if self.is_scaled else wx.Image(io.BytesIO(()))

        self.pause_btn.SetBitmap(image.Scale(self.scale_size[0], self.scale_size[1], wx.IMAGE_QUALITY_HIGH).ConvertToBitmap())

    def getExtraContents(self):
        # 下载附加内容
        extra_parser = ExtraParser(self.info.title_legal, self.info.cid)

        if Config.Extra.download_danmaku:
            extra_parser.get_danmaku()

    def setStatus(self, status: int):
        self.info.status = status

        status_info = {
            "status": status
        }

        self.downloader.downloader_info.update_base_info_kwargs(**status_info)

        if self.info.id in DownloadManagerInfo.download_list:
            # 防止任务 id 不在下载列表中而报错
            DownloadManagerInfo.download_list[self.info.id]  = self.info

    def resizeCoverTo16_9(self, image: wx.Image):
        # 将非 16:9 封面调整为 16:9
        width, height = image.GetSize()

        new_height = int(width * (9 / 16))

        y_offset = (height - new_height) // 2

        cropped_image = image.GetSubImage(wx.Rect(0, y_offset, width, new_height))

        return cropped_image

    def isCover16_9(self, image: wx.Image):
        # 判断封面原始比例是否为 16:9
        width, height = image.GetSize()

        return (width / height) == (16 / 9)

    def getGaugeSize(self):
        match Config.Sys.platform:
            case "windows":
                size = (-1, -1)

            case "darwin" | "linux":
                size = (190, 24)

        return size

    def getButtonSize(self):
        match Config.Sys.platform:
            case "windows" | "darwin":
                size = self.FromDIP((24, 24))

            case "linux":
                size = self.FromDIP((32, 32))

        return size

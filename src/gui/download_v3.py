import wx
from datetime import datetime
from typing import List

from utils.common.icon_v2 import IconManager, IconType
from utils.common.data_type import DownloadTaskInfo
from utils.tool_v2 import DownloadFileTool
from utils.config import Config

from gui.templates import ActionButton, ScrolledPanel
from gui.download_item_v3 import DownloadTaskItemPanel, EmptyItemPanel

class DownloadManagerWindow(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, -1, "下载管理 V3 Demo")

        self.SetSize(self.FromDIP((910, 550)))

        self.init_UI()

        self.Bind_EVT()

        self.init_utils()

        self.CenterOnParent()

    def init_UI(self):
        icon_manager = IconManager(self)

        top_panel = wx.Panel(self, -1)
        top_panel.SetBackgroundColour("white")

        font: wx.Font = self.GetFont()
        font.SetFractionalPointSize(int(font.GetFractionalPointSize() + 5))

        self.top_title_lab = wx.StaticText(top_panel, -1, "2 个任务正在下载")
        self.top_title_lab.SetFont(font)

        top_panel_hbox = wx.BoxSizer(wx.HORIZONTAL)
        top_panel_hbox.AddSpacer(20)
        top_panel_hbox.Add(self.top_title_lab, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        top_panel_vbox = wx.BoxSizer(wx.VERTICAL)
        top_panel_vbox.AddSpacer(10)
        top_panel_vbox.Add(top_panel_hbox, 0, wx.EXPAND)
        top_panel_vbox.AddSpacer(10)

        top_panel.SetSizerAndFit(top_panel_vbox)

        top_separate_line = wx.StaticLine(self, -1)

        left_panel = wx.Panel(self, -1)
        left_panel.SetBackgroundColour("white")

        self.downloading_page_btn = ActionButton(left_panel, "正在下载(2)")
        self.downloading_page_btn.setBitmap(icon_manager.get_icon_bitmap(IconType.DOWNLOADING_ICON))
        self.completed_page_btn = ActionButton(left_panel, "下载完成(0)")
        self.completed_page_btn.setBitmap(icon_manager.get_icon_bitmap(IconType.COMPLETED_ICON))

        self.open_download_dir_btn = wx.Button(left_panel, -1, "打开下载目录", size = self.FromDIP((120, 28)))

        bottom_hbox = wx.BoxSizer(wx.HORIZONTAL)
        bottom_hbox.AddStretchSpacer()
        bottom_hbox.Add(self.open_download_dir_btn, 0, wx.ALL, 10)
        bottom_hbox.AddStretchSpacer()

        left_panel_vbox = wx.BoxSizer(wx.VERTICAL)
        left_panel_vbox.Add(self.downloading_page_btn, 0, wx.EXPAND)
        left_panel_vbox.Add(self.completed_page_btn, 0, wx.EXPAND)
        left_panel_vbox.AddStretchSpacer()
        left_panel_vbox.Add(bottom_hbox, 0, wx.EXPAND)

        left_panel.SetSizerAndFit(left_panel_vbox)

        middle_separate_line = wx.StaticLine(self, -1, style = wx.LI_VERTICAL)

        right_panel = wx.Panel(self, -1)
        right_panel.SetBackgroundColour("white")

        self.book = wx.Simplebook(right_panel, -1)

        self.downloading_page = DownloadingPage(self.book)
        self.completed_page = CompeltedPage(self.book)

        self.book.AddPage(self.downloading_page, "downloading_page")
        self.book.AddPage(self.completed_page, "completed_page")

        right_panel_panel = wx.BoxSizer(wx.VERTICAL)
        right_panel_panel.Add(self.book, 1, wx.EXPAND)

        right_panel.SetSizerAndFit(right_panel_panel)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(left_panel, 0, wx.EXPAND)
        hbox.Add(middle_separate_line, 0, wx.EXPAND)
        hbox.Add(right_panel, 1, wx.EXPAND)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(top_panel, 0, wx.EXPAND)
        vbox.Add(top_separate_line, 0, wx.EXPAND)
        vbox.Add(hbox, 1, wx.EXPAND)

        self.SetSizer(vbox)

    def Bind_EVT(self):
        self.downloading_page_btn.onClickCustomEVT = self.onDownloadingPageBtnEVT
        self.completed_page_btn.onClickCustomEVT = self.onCompletedPageBtnEVT

        self.Bind(wx.EVT_CLOSE, self.onCloseEVT)
    
    def init_utils(self):
        self.downloading_page_btn.setActiveState()
    
    def add_to_download_list(self, download_list: List[DownloadTaskInfo]):
        def create_local_file():
            for index, entry in enumerate(download_list):
                # 记录时间戳
                if not entry.timestamp:
                    entry.timestamp = self.get_timestamp() + index

                # 更新序号
                if len(download_list) and Config.Download.add_number:
                    entry.index = index
                    entry.index_with_zero = str(index + 1).zfill(len(str(len(download_list))))

                download_local_file = DownloadFileTool(entry.id)
                # 如果本地文件不存在，则创建
                if not download_local_file.file_existence:
                    download_local_file.save_download_info(entry)
            
            self.downloading_page.temp_download_list.extend(download_list)
        
        create_local_file()
        
        # 显示下载项
        self.downloading_page.load_more_panel_item()

    def onCloseEVT(self, event):
        self.Hide()

    def onDownloadingPageBtnEVT(self):
        self.book.SetSelection(0)

        self.completed_page_btn.setUnactiveState()

    def onCompletedPageBtnEVT(self):
        self.book.SetSelection(1)

        self.downloading_page_btn.setUnactiveState()

    def get_timestamp(self):
        timestamp_str = str(datetime.now().timestamp()).replace(".", "")
        return int(timestamp_str)

class DownloadingPage(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.init_UI()

        self.init_utils()
    
    def init_UI(self):
        max_download_lab = wx.StaticText(self, -1, "并行下载数")
        self.max_download_choice = wx.Choice(self, -1, choices = [f"{i + 1}" for i in range(8)])

        self.start_all_btn = wx.Button(self, -1, "全部开始")
        self.pause_all_btn = wx.Button(self, -1, "全部暂停")
        self.cancel_all_btn = wx.Button(self, -1, "全部取消")

        top_hbox = wx.BoxSizer(wx.HORIZONTAL)
        top_hbox.Add(max_download_lab, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        top_hbox.Add(self.max_download_choice, 0, wx.ALL & (~wx.LEFT) | wx.ALIGN_CENTER, 10)
        top_hbox.AddStretchSpacer()
        top_hbox.Add(self.start_all_btn, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        top_hbox.Add(self.pause_all_btn, 0, wx.ALL & (~wx.LEFT) | wx.ALIGN_CENTER, 10)
        top_hbox.Add(self.cancel_all_btn, 0, wx.ALL & (~wx.LEFT) | wx.ALIGN_CENTER, 10)

        top_separate_line = wx.StaticLine(self, -1)

        self.scroller = ScrolledPanel(self)
        self.scroller.SetBackgroundColour("white")
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(top_hbox, 0, wx.EXPAND)
        vbox.Add(top_separate_line, 0, wx.EXPAND)
        vbox.Add(self.scroller, 1, wx.EXPAND)

        self.SetSizer(vbox)

    def init_utils(self):
        self.temp_download_list: List[DownloadTaskInfo] = []

    def load_more_panel_item(self):
        def get_download_list():
            # 当前限制每次加载 50 个
            item_threshold = 50

            temp_download_list = self.temp_download_list[:item_threshold]
            self.temp_download_list = self.temp_download_list[item_threshold:]

            return temp_download_list

        def get_items():
            items = []

            for entry in get_download_list():
                item = DownloadTaskItemPanel(self, entry)
                items.append((item, 0, wx.EXPAND))
            
            return items
        
        def worker(items: list):
            # 批量添加下载项
            self.scroller.Freeze()
            self.scroller.sizer.AddMany(items)
            self.scroller.Thaw()

        items = get_items()
        
        wx.CallAfter(worker, items)

        self.refresh_scroller()

    def refresh_scroller(self):
        self.scroller.Layout()
        self.scroller.SetupScrolling(scroll_x = False, scrollToTop = False)

class CompeltedPage(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)

        self.init_UI()

        self.init_utils()

    def init_UI(self):
        self.clear_history_btn = wx.Button(self, -1, "清除下载记录")

        top_hbox = wx.BoxSizer(wx.HORIZONTAL)
        top_hbox.AddStretchSpacer()
        top_hbox.Add(self.clear_history_btn, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        top_separate_line = wx.StaticLine(self, -1)

        self.scroller = ScrolledPanel(self)
        self.scroller.SetBackgroundColour("white")
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(top_hbox, 0, wx.EXPAND)
        vbox.Add(top_separate_line, 0, wx.EXPAND)
        vbox.Add(self.scroller, 1, wx.EXPAND)

        self.SetSizer(vbox)

    def init_utils(self):
        empty = EmptyItemPanel(self.scroller)
    
        self.scroller.sizer.Add(empty, 1, wx.EXPAND)

        self.scroller.Layout()
        self.scroller.SetupScrolling(scroll_x = False, scrollToTop = False)
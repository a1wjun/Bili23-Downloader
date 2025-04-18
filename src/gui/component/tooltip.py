import wx

from utils.common.icon_v3 import Icon, IconID

class ToolTip(wx.StaticBitmap):
    def __init__(self, parent):
        wx.StaticBitmap.__init__(self, parent, -1, Icon.get_icon_bitmap(IconID.INFO_ICON))

    def set_tooltip(self, string: str):
        tooltip = wx.ToolTip(string)
        tooltip.SetDelay(50)

        self.SetToolTip(tooltip)
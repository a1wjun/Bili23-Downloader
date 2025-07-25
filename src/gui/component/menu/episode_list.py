import wx

from gui.id import ID

class EpisodeListMenu(wx.Menu):
    def __init__(self, item_type: str, checked_state: bool, collapsed_state: bool):
        wx.Menu.__init__(self)

        wx.Menu()

        view_cover_menuitem = wx.MenuItem(self, ID.EPISODE_LIST_VIEW_COVER_MENU, "查看封面(&V)")
        copy_title_menuitem = wx.MenuItem(self, ID.EPISODE_LIST_COPY_TITLE_MENU, "复制标题(&C)")
        copy_url_menuitem = wx.MenuItem(self, ID.EPISODE_LIST_COPY_URL_MENU, "复制链接(&U)")
        edit_title_menuitem = wx.MenuItem(self, ID.EPISODE_LIST_EDIT_TITLE_MENU, "修改标题(&E)")
        check_menuitem = wx.MenuItem(self, ID.EPISODE_LIST_CHECK_MENU, "取消选择(&N)" if checked_state else "选择(&S)")
        collapse_menuitem = wx.MenuItem(self, ID.EPISODE_LIST_COLLAPSE_MENU, "展开(&X)" if collapsed_state else "折叠(&O)")

        if item_type == "node":
            view_cover_menuitem.Enable(False)
            copy_title_menuitem.Enable(False)
            copy_url_menuitem.Enable(False)
            edit_title_menuitem.Enable(False)
        else:
            collapse_menuitem.Enable(False)

        self.Append(view_cover_menuitem)
        self.AppendSeparator()
        self.Append(copy_title_menuitem)
        self.Append(copy_url_menuitem)
        self.AppendSeparator()
        self.Append(edit_title_menuitem)
        self.AppendSeparator()
        self.Append(check_menuitem)
        self.Append(collapse_menuitem)
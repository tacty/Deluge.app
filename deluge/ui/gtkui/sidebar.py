#
# sidebar.py
#
# Copyright (C) 2007 Andrew Resch ('andar') <andrewresch@gmail.com>
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA    02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.

import gtk
import gtk.glade

import deluge.component as component
import deluge.common
from deluge.log import LOG as log

class SideBar(component.Component):
    """
    manages the sidebar-tabs.
    purpose : plugins
    """
    def __init__(self):
        component.Component.__init__(self, "SideBar")
        self.window = component.get("MainWindow")
        glade = self.window.main_glade
        self.notebook = glade.get_widget("sidebar_notebook")
        self.hpaned = glade.get_widget("hpaned")
        self.is_visible = True

        # Tabs holds references to the Tab widgets by their name
        self.tabs = {}

    def visible(self, visible):
        if visible:
            self.notebook.show()
        else:
            log.debug("5")
            self.notebook.hide()
            log.debug("6")
            self.hpaned.set_position(-1)
            log.debug("7")

        self.is_visible = visible

    def add_tab(self, widget, tab_name, label):
        """Adds a tab object to the notebook."""
        log.debug("add tab:%s" % tab_name )
        self.tabs[tab_name] = widget
        pos = self.notebook.insert_page(widget, gtk.Label(label), -1)
        log.debug("1")
        widget.show_all()
        log.debug("2")
        if not self.notebook.get_property("visible"):
            # If the notebook isn't visible, show it
            self.visible(True) #Shure?
        log.debug("3")
        self.notebook.select_page(pos)

    def remove_tab(self, tab_name):
        """Removes a tab by name."""
        self.notebook.remove_page(self.notebook.page_num(self.tabs[tab_name]))
        del self.tabs[tab_name]

        # If there are no tabs visible, then do not show the notebook
        if len(self.tabs) == 0:
            self.visible(False)
#
# addtorrentdialog.py
#
# Copyright (C) 2007 Andrew Resch ('andar') <andrewresch@gmail.com>
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

import pygtk
pygtk.require('2.0')
import gtk, gtk.glade
import gettext
import gobject

import pkg_resources

from deluge.ui.client import aclient as client
import deluge.component as component
import deluge.ui.gtkui.listview as listview
from deluge.configmanager import ConfigManager
from deluge.log import LOG as log
import deluge.common

class AddTorrentDialog(component.Component):
    def __init__(self):
        component.Component.__init__(self, "AddTorrentDialog")
        self.glade = gtk.glade.XML(
            pkg_resources.resource_filename(
                "deluge.ui.gtkui", "glade/add_torrent_dialog.glade"))
        
        self.dialog = self.glade.get_widget("dialog_add_torrent")
        
        self.glade.signal_autoconnect({
            "on_button_file_clicked": self._on_button_file_clicked,
            "on_button_url_clicked": self._on_button_url_clicked,
            "on_button_hash_clicked": self._on_button_hash_clicked,
            "on_button_remove_clicked": self._on_button_remove_clicked,
            "on_button_trackers_clicked": self._on_button_trackers_clicked,
            "on_button_cancel_clicked": self._on_button_cancel_clicked,
            "on_button_add_clicked": self._on_button_add_clicked,
            "on_button_apply_clicked": self._on_button_apply_clicked,
            "on_button_revert_clicked": self._on_button_revert_clicked
        })

        self.torrent_liststore = gtk.ListStore(str, str, str)
        #download?, path, filesize, sequence number, inconsistent?
        self.files_treestore = gtk.TreeStore(bool, str, gobject.TYPE_UINT64,
                                        gobject.TYPE_INT64, bool, str)
        # Holds the files info
        self.files = {}
        self.infos = {}
        self.core_config = {}
        self.options = {}
        self.previous_selected_torrent = None
        
        
        self.listview_torrents = self.glade.get_widget("listview_torrents")
        self.listview_files = self.glade.get_widget("listview_files")

        render = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Torrent"), render, text=1)
        self.listview_torrents.append_column(column)

        render = gtk.CellRendererToggle()
        render.connect("toggled", self._on_file_toggled)
        column = gtk.TreeViewColumn(None, render, active=0, inconsistent=4)
        self.listview_files.append_column(column)

        column = gtk.TreeViewColumn(_("Filename"))
        render = gtk.CellRendererPixbuf()
        column.pack_start(render, False)
        column.add_attribute(render, "stock-id", 5)
        render = gtk.CellRendererText()
        column.pack_start(render, True)
        column.add_attribute(render, "text", 1)
        column.set_expand(True)
        self.listview_files.append_column(column)

        render = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Size"))
        column.pack_start(render)
        column.set_cell_data_func(render, listview.cell_data_size, 2)
        self.listview_files.append_column(column)
        
        self.listview_torrents.set_model(self.torrent_liststore)
        self.listview_files.set_model(self.files_treestore)

        self.listview_files.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        self.listview_torrents.get_selection().connect("changed", 
                                    self._on_torrent_changed)

        # Get default config values from the core
        self.core_keys = [
            "compact_allocation",
            "max_connections_per_torrent",
            "max_upload_slots_per_torrent",
            "max_upload_speed_per_torrent",
            "max_download_speed_per_torrent",
            "prioritize_first_last_pieces",
            "download_location",
            "add_paused"
        ]
        self.core_config = {}
            
    def start(self):
        self.update_core_config()
        
    def show(self, focus=False):
        self.update_core_config()

        if client.is_localhost():
            self.glade.get_widget("button_location").show()
            self.glade.get_widget("entry_download_path").hide()
        else:
            self.glade.get_widget("button_location").hide()
            self.glade.get_widget("entry_download_path").show()       
        
        self.dialog.set_transient_for(component.get("MainWindow").window)  
        self.dialog.present()
        if focus:
            self.dialog.window.focus()
        
        return None
    
    def hide(self):
        self.dialog.hide()
        self.files = {}
        self.infos = {}
        self.options = {}
        self.previous_selected_torrent = None
        self.torrent_liststore.clear()
        self.files_treestore.clear()
        self.dialog.set_transient_for(component.get("MainWindow").window)    
        return None
    
    def update_core_config(self):
        self.core_config = {}
        # Send requests to the core for these config values
        for key in self.core_keys:
            client.get_config_value(self._on_config_value, key)

        # Force a call to the core because we need this data now
        client.force_call()
        self.set_default_options()
                
    def _on_config_value(self, value):
        for key in self.core_keys:
            if not self.core_config.has_key(key):
                self.core_config[key] = value
                break
                
    def add_from_files(self, filenames):
        import deluge.libtorrent as lt
        import os.path
        new_row = None
        
        for filename in filenames:
            # Get the torrent data from the torrent file
            try:
                log.debug("Attempting to open %s for add.", filename)
                _file = open(filename, "rb")
                filedump = _file.read()
                if not filedump:
                    log.warning("Torrent appears to be corrupt!")
                    continue
                filedump = lt.bdecode(filedump)
                _file.close()
            except Exception, e:
                log.warning("Unable to open %s: %s", filename, e)
                continue

            try:
                info = lt.torrent_info(filedump)
            except RuntimeError, e:
                log.warning("Torrent appears to be corrupt!")
                continue

            if str(info.info_hash()) in self.infos:
                log.debug("Torrent already in list!")
                continue
                
            # Get list of files from torrent info
            files = []
            for f in info.files():
                files.append({
                    'path': f.path,
                    'size': f.size,
                    'download': True
                })

            name = "%s (%s)" % (info.name(), os.path.split(filename)[-1])
            new_row = self.torrent_liststore.append(
                [str(info.info_hash()), name, filename])
            self.files[str(info.info_hash())] = files
            self.infos[str(info.info_hash())] = info

        (model, row) = self.listview_torrents.get_selection().get_selected()
        if not row and new_row:
            self.listview_torrents.get_selection().select_iter(new_row)
               
    def _on_torrent_changed(self, treeselection):
        (model, row) = treeselection.get_selected()
        self.files_treestore.clear()
        
        if row is None:
            return
        
        # Update files list    
        files_list = self.files[model.get_value(row, 0)]

        self.prepare_file_store(files_list)

        if self.core_config == {}:
            self.update_core_config()
            
        # Save the previous torrents options
        self.save_torrent_options()
        # Update the options frame
        self.update_torrent_options(model.get_value(row, 0))

        self.previous_selected_torrent = row

    def prepare_file_store(self, files):
        split_files = { }
        i = 0
        for file in files:
            self.prepare_file(file, file["path"], i, split_files)
            i += 1
        self.add_files(None, split_files)

    def prepare_file(self, file, file_name, file_num, files_storage):
        first_slash_index = file_name.find("/")
        if first_slash_index == -1:
            files_storage[file_name] = (file_num, file)
        else:
            file_name_chunk = file_name[:first_slash_index+1]
            if file_name_chunk not in files_storage:
                files_storage[file_name_chunk] = { }
            self.prepare_file(file, file_name[first_slash_index+1:],
                              file_num, files_storage[file_name_chunk])

    def add_files(self, parent_iter, split_files):
        ret = 0
        for key,value in split_files.iteritems():
            if key.endswith("/"):
                chunk_iter = self.files_treestore.append(parent_iter,
                                [True, key, 0, -1, False, gtk.STOCK_DIRECTORY])
                chunk_size = self.add_files(chunk_iter, value)
                self.files_treestore.set(chunk_iter, 2, chunk_size)
                ret += chunk_size
            else:
                self.files_treestore.append(parent_iter, [True, key,
                                        value[1]["size"], value[0], False, gtk.STOCK_FILE])
                ret += value[1]["size"]
        return ret

    def update_torrent_options(self, torrent_id):
        if torrent_id not in self.options:
            self.set_default_options()
            return
        
        options = self.options[torrent_id]
        
        if client.is_localhost():
            self.glade.get_widget("button_location").set_current_folder(
                options["download_location"])
        else:
            self.glade.get_widget("entry_download_path").set_text(
                options["download_location"])
                
        self.glade.get_widget("radio_compact").set_active(
            options["compact_allocation"])
        self.glade.get_widget("spin_maxdown").set_value(
            options["max_download_speed_per_torrent"])
        self.glade.get_widget("spin_maxup").set_value(
            options["max_upload_speed_per_torrent"])
        self.glade.get_widget("spin_maxconnections").set_value(
            options["max_connections_per_torrent"])
        self.glade.get_widget("spin_maxupslots").set_value(
            options["max_upload_slots_per_torrent"])
        self.glade.get_widget("chk_paused").set_active(
            options["add_paused"])
        self.glade.get_widget("chk_prioritize").set_active(
            options["prioritize_first_last_pieces"])
            
    def save_torrent_options(self, row=None):
        # Keeps the torrent options dictionary up-to-date with what the user has
        # selected.
        if row is None:
            row = self.previous_selected_torrent
        if row is None or not self.torrent_liststore.iter_is_valid(row):
            return
            
        torrent_id = self.torrent_liststore.get_value(row, 0)
 
        options = {}       
        if client.is_localhost():
            options["download_location"] = \
                self.glade.get_widget("button_location").get_current_folder()
        else:
            options["download_location"] = \
                self.glade.get_widget("entry_download_path").get_text()
        options["compact_allocation"] = \
            self.glade.get_widget("radio_compact").get_active()
        options["max_download_speed_per_torrent"] = \
            self.glade.get_widget("spin_maxdown").get_value()
        options["max_upload_speed_per_torrent"] = \
            self.glade.get_widget("spin_maxup").get_value()
        options["max_connections_per_torrent"] = \
            self.glade.get_widget("spin_maxconnections").get_value_as_int()
        options["max_upload_slots_per_torrent"] = \
            self.glade.get_widget("spin_maxupslots").get_value_as_int()
        options["add_paused"] = \
            self.glade.get_widget("chk_paused").get_active()
        options["prioritize_first_last_pieces"] = \
            self.glade.get_widget("chk_prioritize").get_active()
        options["default_private"] = \
            self.glade.get_widget("chk_private").get_active()
            
        self.options[torrent_id] = options
        
        # Save the file priorities
        files_priorities = self.build_priorities(
                            self.files_treestore.get_iter_first(), {})
        
        for i, file_dict in enumerate(self.files[torrent_id]):
            file_dict["download"] = files_priorities[i]
        
    def build_priorities(self, iter, priorities):
        while iter is not None:
            if self.files_treestore.iter_has_child(iter):
                self.build_priorities(self.files_treestore.iter_children(iter),
                                          priorities)
            elif not self.files_treestore.get_value(iter, 1).endswith("/"):
                priorities[self.files_treestore.get_value(iter, 3)] = self.files_treestore.get_value(iter, 0)
            iter = self.files_treestore.iter_next(iter)
        return priorities

    def set_default_options(self):
        if client.is_localhost():
            self.glade.get_widget("button_location").set_current_folder(
                self.core_config["download_location"])
        else:
            self.glade.get_widget("entry_download_path").set_text(
                self.core_config["download_location"])
               
        self.glade.get_widget("radio_compact").set_active(
            self.core_config["compact_allocation"])
        self.glade.get_widget("spin_maxdown").set_value(
            self.core_config["max_download_speed_per_torrent"])
        self.glade.get_widget("spin_maxup").set_value(
            self.core_config["max_upload_speed_per_torrent"])
        self.glade.get_widget("spin_maxconnections").set_value(
            self.core_config["max_connections_per_torrent"])
        self.glade.get_widget("spin_maxupslots").set_value(
            self.core_config["max_upload_slots_per_torrent"])
        self.glade.get_widget("chk_paused").set_active(
            self.core_config["add_paused"])
        self.glade.get_widget("chk_prioritize").set_active(
            self.core_config["prioritize_first_last_pieces"])
    
    def get_file_priorities(self, torrent_id):
        # A list of priorities
        files_list = []

        for file_dict in self.files[torrent_id]:
            if file_dict["download"] == False:
                files_list.append(0)
            else:
                files_list.append(1)
        
        return files_list
        
    def _on_file_toggled(self, render, path):
        (model, paths) = self.listview_files.get_selection().get_selected_rows()
        if len(paths) > 1:
            for path in paths:
                row = model.get_iter(path)
                self.toggle_iter(row)
        else:
            row = model.get_iter(path)
            self.toggle_iter(row)
        self.update_treeview_toggles(self.files_treestore.get_iter_first())

    def toggle_iter(self, iter, toggle_to=None):
        if toggle_to is None:
            toggle_to = not self.files_treestore.get_value(iter, 0)
        self.files_treestore.set_value(iter, 0, toggle_to)
        if self.files_treestore.iter_has_child(iter):
            child = self.files_treestore.iter_children(iter)
            while child is not None:
                self.toggle_iter(child, toggle_to)
                child = self.files_treestore.iter_next(child)

    def update_treeview_toggles(self, iter):
        TOGGLE_INCONSISTENT = -1
        this_level_toggle = None
        while iter is not None:
            if self.files_treestore.iter_has_child(iter):
                toggle = self.update_treeview_toggles(
                        self.files_treestore.iter_children(iter))
                if toggle == TOGGLE_INCONSISTENT:
                    self.files_treestore.set_value(iter, 4, True)
                else:
                    self.files_treestore.set_value(iter, 0, toggle)
                    #set inconsistent to false
                    self.files_treestore.set_value(iter, 4, False)
            else:
                toggle = self.files_treestore.get_value(iter, 0)
            if this_level_toggle is None:
                this_level_toggle = toggle
            elif this_level_toggle != toggle:
                this_level_toggle = TOGGLE_INCONSISTENT
            iter = self.files_treestore.iter_next(iter)
        return this_level_toggle

    def _on_button_file_clicked(self, widget):
        log.debug("_on_button_file_clicked")
        # Setup the filechooserdialog
        chooser = gtk.FileChooserDialog(_("Choose a .torrent file"),
            None,
            gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, 
                        gtk.RESPONSE_OK))

        chooser.set_transient_for(self.dialog)
        chooser.set_select_multiple(True)
        chooser.set_property("skip-taskbar-hint", True)
        
        # Add .torrent and * file filters
        file_filter = gtk.FileFilter()
        file_filter.set_name(_("Torrent files"))
        file_filter.add_pattern("*." + "torrent")
        chooser.add_filter(file_filter)
        file_filter = gtk.FileFilter()
        file_filter.set_name(_("All files"))
        file_filter.add_pattern("*")
        chooser.add_filter(file_filter)

        # Load the 'default_load_path' from the config
        self.config = ConfigManager("gtkui.conf")
        if self.config.get("default_load_path") is not None:
            chooser.set_current_folder(self.config.get("default_load_path"))

        # Run the dialog
        response = chooser.run()

        if response == gtk.RESPONSE_OK:
            result = chooser.get_filenames()
            self.config.set("default_load_path", chooser.get_current_folder())
        else:
            chooser.destroy()
            return

        chooser.destroy()
        self.add_from_files(result)
                                        
    def _on_button_url_clicked(self, widget):
        log.debug("_on_button_url_clicked")
        dialog = self.glade.get_widget("url_dialog")
        entry = self.glade.get_widget("entry_url")

        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_transient_for(self.dialog)
        entry.grab_focus()
        
        if deluge.common.windows_check():
            import win32clipboard as clip 
            import win32con
            clip.OpenClipboard() 
            text = clip.GetClipboardData(win32con.CF_UNICODETEXT) 
            clip.CloseClipboard() 
        else:
            clip = gtk.clipboard_get(selection='PRIMARY')
            text = clip.wait_for_text()
        if text:
            text = text.strip()
            if deluge.common.is_url(text):
                entry.set_text(text)

        dialog.show_all()
        response = dialog.run()

        if response == gtk.RESPONSE_OK:
            url = entry.get_text().decode("utf_8")
        else:
            url = None

        # This is where we need to fetch the .torrent file from the URL and
        # add it to the list.
        log.debug("url: %s", url)
        if url != None:
            self.add_from_url(url)
        
        entry.set_text("")
        dialog.hide()

    def add_from_url(self, url):
        gobject.idle_add(self._download_from_url, url)

    def _download_from_url(self, url):
        import urllib
        import tempfile
        import os.path
        tmp_file = os.path.join(tempfile.gettempdir(), url.split("/")[-1])
        filename, headers = urllib.urlretrieve(url, tmp_file)
        log.debug("filename: %s", filename)
        self.add_from_files([filename])
    
    def _on_button_hash_clicked(self, widget):
        log.debug("_on_button_hash_clicked")

    def _on_button_remove_clicked(self, widget):
        log.debug("_on_button_remove_clicked")
        (model, row) = self.listview_torrents.get_selection().get_selected()
        if row is None:
            return
            
        torrent_id = model.get_value(row, 0)
        
        model.remove(row)
        del self.files[torrent_id]
        del self.infos[torrent_id]

    def _on_button_trackers_clicked(self, widget):
        log.debug("_on_button_trackers_clicked")

    def _on_button_cancel_clicked(self, widget):
        log.debug("_on_button_cancel_clicked")
        self.hide()

    def _on_button_add_clicked(self, widget):
        log.debug("_on_button_add_clicked")
        # Save the options for selected torrent prior to adding
        (model, row) = self.listview_torrents.get_selection().get_selected()
        if row is not None:
            self.save_torrent_options(row)

        torrent_filenames = []
        torrent_options = []
        
        row = self.torrent_liststore.get_iter_first()
        while row != None:
            torrent_id = self.torrent_liststore.get_value(row, 0)
            filename = self.torrent_liststore.get_value(row, 2)
            try:
                options = self.options[torrent_id]
            except:
                options = None
            
            file_priorities = self.get_file_priorities(torrent_id)
            if options != None:
                options["file_priorities"] = file_priorities
                
            torrent_filenames.append(filename)
            torrent_options.append(options)
            
            row = self.torrent_liststore.iter_next(row)
            
        client.add_torrent_file(torrent_filenames, torrent_options)
        client.force_call()
        self.hide()

    def _on_button_apply_clicked(self, widget):
        log.debug("_on_button_apply_clicked")
        (model, row) = self.listview_torrents.get_selection().get_selected()
        if row is None:
            return
        
        self.save_torrent_options(row)
        
        # The options we want all the torrents to have
        options = self.options[model.get_value(row, 0)]
        
        # Set all the torrent options
        row = model.get_iter_first()
        while row != None:
            torrent_id = model.get_value(row, 0)
            self.options[torrent_id] = options
            row = model.iter_next(row)
            
    def _on_button_revert_clicked(self, widget):
        log.debug("_on_button_revert_clicked")
        (model, row) = self.listview_torrents.get_selection().get_selected()
        if row is None:
            return
        
        del self.options[model.get_value(row, 0)]
        self.set_default_options()
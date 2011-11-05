#!/usr/bin/env python2

import os
import sys

from datetime import datetime
from random import choice
import time

import pygtk
pygtk.require('2.0')

import gtk
import gobject

from WallpaperClock import WallpaperClock

# redraw rate, in 0.001 seconds
FRAME_REFRESH_RATE = 50
# theme change rate, in second
THEME_CHANGE_RATE = float(os.environ.get('WC_THEME_CHANGE_RATE') or 5.0)
# theme change during, in second
THEME_CHANGE_DURING = float(os.environ.get('WC_THEME_CHANGE_DURING') or 2.0)

class WallpaperClockDesktop(gtk.Window):
    clock = None                 # WallpaperClock object
    wcz_filenames = None         # list of wcz filenames
    wcz_filename = None          # current wcz filename
    frame  = None                # frame of the background image
    background = None            # background-pixbuf
    screen = None                # screen
    timer = None
    last_minute = None
    theme_used_since = None      # theme is used since
    edge_frame = None            # current frame (used when switching theme)
    edge_frame_alpha = None      # original frame alpha in current frame
    dirty = False                # pending redraw to screen ?

    def __init__(self, parent = None, filename = None):
        # create window
        gtk.Window.__init__(self)

        # set window properties
        self.set_keep_below(True)
        self.set_decorated(False)
        self.set_focus(None)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DESKTOP)
        self.set_resizable(False)
        self.set_gravity(gtk.gdk.GRAVITY_STATIC)

        # read wcz file list
        self.wcz_filenames = sys.argv[1:]
        if len(self.wcz_filenames) == 0:
            self.wcz_filenames = [ i for i in os.listdir('.') if i.lower().endswith('.wcz') ]
            print('Using wcz files in current directory: %d item(s)' % len(self.wcz_filenames))

        if len(self.wcz_filenames) == 0:
            sys.exit('No wcz file found, exiting...')

        if len(self.wcz_filenames) == 1:
            THEME_CHANGE_RATE = 1e100 # that's a very long time

        try:
            self.set_screen(parent.get_screen())
        except AttributeError:
            self.connect("destroy", lambda *w: gtk.main_quit())

        self.connect("destroy", self.cleanup_callback)
        self.set_title(self.__class__.__name__)

        # pick one wcz file and extract it to cache path and load background
        self.pick_wcz_file()
        self.edge_frame = None
        self.timeout()

        # add drawing area and refresh timer
        da = gtk.DrawingArea()
        da.connect("expose_event", self.expose_cb)

        self.add(da)
        self.timer = gobject.timeout_add(FRAME_REFRESH_RATE, self.timeout)

        # show all
        self.show_all()

    def pick_wcz_file(self):
        # no enough themes to change?
        if len(self.wcz_filenames) < 2 and self.clock is not None:
            return

        last_wcz_filename = self.wcz_filename
        while last_wcz_filename == self.wcz_filename:
           self.wcz_filename = choice(self.wcz_filenames)

        # reinitialize WallpaperClock object
        self.clock = WallpaperClock(self.wcz_filename)

        # get name from wallpaper clock ini configure file
        try:
            name = self.clock.get_information()['Settings']['name'].split('\r')[0]
        except:
            name = '<unknown name>'

        print("Using: %s (%s)" % (name, self.wcz_filename))

        if not self.load_background():
            sys.exit('Failed to load background, exiting...')
        else:
            # resize window
            background_size = self.background.get_width(), self.background.get_height()
            self.set_size_request(background_size[0], background_size[1])

            # create frame, copy background to frame
            if self.frame is None:
                self.frame = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8,
                    background_size[0], background_size[1])

            # force timeout() to redraw (to new edge_frame)
            self.last_minute = -1

            # redirect drawing from self.frame to self.edge_frame
            self.edge_frame_alpha = 0.0
            self.edge_frame = self.background.copy()
            self.theme_used_since = time.time()

    def composite_zoomed_file(self, filename, frame = None, alpha = 255):
        ''' Crop and resize a pixbuf according to frame size.
            Then draw it on frame (self.frame by default).
        '''

        # default frame
        if frame is None:
            frame = self.frame

        # skip if no filename provided
        if filename is None:
            return

        pixbuf = gtk.gdk.pixbuf_new_from_file(filename)
        data = None
        pix_size = pixbuf.get_width(), pixbuf.get_height()
        frame_size = frame.get_width(), frame.get_height()
        ratio = max([ 1.0 * frame_size[i] / pix_size[i] for i in range(2) ])
        crop_offset = [ (frame_size[i] - pix_size[i] * ratio) / 2 for i in range(2) ]

        # crop, scale and draw on self.frame
        pixbuf.composite(frame,
            0, 0, frame_size[0], frame_size[1],
            crop_offset[0], crop_offset[1], ratio, ratio,
            gtk.gdk.INTERP_BILINEAR, alpha)

        pixbuf = None

    def load_background(self):
        ''' Loads the images for the demo and returns whether the
            operation succeeded.
        '''

        # load wallpaper clock background
        try:
            self.screen = gtk.gdk.screen_get_default()
            self.background = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8,
                self.screen.get_width(), self.screen.get_height())
            self.composite_zoomed_file(self.clock.get_path('bg.jpg'), self.background)

        except gobject.GError, error:
           return False

        return True

    def expose_cb(self, draw_area, event):
        ''' Expose callback for the drawing area. '''

        rowstride = self.frame.get_rowstride()
        pixels = self.frame.get_pixels()

        draw_area.window.draw_rgb_image(
            draw_area.style.black_gc,
            event.area.x, event.area.y,
            event.area.width, event.area.height,
            'normal',
            pixels, rowstride,
            event.area.x, event.area.y)

        self.dirty = False

        return True

    def cleanup_callback(self, win):
        if self.timer is not None:
            gobject.source_remove(self.timer)
            self.timer = None

    def timeout(self):
        ''' Check if we need regenerate the frame. '''

        # if there is a unfinished drawing, do nothing
        if self.dirty:
            return True

        now = datetime.today()
        drawed = False

        # need to load new theme?
        if time.time() - self.theme_used_since > THEME_CHANGE_RATE :
            self.pick_wcz_file()

        if self.last_minute != now.minute :
            # need redraw
            self.last_minute = now.minute

            # decide draw dest
            # if current switching theme, not draw to frame directly but draw to 'edge_frame'
            dest = self.edge_frame or self.frame

            # clean self.frame to background
            self.background.copy_area(0, 0,
                self.background.get_width(), self.background.get_height(),
                dest, 0, 0)

            # draw month, day, hour, minute, weekday, etc.
            for filename in self.clock.get_image_filenames(now) :
                self.composite_zoomed_file(self.clock.get_path(filename), dest)

            self.composite_zoomed_file(self.clock.get_path("%s.png" % ("am" if now.hour < 12 else "pm")), dest)

            drawed = True

        # mix with edge_frame
        if self.edge_frame is not None:
            # dest alpha for edge_frame (from 0 to 1)
            dest_alpha = (time.time() - self.theme_used_since) / THEME_CHANGE_DURING

            if dest_alpha > 0.0 and dest_alpha < 1.0:
                # current_alpha, need_alpha, dest_alpha are in (0..1)
                # (1 - current)*need + current == dest
                # need = (current - dest) / (current - 1)
                need_alpha = int((dest_alpha - self.edge_frame_alpha) / (1.0 - self.edge_frame_alpha) * 255)
                if need_alpha > 0 and need_alpha < 255:
                    self.edge_frame.composite(self.frame,
                                              0, 0, self.frame.get_width(), self.frame.get_height(),
                                              0, 0, 1, 1,
                                              gtk.gdk.INTERP_NEAREST, need_alpha)
                    self.edge_frame_alpha = dest_alpha
                    drawed = True

            # not drawed but has edge_frame, copy edge_frame to frame
            if not drawed:
                self.edge_frame.copy_area(0, 0,
                    self.edge_frame.get_width(), self.edge_frame.get_height(),
                    self.frame, 0, 0)
                self.edge_frame = None
                drawed = True

        # refresh
        if drawed:
            self.dirty = True
            self.queue_draw()

        return True

def main():
    WallpaperClockDesktop(None, sys.argv[0])
    gtk.main()

if __name__ == '__main__':
    main()

# vim: set expandtab tabstop=4 autoindent shiftwidth=4:

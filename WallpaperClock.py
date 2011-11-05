import os
from hashlib import md5
from ConfigParser import RawConfigParser
from zipfile import ZipFile
from datetime import datetime

XDG_CACHE_HOME = os.environ.get('XDG_CACHE_HOME') or os.environ.get('HOME') + '/.cache'

class WallpaperClock(object):
    """ Wallpaper Clock (wcz) file wrapper """
    wcz_filename = None
    wcz_mtime = None
    cache_path = None
    information = None
    hour_images = None
    image_list = None

    def __init__(self, filename, extract_all = True):
        self.wcz_filename = filename
        self.wcz_mtime = os.path.getmtime(filename)

        # construct cache_path using XDG_CACHE_HOME and file md5
        checksum = md5()
        with open(filename, 'rb') as f:
            for chunk in iter(lambda: f.read(2 ** 19), ''):
                checksum.update(chunk)
        self.cache_path = XDG_CACHE_HOME + "/wallpaper_clock/" + checksum.hexdigest()

        # set hour_images (it may be 24 or 60)
        try :
            self.hour_images = int(self.get_information()['Settings'].get('hourimages') or 24)
        except :
            self.hour_images = 24

        # extract files, fill self.image_list
        self.extract(None if extract_all else '')

    def get_image_filenames(self, time = None) :
        ''' Get image filenames (basename) that should be used at specified time '''

        if time is None :
            time = datetime.today()

        # decide hour image index
        if self.hour_images == 24 :
            hour_index = time.hour
        else :
            hour_index = ((time.hour % 12) * 60 + time.minute) * self.hour_images / 720

        candidates = [ "%s%d.png" % (name, p) for name, p in [
                            ('month', time.month), ('day', time.day),
                            ('weekday', time.weekday() + 1), 
                            ('hour', hour_index),
                            ('minute', time.minute) ] ] \
                     + [ "%s.png" % ( 'am' if time.hour < 12 else 'pm' ) ]

        # filter according to image_list
        candidates = [ x for x in candidates if x in self.image_list ]

        # try to make sure file exists
        for filename in candidates :
            if not os.path.isfile(self.get_path(filename)):
                self.extract(filename)

        return candidates

    def extract(self, filename = None):
        ''' Extract files or a single file from wcz to cache '''
        path = self.cache_path

        if not os.path.isdir(path):
            os.makedirs(path)

        with ZipFile(self.wcz_filename) as wcz:
            filelist = wcz.namelist()
            self.image_list = [ x for x in filelist if x.endswith('.png') ]

            if filename is None :
                # extract all

                for i in [ 'bg.jpg', 'am.png', 'pm.png', 'clock.ini' ]:
                    # since md5 is used, no mtime compare here:
                    #   os.path.getmtime(path + '/' + i) < self.wcz_mtime):
                    if (i in filelist) and (not os.path.isfile(path + '/' + i)):
                        wcz.extract(i, path)

                for name, start, length in [ ('minute', 0, 60), ('hour', 0, self.hour_images), 
                                          ('month', 1, 12), ('weekday', 1, 7),
                                          ('day', 1, 31) ]:
                    for j in xrange(start, start + length):
                        filename = (name + '%d.png') % j
                        if (filename in filelist) and (not os.path.isfile(path + '/' + filename)):
                            wcz.extract(filename, path)
            else :
                # extract filename
                if (filename in filelist) and (not os.path.isfile(path + '/' + filename)) :
                    wcz.extract(filename, path)


    def get_path(self, content):
        ''' Get full cache file path from single filename such as am.png '''
        path = self.cache_path + ("/%s" % content) 

        if not os.path.isfile(path):
            self.extract(content)

        if not os.path.isfile(path):
            return None
        else:
            return path

    def get_information(self):
        ''' Get information from config file, clock.ini '''
        if self.information is None :
            config_file = 'clock.ini'
            path = self.cache_path + '/' + config_file

            if not os.path.isfile(path):
                self.extract(config_file)

            if os.path.isfile(path):
                config = RawConfigParser()
                config.read(path)
                self.information = { i: { k: v for k, v in config.items(i) } for i in config.sections() }

        return self.information
 
# vim: set expandtab tabstop=4 autoindent shiftwidth=4: 
    

from datetime import datetime
from os import scandir, listdir
from os.path import isfile, isdir, relpath, join, getsize
import os


MODELS_DIR = "models"


class Scaner(object):
    def __init__(self, path):
        self.entries = [Entry(entry) for entry in scandir(path.encode()) if '.tar.gz' in entry.path.decode()]
        # a = list(map(lambda p: (p.path, p.modified_time), sorted(self.entries, key=lambda e:
        # e.modified_time, reverse=True)))
        # print(a)
        self.latest_entry = next(iter(sorted(self.entries, key=lambda e: e.modified_time, reverse=True)), None)


class Entry(object):
    def __init__(self, entry):
        self.name = entry.name.decode()
        self.path = entry.path.decode()
        self.rel_path = relpath(self.path, MODELS_DIR)
        self.is_dir = entry.is_dir()
        self.created_time = datetime.fromtimestamp(entry.stat().st_ctime).ctime()
        # self.modified_time = datetime.fromtimestamp(entry.stat().st_mtime).ctime()
        self.modified_time = os.path.getmtime(self.path)
        self.size = self._human_readable_size(self._get_size(entry.path))

    def _get_size(self, path):
        total_size = getsize(path)
        if isdir(path):
            for item in listdir(path):
                item_path = join(path, item)
                if isfile(item_path):
                    total_size += getsize(item_path)
                elif isdir(item_path):
                    total_size += self._get_size(item_path)
        return total_size

    @staticmethod
    def _human_readable_size(size):
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        human_fmt = '{0:.2f} {1}'
        human_radix = 1024.

        for unit in units[:-1]:
            if size < human_radix:
                return human_fmt.format(size, unit)
            size /= human_radix

        return human_fmt.format(size, units[-1])


if __name__ == "__main__":
    real_path = MODELS_DIR
    latest_entry = Scaner(real_path).latest_entry
    print(latest_entry.path)
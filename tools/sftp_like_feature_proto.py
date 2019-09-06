# coding: utf-8

from fs.osfs import OSFS

home_fs = OSFS("~/")
#print(home_fs.listdir("/"))
#print(home_fs.tree(max_levels = 0, dirs_first = True))
dir_obj_infos = home_fs.scandir("/")
for info in dir_obj_infos:
    if info.is_dir:
        print("[dir]  {}".format(info.name))
    else:
        print("[file] {}".format(info.name))

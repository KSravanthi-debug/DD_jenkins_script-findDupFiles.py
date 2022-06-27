# DD_jenkins_script-findDupFiles.py

""" Produce a list of file that are exactly the same.

TODO 
2. yield iterators - save memory
5. Multiple directories on the command line
"""

import sys
import types

import pathlib
from pathlib import Path
import hashlib
import os
import logging
import time
import psutil
import shelve
import json
from collections import deque

SHA256_SIZE = 64           # 256 bits = 64 bytes
BLOCKSIZE = 65536


dir_stack = []         # list of directory names that prepend the file name
file_nodes_dict = {}   # key = hash: str, value list[file_name : str]


def hash_and_save(item: Path, dir_index: int, cache: bool = True) -> None:
    """ Hash the file contents and save the hash value and file name prefixed with a directory name 
        a key (hash), value list[ file_directory_number_key/filename , file_directory_number_key/filename ...] 
    """
    logging.debug(item.name)
    file_size = os.path.getsize(item)
    if file_size <= SHA256_SIZE:     # If the file is smaller than the hash - save the entire file as the key
        try:
            with open(item, 'r') as afile:
                digest = afile.read()
        except:
            return
    else:
        hasher = hashlib.sha256()
        try:
            with open(item, 'rb') as afile:
                # Do not block it if size < blocksize
                if file_size >= BLOCKSIZE:
                    buf = afile.read(BLOCKSIZE)
                    while len(buf) > 0:
                        hasher.update(buf)
                        buf = afile.read(BLOCKSIZE)
                else:
                    buf = afile.read()
                    hasher.update(buf)
            digest = hasher.hexdigest()
        except:
            return

    # prepend the file name with its compressed path
    file_name = str(dir_index) + '/' + item.name

    if digest in file_nodes_dict:
        #logging.debug('Found matching digest value: ', file_nodes[digest])
        if cache:                                  # spill to shelve
            file_list = file_nodes_dict[digest]
            file_list.append(file_name)
            file_nodes_dict[digest] = file_list
        else:                                      # In memory or writeback=True for the shelve
            file_list = file_nodes_dict[digest]
            file_list.append(file_name)
    else:
        file_list = [file_name]
        file_nodes_dict[digest] = file_list


def count_files(path: Path) -> int:
    """ Count the total number of files to process.
    """
    return sum(len(files) for _, _, files in os.walk(path))


def traverse_dir(path: Path, cache: bool = True) -> None:
    """ Traverse the contents of a directory, iteratively hash files, recurse for a directory
    """
    files_in_path = path.iterdir()
    dir_stack.append(os.path.join(path))  # TODO Compress the string?
    at = len(dir_stack) - 1               # location of directory
    try:
        for item in files_in_path:
            if item.is_dir():
                #logging.debug('Directory: ', item.name)
                traverse_dir(item, cache)
            elif item.is_file():
                #logging.debug('File: ', item.name)
                hash_and_save(item, at, cache)
            else:
                pass
    except (OSError, PermissionError):
        pass


def cache_dict(files: int) -> bool:
    """ Determine whether or not to cache the dictionary
    """
    mem = dict(psutil.virtual_memory()._asdict())
    if mem['free'] > (files * SHA256_SIZE):
        return True
    else:
        return False


if __name__ == '__main__':
    print('Number of arguments:', len(sys.argv), 'arguments.')
    print('Argument List:', str(sys.argv))
    logging.basicConfig(level=logging.DEBUG)
    # logging.basicConfig(format='%(process)d-%(levelname)s-%(message)s')
    dirname = sys.argv[1]
    path = pathlib.Path(dirname)
    start = time.time()
    #number_of_files = count_files(path)
    number_of_files = 20
    print(time.time() - start)
    if cache_dict(number_of_files):
        with shelve.open('__dict_cache') as file_nodes_dict:       # Persist the dict
            traverse_dir(path, True)
    else:
        traverse_dir(path, False)

    # Iterate through the keys, copy any to output with >= 2 files, and replace the paths
    final_dict = {}
    for file_hash_key in file_nodes_dict.keys():
        if len(file_nodes_dict[file_hash_key]) >= 2:
            file_name_list = []
            for file_name in file_nodes_dict[file_hash_key]:
                file_paths = file_name.split('/')               # Split off the number index
                directory_name = dir_stack[int(file_paths[0])]  # Look up the directory name
                file_name = directory_name + '/' + file_paths[1]
                file_name_list.append(file_name)
                # Put this back in a new dict?
            final_dict.update({file_hash_key : file_name_list})

    with open('output.json', 'w') as fout:
        json.dump(final_dict, fout)

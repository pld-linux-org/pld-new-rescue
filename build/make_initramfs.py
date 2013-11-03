#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import errno

from glob import glob

KERNEL_MOD_RE = re.compile("^lib/modules/([^/]*)/(.*\.ko(?:\.gz)?)$")

#   libc.so.6 => /lib/libc.so.6 (0xb7544000)
LD_LIST_RE = re.compile("^\s*\S+\s*=>\s*(\S+)\s*\(.*")

modules_dep = {}

def load_modules_dep(kernel_ver):
    if kernel_ver in modules_dep:
        return modules_dep[kernel_ver]
    modules_dep_fn = os.path.join("lib/modules", kernel_ver, "modules.dep")
    deps = {}
    with open(modules_dep_fn, "rt") as modules_dep_f:
        for line in modules_dep_f:
            module, mod_deps = line.split(":")
            mod_deps = mod_deps.split()
            deps[module] = mod_deps
    modules_dep[kernel_ver] = deps
    return deps

def find_kernel_mod_deps(kernel_ver, mod_path):
    print("find_kernel_mod_deps({0!r}, {1!r})".format(kernel_ver, mod_path))
    deps = load_modules_dep(kernel_ver)
    result = []
    for path in deps[mod_path]:
        result.append("lib/modules/{0}/{1}".format(kernel_ver, path))
    return result

def find_executable_deps(path, root_dir):
    print("find_executable_deps({0!r})".format(path))
    with open(path, "rb") as exec_f:
        header = exec_f.read(1024)
    if header[:2] == b"#!":
        line = header.split(b"\n")[0].decode("utf-8")
        interpreter = line[2:].split()[0]
        return [interpreter.lstrip("/")]

    try:
        output = subprocess.check_output(
                        ["chroot", root_dir, "/lib/ld-linux.so.2",
                            "--list", "/" + path])
    except subprocess.CalledProcessError as err:
        print(err)
        return []

    result = ["lib/ld-linux.so.2"]
    target = os.readlink("lib/ld-linux.so.2")
    target = os.path.join("/lib", target)
    result.append(os.path.abspath(target).lstrip("/"))
    for line in output.decode("utf-8").split("\n"):
        match = LD_LIST_RE.match(line)
        if match:
            lib_path = match.group(1).lstrip("/")
            result.append(lib_path)
            if os.path.islink(lib_path):
                target = os.readlink(lib_path)
                target = os.path.join("/" + os.path.dirname(lib_path), target)
                result.append(os.path.abspath(target).lstrip("/"))
    return result

def find_deps(files, all_files, root_dir):
    present = set(all_files)
    unprocessed = list(files)
    while unprocessed:
        path = unprocessed.pop(0)
        dir_path = os.path.dirname(path)
        while dir_path:
            if dir_path not in present:
                present.add(dir_path)
                files.append(dir_path)
                all_files.append(dir_path)
                unprocessed.append(dir_path)
            dir_path = os.path.dirname(dir_path)
        present.add(path)
        try:
            path_stat = os.stat(path, follow_symlinks=False)
        except OSError as err:
            if err.errno == errno.ENOENT:
                continue
            raise
        if not stat.S_ISREG(path_stat.st_mode):
            continue
        match = KERNEL_MOD_RE.match(path)
        if match:
            deps = find_kernel_mod_deps(match.group(1), match.group(2))
        elif (stat.S_IMODE(path_stat.st_mode) & 0o111):
            deps = find_executable_deps(path, root_dir)
        else:
            continue
        print("deps={0!r}".format(deps))
        for dep_path in deps:
            if dep_path not in present:
                present.add(dep_path)
                files.append(dep_path)
                all_files.append(dep_path)
                unprocessed.append(dep_path)

def process_files_list(file_list_fn, gic_list_fn, skel_dir, root_dir):
    files = []
    globs = []
    with open(file_list_fn, "rt") as files_list:
        with open(gic_list_fn, "wt") as cpio_list:
            for line in files_list:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts[0] == "*" and len(parts) == 2:
                    globs.append(parts[1])
                elif len(parts) >= 5:
                    parts[2] = parts[2].replace("@skel@", skel_dir).replace(
                                                            "@root@", root_dir)
                    files.append(parts[1].lstrip("/"))
                    cpio_list.write(" ".join(parts) + "\n")
                else:
                    raise ValueError("Invalid files.list line: {0!r}"
                                                            .format(line))
    return files, globs

def expand_globs(globs):
    search_paths = []
    for pattern in globs:
        pattern = os.path.abspath("/" + pattern).lstrip("/")
        search_paths += glob(pattern)
    paths = subprocess.check_output(["find"] + search_paths + ["-print"])
    paths = [p.decode("utf-8") for p in paths.split(b"\n") if p]
    return paths

def cpio_append(cpio_fn, paths):
    cpio_p = subprocess.Popen(["cpio", "-o", "--append", "-H", "newc",
                                "-F", cpio_fn],
                              stdin=subprocess.PIPE)
    for path in paths:
        cpio_p.stdin.write(path.encode("utf-8"))
        cpio_p.stdin.write(b"\n")
    cpio_p.stdin.close()
    rc = cpio_p.wait()
    if rc:
        raise subprocess.CalledProcessError(rc, "cpio")

def main():
    parser = argparse.ArgumentParser(description="Make initramfs")
    args = parser.parse_args()

    skel_dir = os.path.abspath("../initramfs/skel")
    root_dir = os.path.abspath("root")
    init_cpio_fn = os.path.abspath("init.cpi")
    files_list_fn = os.path.abspath("../initramfs/files.list")
    gic_list_fn = os.path.abspath("gen_init_cpio.list")
    init_lst_fn = os.path.abspath("init.lst")
    
    os.chdir(root_dir)

    files, globs = process_files_list(files_list_fn, gic_list_fn,
                                      skel_dir, root_dir)
    subprocess.check_call(["gen_init_cpio", gic_list_fn],
                          stdout=open(init_cpio_fn, "wb"))

    paths = expand_globs(globs)
    files += paths

    find_deps(paths, files, root_dir)

    paths.sort()

    cpio_append(init_cpio_fn, paths)

    with open(init_lst_fn, "wt") as init_lst:
        for path in paths:
            print(path, file=init_lst)

    subprocess.check_call(["gzip", init_cpio_fn])
    os.rename(init_cpio_fn + ".gz", init_cpio_fn)

if __name__ == "__main__":
    main()

# vi: sts=4 sw=4 et

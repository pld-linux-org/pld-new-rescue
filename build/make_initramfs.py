#!/usr/bin/python3

import argparse
import sys
import os
import subprocess
import shutil
import re
import stat
import errno
import logging

from glob import glob

import pld_nr_buildconf

logger = logging.getLogger("make_initramfs")

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
    logger.debug("find_kernel_mod_deps({0!r}, {1!r})"
                                            .format(kernel_ver, mod_path))
    deps = load_modules_dep(kernel_ver)
    result = []
    for path in deps[mod_path]:
        result.append("lib/modules/{0}/{1}".format(kernel_ver, path))
    return result

def find_executable_deps(config, path, root_dir, bits):
    logger.debug("find_executable_deps({0!r})".format(path))
    if bits == 64:
        lib = "lib64"
        ld_linux = "/lib64/ld-linux-x86-64.so.2"
    else:
        lib = "lib"
        ld_linux = "/lib/ld-linux.so.2"
    if path.startswith("lib/ld-") or path.startswith("lib64/ld-"):
        logger.debug("Returning empty list for dynamic loader")
        return []
    with open(path, "rb") as exec_f:
        header = exec_f.read(1024)
    if header[:2] == b"#!":
        line = header.split(b"\n")[0].decode("utf-8")
        interpreter = line[2:].split()[0]
        return [interpreter.lstrip("/")]

    try:
        output = subprocess.check_output(config.c_sudo + [
                        "chroot", root_dir, ld_linux, "--list", "/" + path])
    except subprocess.CalledProcessError as err:
        logger.error(err)
        return []

    result = [ld_linux.lstrip("/")]
    target = os.readlink(ld_linux.lstrip("/"))
    target = os.path.join("/" + lib, target)
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

def find_deps(config, files, all_files, root_dir):
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
            deps = find_executable_deps(config, path, root_dir, config.bits)
        else:
            continue
        logger.debug("deps={0!r}".format(deps))
        for dep_path in deps:
            if dep_path not in present:
                present.add(dep_path)
                files.append(dep_path)
                all_files.append(dep_path)
                unprocessed.append(dep_path)

def process_files_list(config, file_list_fn, gic_list_fn, root_dir,
                                                            extra_files):
    if config.bits == 64:
        lib = "lib64"
    else:
        lib = "lib"
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
                    globs.append(parts[1].replace("@lib@", lib))
                elif len(parts) >= 5:
                    parts[2] = parts[2].replace("@root@", root_dir).replace(
                                                            "@lib@", lib)
                    files.append(parts[1].lstrip("/"))
                    cpio_list.write(" ".join(parts) + "\n")
                else:
                    raise ValueError("Invalid files.list line: {0!r}"
                                                            .format(line))
            for rule in extra_files:
                    cpio_list.write(rule + "\n")
    return files, globs

def expand_globs(config, globs):
    search_paths = []
    for pattern in globs:
        pattern = os.path.abspath("/" + pattern).lstrip("/")
        search_paths += glob(pattern)
    paths = subprocess.check_output(config.c_sudo + [
                                    "find"] + search_paths + ["-print"])
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
    log_parser = pld_nr_buildconf.get_logging_args_parser()
    parser = argparse.ArgumentParser(description="Make initramfs",
                                     parents=[log_parser])
    parser.add_argument("--out-list", metavar="FILE",
                        help="Save initramfs contents list to FILE")
    parser.add_argument("--substract-contents", metavar=("INFILE", "OUTFILE"),
                        nargs=2,
                        help="Read file list from INFILE, exclude contents"
                              " of this initramfs module and write to OUTFILE"),
    parser.add_argument("--exclude", metavar="FILE",
                        help="Do not include any files listed in FILE")
    parser.add_argument("name", metavar="NAME",
                        help="Name of the initramfs module."
                            " _NAME.cpi and _NAME.lst files will be written.")
    args = parser.parse_args()
    args = parser.parse_args()
    pld_nr_buildconf.setup_logging(args)
    
    config = pld_nr_buildconf.Config.get_config()

    skel_dir = os.path.abspath("../initramfs/{}.skel".format(args.name))
    root_dir = os.path.abspath("root")
    modules_dir = os.path.abspath("../modules")
    built_skel_dir = os.path.abspath("initramfs")
    out_cpio_fn = os.path.abspath("_{}.cpi".format(args.name))
    files_list_fn = os.path.abspath("../initramfs/{}.files".format(args.name))
    gic_list_fn = os.path.abspath("_{}.gen_init_cpio.list".format(args.name))
    out_lst_fn = os.path.abspath("_{0}.lst".format(args.name))
    if args.substract_contents:
        base_full_lst_fn = os.path.abspath(args.substract_contents[0])
        base_lst_fn = os.path.abspath(args.substract_contents[1])
    else:
        base_full_lst_fn = None
        base_lst_fn = None

    os.chdir(root_dir)

    extra_files = []
    if args.name == "init":
        logger.debug("Looking for module scripts")
        for module in config.modules:
            module_init_fn = os.path.join(modules_dir, module, "init.sh")
            logger.debug("  {}".format(module_init_fn))
            if os.path.exists(module_init_fn):
                logger.debug("    got it")
                extra_files.append("file /.rcd/modules/{}.init {} 0644 0 0"
                                                .format(module, module_init_fn))

    logger.debug("Completing file list")
    files, globs = process_files_list(config, files_list_fn, gic_list_fn,
                                                        root_dir, extra_files)
    subprocess.check_call(["gen_init_cpio", gic_list_fn],
                          stdout=open(out_cpio_fn, "wb"))

    paths = expand_globs(config, globs)
    files += paths

    find_deps(config, paths, files, root_dir)

    paths.sort()

    cpio_append(out_cpio_fn, paths)

    if os.path.exists(built_skel_dir):
        shutil.rmtree(built_skel_dir)
    os.makedirs(built_skel_dir)
    try:
        config.copy_template_dir(skel_dir, built_skel_dir)
        os.chdir(built_skel_dir)
        built_paths = []
        for dirpath, dirnames, filenames in os.walk("."):
            dirpath = dirpath[2:] # strip "./"
            for dirname in dirnames:
                path = os.path.join(dirpath, dirname)
                built_paths.append(path)
            for filename in filenames:
                path = os.path.join(dirpath, filename)
                built_paths.append(path)
        if os.path.exists("init"):
            os.chmod("init", 0o755)
        cpio_append(out_cpio_fn, built_paths)
    finally:
        os.chdir(root_dir)
        shutil.rmtree(built_skel_dir)

    with open(out_lst_fn, "wt") as init_lst:
        for path in sorted(set(paths) | set(files) | set(built_paths)):
            print(path, file=init_lst)

    os.chdir(os.path.dirname(out_lst_fn))
    cpio_append(out_cpio_fn, [os.path.basename(out_lst_fn)])

    if args.substract_contents:
        base_all_paths = set(l.rstrip() for l in
                                    open(base_full_lst_fn, "rt").readlines())
        base_paths = set(base_all_paths) - set(paths)

        with open(base_lst_fn, "wt") as base_lst:
            for path in base_paths:
                print(path, file=base_lst)

    logger.debug("compressing {0!r}".format(out_cpio_fn))
    subprocess.check_call(config.compress_cmd + ["-f", out_cpio_fn])
    compressed_fn = out_cpio_fn + config.compressed_ext
    logger.debug("renaming {0!r} to {1!r}".format(compressed_fn, out_cpio_fn))
    os.rename(compressed_fn, out_cpio_fn)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as err:
        logger.error(str(err))
        sys.exit(1)

# vi: sts=4 sw=4 et

#! /usr/bin/python3
## encoding: utf-8
#
# Copyright (c) 2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

"""Handle the creation of britney faux packages.

This program gets called from the "britney" script in order to append to the
Packages_<arch> files a list of faux packages. This is done with the "generate"
command, passing a list of britney suite directories:

  % fauxpkg.py generate /home/release/britney/var/data/{testing,unstable}

This automatically appeds to the Packages files the list of faux packages. See
the README file in this directory for the input files from which such list is
generated.
"""

import os
import re
import sys
import glob
import tempfile
import subprocess

from collections import defaultdict

import apt_pkg
apt_pkg.init()

##

BASEDIR = os.path.dirname(__file__)

NOREMOVE_DIR =  os.path.join(BASEDIR, 'noremove.d')
FAUX_PACKAGES = os.path.join(BASEDIR, 'FauxPackages')

DEFAULT_NOREMOVE_ARCH = 'amd64'

##

def main():
    if not sys.argv[1:]:
        print('Usage: %s <generate | update-tasksel> [ britney_suite_dir1 ... ]' % (
                os.path.basename(sys.argv[0])), file=sys.stderr)
        sys.exit(1)
    else:
        command = sys.argv.pop(1)

    if command == 'generate':
        if not sys.argv[1:]:
            print('E: need at least one britney suite directory', file=sys.stderr)
            sys.exit(1)
        else:
            do_generate(sys.argv[1:])
    elif command == 'update-tasksel':
        if sys.argv[1:]:
            print('E: extra arguments not allowed', file=sys.stderr)
            sys.exit(1)
        else:
            do_update_tasksel()
    else:
        print('E: unknown command %s' % (command,), file=sys.stderr)

##

def do_generate(directories):
    arches = set()
    allfaux = {}

    for dir_ in directories:
        arches.update([ re.sub(r'^.*/Packages_', '', x)
            for x in glob.glob(os.path.join(dir_, 'Packages_*')) ])

    unstable_versions = {}
    all_packages = defaultdict(set)
    for dir_ in directories:
        with open(os.path.join(dir_, 'Sources')) as f:
            parser = apt_pkg.TagFile(f)
            for section in parser:
                if 'Package' in section and 'Version' in section:
                    unstable_versions[section['Package']] = section['Version']
        for packages_file in glob.glob(os.path.join(dir_, 'Packages_*')):
            arch = re.sub(r'^.*/Packages_', '', packages_file)
            with open(packages_file, 'r') as f:
                with apt_pkg.TagFile(f) as tf:
                    for section in tf:
                        all_packages[arch] |= {section.get('Package')}

    # First, FauxPackages
    try:
        parser = apt_pkg.TagFile(open(FAUX_PACKAGES))
        step = parser.step
        section = parser.section
    except AttributeError as e:
        parser = apt_pkg.ParseTagFile(open(FAUX_PACKAGES))
        step = parser.Step
        section = parser.Section
    while step():
        d = dict(section)
        d['Section'] = 'faux' # crucial; britney filters HeidiResult based on section

        if 'Architecture' not in d:
            these_arches = arches
        else:
            these_arches = set(re.split(r'[, ]+', d['Architecture']))

        d['Architecture'] = 'all' # same everywhere

        if d.get('Version') == '${unstable-version}':
            source = d.get('Source', d.get('Package'))
            if source in unstable_versions:
                d['Version'] = unstable_versions[source]

        for arch in these_arches:
            allfaux.setdefault(arch, []).append(d)

    # Now, noremove.d
    for f in glob.glob(os.path.join(NOREMOVE_DIR, '*.list')):
        pkgs = {}
        basename = re.sub(r'.+/(.+)\.list', r'\1', f)

        for line in open(f):
            line = line.strip()
            if re.match(r'^#', line):
                continue
            elif re.match(r'\S+$', line):
                pkg = line
                arch = DEFAULT_NOREMOVE_ARCH
            else:
                m = re.match(r'(\S+)\s+\[(.+)\]', line)
                if m:
                    pkg, arch = m.groups()
                else:
                    print('W: could not parse line %r' % (line,), file=sys.stderr)

            arch = re.split(r'[, ]+', arch)[0] # just in case
            pkgs.setdefault(arch, set()).add(pkg)

        for arch in list(pkgs.keys()):
            d = { 'Package': '%s-meta-faux' % (basename,), 'Version': '1',
                  'Section': 'faux', 'Architecture': '%s' % (arch,),
                  'Depends': ', '.join(pkgs[arch]) }
            allfaux.setdefault(arch, []).append(d)

    # Write the result
    for arch in arches:
        if arch not in allfaux:
            continue
        for dir_ in directories:
            f = os.path.join(dir_, 'Packages_' + arch)
            if not os.path.exists(f):
                continue
            else:
                f = open(f, 'a')
                for d in allfaux[arch]:
                    if d['Package'] in all_packages[arch]:
                        print('W: skipping %s/%s (%s) as it is already known' % (d['Package'], arch, f.name), file=sys.stderr)
                        continue
                    f.write('\n'.join('%s: %s' % (k, v) for k, v in d.items()) + '\n\n')

##

def do_update_tasksel():
    p = subprocess.Popen('dak ls -f control-suite -s unstable -a source tasksel',
            shell=True, stdout=subprocess.PIPE)
    p.wait()
    version = p.stdout.readline().split()[1]

    p = subprocess.Popen('dak ls -f control-suite -s unstable -S -a i386,all tasksel',
            shell=True, stdout=subprocess.PIPE)
    p.wait()
    tasks = []

    for line in p.stdout:
        pkg = line.split()[0]

        if pkg.startswith('task-'):
            tasks.append(pkg)

    # Write the new file
    tmpfd, tmpname = tempfile.mkstemp(dir=NOREMOVE_DIR)
    os.write(tmpfd, '# Generated from tasksel-data %s\n' % (version,))
    os.write(tmpfd, '\n'.join(sorted(tasks)) + '\n')
    os.close(tmpfd)
    os.chmod(tmpname, 0o644)
    os.rename(tmpname, os.path.join(NOREMOVE_DIR, 'tasksel.list'))

##

if __name__ == '__main__':
    main()

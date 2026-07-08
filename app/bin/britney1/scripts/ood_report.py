#! /usr/bin/python3
## encoding: utf-8
#
# Copyright (c) 2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

"""Create a report of packages that are out-of-date in each architecture.

It expects a single "directory" argument, that should be a britney directory
for a distribution, i.e. containing Packages_<arch> files and Sources.
"""

import os
import re
import sys
import glob

import apt_pkg
apt_pkg.init()

##

def main():
    if len(sys.argv) != 2:
        print('Usage: %s <directory>', file=sys.stderr)
        sys.exit(1)
    else:
        directory = sys.argv[1]

    pkgfiles = glob.glob(os.path.join(directory, 'Packages_*'))
    versions = get_src_versions(os.path.join(directory, 'Sources'))

    ood = {} # { arch1: { srcpk1: (oldver, [binpkg1, binpkg2, ...]), ... }, ... }

    for pkgfile in pkgfiles:
        arch = re.sub(r'^.*/Packages_', '', pkgfile)
        try:
            parser = apt_pkg.TagFile(open(pkgfile))
            step = parser.step
            get_section = parser.section
            get_field = parser.section.get
        except AttributeError as e:
            parser = apt_pkg.ParseTagFile(open(pkgfile))
            step = parser.Step
            get_section = parser.Section
            get_field = parser.Section.get
        d = ood[arch] = {}

        while step():
            pkg = get_section['Package']
            src = get_field('Source') or pkg

            if ' ' in src:
                m = re.match(r'(\S+) \((\S+)\)$', src)
                src = m.group(1)
                ver = m.group(2)
            else:
                ver = re.sub(r'\+b\d+$', '', get_section['Version'])

            try:
                distver = versions[src]
            except KeyError:
                pass # faux package
            else:
                if ver != distver:
                    d.setdefault(src, (ver, []))[1].append(pkg)

    arches = sorted(ood.keys())

    for arch in arches:
        print('* %s' % (arch,))
        for src, (oldver, binpkgs) in sorted(ood[arch].items()):
            # do not print binpkgs, I think it clutters the view too much
            print('  %s (%s)' % (src, oldver))
        print()

    print('* summary')
    print('\n'.join(['%4d %s' % (len(ood[x]), x) for x in arches]))

##

def get_src_versions(sources_file):
    """Return a dict { srcname: version, ... }."""
    mydict = {}
    try:
        parser = apt_pkg.TagFile(open(sources_file))

        while parser.step():
            mydict[parser.section['Package']] = parser.section['Version']
    except AttributeError as e:
        parser = apt_pkg.ParseTagFile(open(sources_file))

        while parser.Step():
            mydict[parser.Section['Package']] = parser.Section['Version']

    return mydict

##

if __name__ == '__main__':
    main()

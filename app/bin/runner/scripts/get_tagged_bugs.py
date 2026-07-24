#!/usr/bin/python3

import pathlib
import argparse
import calendar
import os
import sys
from urllib.parse import urlsplit

from launchpadlib.launchpad import Launchpad

def parse_args():
    parser = argparse.ArgumentParser(
        description="Get all bugs with a given tag for a series"
    )
    parser.add_argument("lp_service")
    parser.add_argument("distribution")
    parser.add_argument("tags")
    parser.add_argument("series")
    parser.add_argument("--output", "-o", default=sys.stdout)
    return parser.parse_args()

def main(lp_service, distribution, tags, series, output):
    launchpad = Launchpad.login_anonymously("proposed-migration", lp_service)
    distro = launchpad.distributions[distribution]
    tags = tags.split()
    series = distro.getSeries(name_or_version=series)
    blocks = set()
    tasks = list(series.searchTasks(omit_targeted=False, tags=tags))
    tasks += list(distro.searchTasks(omit_targeted=False, tags=tags))
    block_detail = {}
    print(f"Found {len(tasks)} tasks with tags {tags} in series {series.name} of distribution {distribution}")
    for task in tasks:
        target = task.target
        bug = task.bug
        if urlsplit(target.resource_type_link).fragment in (
                "distribution_source_package", "source_package"):
            date = block_detail.get(bug.id)
            if date is None:
                for action in reversed(
                        [a for a in bug.activity if a.whatchanged == "tags"]):
                    oldtags = action.oldvalue.split()
                    newtags = action.newvalue.split()
                    gained_block = False
                    for tag in tags:
                        if tag not in oldtags and tag in newtags:
                            gained_block = True
                            break
                    if gained_block:
                        date = action.datechanged
                        break
                else:
                    date = bug.date_created
                block_detail[bug.id] = date
            blocks.add("%s %d %d" %
                (os.path.basename(target.self_link), bug.id,
                calendar.timegm(date.timetuple())))
    result = "\n".join(sorted(blocks))
    if output == sys.stdout:
        output.write(result)
    else:
        output = pathlib.Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w") as f:
            f.write(result)

if __name__ == "__main__":
    args = parse_args()
    main(args.lp_service, args.distribution, args.tags, args.series, args.output)

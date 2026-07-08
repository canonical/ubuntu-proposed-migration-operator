#!/usr/bin/python3
import argparse

from launchpadlib.launchpad import Launchpad

def parse_args():
    parser = argparse.ArgumentParser(
        description="Get series information from Launchpad",
    )
    parser.add_argument("lp_service")
    parser.add_argument("distribution")
    parser.add_argument("series")
    parser.add_argument("info", choices=["arches", "archindep"])
    return parser.parse_args()

def main(lp_service, distribution, series, info):
    launchpad = Launchpad.login_anonymously("proposed-migration", lp_service)
    distro = launchpad.distributions[distribution]
    series_name = series.split("-")[0]
    series = distro.getSeries(name_or_version=series_name)
    if info == "arches":
        print(" ".join(arch.architecture_tag for arch in series.architectures))
    elif info == "archindep":
        print(series.nominatedarchindep.architecture_tag)

if __name__ == "__main__":
    args = parse_args()
    main(args.lp_service, args.distribution, args.series, args.info)

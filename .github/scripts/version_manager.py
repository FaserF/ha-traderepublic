import argparse
import glob
import json
import os
import re
import subprocess


def find_manifest():
    matches = glob.glob("custom_components/*/manifest.json")
    return matches[0] if matches else None


MANIFEST_FILE = find_manifest()


def get_current_version(manifest_path=None):
    if manifest_path is None:
        manifest_path = MANIFEST_FILE
    try:
        tags = (
            subprocess.check_output(["git", "tag"], stderr=subprocess.DEVNULL)
            .decode()
            .splitlines()
        )
        v_tags = []
        for tag in tags:
            tag = tag.strip()
            match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:(b)(\d+)|(-dev)(\d+))?$", tag)
            if match:
                y, m, p, bp, bn, dp, dn = match.groups()
                v_tags.append(
                    {
                        "tag": tag,
                        "key": (
                            int(y),
                            int(m),
                            int(p),
                            (1 if bp else (0 if dp else 2)),
                            (int(bn) if bp else (int(dn) if dp else 0)),
                        ),
                    }
                )
        if v_tags:
            return sorted(v_tags, key=lambda x: x["key"], reverse=True)[0]["tag"]
    except (subprocess.CalledProcessError, IndexError, ValueError):
        pass
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f).get("version", "1.0.0")
    return "1.0.0"


def write_version(v, manifest_path=None):
    if manifest_path is None:
        manifest_path = MANIFEST_FILE
    if manifest_path and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        data["version"] = v
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def bump_version(release_type="beta", level="patch", override=None, manifest_path=None):
    if override and override.strip():
        new_v = override.strip().lstrip("v")
        write_version(new_v, manifest_path)
        return new_v

    current = get_current_version(manifest_path).lstrip("v")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:b(\d+))?$", current)
    if not m:
        major, minor, patch, beta = 1, 0, 0, None
    else:
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
        beta = int(m.group(4)) if m.group(4) else None

    if release_type == "stable":
        if beta is not None:
            new_v = f"{major}.{minor}.{patch}"
        else:
            if level == "major":
                major += 1
                minor = 0
                patch = 0
            elif level == "minor":
                minor += 1
                patch = 0
            else:
                patch += 1
            new_v = f"{major}.{minor}.{patch}"
    else:  # beta / dev / nightly
        if beta is None:
            if level == "major":
                major += 1
                minor = 0
                patch = 0
            elif level == "minor":
                minor += 1
                patch = 0
            else:
                patch += 1
            beta = 1
        else:
            beta += 1
        new_v = f"{major}.{minor}.{patch}b{beta}"

    write_version(new_v, manifest_path)
    return new_v


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    b = sub.add_parser("bump")
    b.add_argument("--type", default="beta")
    b.add_argument("--level", default="patch")
    b.add_argument("--override", default="")
    b.add_argument("--manifest", default=None)
    g = sub.add_parser("get")
    g.add_argument("--manifest", default=None)
    args = parser.parse_args()

    if args.cmd == "get":
        print(get_current_version(args.manifest))
    elif args.cmd == "bump":
        print(bump_version(args.type, args.level, args.override, args.manifest))

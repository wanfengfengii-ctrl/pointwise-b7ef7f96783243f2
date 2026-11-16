"""Run the full business suite or a real temporary-database demonstration."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from analysis import Analysis
from archive import Archive
from samples import build_legacy
from storage import connect

def demo():
    with tempfile.TemporaryDirectory(prefix="ring-archive-") as directory:
        path = Path(directory) / "archive.sqlite"
        db = connect(path)
        try:
            archive = build_legacy(db)
            analysis = Analysis(archive)
            before = analysis.run("upper")
            archive.put("bow", (((0, 0), (4, 0), (4, 2), (0, 2), (0, 0)),))
            after = analysis.run("upper")
        finally:
            db.close()
        db = connect(path)
        try:
            reopened = Analysis(Archive(db)).run("upper")
            assert before[0].area == 1 and after[0].area == 2 and reopened == after
            def rows(hits):
                return [dict(id=h.region_id, area=str(h.area), boundary=h.boundary) for h in hits]
            print(json.dumps(dict(before=rows(before), after=rows(after),
                                  reopened=rows(reopened)), sort_keys=True))
        finally:
            db.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "demo"))
    args = parser.parse_args()
    if args.command == "demo":
        demo()
        return 0
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent / "tests"))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())

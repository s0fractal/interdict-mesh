"""scripts/check-retired.sh, the retired-files (2026-10-12 on) and retired-objects (2026-10-28 on) tables.

Each case builds a small repository whose archive tags hold a file that was then retired, and
breaks one rule of its table row: the file is back, the digest is not the tag's bytes, the loss
is empty, a SUPERSEDED row names no replacement or one that does not exist, the table is empty.

    python3 scripts/test_check_retired.py
"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
OLD = "# An old pilot\n\nStatus: do not merge.\n"
DIGEST = hashlib.sha256(OLD.encode()).hexdigest()
LEDGER = """# Retired

| ID | What | Fixed | Cited in |
|---|---|---|---|
| F01 | x | #1 | `x.rs` |

<!-- retired-files: path | mode | sha256 at the tag | replacement | loss -->
{row}

<!-- retired-objects archive/2026-10-28: path | mode | git object at the tag | replacement | loss -->
{objects}

## After
"""
ROW = f"| `docs/OLD.md` | SUPERSEDED | {DIGEST} | ADR-0001 | the pilot's narrative |"


def run(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)


class RetiredFiles(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for sub in ("scripts", "docs/adr"):
            (self.dir / sub).mkdir(parents=True)
        shutil.copy(HERE / "check-retired.sh", self.dir / "scripts/check-retired.sh")
        (self.dir / "docs/adr/0001-a.md").write_text("# ADR-0001\n")
        (self.dir / "x.rs").write_text("// F01\n")
        (self.dir / "docs/OLD.md").write_text(OLD)
        (self.dir / "docs/old-dir").mkdir()
        (self.dir / "docs/old-dir/a.json").write_text("{}\n")
        self.objects = ""
        (self.dir / "docs/RETIRED.md").write_text(LEDGER.format(row=ROW, objects=""))
        git = lambda *a: run(self.dir, "git", "-c", "user.name=t", "-c", "user.email=t@t", *a)
        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "before")
        for tag in ("archive/2026-09-29", "archive/2026-10-05", "archive/2026-10-12", "archive/2026-10-28"):
            git("tag", tag)
        tree = git("rev-parse", "HEAD:docs/old-dir").stdout.strip()
        self.objects = f"| `docs/old-dir` | SUPERSEDED | {tree} | ADR-0001 | the old files |"
        (self.dir / "docs/RETIRED.md").write_text(LEDGER.format(row=ROW, objects=self.objects))
        git("rm", "-q", "-r", "docs/OLD.md", "docs/old-dir")
        git("add", "-A")
        git("commit", "-qm", "retire")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def check(self):
        return run(self.dir, "bash", "scripts/check-retired.sh")

    def with_row(self, row, objects=None):
        (self.dir / "docs/RETIRED.md").write_text(LEDGER.format(row=row, objects=self.objects if objects is None else objects))

    def assert_refused(self, needle):
        r = self.check()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(needle, r.stdout)

    def test_a_retired_file_with_its_digest_and_loss_passes(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 retired files: absent, digests match", r.stdout)

    def test_a_retired_file_back_in_the_tree_is_refused(self):
        (self.dir / "docs/OLD.md").write_text(OLD)
        self.assert_refused("docs/OLD.md is retired but still in the tree")

    def test_a_digest_that_is_not_the_tagged_bytes_is_refused(self):
        self.with_row(ROW.replace(DIGEST, "0" * 64))
        self.assert_refused("bytes at archive/2026-10-12 are not")

    def test_an_empty_loss_is_refused(self):
        self.with_row(ROW.replace("the pilot's narrative", "—"))
        self.assert_refused("a retirement names what is lost")

    def test_superseded_names_an_existing_replacement(self):
        self.with_row(ROW.replace("ADR-0001", "—"))
        self.assert_refused("SUPERSEDED names its replacement")
        self.with_row(ROW.replace("ADR-0001", "ADR-0099"))
        self.assert_refused("ADR-0099 does not exist")

    def test_an_unknown_mode_is_refused(self):
        self.with_row(ROW.replace("SUPERSEDED", "FORGOTTEN"))
        self.assert_refused("mode FORGOTTEN")

    def test_a_depth_1_clone_fetches_the_archive_tag(self):
        # CI's checkout has one commit and no tags (2026-10-12: the check died with git's 128).
        run(self.dir, "git", "config", "uploadpack.allowAnySHA1InWant", "true")
        clone = self.dir.parent / f"{self.dir.name}-ci"
        run(self.dir.parent, "git", "init", "-q", str(clone))
        run(clone, "git", "remote", "add", "origin", str(self.dir))
        head = run(self.dir, "git", "rev-parse", "HEAD").stdout.strip()
        run(clone, "git", "fetch", "-q", "--depth=1", "origin", head)
        run(clone, "git", "checkout", "-q", "FETCH_HEAD")
        self.assertNotEqual(run(clone, "git", "rev-parse", "-q", "--verify", "refs/tags/archive/2026-10-12").returncode, 0)
        r = run(clone, "bash", "scripts/check-retired.sh")
        shutil.rmtree(clone, ignore_errors=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 retired files: absent, digests match", r.stdout)

    def test_missing_tagged_bytes_are_a_failure_not_a_crash(self):
        run(self.dir, "git", "tag", "-d", "archive/2026-10-12")
        run(self.dir, "git", "tag", "archive/2026-10-12", "HEAD")
        self.assert_refused("bytes at archive/2026-10-12 are not")

    def test_an_empty_table_is_refused(self):
        self.with_row("")
        self.assert_refused("has no retired-files rows")


    def test_a_retired_object_is_named_by_its_id_at_the_tag(self):
        self.assertEqual(self.check().returncode, 0, self.check().stdout)
        self.with_row(ROW, self.objects.replace(self.objects.split(" | ")[2], "0" * 40))
        self.assert_refused("docs/old-dir: the object at archive/2026-10-28 is not")

    def test_a_retired_object_back_in_the_tree_or_without_loss_is_refused(self):
        (self.dir / "docs/old-dir").mkdir()
        self.assert_refused("docs/old-dir is retired but still in the tree")
        (self.dir / "docs/old-dir").rmdir()
        self.with_row(ROW, self.objects.replace("the old files", "—"))
        self.assert_refused("docs/old-dir: a retirement names what is lost")


if __name__ == "__main__":
    unittest.main()

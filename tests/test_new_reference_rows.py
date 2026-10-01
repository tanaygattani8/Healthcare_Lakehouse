import csv

from scripts.new_reference_rows import main, new_rows


def test_only_ids_batch_one_lacks_are_kept():
    rows = [{"Id": "a", "NAME": "old"}, {"Id": "z", "NAME": "new"}]
    assert new_rows({"a", "b"}, rows) == [{"Id": "z", "NAME": "new"}]


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Id", "NAME"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def test_batch_two_files_are_rewritten_and_a_rerun_changes_nothing(tmp_path):
    for name in ("organizations", "providers", "payers"):
        write(tmp_path / "b1" / "csv" / f"{name}.csv", [{"Id": "a", "NAME": "x"}])
        write(tmp_path / "b2" / "csv" / f"{name}.csv",
              [{"Id": "a", "NAME": "y"}, {"Id": "n", "NAME": "z"}])
    main(tmp_path / "b1", tmp_path / "b2")
    first = (tmp_path / "b2" / "csv" / "providers.csv").read_text("utf-8")
    assert first == "Id,NAME\nn,z\n"
    main(tmp_path / "b1", tmp_path / "b2")
    assert (tmp_path / "b2" / "csv" / "providers.csv").read_text("utf-8") == first

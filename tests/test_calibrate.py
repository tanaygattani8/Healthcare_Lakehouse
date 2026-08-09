import duckdb
import pytest

from scripts.calibrate import (
    distinct_codes,
    measure_file,
    note_stats,
    parquet_bytes,
    render_markdown,
)


@pytest.fixture
def con():
    return duckdb.connect()


def test_measure_file_counts_rows_excluding_header(tmp_path, con):
    csv = tmp_path / "conditions.csv"
    csv.write_text("Id,CODE\n1,44054006\n2,73211009\n3,44054006\n")
    
    result = measure_file(con, csv)

    assert result["file"] == "conditions.csv"
    assert result["rows"] == 3
    assert result["bytes"] == csv.stat().st_size


def test_measure_file_handles_empty_file_with_only_header(tmp_path, con):
    csv = tmp_path / "allergies.csv"
    csv.write_text("Id,CODE\n")

    assert measure_file(con, csv)["rows"] == 0


def test_parquet_bytes_is_smaller_than_csv_for_repetitive_data(tmp_path, con):
    csv = tmp_path / "conditions.csv"
    csv.write_text("Id,CODE\n" + "".join(f"{i},44054006\n"
    for i in range(2000)))
    out_dir = tmp_path / "pq"
    out_dir.mkdir()

    assert parquet_bytes(con, csv, out_dir) < csv.stat().st_size


def test_distinct_codes_deduplicates(tmp_path, con):
    csv = tmp_path / "conditions.csv"
    csv.write_text("Id,CODE\n1,44054006\n2,73211009\n3,44054006\n")

    assert distinct_codes(con, csv) == 2


def test_distinct_codes_returns_zero_when_column_absent(tmp_path, con):
    csv = tmp_path / "patients.csv"
    csv.write_text("Id,FIRST\n1,Ada\n")

    assert distinct_codes(con, csv) == 0


def test_note_stats_counts_files_and_mean_length(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "a.txt").write_text("abcd")
    (notes / "b.txt").write_text("abcdef")

    result = note_stats(notes)

    assert result["note_count"] == 2
    assert result["mean_chars"] == 5.0
    assert result["max_chars"] == 6
    assert result["total_bytes"] == 10


def test_note_stats_returns_zero_for_missing_directory(tmp_path):
    result = note_stats(tmp_path / "does_not_exist")

    assert result == {"note_count": 0, "total_bytes": 0, "mean_chars": 0.0, "max_chars": 0}


def test_render_markdown_includes_rows_per_patient(tmp_path):
    rows = [
        {
            "file": "encounters.csv",
            "rows": 5000,
            "bytes": 1024,
            "parquet_bytes": 256,
            "distinct_codes": 40,
        }
    ]

    md = render_markdown(rows, patient_count=1000, notes={
        "note_count": 3, "total_bytes": 2700, "mean_chars": 900.0, "max_chars": 1500
    })
    assert "encounters.csv" in md
    assert "5.0" in md  # 5000 rows / 1000 patients
    # Reporting the CSV total here instead would be a silent 4x error, and the
    # report's own closing paragraph tells the reader to size from this number.
    assert "**Total Parquet bytes:** 256" in md
    assert "1,500" in md  # max note length, not just the mean

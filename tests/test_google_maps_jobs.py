import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import google_maps_jobs as jobs


class GoogleMapsJobsTests(unittest.TestCase):
    def test_build_query_from_template_compacts_blank_parts(self):
        self.assertEqual(
            jobs.build_query("{type} {keyword} {location}", "khach san", "view bien", "Da Nang"),
            "khach san view bien Da Nang",
        )
        self.assertEqual(
            jobs.build_query("{type} {keyword} {location}", "nha hang", "", "Hoi An"),
            "nha hang Hoi An",
        )

    def test_expand_jobs_cross_joins_types_keywords_and_locations(self):
        expanded = jobs.expand_jobs(
            place_types=["khach san", "resort"],
            keywords=["view bien"],
            locations=["Da Nang", "Hoi An"],
            limit=25,
            query_template="{type} {keyword} {location}",
        )

        self.assertEqual([job.query for job in expanded], [
            "khach san view bien Da Nang",
            "khach san view bien Hoi An",
            "resort view bien Da Nang",
            "resort view bien Hoi An",
        ])
        self.assertTrue(all(job.limit == 25 for job in expanded))

    def test_import_jobs_from_txt_pipe_format(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "jobs.txt"
            path.write_text("khach san|Da Nang|50\nnha hang|dac san|Hoi An|30\n", encoding="utf-8")

            imported = jobs.import_jobs(path)

        self.assertEqual(len(imported), 2)
        self.assertEqual(imported[0].place_type, "khach san")
        self.assertEqual(imported[0].keyword, "")
        self.assertEqual(imported[0].location, "Da Nang")
        self.assertEqual(imported[0].limit, 50)
        self.assertEqual(imported[1].keyword, "dac san")
        self.assertEqual(imported[1].query, "nha hang dac san Hoi An")

    def test_import_jobs_from_csv_named_columns(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "jobs.csv"
            path.write_text(
                "type,keyword,location,limit,output\n"
                "spa,,Hue,15,data/spa_hue.csv\n",
                encoding="utf-8",
            )

            imported = jobs.import_jobs(path)

        self.assertEqual(imported[0].place_type, "spa")
        self.assertEqual(imported[0].location, "Hue")
        self.assertEqual(imported[0].limit, 15)
        self.assertEqual(imported[0].output, "data/spa_hue.csv")

    def test_save_and_load_preset_round_trip(self):
        crawl_jobs = [
            jobs.CrawlJob(place_type="khach san", keyword="", location="Da Nang", limit=10),
            jobs.CrawlJob(place_type="nha hang", keyword="dac san", location="Hue", limit=20),
        ]

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "preset.json"
            jobs.save_preset(path, crawl_jobs, settings={"delay": 2.5})
            loaded_jobs, settings = jobs.load_preset(path)

        self.assertEqual([job.query for job in loaded_jobs], ["khach san Da Nang", "nha hang dac san Hue"])
        self.assertEqual(settings["delay"], 2.5)

    def test_category_presets_include_requested_groups(self):
        for name in ("Du lich", "An uong", "Y te", "Mua sam", "Van tai"):
            self.assertIn(name, jobs.CATEGORY_PRESETS)
            self.assertGreater(len(jobs.CATEGORY_PRESETS[name]), 1)

    def test_dedupe_places_by_destination_id_and_merge_missing_values(self):
        rows = [
            {"destination_id": "a1", "name": "A", "address": "", "rating": ""},
            {"destination_id": "a1", "name": "A", "address": "Da Nang", "rating": "4.5"},
            {"destination_id": "b1", "name": "B", "address": "Hoi An", "rating": ""},
        ]

        deduped = jobs.dedupe_rows(rows, mode="destination_id", merge=True)

        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["address"], "Da Nang")
        self.assertEqual(deduped[0]["rating"], "4.5")

    def test_missing_field_report_counts_empty_values(self):
        report = jobs.build_missing_field_report(
            [
                {"name": "A", "price_min": "", "image_url": "x", "latitude": ""},
                {"name": "B", "price_min": "10", "image_url": "", "latitude": "16.1"},
            ],
            fields=["price_min", "image_url", "latitude"],
        )

        self.assertEqual(report["total_rows"], 2)
        self.assertEqual(report["missing"]["price_min"], 1)
        self.assertEqual(report["missing"]["image_url"], 1)
        self.assertEqual(report["missing"]["latitude"], 1)

    def test_format_output_path_replaces_template_tokens(self):
        path = jobs.format_output_path(
            "data/{type}_{location}_{date}.csv",
            place_type="khach san",
            location="Da Nang",
            date_text="20260628",
        )

        self.assertEqual(path, Path("data/khach_san_Da_Nang_20260628.csv"))

    def test_checkpoint_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "checkpoint.json"
            jobs.save_checkpoint(path, completed_ids={"a", "b"}, failed_rows=[{"url": "x"}])
            checkpoint = jobs.load_checkpoint(path)

        self.assertEqual(set(checkpoint["completed_ids"]), {"a", "b"})
        self.assertEqual(checkpoint["failed_rows"], [{"url": "x"}])

    def test_extract_address_parts_finds_ward_district_province(self):
        parts = jobs.extract_address_parts("1 Dong Khoi, Phuong Ben Nghe, Quan 1, TP. Ho Chi Minh")

        self.assertEqual(parts["ward"], "Phuong Ben Nghe")
        self.assertEqual(parts["district"], "Quan 1")
        self.assertEqual(parts["province"], "TP. Ho Chi Minh")


if __name__ == "__main__":
    unittest.main()

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import faiss
import numpy as np

from apps.ai.embeddings.base import EmbeddedChunks, EmbeddingConfig
from apps.ai.retrieval.index import DenseIndex
from apps.ai.retrieval.storage import IndexStorageError, load_index, save_index


class IndexStorageTests(unittest.TestCase):
    def setUp(self):
        processed = Path(__file__).resolve().parents[4] / "data/processed"
        processed.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=processed)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(processed.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.config = EmbeddingConfig()
        self.chunks = [{
            "chunk_id": f"chunk-{i}", "text": f"fixture-{i}",
            "course_id": "00000000-0000-4000-8000-000000000001",
            "document_id": "00000000-0000-4000-8000-000000000101",
            "version_id": "00000000-0000-4000-8000-000000001001",
            "page_number": i + 1,
        } for i in range(3)]
        self.vectors = np.zeros((3, 1024), dtype=np.float32)
        self.vectors[np.arange(3), np.arange(3)] = 1
        self.index = DenseIndex(self.chunks, EmbeddedChunks(tuple(c["chunk_id"] for c in self.chunks), self.vectors, (), self.config.fingerprint()), self.config)
        self.snapshot = save_index(self.index, self.root)

    def resign_manifest(self, mutate=None):
        path = self.snapshot / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if mutate:
            mutate(manifest)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        pointer_path = self.root / "current.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        pointer["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    def assert_load_error(self, code, config=None):
        with self.assertRaises(IndexStorageError) as ctx:
            load_index(self.root, config or self.config)
        self.assertEqual(ctx.exception.code, code)

    def test_roundtrip_preserves_all_query_fields_and_manifest(self):
        loaded = load_index(self.root, self.config)
        self.assertEqual(loaded.manifest(), self.index.manifest())
        for vector in self.vectors:
            self.assertEqual(loaded.search(vector, 3), self.index.search(vector, 3))

    def test_multiple_saves_publish_complete_generations_without_appending(self):
        second = save_index(self.index, self.root)
        self.assertNotEqual(second, self.snapshot)
        self.assertTrue(self.snapshot.exists())
        self.assertEqual(load_index(self.root, self.config).count, 3)
        self.assertEqual(json.loads((self.root / "current.json").read_text())["generation"], second.name)

    def test_partial_write_retains_previous_pointer(self):
        previous = (self.root / "current.json").read_bytes()
        with patch("apps.ai.retrieval.storage._write_file", side_effect=OSError("disk full")):
            with self.assertRaises(IndexStorageError) as ctx:
                save_index(self.index, self.root)
        self.assertEqual(ctx.exception.code, "SAVE_FAILED")
        self.assertEqual((self.root / "current.json").read_bytes(), previous)
        self.assertEqual(load_index(self.root, self.config).count, 3)

    def test_pointer_publish_failure_retains_previous_snapshot(self):
        previous = (self.root / "current.json").read_bytes()
        with patch("apps.ai.retrieval.storage.os.replace", side_effect=OSError("sharing violation")):
            with self.assertRaises(IndexStorageError):
                save_index(self.index, self.root)
        self.assertEqual((self.root / "current.json").read_bytes(), previous)
        self.assertEqual(list(self.root.glob(".current-*.tmp")), [])
        self.assertEqual(load_index(self.root, self.config).count, 3)

    def test_missing_bundle(self):
        with self.assertRaises(IndexStorageError) as ctx:
            load_index(self.root / "missing", self.config)
        self.assertEqual(ctx.exception.code, "SNAPSHOT_NOT_FOUND")

    def test_missing_files(self):
        for name in ("index.faiss", "chunks.jsonl", "manifest.json"):
            with self.subTest(name=name):
                path = self.snapshot / name
                content = path.read_bytes()
                path.unlink()
                self.assert_load_error("SNAPSHOT_NOT_FOUND")
                path.write_bytes(content)

    def test_corrupt_manifest(self):
        (self.snapshot / "manifest.json").write_bytes(b"changed")
        self.assert_load_error("CHECKSUM_MISMATCH")

    def test_corrupt_binary_rejected_before_faiss_deserialization(self):
        (self.snapshot / "index.faiss").write_bytes(b"changed")
        with patch("apps.ai.retrieval.storage.faiss.deserialize_index") as deserialize:
            self.assert_load_error("CHECKSUM_MISMATCH")
        deserialize.assert_not_called()

    def test_corrupt_chunks(self):
        with (self.snapshot / "chunks.jsonl").open("ab") as stream:
            stream.write(b"\n")
        self.assert_load_error("CHECKSUM_MISMATCH")

    def test_wrong_expected_model_revision(self):
        self.assert_load_error("CONFIG_MISMATCH", replace(self.config, revision="a" * 40))

    def test_wrong_expected_config(self):
        self.assert_load_error("CONFIG_MISMATCH", replace(self.config, batch_size=4))

    def test_invalid_stored_config(self):
        self.resign_manifest(lambda m: m["embedding_config"].update(revision="main"))
        self.assert_load_error("CONFIG_MISMATCH")

    def test_mapping_metadata_tampering(self):
        self.resign_manifest(lambda m: m["vector_mapping"][0]["source"].update(page_number=99))
        self.assert_load_error("MAPPING_MISMATCH")

    def test_chunk_order_tampering_even_with_updated_file_checksum(self):
        path = self.snapshot / "chunks.jsonl"
        records = [json.loads(line) for line in path.read_text().splitlines()]
        path.write_text("".join(json.dumps(c) + "\n" for c in reversed(records)), encoding="utf-8")
        self.resign_manifest(lambda m: m.update(chunks_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.assert_load_error("MAPPING_MISMATCH")

    def test_vector_count_mismatch(self):
        self.resign_manifest(lambda m: m.update(vector_count=4))
        self.assert_load_error("COUNT_MISMATCH")

    def test_manifest_schema_and_file_names(self):
        for changes in ({"storage_schema_version": "2.0"}, {"index_file": "../outside"}):
            with self.subTest(changes=changes):
                self.snapshot = save_index(self.index, self.root)
                self.resign_manifest(lambda m: m.update(changes))
                self.assert_load_error("INVALID_MANIFEST")

    def test_invalid_pointer_and_path_traversal(self):
        for pointer in ([], {"storage_schema_version": "1.0", "generation": "../outside"}, {"storage_schema_version": "2.0", "generation": self.snapshot.name}):
            with self.subTest(pointer=pointer):
                (self.root / "current.json").write_text(json.dumps(pointer))
                self.assert_load_error("INVALID_POINTER")

    def test_wrong_native_index_type(self):
        path = self.snapshot / "index.faiss"
        other = faiss.IndexFlatL2(1024)
        other.add(self.vectors)
        path.write_bytes(faiss.serialize_index(other).tobytes())
        self.resign_manifest(lambda m: m.update(index_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.assert_load_error("INVALID_INDEX")

    def test_native_vector_count_mismatch(self):
        path = self.snapshot / "index.faiss"
        other = faiss.IndexFlatIP(1024)
        other.add(self.vectors[:2])
        path.write_bytes(faiss.serialize_index(other).tobytes())
        self.resign_manifest(lambda m: m.update(index_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.assert_load_error("COUNT_MISMATCH")

    def test_nonfinite_native_vectors(self):
        path = self.snapshot / "index.faiss"
        other = faiss.IndexFlatIP(1024)
        other.add(np.full((3, 1024), np.nan, dtype=np.float32))
        path.write_bytes(faiss.serialize_index(other).tobytes())
        self.resign_manifest(lambda m: m.update(index_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.assert_load_error("INVALID_VECTORS")

    def test_unsafe_metadata_does_not_replace_snapshot(self):
        pointer = (self.root / "current.json").read_bytes()
        with self.assertRaises(IndexStorageError) as ctx:
            save_index(self.index, self.root, {"not_json": object()})
        self.assertEqual(ctx.exception.code, "INVALID_METADATA")
        self.assertEqual(pointer, (self.root / "current.json").read_bytes())

    def test_cannot_save_into_corpus(self):
        corpus = Path(__file__).resolve().parents[4] / "data/corpus"
        with self.assertRaises(IndexStorageError) as ctx:
            save_index(self.index, corpus)
        self.assertEqual(ctx.exception.code, "INVALID_PATH")

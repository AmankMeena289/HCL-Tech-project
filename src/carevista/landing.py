"""Task 1 - landing: copy the four staged files, unchanged, into the landing zone.

The copy is checked byte for byte (size + SHA-256). The source files are only
read, never changed.
"""

from __future__ import annotations

from pyspark.sql import SparkSession

from .audit import write_audit
from .config import SOURCE_FILES, PipelineConfig
from .io import copy_file, file_digest


def run(spark: SparkSession, cfg: PipelineConfig) -> list[dict]:
    results = []
    for entity, file_name in SOURCE_FILES.items():
        src = f"{cfg.input_path.rstrip('/')}/{file_name}"
        dst = f"{cfg.landing_dir()}/{file_name}"
        src_size, src_hash = file_digest(spark, src)
        copy_file(spark, src, dst)
        dst_size, dst_hash = file_digest(spark, dst)
        if (src_size, src_hash) != (dst_size, dst_hash):
            raise RuntimeError(f"Landing copy of {file_name} does not match the source file.")
        results.append(
            {
                "entity": entity,
                "source_file": file_name,
                "detail": f"bytes={dst_size}; sha256={dst_hash}",
            }
        )
        print(f"[landing] {file_name}: {dst_size} bytes copied, sha256 {dst_hash[:12]}... verified")
    write_audit(spark, cfg, "landing", results)
    return results

"""Actual bounded CSV/TSV analysis; no arbitrary Python, shell or fabricated data."""
from pathlib import Path
import csv
import io
import math
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.session_files import SessionFiles
from mcp.server import MCPServer
from mcp.types import ToolAnnotations


from scenarios.data_analysis.evidence import DatasetEvidence


def create_server(directory):
    files = DatasetEvidence(directory)
    server = MCPServer('Harless uploaded research data')
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=annotation)
    def list_inputs() -> dict:
        """List only this Session's uploaded CSV/TSV files and their exact SHA256."""
        return files.list_files()

    @server.tool(annotations=annotation)
    def pin_dataset(name: str, sha256: str) -> dict:
        """Pin one listed UTF-8 CSV/TSV version to a fresh Session-local source_id."""
        if Path(name).suffix.lower() not in ('.csv', '.tsv'): raise ValueError('csv_or_tsv_required')
        return files.pin(name, sha256)

    @server.tool(annotations=annotation)
    def read_pinned_dataset_summary(source_id: str) -> dict:
        """Read row counts, missingness, types and descriptive numeric statistics; recheck the pinned bytes."""
        return files.summary(source_id)

    @server.tool(annotations=annotation)
    def correlate_pinned_columns(source_id: str, x: str, y: str) -> dict:
        """Calculate Pearson r for two finite numeric columns using complete pairs, with exclusion counts; no causal claim."""
        return files.correlation(source_id, x, y)

    return server


if __name__ == '__main__': create_server(Path(sys.argv[1])).run(transport='stdio')

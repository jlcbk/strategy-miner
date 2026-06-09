from packages.data_lake.store import DataLakeReader, DataLakeWriter, Partition

_COVERAGE_EXPORTS = {
    "CoverageItem",
    "DataCollectionJob",
    "DataCollectionJobPlan",
    "DataCoverageReport",
    "check_data_coverage",
    "generate_data_collection_jobs",
}

__all__ = [
    "CoverageItem",
    "DataCollectionJob",
    "DataCollectionJobPlan",
    "DataCoverageReport",
    "DataLakeReader",
    "DataLakeWriter",
    "Partition",
    "check_data_coverage",
    "generate_data_collection_jobs",
]


def __getattr__(name: str):
    if name in _COVERAGE_EXPORTS:
        from packages.data_lake import coverage

        return getattr(coverage, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Feature view applied by ``jrr.features.retrieve_historical``.

The offline store is DuckDB reading ``data/features/sa4_features.parquet``.
The online store is SQLite. Paths are rewritten to absolute paths at runtime
so retrieval does not depend on the working directory.
"""

from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource
from feast.data_format import ParquetFormat
from feast.types import Float64
from feast.value_type import ValueType

from jrr.columns import FEATURE_COLUMNS
from jrr.paths import feature_dir

sa4 = Entity(
    name="sa4",
    join_keys=["sa4_code"],
    value_type=ValueType.STRING,
    description="ABS labour market region",
)

source = FileSource(
    name="sa4_features",
    path=str(feature_dir() / "sa4_features.parquet"),
    timestamp_field="event_timestamp",
    file_format=ParquetFormat(),
)

sa4_labour = FeatureView(
    name="sa4_labour",
    entities=[sa4],
    ttl=timedelta(days=5000),
    schema=[Field(name=column, dtype=Float64) for column in FEATURE_COLUMNS],
    source=source,
    online=True,
)

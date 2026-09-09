"""Minimal PostGIS Point(4326) column type for SQLAlchemy ORM models.

Phase 3 / Task 3.1 (Ride Booking — Create Ride Request), first consumer:
modules/ride/models.py's original_pickup/current_pickup/original_
destination/current_destination columns (database-design.md §9.1).

No ORM geometry library (e.g. geoalchemy2) is added as a dependency —
this task doesn't need one. `GeometryPoint4326` only knows:

  - its DDL column type (`geometry(Point,4326)`, via get_col_spec);
  - how to wrap a bound WKT string in ST_GeomFromText(...) when writing
    (bind_expression);
  - how to unwrap a stored geometry into WKT text via ST_AsText(...)
    when reading (column_expression).

This is a standard SQLAlchemy technique (UserDefinedType with bind_/
column_expression hooks), not custom marshalling logic — the Python-side
value is always a WKT string (e.g. "POINT(85.1376 25.5941)", longitude
first per the WKT/PostGIS convention), never a domain-specific type.
modules/ride/repositories.py converts to/from plain latitude/longitude
floats at the boundary, keeping modules/ride/domain/entities.py free of
any SQL/WKT concept (implementation-readiness.md §6: domain modules must
stay framework-independent).

Not implemented here: this type does not itself validate SRID/geometry-
type mismatches, coordinate ranges, or WKT syntax — Postgres/PostGIS
enforces the column's declared geometry(Point,4326) constraint, and
modules/ride/domain/entities.py validates latitude/longitude ranges
before a WKT string is ever built.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.sql import func


class GeometryPoint4326(sa.types.UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "geometry(Point,4326)"

    def bind_expression(self, bindvalue: sa.BindParameter) -> sa.ColumnElement:
        return func.ST_GeomFromText(bindvalue, 4326, type_=self)

    def column_expression(self, col: sa.ColumnElement) -> sa.ColumnElement:
        return func.ST_AsText(col, type_=sa.String())

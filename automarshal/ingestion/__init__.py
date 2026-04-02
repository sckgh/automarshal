"""Ingestion sub-package: MyLaps and GPS data adapters."""

from automarshal.ingestion.mylaps_client import MyLapsClient
from automarshal.ingestion.gps_client import GPSClient

__all__ = ["MyLapsClient", "GPSClient"]

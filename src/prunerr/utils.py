"""
Prunerr utility functions not dependent on Servarr or download clients.
"""

import ciso8601

# Needs to be here instead of `prunerr.servarr` to avoid circular imports because the
# history deserialization/serialization is used both in the Servarr client to collate
# history and the download client in the Prunerr data files.
SERVARR_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def deserialize_history(history_record):
    """
    Convert Servarr history values to native Python types when possible.
    """
    for history_data in (
        history_record,
        history_record["data"],
        history_record.get("prunerr", {}),
    ):
        for key, value in list(history_data.items()):
            # Perform any data transformations, e.g. to native Python types
            if key == "date" or key.endswith("Date"):
                # More efficient than dateutil.parser.parse(value)
                history_data[key] = ciso8601.parse_datetime(value)
    return history_record


def serialize_history(history_record):
    """
    Convert Servarr history values to native Python types when possible.
    """
    # Prevent serialized values from leaking into cached Servarr history
    for history_data in (
        history_record,
        history_record["data"],
        history_record.get("prunerr", {}),
    ):
        for key, value in list(history_data.items()):
            # Perform any data transformations, e.g. to native Python types
            if key == "date" or key.endswith("Date"):
                history_data[key] = value.strftime(SERVARR_DATETIME_FORMAT)
    return history_record

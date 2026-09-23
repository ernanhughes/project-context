"""Provider telemetry normalisation. Adapters translate provider payloads
into TokenCount records WITHOUT hiding provider differences: anything a
provider does not expose stays None (unavailable), never zero."""

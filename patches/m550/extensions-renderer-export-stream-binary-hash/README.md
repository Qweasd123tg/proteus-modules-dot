# Renderer benchmark exporter: stream binary verification

Hash each renderer binary in bounded blocks when exporting existing measurements, rather than loading it as a single byte string. Use the same descriptor, preserve the byte budget, identity and byte-count checks, validation order, and the independent verification of every case. Parsed evidence is still read and validated as before.

All nine synthetic cases produced equivalent reports except the exporter's own source hash; Markdown matched byte for byte. Current unit and paired validation checks passed. The largest test payload returned in one read decreased from 3,145,991 bytes to 1,048,576 bytes. Total data and separate checks were unchanged.

This changes the optional offline benchmark exporter, not the renderer or application. The figures are maximum bytes returned by an individual read, not time or process memory. No renderer binary was executed.

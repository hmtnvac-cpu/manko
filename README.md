# Manko API

Extracts the playable HLS URL from a Manko movie page by resolving the embedded javplayer stream.

## Endpoints

- `GET /health`
- `GET /manko?url=<MANKO_URL>&verify=1`

Example:

`/manko?url=https://manko.fun/movie-info/6aa2f0d3131836087eb79867?series=false&verify=1`

A successful response includes `player_id`, `stream_url`, request headers, and optional HLS verification details.

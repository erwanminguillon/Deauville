# API

JSON API under `/api`. The same server serves the website (`/`) and the
admin (`/admin/`), which only use these routes. With FastAPI, the interactive
documentation is at `/docs`.

Dates and times are local festival time, without time zone:
`2027-06-11` for a day, `2027-06-11T21:00` for a moment.

## Objects

### Venue

```json
{
  "slug": "le-kiosque",
  "name": "Le Kiosque",
  "capacity": 120,
  "address": "Beach promenade"
}
```

### Artist

```json
{
  "slug": "nora-lebrun",
  "name": "Nora Lebrun",
  "bio": "Deadpan stories.",
  "photo_url": ""
}
```

### Performance

Common fields, for every kind:

| Field              | Example                          | Note                                      |
| ------------------ | -------------------------------- | ----------------------------------------- |
| `id`               | `"le-kiosque-2027-06-12-0100"`   | venue slug + start                        |
| `kind`             | `"solo"`                         | `"solo"`, `"lineup"` or `"workshop"`      |
| `title`            | `"After Hours"`                  |                                           |
| `venue`            | `"le-kiosque"`                   | venue slug                                |
| `venue_name`       | `"Le Kiosque"`                   |                                           |
| `start`, `end`     | `"2027-06-12T01:00"`             |                                           |
| `duration_minutes` | `60`                             | 1 to 360                                  |
| `festival_day`     | `"2027-06-11"`                   | a day ends at 06:00                       |
| `description`      | `""`                             |                                           |
| `summary`          | `"hosted by Tom Vasseur, with…"` | one line for the programme                |
| `capacity`         | `120`                            | seats, or places for a workshop           |
| `artists`          | `[{"slug": …, "name": …}]`       | everyone on stage, in order of appearance |

Fields of each kind:

| Kind       | Fields                                                                      |
| ---------- | --------------------------------------------------------------------------- |
| `solo`     | `artist` (slug), `min_age` (0 to 18)                                        |
| `lineup`   | `host` (slug), `acts` (list of slugs, at least 2)                           |
| `workshop` | `teacher` (slug), `max_participants`, `participants` (names), `places_left` |

## Read

| Method and path              | Answer                                                                                                         |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `GET /api/festival`          | `{"name", "first_day", "last_day", "days": [...]}`                                                             |
| `GET /api/venues`            | list of venues, in the order they were added                                                                   |
| `GET /api/artists`           | list of artists, alphabetical order                                                                            |
| `GET /api/artists/{slug}`    | an artist, plus `performances`: their performances in order                                                    |
| `GET /api/programme`         | performances in programme order; filters `?day=2027-06-11`, `?venue=le-kiosque`                                |
| `GET /api/performances/{id}` | a performance                                                                                                  |
| `GET /api/now`               | `{"at", "now_playing": [...], "up_next": [...]}` (3 at most); `?at=2027-06-11T21:00` replaces the current time |

## Write (admin)

| Method and path                            | Body                             | Success                  |
| ------------------------------------------ | -------------------------------- | ------------------------ |
| `POST /api/artists`                        | `{"name", "bio"?, "photo_url"?}` | 201, the artist          |
| `POST /api/performances`                   | a performance (below)            | 201, the performance     |
| `PUT /api/performances/{id}`               | a performance (below)            | 200, the new performance |
| `DELETE /api/performances/{id}`            | none                             | 204                      |
| `POST /api/performances/{id}/participants` | `{"name"}`                       | 201, the workshop        |

A performance body has the saved fields only (no `id`, `end`, `summary`…):

```json
{
  "kind": "lineup",
  "title": "Gala",
  "venue": "grand-casino",
  "start": "2027-06-10T20:30",
  "duration_minutes": 90,
  "host": "paul-kerbrat",
  "acts": ["nora-lebrun", "max-pellerin"]
}
```

`PUT` can move a performance to another venue or time: its `id` changes, and
the answer gives the new one. If the new version breaks a rule, nothing
changes.

Every change is saved to the data file at once.

## Errors

Errors of the festival answer `{"detail": "a sentence for the user"}`:

| Status | When                                                                           |
| ------ | ------------------------------------------------------------------------------ |
| 404    | unknown artist, venue or performance                                           |
| 409    | venue or artist busy, date outside the festival, workshop full, already exists |
| 422    | invalid value: empty name, duration out of range, not a workshop…              |
| 500    | the data file cannot be read or written                                        |

A body or parameter of the wrong shape (missing field, `"day=June 11"`) is
refused by FastAPI with a 422 whose `detail` is a list of problems.
